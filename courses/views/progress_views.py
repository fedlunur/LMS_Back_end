from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from courses.models import Enrollment, Lesson, Lesson, LessonProgress, Module, ModuleProgress
from rest_framework.response import Response
from rest_framework import status
from ..serializers import DynamicFieldSerializer

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

