from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from courses.services.access_service import is_lesson_accessible
from courses.services.progress_service import mark_lesson_completed
from courses.models import Course, Lesson, Enrollment, LessonProgress
from ..serializers import DynamicFieldSerializer


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_lesson_completed_view(request, lesson_id):
    """
    API endpoint to mark a lesson as completed.
    Only the enrolled student can mark their own lessons as completed.
    """
    result = mark_lesson_completed(request.user, lesson_id)
    # Backward compatibility: older signature returned (success, message)
    if isinstance(result, tuple) and len(result) == 3:
        success, message, next_lesson_id = result
    else:
        success, message = result
        next_lesson_id = None
    if success:
        # Return updated progress information
        try:
            lesson = Lesson.objects.get(id=lesson_id)
            enrollment = Enrollment.objects.get(student=request.user, course=lesson.course)
            lesson_progress = LessonProgress.objects.get(enrollment=enrollment, lesson=lesson)
            
            
            progress_serializer = DynamicFieldSerializer(lesson_progress, model_name="lessonprogress")
            enrollment_serializer = DynamicFieldSerializer(enrollment, model_name="enrollment")
            
            # Determine if a next lesson exists and is unlocked now
            next_unlocked = False
            if next_lesson_id:
                try:
                    next_lesson = Lesson.objects.get(id=next_lesson_id)
                    next_unlocked = is_lesson_accessible(request.user, next_lesson)
                except Lesson.DoesNotExist:
                    next_unlocked = False

            return Response({
                "success": True,
                "message": message,
                "data": {
                    "lesson_progress": progress_serializer.data,
                    "enrollment_progress": {
                        "progress": float(enrollment.progress),
                        "completed_lessons": enrollment.completed_lessons,
                        "is_completed": enrollment.is_completed
                    },
                    "next_lesson_unlocked": bool(next_unlocked),
                    "next_lesson_id": next_lesson_id
                }
            }, status=status.HTTP_200_OK)
        except (Lesson.DoesNotExist, Enrollment.DoesNotExist, LessonProgress.DoesNotExist):
            return Response({
                "success": True,
                "message": message,
                "data": {
                    "next_lesson_unlocked": bool(next_lesson_id),
                    "next_lesson_id": next_lesson_id
                }
            }, status=status.HTTP_200_OK)
    else:
        return Response({"success": False, "message": message}, status=status.HTTP_400_BAD_REQUEST)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_course_lessons_view(request, course_id):
    """
    List all lessons in a course with their lock/unlock status for the authenticated student.
    """
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)

    # Allow course instructor or staff to browse without enrollment/locks
    is_instructor = (course.instructor_id == request.user.id) or request.user.is_staff

    # Ensure the user is enrolled (students only)
    enrollment = None
    if not is_instructor:
        enrollment = Enrollment.objects.filter(student=request.user, course=course, payment_status='completed').first()
        if not enrollment:
            return Response({"success": False, "message": "You are not enrolled in this course."}, status=status.HTTP_403_FORBIDDEN)

    lessons = Lesson.objects.filter(course=course).order_by('module__order', 'order')
    data = []
    for lesson in lessons:
        unlocked = True if is_instructor else is_lesson_accessible(request.user, lesson)
        data.append({
            'id': lesson.id,
            'title': lesson.title,
            'description': lesson.description,
            'content_type': lesson.content_type,
            'module_id': lesson.module_id,
            'order': lesson.order,
            'unlocked': unlocked,
        })
    return Response({"success": True, "data": data, "message": "Lessons retrieved successfully."}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_lesson_completed_view(request, lesson_id):
    """
    API endpoint to mark a lesson as completed.
    Only the enrolled student can mark their own lessons as completed.
    """
    result = mark_lesson_completed(request.user, lesson_id)
    # Backward compatibility: older signature returned (success, message)
    if isinstance(result, tuple) and len(result) == 3:
        success, message, next_lesson_id = result
    else:
        success, message = result
        next_lesson_id = None
    if success:
        # Return updated progress information
        try:
            lesson = Lesson.objects.get(id=lesson_id)
            enrollment = Enrollment.objects.get(student=request.user, course=lesson.course)
            lesson_progress = LessonProgress.objects.get(enrollment=enrollment, lesson=lesson)
            
            progress_serializer = DynamicFieldSerializer(lesson_progress, model_name="lessonprogress")
            enrollment_serializer = DynamicFieldSerializer(enrollment, model_name="enrollment")
            
            # Determine if a next lesson exists and is unlocked now
            next_unlocked = False
            if next_lesson_id:
                try:
                    next_lesson = Lesson.objects.get(id=next_lesson_id)
                    next_unlocked = is_lesson_accessible(request.user, next_lesson)
                except Lesson.DoesNotExist:
                    next_unlocked = False

            return Response({
                "success": True,
                "message": message,
                "data": {
                    "lesson_progress": progress_serializer.data,
                    "enrollment_progress": {
                        "progress": float(enrollment.progress),
                        "completed_lessons": enrollment.completed_lessons,
                        "is_completed": enrollment.is_completed
                    },
                    "next_lesson_unlocked": bool(next_unlocked),
                    "next_lesson_id": next_lesson_id
                }
            }, status=status.HTTP_200_OK)
        except (Lesson.DoesNotExist, Enrollment.DoesNotExist, LessonProgress.DoesNotExist):
            return Response({
                "success": True,
                "message": message,
                "data": {
                    "next_lesson_unlocked": bool(next_lesson_id),
                    "next_lesson_id": next_lesson_id
                }
            }, status=status.HTTP_200_OK)
    else:
        return Response({"success": False, "message": message}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lesson_detail_view(request, lesson_id):
    """
    Return lesson details and its content only if unlocked for the authenticated student.
    """
    try:
        lesson = Lesson.objects.select_related('course').get(id=lesson_id)
    except Lesson.DoesNotExist:
        return Response({"success": False, "message": "Lesson not found."}, status=status.HTTP_404_NOT_FOUND)

    # Allow course instructor/staff to access regardless of locks or enrollment
    is_instructor = (lesson.course.instructor_id == request.user.id) or request.user.is_staff

    # Ensure enrollment and unlock for students only
    if not is_instructor:
        if not Enrollment.objects.filter(student=request.user, course=lesson.course, payment_status='completed').exists():
            return Response({"success": False, "message": "You are not enrolled in this course."}, status=status.HTTP_403_FORBIDDEN)
        if not is_lesson_accessible(request.user, lesson):
            return Response({"success": False, "message": "This lesson is locked. Please complete the previous lesson first."}, status=status.HTTP_403_FORBIDDEN)

    # Serialize base lesson
    lesson_data = DynamicFieldSerializer(lesson, model_name="lesson").data

    # Attach content based on type
    content = None
    if lesson.content_type == Lesson.ContentType.ARTICLE and hasattr(lesson, 'article'):
        content = DynamicFieldSerializer(lesson.article, model_name="articlelesson").data
    elif lesson.content_type == Lesson.ContentType.ASSIGNMENT and hasattr(lesson, 'assignment'):
        content = DynamicFieldSerializer(lesson.assignment, model_name="assignmentlesson").data
    elif lesson.content_type == Lesson.ContentType.QUIZ and hasattr(lesson, 'quiz'):
        # Include config and question count for context, not answers here
        quiz = lesson.quiz
        cfg = getattr(lesson, 'quiz_config', None)
        content = {
            'quiz': DynamicFieldSerializer(quiz, model_name="quizlesson").data,
            'config': DynamicFieldSerializer(cfg, model_name="quizconfiguration").data if cfg else None,
            'question_count': lesson.quiz_questions.count(),
            'total_marks': lesson.calculate_total_marks(),
        }
    elif lesson.content_type == Lesson.ContentType.VIDEO and hasattr(lesson, 'video'):
        content = DynamicFieldSerializer(lesson.video, model_name="videolesson").data

    return Response({
        "success": True,
        "data": {
            "lesson": lesson_data,
            "content": content
        },
        "message": "Lesson detail retrieved successfully."
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_video_player_data_view(request, lesson_id):
    """
    Clean payload for video player + checkpoint quizzes.
    Returns a single object with video metadata and embedded checkpoint quizzes.
    """
    try:
        lesson = Lesson.objects.select_related('course', 'video').get(id=lesson_id)
    except Lesson.DoesNotExist:
        return Response({"success": False, "message": "Lesson not found."}, status=status.HTTP_404_NOT_FOUND)

    # Allow course instructor/staff to access regardless of locks or enrollment
    is_instructor = (lesson.course.instructor_id == request.user.id) or request.user.is_staff

    # Ensure enrollment and unlock for students only
    if not is_instructor:
        if not Enrollment.objects.filter(student=request.user, course=lesson.course, payment_status='completed').exists():
            return Response({"success": False, "message": "You are not enrolled in this course."}, status=status.HTTP_403_FORBIDDEN)
        if not is_lesson_accessible(request.user, lesson):
            return Response({"success": False, "message": "This lesson is locked. Please complete the previous lesson first."}, status=status.HTTP_403_FORBIDDEN)

    if lesson.content_type != Lesson.ContentType.VIDEO or not hasattr(lesson, 'video'):
        return Response({"success": False, "message": "This endpoint is only available for video lessons."}, status=status.HTTP_400_BAD_REQUEST)

    video = lesson.video

    def format_duration(value):
        if not value:
            return None
        total_seconds = int(value.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def get_video_url():
        if getattr(video, "youtube_url", None):
            return video.youtube_url
        if getattr(video, "video_file", None):
            try:
                return request.build_absolute_uri(video.video_file.url)
            except Exception:
                return None
        return None

    # Collect checkpoint quizzes grouped by timestamp
    quizzes_qs = lesson.video_checkpoint_quizzes.all().order_by('timestamp_seconds', 'id')
    grouped = {}
    for q in quizzes_qs:
        quiz_obj = {
            "id": q.id,
            "title": q.title,
            "question_text": q.question_text,
            "question_type": q.question_type,
            "options": q.options,
            "correct_answer_index": q.correct_answer_index,
        }
        if q.explanation:
            quiz_obj["explanation"] = q.explanation
        ts = int(q.timestamp_seconds)
        grouped.setdefault(ts, []).append(quiz_obj)

    checkpoint_quizzes = [
        {"timestamp_seconds": ts, "quizzes": quizzes}
        for ts, quizzes in sorted(grouped.items(), key=lambda x: x[0])
    ]

    payload = {
        "id": lesson.id,
        "title": video.title or lesson.title,
        "video_url": get_video_url(),
        "duration": format_duration(video.duration or lesson.duration),
        "checkpoint_quizzes": checkpoint_quizzes,
    }

    return Response({"success": True, "data": payload, "message": "Video player data retrieved successfully."}, status=status.HTTP_200_OK)