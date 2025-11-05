from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, status
from .serializers import DynamicFieldSerializer
from .UtilMethods import *
from lms_project.utils import *
from .models import (
    Course, Enrollment, Lesson, Module, ModuleProgress,
    QuizAttempt, AssignmentSubmission, FinalCourseAssessment, AssessmentAttempt,
    LessonProgress, AssignmentLesson, Certificate
)

class GenericModelViewSet(viewsets.ModelViewSet):
    pagination_class = CustomPagination

    # def get_permissions(self):
    #     # Require login for listing/retrieving courses and their overviews,
    #     # keep existing behavior (open read, auth for write) for other models.
    #     if self.action in ["list", "retrieve"]:
    #         if self.basename.lower() in ["course", "course_overview"]:
    #             return [IsAuthenticated()]
    #         return [AllowAny()]
    #     return [IsAuthenticated()]
    
    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [AllowAny()]
        return [IsAuthenticated()]

    # def get_queryset(self):
    #     model = model_mapping.get(self.basename.lower())
    #     if not model:
    #         raise AssertionError(f"Model not found for basename '{self.basename}'")
    #     return model.objects.all()
    def get_queryset(self):
            model = model_mapping.get(self.basename.lower())
            if not model:
                raise AssertionError(f"Model not found for basename '{self.basename}'")

            queryset = model.objects.all()

            # 🔹 Security: Filter by user for student-specific models
            if self.basename.lower() in ['enrollment', 'lessonprogress', 'moduleprogress', 'quizattempt', 
                                         'assignmentsubmission', 'assessmentattempt', 'certificate']:
                # Students can only see their own data
                if not self.request.user.is_staff and self.request.user.is_authenticated:
                    if self.basename.lower() == 'enrollment':
                        queryset = queryset.filter(student=self.request.user)
                    elif self.basename.lower() in ['lessonprogress', 'moduleprogress']:
                        queryset = queryset.filter(enrollment__student=self.request.user)
                    elif self.basename.lower() in ['quizattempt', 'assignmentsubmission', 'assessmentattempt']:
                        queryset = queryset.filter(student=self.request.user)
                    elif self.basename.lower() == 'certificate':
                        queryset = queryset.filter(enrollment__student=self.request.user)
            
            # 🔹 Filter published courses for students (they can only see published courses)
            if self.basename.lower() == 'course' and not self.request.user.is_staff and self.request.user.is_authenticated:
                queryset = queryset.filter(status='published')

            # 🔹 Dynamic filtering by query params
            filter_kwargs = {}
            for field, value in self.request.query_params.items():
                if field in [f.name for f in model._meta.get_fields()]:
                    filter_kwargs[field] = value

            if filter_kwargs:
                queryset = queryset.filter(**filter_kwargs)

            return queryset


    def get_serializer(self, *args, **kwargs):
        kwargs["model_name"] = self.basename
        return DynamicFieldSerializer(*args, **kwargs)

    # Unified success/failure responses
    def success_response(self, data, message, code=status.HTTP_200_OK):
        return Response({"success": True, "data": data, "message": message}, status=code)

    def failure_response(self, message, code=status.HTTP_400_BAD_REQUEST):
        return Response({"success": False, "message": message}, status=code)

    # Only override where needed
    def create(self, request, *args, **kwargs):
        if self.basename.lower() == "enrollment":
            # Custom enrollment logic
            student_id = request.data.get("student")
            course_id = request.data.get("course")
            
            if not student_id or not course_id:
                return self.failure_response("Student and course IDs are required.")
            
            try:
                from user_managment.models import User
                student = User.objects.get(pk=student_id)
                course = Course.objects.get(pk=course_id)
            except User.DoesNotExist:
                return self.failure_response("Student not found.")
            except Course.DoesNotExist:
                return self.failure_response("Course not found.")
            
            success, message = enroll_user_in_course(student, course)
            if not success:
                return self.failure_response(message)
            
            # Get the created enrollment
            enrollment = Enrollment.objects.get(student=student, course=course)
            serializer = self.get_serializer(enrollment)
            return self.success_response(serializer.data, message, status.HTTP_201_CREATED)
        
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            # if self.basename.lower() == "course":
            #     # Pass get_serializer method to the handler so it can serialize instance properly
            #     return handle_course_create_or_update(request, serializer.__class__, self.get_serializer)
            # else:
                instance = serializer.save()
                return self.success_response(self.get_serializer(instance).data, "Created successfully", status.HTTP_201_CREATED)

        return self.failure_response(serializer.errors)    

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return self.success_response(serializer.data, "Updated successfully")
        return self.failure_response(serializer.errors)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return self.success_response({}, "Deleted successfully")
        
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Access control for lessons
        if self.basename.lower() == 'lesson':
            if not is_lesson_accessible(request.user, instance):
                return self.failure_response("You do not have access to this lesson. Please complete the previous lesson first.")
        # Access control for modules
        elif self.basename.lower() == 'module':
            if not is_module_accessible(request.user, instance):
                return self.failure_response("You do not have access to this module. Please complete all lessons in the previous module first.")
        serializer = self.get_serializer(instance)
        return self.success_response(serializer.data, "Record retrieved successfully.")
        
    def list(self, request, *args, **kwargs):
            queryset = self.filter_queryset(self.get_queryset())

            # Apply pagination
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                # Wrap DRF's paginated response
                return self.get_paginated_response({
                    "success": True,
                    "data": serializer.data,
                    "message": "Records retrieved successfully."
                })

            # If no pagination
            serializer = self.get_serializer(queryset, many=True)
            return self.success_response(serializer.data, "Records retrieved successfully.")

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_lesson_completed_view(request, lesson_id):
    """
    API endpoint to mark a lesson as completed.
    Only the enrolled student can mark their own lessons as completed.
    """
    success, message = mark_lesson_completed(request.user, lesson_id)
    if success:
        # Return updated progress information
        try:
            lesson = Lesson.objects.get(id=lesson_id)
            enrollment = Enrollment.objects.get(student=request.user, course=lesson.course)
            lesson_progress = LessonProgress.objects.get(enrollment=enrollment, lesson=lesson)
            
            from .serializers import DynamicFieldSerializer
            progress_serializer = DynamicFieldSerializer(lesson_progress, model_name="lessonprogress")
            enrollment_serializer = DynamicFieldSerializer(enrollment, model_name="enrollment")
            
            return Response({
                "success": True,
                "message": message,
                "data": {
                    "lesson_progress": progress_serializer.data,
                    "enrollment_progress": {
                        "progress": float(enrollment.progress),
                        "completed_lessons": enrollment.completed_lessons,
                        "is_completed": enrollment.is_completed
                    }
                }
            }, status=status.HTTP_200_OK)
        except (Lesson.DoesNotExist, Enrollment.DoesNotExist, LessonProgress.DoesNotExist):
            return Response({"success": True, "message": message}, status=status.HTTP_200_OK)
    else:
        return Response({"success": False, "message": message}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def enroll_in_course_view(request, course_id):
    """
    Enroll the authenticated user in a course.
    """
    try:
        course = Course.objects.get(id=course_id)
        success, message = enroll_user_in_course(request.user, course)
        if success:
            enrollment = Enrollment.objects.get(student=request.user, course=course)
            from .serializers import DynamicFieldSerializer
            serializer = DynamicFieldSerializer(enrollment, model_name="enrollment")
            return Response({
                "success": True,
                "message": message,
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({"success": False, "message": message}, status=status.HTTP_400_BAD_REQUEST)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_enrolled_courses_view(request):
    """
    Get all courses enrolled by the authenticated user with their progress and analytics.
    Only returns courses the authenticated user is enrolled in.
    """
    enrollments = Enrollment.objects.filter(
        student=request.user,
        payment_status='completed'
    ).select_related('course', 'course__instructor', 'course__category', 'course__level').prefetch_related(
        'module_progress', 'lesson_progress'
    )
    
    from .serializers import DynamicFieldSerializer
    enrollment_data = []
    
    for enrollment in enrollments:
        enrollment_serializer = DynamicFieldSerializer(enrollment, model_name="enrollment")
        enrollment_dict = enrollment_serializer.data
        
        # Add progress analytics
        total_modules = Module.objects.filter(course=enrollment.course).count()
        completed_modules = ModuleProgress.objects.filter(
            enrollment=enrollment,
            completed=True
        ).count()
        
        enrollment_dict['analytics'] = {
            'progress_percentage': float(enrollment.progress),
            'completed_lessons': enrollment.completed_lessons,
            'total_modules': total_modules,
            'completed_modules': completed_modules,
            'is_completed': enrollment.is_completed,
            'enrolled_at': enrollment.enrolled_at,
            'last_accessed': enrollment.last_accessed,
            'completed_at': enrollment.completed_at
        }
        
        enrollment_data.append(enrollment_dict)
    
    return Response({
        "success": True,
        "data": enrollment_data,
        "message": "Enrolled courses retrieved successfully."
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_published_courses_view(request):
    """
    Get all published courses available for enrollment (for all authenticated users).
    Includes course overview and enrollment status for the current user.
    """
    courses = Course.objects.filter(
        status='published'
    ).select_related('instructor', 'category', 'level').prefetch_related('overview', 'modules', 'lessons')
    
    # Check which courses the user is enrolled in
    enrolled_course_ids = set(
        Enrollment.objects.filter(
            student=request.user,
            payment_status='completed'
        ).values_list('course_id', flat=True)
    )
    
    from .serializers import DynamicFieldSerializer
    courses_data = []
    
    for course in courses:
        course_serializer = DynamicFieldSerializer(course, model_name="course")
        course_dict = course_serializer.data
        
        # Add course overview if exists
        if hasattr(course, 'overview'):
            overview_serializer = DynamicFieldSerializer(course.overview, model_name="course_overview")
            course_dict['overview'] = overview_serializer.data
        else:
            course_dict['overview'] = None
        
        # Add enrollment status
        course_dict['is_enrolled'] = course.id in enrolled_course_ids
        
        # Get enrollment info if enrolled
        if course.id in enrolled_course_ids:
            enrollment = Enrollment.objects.get(student=request.user, course=course)
            course_dict['enrollment'] = {
                'id': enrollment.id,
                'progress': float(enrollment.progress),
                'is_completed': enrollment.is_completed,
                'enrolled_at': enrollment.enrolled_at
            }
        else:
            course_dict['enrollment'] = None
        
        courses_data.append(course_dict)
    
    return Response({
        "success": True,
        "data": courses_data,
        "message": "Published courses retrieved successfully."
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_course_overview_view(request, course_id):
    """
    Get course overview for a published course (for all authenticated users).
    If user is enrolled, also includes their progress.
    """
    try:
        course = Course.objects.select_related('instructor', 'category', 'level').prefetch_related('overview').get(id=course_id)
        
        # Check if course is published
        if course.status != 'published':
            return Response({
                "success": False,
                "message": "Course is not published."
            }, status=status.HTTP_403_FORBIDDEN)
        
        from .serializers import DynamicFieldSerializer
        course_serializer = DynamicFieldSerializer(course, model_name="course")
        course_dict = course_serializer.data
        
        # Add course overview
        if hasattr(course, 'overview'):
            overview_serializer = DynamicFieldSerializer(course.overview, model_name="course_overview")
            course_dict['overview'] = overview_serializer.data
        else:
            course_dict['overview'] = None
        
        # Check if user is enrolled
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=course,
            payment_status='completed'
        ).first()
        
        if enrollment:
            course_dict['is_enrolled'] = True
            course_dict['enrollment'] = {
                'id': enrollment.id,
                'progress': float(enrollment.progress),
                'is_completed': enrollment.is_completed,
                'enrolled_at': enrollment.enrolled_at
            }
        else:
            course_dict['is_enrolled'] = False
            course_dict['enrollment'] = None
        
        return Response({
            "success": True,
            "data": course_dict,
            "message": "Course overview retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response({
            "success": False,
            "message": "Course not found."
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_quiz_view(request, lesson_id):
    """
    Submit quiz answers for a lesson.
    Expected payload: {"responses": [{"question_id": 1, "answer_id": 2}, ...]}
    """
    responses = request.data.get('responses', [])
    if not responses:
        return Response({
            "success": False,
            "message": "Responses are required."
        }, status=status.HTTP_400_BAD_REQUEST)
    
    success, message, attempt_data = submit_quiz(request.user, lesson_id, responses)
    if success:
        return Response({
            "success": True,
            "message": message,
            "data": attempt_data
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            "success": False,
            "message": message
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_assignment_view(request, lesson_id):
    """
    Submit assignment for a lesson.
    Expected payload: {
        "submission_text": "...",
        "submission_file": <file>,
        "submission_url": "...",
        "github_repo": "..."
    }
    """
    submission_data = {
        'submission_text': request.data.get('submission_text', ''),
        'submission_file': request.FILES.get('submission_file'),
        'submission_url': request.data.get('submission_url', ''),
        'github_repo': request.data.get('github_repo', '')
    }
    
    success, message, submission = submit_assignment(request.user, lesson_id, submission_data)
    if success:
        from .serializers import DynamicFieldSerializer
        serializer = DynamicFieldSerializer(submission, model_name="assignmentsubmission")
        return Response({
            "success": True,
            "message": message,
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            "success": False,
            "message": message
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_assignment_and_complete_view(request, lesson_id):
    """
    Submit assignment and mark lesson as completed.
    """
    # First submit the assignment
    submission_data = {
        'submission_text': request.data.get('submission_text', ''),
        'submission_file': request.FILES.get('submission_file'),
        'submission_url': request.data.get('submission_url', ''),
        'github_repo': request.data.get('github_repo', '')
    }
    
    success, message, submission = submit_assignment(request.user, lesson_id, submission_data)
    if not success:
        return Response({
            "success": False,
            "message": message
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Mark lesson as completed
    success, message = mark_lesson_completed(request.user, lesson_id)
    if success:
        from .serializers import DynamicFieldSerializer
        serializer = DynamicFieldSerializer(submission, model_name="assignmentsubmission")
        return Response({
            "success": True,
            "message": "Assignment submitted and lesson marked as completed.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            "success": False,
            "message": f"Assignment submitted but failed to mark lesson complete: {message}"
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_final_assessment_view(request, course_id):
    """
    Get final assessment for a course (with randomized questions if enabled).
    """
    try:
        enrollment = Enrollment.objects.get(student=request.user, course_id=course_id)
        
        if enrollment.payment_status != 'completed':
            return Response({
                "success": False,
                "message": "Payment not completed for this course."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check eligibility
        can_take, message = can_take_final_assessment(request.user, course_id)
        if not can_take:
            return Response({
                "success": False,
                "message": message
            }, status=status.HTTP_400_BAD_REQUEST)
        
        assessment = getattr(enrollment.course, 'final_assessment', None)
        if not assessment:
            return Response({
                "success": False,
                "message": "Final assessment not found for this course."
            }, status=status.HTTP_404_NOT_FOUND)
        
        if not assessment.is_active:
            return Response({
                "success": False,
                "message": "Final assessment is not active."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get questions
        questions = assessment.questions.all()
        
        # Randomize if enabled
        if assessment.randomize_questions:
            questions = questions.order_by('?')
        
        from .serializers import DynamicFieldSerializer
        question_serializer = DynamicFieldSerializer(questions, many=True, model_name="assessmentquestion")
        
        return Response({
            "success": True,
            "data": {
                "assessment": {
                    "id": assessment.id,
                    "title": assessment.title,
                    "description": assessment.description,
                    "time_limit": assessment.time_limit,
                    "max_attempts": assessment.max_attempts,
                    "show_correct_answers": assessment.show_correct_answers
                },
                "questions": question_serializer.data
            },
            "message": "Final assessment retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    except Enrollment.DoesNotExist:
        return Response({
            "success": False,
            "message": "You are not enrolled in this course."
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_final_assessment_view(request, course_id):
    """
    Submit final course assessment.
    Expected payload: {"responses": [{"question_id": 1, "answer_id": 2}, ...]}
    """
    responses = request.data.get('responses', [])
    if not responses:
        return Response({
            "success": False,
            "message": "Responses are required."
        }, status=status.HTTP_400_BAD_REQUEST)
    
    success, message, attempt_data = submit_final_assessment(request.user, course_id, responses)
    if success:
        return Response({
            "success": True,
            "message": message,
            "data": attempt_data
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            "success": False,
            "message": message
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_course_progress_view(request, course_id):
    """
    Get detailed progress for a course including module and lesson progress.
    Only returns progress for the authenticated user's own enrollment.
    """
    try:
        enrollment = Enrollment.objects.get(student=request.user, course_id=course_id)
        
        # Get module progress
        module_progress_list = ModuleProgress.objects.filter(
            enrollment=enrollment
        ).select_related('module').order_by('module__order')
        
        # Get lesson progress
        lesson_progress_list = LessonProgress.objects.filter(
            enrollment=enrollment
        ).select_related('lesson', 'lesson__module').order_by('lesson__module__order', 'lesson__order')
        
        # Calculate analytics
        total_modules = Module.objects.filter(course=enrollment.course).count()
        completed_modules = ModuleProgress.objects.filter(enrollment=enrollment, completed=True).count()
        total_lessons = Lesson.objects.filter(course=enrollment.course).count()
        completed_lessons = LessonProgress.objects.filter(enrollment=enrollment, completed=True).count()
        
        from .serializers import DynamicFieldSerializer
        module_serializer = DynamicFieldSerializer(module_progress_list, many=True, model_name="moduleprogress")
        lesson_serializer = DynamicFieldSerializer(lesson_progress_list, many=True, model_name="lessonprogress")
        
        return Response({
            "success": True,
            "data": {
                "enrollment": {
                    "id": enrollment.id,
                    "progress": float(enrollment.progress),
                    "completed_lessons": enrollment.completed_lessons,
                    "is_completed": enrollment.is_completed,
                    "enrolled_at": enrollment.enrolled_at,
                    "last_accessed": enrollment.last_accessed,
                    "completed_at": enrollment.completed_at
                },
                "analytics": {
                    "total_modules": total_modules,
                    "completed_modules": completed_modules,
                    "module_completion_percentage": round((completed_modules / total_modules * 100) if total_modules > 0 else 0, 2),
                    "total_lessons": total_lessons,
                    "completed_lessons": completed_lessons,
                    "lesson_completion_percentage": round((completed_lessons / total_lessons * 100) if total_lessons > 0 else 0, 2),
                    "overall_progress": float(enrollment.progress)
                },
                "module_progress": module_serializer.data,
                "lesson_progress": lesson_serializer.data
            },
            "message": "Course progress retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    except Enrollment.DoesNotExist:
        return Response({
            "success": False,
            "message": "You are not enrolled in this course."
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_quiz_results_view(request, lesson_id):
    """
    Get quiz results for a lesson (with correct answers if show_correct_answers is enabled).
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        enrollment = Enrollment.objects.get(student=request.user, course=lesson.course)
        
        # Get latest attempt
        attempt = QuizAttempt.objects.filter(
            student=request.user,
            lesson=lesson
        ).order_by('-completed_at').first()
        
        if not attempt:
            return Response({
                "success": False,
                "message": "No quiz attempt found for this lesson."
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get quiz config
        quiz_config = getattr(lesson, 'quiz_config', None)
        show_answers = quiz_config.show_correct_answers if quiz_config else True
        
        # Get responses
        responses = attempt.responses.all().select_related('question', 'answer')
        
        from .serializers import DynamicFieldSerializer
        response_serializer = DynamicFieldSerializer(responses, many=True, model_name="quizresponse")
        
        result_data = {
            "attempt": {
                "score": attempt.score,
                "correct_answers": attempt.correct_answers,
                "total_questions": attempt.total_questions,
                "completed_at": attempt.completed_at
            },
            "responses": response_serializer.data
        }
        
        # Include correct answers if enabled
        if show_answers:
            result_data["show_correct_answers"] = True
        
        return Response({
            "success": True,
            "data": result_data,
            "message": "Quiz results retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    except Lesson.DoesNotExist:
        return Response({
            "success": False,
            "message": "Lesson not found."
        }, status=status.HTTP_404_NOT_FOUND)
    except Enrollment.DoesNotExist:
        return Response({
            "success": False,
            "message": "You are not enrolled in this course."
        }, status=status.HTTP_404_NOT_FOUND)


# ============ Teacher/Instructor Endpoints ============

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_course_students_view(request, course_id):
    """Get all students enrolled in a course (for instructors)."""
    try:
        course = Course.objects.get(id=course_id)
        if course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view students for this course."
            }, status=status.HTTP_403_FORBIDDEN)
        
        enrollments = Enrollment.objects.filter(
            course=course,
            payment_status='completed'
        ).select_related('student')
        
        serializer = DynamicFieldSerializer(enrollments, many=True, model_name="enrollment")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Course students retrieved successfully."
        }, status=status.HTTP_200_OK)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_student_progress_view(request, course_id, student_id):
    """Get detailed progress for a specific student in a course (for instructors)."""
    try:
        course = Course.objects.get(id=course_id)
        if course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view this student's progress."
            }, status=status.HTTP_403_FORBIDDEN)
        
        from user_managment.models import User
        student = User.objects.get(id=student_id)
        enrollment = Enrollment.objects.get(student=student, course=course)
        
        module_progress_list = ModuleProgress.objects.filter(enrollment=enrollment).select_related('module')
        lesson_progress_list = LessonProgress.objects.filter(enrollment=enrollment).select_related('lesson', 'lesson__module')
        
        module_serializer = DynamicFieldSerializer(module_progress_list, many=True, model_name="moduleprogress")
        lesson_serializer = DynamicFieldSerializer(lesson_progress_list, many=True, model_name="lessonprogress")
        
        return Response({
            "success": True,
            "data": {
                "student": {"id": student.id, "email": student.email, "name": student.get_full_name()},
                "enrollment": {
                    "progress": float(enrollment.progress),
                    "completed_lessons": enrollment.completed_lessons,
                    "is_completed": enrollment.is_completed,
                    "enrolled_at": enrollment.enrolled_at
                },
                "module_progress": module_serializer.data,
                "lesson_progress": lesson_serializer.data
            },
            "message": "Student progress retrieved successfully."
        }, status=status.HTTP_200_OK)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)
    except Enrollment.DoesNotExist:
        return Response({"success": False, "message": "Student is not enrolled in this course."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_assignment_submissions_view(request, lesson_id):
    """Get all submissions for an assignment lesson (for instructors)."""
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        if lesson.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view submissions for this lesson."
            }, status=status.HTTP_403_FORBIDDEN)
        
        if lesson.content_type != Lesson.ContentType.ASSIGNMENT:
            return Response({
                "success": False,
                "message": "This lesson is not an assignment."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        submissions = AssignmentSubmission.objects.filter(lesson=lesson).select_related('student', 'enrollment').order_by('-submitted_at')
        
        serializer = DynamicFieldSerializer(submissions, many=True, model_name="assignmentsubmission")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Assignment submissions retrieved successfully."
        }, status=status.HTTP_200_OK)
    except Lesson.DoesNotExist:
        return Response({"success": False, "message": "Lesson not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def grade_assignment_view(request, submission_id):
    """Grade an assignment submission (for instructors). Expected payload: {"score": 85.0, "feedback": "Great work!", "status": "graded"}"""
    try:
        submission = AssignmentSubmission.objects.get(id=submission_id)
        if submission.lesson.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to grade this submission."
            }, status=status.HTTP_403_FORBIDDEN)
        
        score = request.data.get('score')
        feedback = request.data.get('feedback', '')
        status_val = request.data.get('status', 'graded')
        
        if score is None:
            return Response({"success": False, "message": "Score is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        if submission.max_score and score > submission.max_score:
            return Response({
                "success": False,
                "message": f"Score cannot exceed maximum score of {submission.max_score}."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        submission.score = float(score)
        submission.feedback = feedback
        submission.status = status_val
        submission.graded_by = request.user
        submission.graded_at = timezone.now()
        submission.save()
        
        serializer = DynamicFieldSerializer(submission, model_name="assignmentsubmission")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Assignment graded successfully."
        }, status=status.HTTP_200_OK)
    except AssignmentSubmission.DoesNotExist:
        return Response({"success": False, "message": "Submission not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_certificate_view(request, enrollment_id):
    """Get certificate for an enrollment (for students and instructors)."""
    try:
        enrollment = Enrollment.objects.get(id=enrollment_id)
        if enrollment.student != request.user and enrollment.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view this certificate."
            }, status=status.HTTP_403_FORBIDDEN)
        
        certificate = getattr(enrollment, 'certificate', None)
        if not certificate:
            return Response({
                "success": False,
                "message": "Certificate not found. Complete the course and pass the final assessment to receive a certificate."
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = DynamicFieldSerializer(certificate, model_name="certificate")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Certificate retrieved successfully."
        }, status=status.HTTP_200_OK)
    except Enrollment.DoesNotExist:
        return Response({"success": False, "message": "Enrollment not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_student_analytics_view(request):
    """
    Get overall analytics for the authenticated student across all enrolled courses.
    """
    enrollments = Enrollment.objects.filter(
        student=request.user,
        payment_status='completed'
    ).select_related('course')
    
    total_courses = enrollments.count()
    completed_courses = enrollments.filter(is_completed=True).count()
    
    # Calculate overall progress
    total_progress = 0.0
    total_lessons_completed = 0
    total_lessons = 0
    
    for enrollment in enrollments:
        total_progress += float(enrollment.progress)
        total_lessons_completed += enrollment.completed_lessons
        total_lessons += Lesson.objects.filter(course=enrollment.course).count()
    
    average_progress = round((total_progress / total_courses) if total_courses > 0 else 0, 2)
    
    # Get course-wise analytics
    course_analytics = []
    for enrollment in enrollments:
        course_analytics.append({
            'course_id': enrollment.course.id,
            'course_title': enrollment.course.title,
            'progress': float(enrollment.progress),
            'is_completed': enrollment.is_completed,
            'enrolled_at': enrollment.enrolled_at,
            'completed_at': enrollment.completed_at
        })
    
    return Response({
        "success": True,
        "data": {
            "overall_analytics": {
                "total_courses_enrolled": total_courses,
                "completed_courses": completed_courses,
                "in_progress_courses": total_courses - completed_courses,
                "average_progress": average_progress,
                "total_lessons_completed": total_lessons_completed,
                "total_lessons": total_lessons,
                "overall_lesson_completion": round((total_lessons_completed / total_lessons * 100) if total_lessons > 0 else 0, 2)
            },
            "course_analytics": course_analytics
        },
        "message": "Student analytics retrieved successfully."
    }, status=status.HTTP_200_OK)

