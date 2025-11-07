# views/base.py
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count
from django.contrib.auth import get_user_model

from ..serializers import DynamicFieldSerializer
from ..UtilMethods import *
from lms_project.utils import model_mapping  # this utility provides a mapping of model names to model classes

User = get_user_model()


# Custom Pagination
class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class GenericModelViewSet(viewsets.ModelViewSet):
    pagination_class = CustomPagination

    # Permissions
    def get_permissions(self):
        from rest_framework.permissions import AllowAny, IsAuthenticated

        sensitive = {
            'enrollment', 'lessonprogress', 'moduleprogress', 'quizattempt',
            'assignmentsubmission', 'assessmentattempt', 'certificate',
            'conversation', 'message'
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
                queryset = queryset.select_related('instructor', 'category', 'level')
            except Exception:
                pass

        # Apply user-based filtering for restricted models
        if model_name in [
            'enrollment', 'lessonprogress', 'moduleprogress', 'quizattempt',
            'assignmentsubmission', 'assessmentattempt', 'certificate'
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

        # Only show published courses to non-admins
        if model_name == 'course' and not self.request.user.is_staff and self.request.user.is_authenticated:
            queryset = queryset.filter(status='published')

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

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return self.success_response(
                self.get_serializer(instance).data, "Created successfully", status.HTTP_201_CREATED
            )
        return self.failure_response(serializer.errors)

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
            elif model_name in [
                'module', 'lesson', 'videolesson', 'quizlesson', 'assignmentlesson', 'articlelesson',
                'lessonresource', 'quizquestion', 'quizanswer', 'quizconfiguration'
            ]:
                course = getattr(instance, 'course', None) or \
                         getattr(getattr(instance, 'module', None), 'course', None) or \
                         getattr(getattr(instance, 'lesson', None), 'course', None)
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
            elif model_name in [
                'module', 'lesson', 'videolesson', 'quizlesson', 'assignmentlesson', 'articlelesson',
                'lessonresource', 'quizquestion', 'quizanswer', 'quizconfiguration'
            ]:
                course = getattr(instance, 'course', None) or \
                         getattr(getattr(instance, 'module', None), 'course', None) or \
                         getattr(getattr(instance, 'lesson', None), 'course', None)
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

        instance.delete()
        return self.success_response({}, "Deleted successfully")

    # Retrieve
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        model_name = self.basename.lower()

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
