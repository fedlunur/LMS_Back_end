# views/base.py
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.db.models import Count, Q
from django.contrib.auth import get_user_model

from ..serializers import DynamicFieldSerializer
from courses.services.pagination import CustomPagination
from courses.services.enrollment_service import enroll_user_in_course
from courses.services.access_service import is_lesson_accessible, is_module_accessible
from lms_project.utils import model_mapping  # this utility provides a mapping of model names to model classes

User = get_user_model()

class GenericModelViewSet(viewsets.ModelViewSet):
    pagination_class = CustomPagination

    # Permissions
    def get_permissions(self):
        from rest_framework.permissions import AllowAny, IsAuthenticated

        sensitive = {
            'enrollment', 'lessonprogress', 'moduleprogress', 'quizattempt',
            'assignmentsubmission', 'assessmentattempt', 'certificate',
            'conversation', 'message', 'courserating', 'questionbank',
            'questionbankquestion', 'questionbankanswer', 'courseresource'
        }

        if self.action in ["list", "retrieve"]:
            if self.basename.lower() in sensitive:
                return [IsAuthenticated()]
            return [AllowAny()]
        return [IsAuthenticated()]

    #  Dynamic Queryset
    def get_queryset(self):
        model_name = self.basename.lower()
        model = model_mapping.get(model_name)
        if not model:
            raise AssertionError(f"Model not found for basename '{self.basename}'")

        queryset = model.objects.all()

        # Optimize course queries
        if model_name == 'course':
            try:
                # Select common relations and annotate enrollment counts for efficient serialization
                queryset = queryset.select_related('instructor', 'category', 'level').annotate(
                    _total_enrollments=Count(
                        'enrollments',
                        filter=Q(enrollments__payment_status='completed', enrollments__is_enrolled=True),
                        distinct=True,
                    )
                )
            except Exception:
                pass

        # Apply user-based filtering for restricted models
        if model_name in [
            'enrollment', 'lessonprogress', 'moduleprogress', 'quizattempt',
            'assignmentsubmission', 'assessmentattempt', 'certificate', 'courserating',
            'questionbank', 'questionbankquestion', 'questionbankanswer'
        ]:
            if not self.request.user.is_staff and self.request.user.is_authenticated:
                user = self.request.user
                if model_name == 'enrollment':
                    queryset = queryset.filter(student=user)
                elif model_name in ['lessonprogress', 'moduleprogress']:
                    queryset = queryset.filter(enrollment__student=user)
                elif model_name in ['quizattempt', 'assignmentsubmission', 'assessmentattempt']:
                    queryset = queryset.filter(student=user)
                elif model_name == 'certificate':
                    queryset = queryset.filter(enrollment__student=user)
                elif model_name == 'courserating':
                    queryset = queryset.filter(student=user)
                elif model_name == 'questionbank':
                    queryset = queryset.filter(teacher=user)
                elif model_name == 'questionbankquestion':
                    queryset = queryset.filter(question_bank__teacher=user)
                elif model_name == 'questionbankanswer':
                    queryset = queryset.filter(question__question_bank__teacher=user)
        
        # Event filtering: students see events for enrolled courses, instructors see their courses
        if model_name == 'event' and self.request.user.is_authenticated:
            user = self.request.user
            if user.is_staff:
                # Staff can see all events
                pass
            else:
                # Check if user is instructor (has teacher role)
                is_instructor = bool(getattr(user, 'is_staff', False) or 
                                   (getattr(user, 'role', None) and 
                                    getattr(user.role, 'name', '').lower() == 'teacher'))
                
                if is_instructor:
                    # Instructors see events for their courses
                    queryset = queryset.filter(course__instructor=user)
                else:
                    # Students see events for courses they're enrolled in
                    from courses.models import Enrollment
                    enrolled_course_ids = Enrollment.objects.filter(
                        student=user,
                        payment_status='completed',
                        is_enrolled=True
                    ).values_list('course_id', flat=True)
                    queryset = queryset.filter(course_id__in=enrolled_course_ids)

        # Only show published courses to regular users, but allow instructors to see their own drafts
        if model_name == 'course' and self.request.user.is_authenticated and not self.request.user.is_staff:
            queryset = queryset.filter(Q(status='published') | Q(instructor_id=self.request.user.id))

        # CourseResource: only show to enrolled users, instructors, or staff
        if model_name == 'courseresource' and self.request.user.is_authenticated:
            user = self.request.user
            if not user.is_staff:
                from courses.models import Enrollment
                # Get courses where user is enrolled
                enrolled_course_ids = Enrollment.objects.filter(
                    student=user,
                    payment_status='completed',
                    is_enrolled=True
                ).values_list('course_id', flat=True)
                # Instructors see all resources for their courses
                # Enrolled students see only public resources (is_public=True)
                queryset = queryset.filter(
                    Q(course__instructor=user) |  # Instructor sees all
                    Q(course_id__in=enrolled_course_ids, is_public=True)  # Enrolled sees public only
                )

        # Query parameter filtering
        filter_kwargs = {}
        for field, value in self.request.query_params.items():
            if field in [f.name for f in model._meta.get_fields()]:
                filter_kwargs[field] = value
        if filter_kwargs:
            queryset = queryset.filter(**filter_kwargs)

        return queryset

    #  Dynamic Serializer
    def get_serializer(self, *args, **kwargs):
        kwargs["model_name"] = self.basename
        # Ensure request context is passed for file uploads
        if 'context' not in kwargs:
            kwargs['context'] = self.get_serializer_context()
        return DynamicFieldSerializer(*args, **kwargs)

    #  Response Helpers
    def success_response(self, data, message, code=status.HTTP_200_OK):
        return Response({"success": True, "data": data, "message": message}, status=code)

    def failure_response(self, message, code=status.HTTP_400_BAD_REQUEST):
        return Response({"success": False, "message": message}, status=code)

    #  Create
    def create(self, request, *args, **kwargs):
        if self.basename.lower() == "enrollment":
            student_id = request.data.get("student")
            course_id = request.data.get("course")
            if not student_id or not course_id:
                return self.failure_response("Student and course IDs are required.")

            try:
                student = User.objects.get(pk=student_id)
                Course = model_mapping["course"]
                course = Course.objects.get(pk=course_id)
            except User.DoesNotExist:
                return self.failure_response("Student not found.")
            except Course.DoesNotExist:
                return self.failure_response("Course not found.")

            success, message = enroll_user_in_course(student, course)
            if not success:
                return self.failure_response(message)

            Enrollment = model_mapping["enrollment"]
            enrollment = Enrollment.objects.get(student=student, course=course)
            serializer = self.get_serializer(enrollment)
            return self.success_response(serializer.data, message, status.HTTP_201_CREATED)

        # Ownership checks on create for content models (teacher-only)
        model_name = self.basename.lower()
        user = request.user
        if not user.is_staff and user.is_authenticated:
            # Event creation: only instructors can create events for their courses
            if model_name == 'event':
                course_id = request.data.get('course')
                if course_id:
                    Course = model_mapping.get('course')
                    if Course:
                        try:
                            course = Course.objects.get(pk=course_id)
                            is_instructor = bool(getattr(user, 'is_staff', False) or 
                                               (getattr(user, 'role', None) and 
                                                getattr(user.role, 'name', '').lower() == 'teacher'))
                            if not is_instructor or course.instructor_id != user.id:
                                return self.failure_response(
                                    "You can only create events for your own courses.", 
                                    status.HTTP_403_FORBIDDEN
                                )
                        except Course.DoesNotExist:
                            return self.failure_response("Course not found.", status.HTTP_404_NOT_FOUND)
                else:
                    # Events without a course can be created by any instructor
                    is_instructor = bool(getattr(user, 'is_staff', False) or 
                                       (getattr(user, 'role', None) and 
                                        getattr(user.role, 'name', '').lower() == 'teacher'))
                    if not is_instructor:
                        return self.failure_response(
                            "Only instructors can create events.", 
                            status.HTTP_403_FORBIDDEN
                        )
            
            protected = [
                'module', 'lesson', 'videolesson', 'quizlesson', 'assignmentlesson', 'articlelesson',
                'lessonresource', 'lessonattachment', 'quizquestion', 'quizanswer', 'quizconfiguration',
                'course_overview', 'course_faq', 'courseresource', 'courseannouncement', 'videocheckpointquiz',
                'finalcourseassessment', 'assessmentquestion', 'assessmentanswer'
            ]
            if model_name in protected:
                try:
                    Course = model_mapping.get("course")
                    Module = model_mapping.get("module")
                    Lesson = model_mapping.get("lesson")
                    QuizQuestion = model_mapping.get("quizquestion")
                    VideoCheckpointQuiz = model_mapping.get("videocheckpointquiz")

                    course = None
                    data = request.data

                    if model_name == "module":
                        course_id = data.get("course")
                        if course_id and Course:
                            course = Course.objects.get(pk=course_id)
                    elif model_name == "lesson":
                        course_id = data.get("course")
                        module_id = data.get("module")
                        if course_id and Course:
                            course = Course.objects.get(pk=course_id)
                        elif module_id and Module:
                            module = Module.objects.get(pk=module_id)
                            course = getattr(module, "course", None)
                    elif model_name in ["videolesson", "quizlesson", "assignmentlesson", "articlelesson", "lessonresource", "lessonattachment", "quizconfiguration", "videocheckpointquiz"]:
                        lesson_id = data.get("lesson")
                        if lesson_id and Lesson:
                            lesson = Lesson.objects.get(pk=lesson_id)
                            course = getattr(lesson, "course", None)
                    elif model_name == "quizquestion":
                        lesson_id = data.get("lesson")
                        if lesson_id and Lesson:
                            lesson = Lesson.objects.get(pk=lesson_id)
                            course = getattr(lesson, "course", None)
                    elif model_name == "quizanswer":
                        question_id = data.get("question")
                        if question_id and QuizQuestion:
                            question = QuizQuestion.objects.get(pk=question_id)
                            lesson = getattr(question, "lesson", None)
                            course = getattr(lesson, "course", None) if lesson else None
                    elif model_name in ["course_overview", "course_faq", "courseresource", "courseannouncement"]:
                        course_id = data.get("course")
                        if course_id and Course:
                            course = Course.objects.get(pk=course_id)
                    elif model_name == "finalcourseassessment":
                        course_id = data.get("course")
                        if course_id and Course:
                            course = Course.objects.get(pk=course_id)
                    elif model_name == "assessmentquestion":
                        assessment_id = data.get("assessment")
                        if assessment_id:
                            FinalCourseAssessment = model_mapping.get("finalcourseassessment")
                            if FinalCourseAssessment:
                                assessment = FinalCourseAssessment.objects.get(pk=assessment_id)
                                course = getattr(assessment, "course", None)
                    elif model_name == "assessmentanswer":
                        question_id = data.get("question")
                        if question_id:
                            AssessmentQuestion = model_mapping.get("assessmentquestion")
                            if AssessmentQuestion:
                                question = AssessmentQuestion.objects.get(pk=question_id)
                                assessment = getattr(question, "assessment", None)
                                course = getattr(assessment, "course", None) if assessment else None

                    if not course or getattr(course, "instructor_id", None) != user.id:
                        return self.failure_response("You are not allowed to create this content.", status.HTTP_403_FORBIDDEN)
                except Exception:
                    # Fall back to deny if we cannot resolve ownership safely
                    return self.failure_response("You are not allowed to create this content.", status.HTTP_403_FORBIDDEN)

        # Student review upsert: allow a single rating per (course, student)
        if model_name == "courserating":
            try:
                Course = model_mapping["course"]
                Enrollment = model_mapping["enrollment"]
                CourseRating = model_mapping["courserating"]
            except Exception:
                return self.failure_response("Rating model not available.")

            if not user.is_authenticated:
                return self.failure_response("Authentication required.", status.HTTP_401_UNAUTHORIZED)

            course_id = request.data.get("course")
            if not course_id:
                return self.failure_response({"course": ["This field is required."]})

            try:
                course = Course.objects.get(pk=course_id)
            except Course.DoesNotExist:
                return self.failure_response("Course not found.", status.HTTP_404_NOT_FOUND)

            # Must be enrolled and have completed the course to rate
            enrollment = Enrollment.objects.filter(student=user, course=course, payment_status='completed').first()
            if not enrollment or not getattr(enrollment, "is_completed", False):
                return self.failure_response("You can rate a course only after completing it.", status.HTTP_403_FORBIDDEN)

            defaults = {"enrollment": enrollment}
            for fld in ["rating", "review_title", "review_text", "content_quality", "instructor_quality", "difficulty_level", "value_for_money", "is_public"]:
                if fld in request.data:
                    defaults[fld] = request.data.get(fld)

            obj, _ = CourseRating.objects.update_or_create(
                course=course,
                student=user,
                defaults=defaults,
            )
            return self.success_response(self.get_serializer(obj).data, "Rating submitted successfully.", status.HTTP_200_OK)

        # Combine request.data and request.FILES for file uploads
        # Convert QueryDict to a standard mutable dictionary
        data = request.data.dict() if hasattr(request.data, 'dict') else request.data.copy()

        # Remove 'attachments' from data initially to avoid conflict with non-file data
        if "attachments" in data:
            del data["attachments"]
        
        if hasattr(request, 'FILES'):
            for key in request.FILES:
                files = request.FILES.getlist(key)
                
                # Special handling for 'attachments' field
                if key == "attachments" or key == "attachments[]":
                    # Ensure it's stored as 'attachments' and is a list
                    data["attachments"] = files
                # Standard handling for other fields
                elif len(files) == 1:
                    data[key] = files[0]
                else:
                    data[key] = files
        
        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            try:
                instance = serializer.save()
                return self.success_response(
                    self.get_serializer(instance).data, "Created successfully", status.HTTP_201_CREATED
                )
            except Exception as e:
                error_message = str(e)
                # Try to extract more specific error information
                if hasattr(e, 'message_dict'):
                    error_message = e.message_dict
                elif hasattr(e, 'messages'):
                    error_message = list(e.messages)
                return self.failure_response(
                    {"error": error_message, "detail": "An error occurred while creating the record."},
                    status.HTTP_400_BAD_REQUEST
                )
        return self.failure_response(serializer.errors, status.HTTP_400_BAD_REQUEST)

        # Note: Above is default flow; custom flows may early-return before this point

    # Update
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return self.failure_response(serializer.errors)

        model_name = self.basename.lower()
        user = request.user
        if not user.is_staff:
            # Ownership checks
            if model_name == 'course' and getattr(instance, 'instructor_id', None) != user.id:
                return self.failure_response("You are not allowed to modify this course.", status.HTTP_403_FORBIDDEN)
            elif model_name == 'event':
                # Events: only instructors can modify events for their courses
                course = getattr(instance, 'course', None)
                is_instructor = bool(getattr(user, 'is_staff', False) or 
                                   (getattr(user, 'role', None) and 
                                    getattr(user.role, 'name', '').lower() == 'teacher'))
                if not is_instructor:
                    return self.failure_response("Only instructors can modify events.", status.HTTP_403_FORBIDDEN)
                if course and course.instructor_id != user.id:
                    return self.failure_response("You can only modify events for your own courses.", status.HTTP_403_FORBIDDEN)
            elif model_name in [
                'module', 'lesson', 'videolesson', 'quizlesson', 'assignmentlesson', 'articlelesson',
                'lessonresource', 'lessonattachment', 'quizquestion', 'quizanswer', 'quizconfiguration',
                'course_overview', 'course_faq', 'courseresource', 'courseannouncement', 'videocheckpointquiz',
                'finalcourseassessment', 'assessmentquestion', 'assessmentanswer'
            ]:
                course = getattr(instance, 'course', None) or \
                         getattr(getattr(instance, 'module', None), 'course', None) or \
                         getattr(getattr(instance, 'lesson', None), 'course', None) or \
                         getattr(getattr(instance, 'assessment', None), 'course', None) or \
                         getattr(getattr(getattr(instance, 'question', None), 'assessment', None), 'course', None)
                if not course or course.instructor_id != user.id:
                    return self.failure_response("You are not allowed to modify this content.", status.HTTP_403_FORBIDDEN)
            elif model_name in [
                'enrollment', 'lessonprogress', 'moduleprogress', 'quizattempt',
                'assignmentsubmission', 'assessmentattempt', 'certificate'
            ]:
                owner_id = getattr(instance, 'student_id', None) or \
                           getattr(getattr(instance, 'enrollment', None), 'student_id', None)
                if owner_id and owner_id != user.id:
                    return self.failure_response("You are not allowed to modify this record.", status.HTTP_403_FORBIDDEN)
            elif model_name == 'courserating':
                if getattr(instance, 'student_id', None) != user.id:
                    return self.failure_response("You are not allowed to modify this review.", status.HTTP_403_FORBIDDEN)

        serializer.save()
        return self.success_response(serializer.data, "Updated successfully")

    #  Delete
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        model_name = self.basename.lower()
        user = request.user

        if not user.is_staff:
            if model_name == 'course' and getattr(instance, 'instructor_id', None) != user.id:
                return self.failure_response("You are not allowed to delete this course.", status.HTTP_403_FORBIDDEN)
            elif model_name == 'event':
                # Events: only instructors can delete events for their courses
                course = getattr(instance, 'course', None)
                is_instructor = bool(getattr(user, 'is_staff', False) or 
                                   (getattr(user, 'role', None) and 
                                    getattr(user.role, 'name', '').lower() == 'teacher'))
                if not is_instructor:
                    return self.failure_response("Only instructors can delete events.", status.HTTP_403_FORBIDDEN)
                if course and course.instructor_id != user.id:
                    return self.failure_response("You can only delete events for your own courses.", status.HTTP_403_FORBIDDEN)
            elif model_name in [
                'module', 'lesson', 'videolesson', 'quizlesson', 'assignmentlesson', 'articlelesson',
                'lessonresource', 'lessonattachment', 'quizquestion', 'quizanswer', 'quizconfiguration',
                'course_overview', 'course_faq', 'courseresource', 'courseannouncement', 'videocheckpointquiz',
                'finalcourseassessment', 'assessmentquestion', 'assessmentanswer'
            ]:
                course = getattr(instance, 'course', None) or \
                         getattr(getattr(instance, 'module', None), 'course', None) or \
                         getattr(getattr(instance, 'lesson', None), 'course', None) or \
                         getattr(getattr(instance, 'assessment', None), 'course', None) or \
                         getattr(getattr(getattr(instance, 'question', None), 'assessment', None), 'course', None)
                if not course or course.instructor_id != user.id:
                    return self.failure_response("You are not allowed to delete this content.", status.HTTP_403_FORBIDDEN)
            elif model_name in [
                'enrollment', 'lessonprogress', 'moduleprogress', 'quizattempt',
                'assignmentsubmission', 'assessmentattempt', 'certificate'
            ]:
                owner_id = getattr(instance, 'student_id', None) or \
                           getattr(getattr(instance, 'enrollment', None), 'student_id', None)
                if owner_id and owner_id != user.id:
                    return self.failure_response("You are not allowed to delete this record.", status.HTTP_403_FORBIDDEN)
            elif model_name == 'courserating':
                if getattr(instance, 'student_id', None) != user.id:
                    return self.failure_response("You are not allowed to delete this review.", status.HTTP_403_FORBIDDEN)

        instance.delete()
        return self.success_response({}, "Deleted successfully")

    # Retrieve
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        model_name = self.basename.lower()

        # For instructors/staff of the course, skip student lock checks
        user = request.user
        is_instructor = False
        try:
            if model_name == 'lesson':
                is_instructor = bool(instance.course and instance.course.instructor_id == user.id)
            elif model_name == 'module':
                is_instructor = bool(instance.course and instance.course.instructor_id == user.id)
        except Exception:
            is_instructor = False

        if not (user.is_staff or is_instructor):
            if model_name == 'lesson' and not is_lesson_accessible(request.user, instance):
                return self.failure_response("You do not have access to this lesson. Please complete the previous lesson first.")
            elif model_name == 'module' and not is_module_accessible(request.user, instance):
                return self.failure_response("You do not have access to this module. Please complete all lessons in the previous module first.")

        serializer = self.get_serializer(instance)
        return self.success_response(serializer.data, "Record retrieved successfully.")

    # List
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                "success": True,
                "data": serializer.data,
                "message": "Records retrieved successfully."
            })

        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(serializer.data, "Records retrieved successfully.")
