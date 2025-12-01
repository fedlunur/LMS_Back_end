from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count
from courses.models import Course, Enrollment, Lesson, LessonProgress, Module, AssessmentAttempt
from courses.services.access_service import is_lesson_accessible, is_module_accessible
from courses.services.pagination import paginate_queryset_or_list


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_course_modules_view(request, course_id):
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)

    # Allow course instructor or staff to browse regardless of publish status
    is_instructor = (course.instructor_id == request.user.id) or request.user.is_staff
    if course.status != 'published' and not is_instructor:
        return Response({"success": False, "message": "Course not accessible."}, status=status.HTTP_403_FORBIDDEN)

    # Students must be enrolled; instructors can browse freely
    enrollment = None
    if not is_instructor:
        enrollment = Enrollment.objects.filter(student=request.user, course=course, payment_status='completed').first()
    modules = Module.objects.filter(course=course).annotate(lesson_count=Count('lessons')).order_by('order')
    data = []
    for m in modules:
        # Instructors/staff: unlocked; students: check module access
        is_unlocked = True if is_instructor else False
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
    
    # Add final assessment at the bottom if course requires it
    final_assessment_data = None
    if course.requires_final_assessment:
        assessment = getattr(course, 'final_assessment', None)
        
        # Check if student can access (all lessons completed)
        total_lessons = Lesson.objects.filter(course=course).count()
        completed_lessons = 0
        has_passed = False
        best_score = None
        attempts_count = 0
        last_attempt = None
        
        if enrollment:
            completed_lessons = LessonProgress.objects.filter(
                enrollment=enrollment,
                completed=True
            ).count()
            
            # Get attempt info if assessment exists
            if assessment:
                attempts = AssessmentAttempt.objects.filter(
                    student=request.user,
                    assessment=assessment
                ).order_by('-completed_at')
                attempts_count = attempts.count()
                has_passed = attempts.filter(passed=True).exists()
                best_attempt = attempts.order_by('-score').first()
                if best_attempt:
                    best_score = best_attempt.score
                if attempts.exists():
                    last = attempts.first()
                    last_attempt = {
                        'score': last.score,
                        'passed': last.passed,
                        'completed_at': last.completed_at.isoformat() if last.completed_at else None
                    }
        
        can_access = (completed_lessons >= total_lessons) or is_instructor
        
        if assessment:
            final_assessment_data = {
                'id': assessment.id,
                'title': assessment.title,
                'description': assessment.description,
                'type': 'final_assessment',
                'order': len(data) + 1,  # Place after all modules
                'passing_score': assessment.passing_score,
                'time_limit': assessment.time_limit,
                'total_questions': assessment.questions.count(),
                'unlocked': can_access,
                'is_completed': has_passed,
                'is_active': assessment.is_active,
                'progress': {
                    'attempts_count': attempts_count,
                    'best_score': best_score,
                    'last_attempt': last_attempt,
                    'lessons_completed': completed_lessons,
                    'lessons_total': total_lessons,
                    'lessons_remaining': max(0, total_lessons - completed_lessons)
                }
            }
        else:
            # Assessment required but not created yet
            final_assessment_data = {
                'id': None,
                'title': 'Final Course Assessment',
                'description': 'Assessment not yet created by instructor',
                'type': 'final_assessment',
                'order': len(data) + 1,
                'passing_score': None,
                'time_limit': None,
                'total_questions': 0,
                'unlocked': False,
                'is_completed': False,
                'is_active': False,
                'not_created': True,
                'progress': {
                    'attempts_count': 0,
                    'best_score': None,
                    'last_attempt': None,
                    'lessons_completed': completed_lessons,
                    'lessons_total': total_lessons,
                    'lessons_remaining': max(0, total_lessons - completed_lessons)
                }
            }
    
    # Build response with pagination
    paginated_response = paginate_queryset_or_list(request, data)
    
    # Add final assessment and course info to response
    if hasattr(paginated_response, 'data'):
        paginated_response.data['final_assessment'] = final_assessment_data
        paginated_response.data['course'] = {
            'id': course.id,
            'title': course.title,
            'requires_final_assessment': course.requires_final_assessment,
            'issue_certificate': course.issue_certificate
        }
    
    return paginated_response



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
    # Apply pagination
    return paginate_queryset_or_list(request, data)

