
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from courses.models import Enrollment, Lesson, LessonProgress, Module, ModuleProgress
from courses.serializers import DynamicFieldSerializer


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


