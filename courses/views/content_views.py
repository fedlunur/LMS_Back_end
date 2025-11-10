from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count
from courses.models import Course, Enrollment, Lesson, LessonProgress, Module
from courses.services.access_service import is_lesson_accessible, is_module_accessible


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_course_modules_view(request, course_id):
    try:
        course = Course.objects.get(id=course_id, status='published')
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found or not published."}, status=status.HTTP_404_NOT_FOUND)

    enrollment = Enrollment.objects.filter(student=request.user, course=course, payment_status='completed').first()
    modules = Module.objects.filter(course=course).annotate(lesson_count=Count('lessons')).order_by('order')
    data = []
    for m in modules:
        is_unlocked = False
        if enrollment:
            is_unlocked = is_module_accessible(request.user, m)
        data.append({
            'id': m.id,
            'title': m.title,
            'description': m.description,
            'order': m.order,
            'lesson_count': m.lesson_count,
            'unlocked': is_unlocked,
        })
    return Response({"success": True, "data": data, "message": "Modules retrieved successfully."}, status=status.HTTP_200_OK)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_module_lessons_view(request, module_id):
    try:
        module = Module.objects.select_related('course').get(id=module_id)
    except Module.DoesNotExist:
        return Response({"success": False, "message": "Module not found."}, status=status.HTTP_404_NOT_FOUND)

    # Allow course instructor or staff to access regardless of publish status
    is_instructor = (module.course.instructor_id == request.user.id) or request.user.is_staff
    if module.course.status != 'published' and not is_instructor:
        return Response({"success": False, "message": "Module not accessible."}, status=status.HTTP_403_FORBIDDEN)

    # Students must be enrolled to see unlock/completion; instructors can browse freely
    enrollment = None
    if not is_instructor:
        enrollment = Enrollment.objects.filter(student=request.user, course=module.course, payment_status='completed').first()
    lessons = Lesson.objects.filter(module=module).order_by('order')
    data = []
    for lesson in lessons:
        # Keep behavior in sync with list_course_lessons_view:
        # instructors/staff see everything unlocked; students require access checks
        unlocked = True if is_instructor else False
        is_completed = False
        if enrollment:
            unlocked = is_lesson_accessible(request.user, lesson)
            # Query for LessonProgress for this enrollment and lesson
            lp = LessonProgress.objects.filter(enrollment=enrollment, lesson=lesson).first()
            if lp:
                is_completed = lp.completed
        data.append({
            'id': lesson.id,
            'title': lesson.title,
            'description': lesson.description,
            'content_type': lesson.content_type,
            'order': lesson.order,
            'unlocked': unlocked,
            'is_completed': is_completed,
        })
    return Response({"success": True, "data": data, "message": "Lessons retrieved successfully."}, status=status.HTTP_200_OK)

