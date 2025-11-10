from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from courses.services.access_service import is_lesson_accessible
from courses.services.progress_service import mark_lesson_completed
from courses.models import Course, Lesson, Enrollment, LessonProgress, VideoCheckpointQuiz, VideoCheckpointResponse
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
        # Keep behavior in sync with list_module_lessons_view:
        # instructors/staff see everything unlocked; students require access checks
        unlocked = True if is_instructor else is_lesson_accessible(request.user, lesson)

        # Include completion flag for consistency with module-lessons
        is_completed = False
        if enrollment:
            lp = LessonProgress.objects.filter(enrollment=enrollment, lesson=lesson).first()
            if lp:
                is_completed = lp.completed

        data.append({
            'id': lesson.id,
            'title': lesson.title,
            'description': lesson.description,
            'content_type': lesson.content_type,
            'module_id': lesson.module_id,
            'order': lesson.order,
            'unlocked': unlocked,
            'is_completed': is_completed,
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

        # Also include player payload (without exposing solutions)
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

        quizzes_qs = lesson.video_checkpoint_quizzes.all().order_by('timestamp_seconds', 'id')
        grouped = {}
        for q in quizzes_qs:
            quiz_obj = {
                "id": q.id,
                "title": q.title,
                "question_text": q.question_text,
                "question_type": q.question_type,
                "options": q.options,
            }
            ts = int(q.timestamp_seconds)
            grouped.setdefault(ts, []).append(quiz_obj)

        checkpoint_quizzes = [
            {"timestamp_seconds": ts, "quizzes": quizzes}
            for ts, quizzes in sorted(grouped.items(), key=lambda x: x[0])
        ]

        content["player"] = {
            "id": lesson.id,
            "title": video.title or lesson.title,
            "video_url": get_video_url(),
            "duration": format_duration(video.duration or lesson.duration),
            "checkpoint_quizzes": checkpoint_quizzes,
        }

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

    # Reveal solutions only when explicitly requested by instructor/staff
    include_solutions = False
    try:
        reveal_param = (request.query_params.get("include_solutions") or "").strip().lower()
        include_solutions = bool(is_instructor and reveal_param in {"1", "true", "yes", "on"})
    except Exception:
        include_solutions = False

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
        }
        # Only expose solutions when explicitly requested by instructor/staff
        if include_solutions:
            quiz_obj["correct_answer_index"] = q.correct_answer_index
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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_video_checkpoint_answer_view(request, lesson_id):
    """
    Submit an answer for a video checkpoint quiz and return correctness.
    Does NOT expose the correct answer. Returns is_correct (and optional explanation).
    Payload:
    {
        "checkpoint_quiz_id": number,
        "selected_answer_index": number
    }
    """
    try:
        lesson = Lesson.objects.select_related('course').get(id=lesson_id)
    except Lesson.DoesNotExist:
        return Response({"success": False, "message": "Lesson not found."}, status=status.HTTP_404_NOT_FOUND)

    # Allow course instructor/staff for testing; students must be enrolled and lesson unlocked
    is_instructor = (lesson.course.instructor_id == request.user.id) or request.user.is_staff
    if not is_instructor:
        if not Enrollment.objects.filter(student=request.user, course=lesson.course, payment_status='completed').exists():
            return Response({"success": False, "message": "You are not enrolled in this course."}, status=status.HTTP_403_FORBIDDEN)
        if not is_lesson_accessible(request.user, lesson):
            return Response({"success": False, "message": "This lesson is locked. Please complete the previous lesson first."}, status=status.HTTP_403_FORBIDDEN)

    data = request.data or {}
    checkpoint_quiz_id = data.get("checkpoint_quiz_id")
    selected_answer_index = data.get("selected_answer_index")
    if checkpoint_quiz_id is None or selected_answer_index is None:
        return Response({"success": False, "message": "checkpoint_quiz_id and selected_answer_index are required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        checkpoint = VideoCheckpointQuiz.objects.get(id=checkpoint_quiz_id, lesson=lesson)
    except VideoCheckpointQuiz.DoesNotExist:
        return Response({"success": False, "message": "Checkpoint quiz not found for this lesson."}, status=status.HTTP_404_NOT_FOUND)

    # Create or update the student's response; model save() computes is_correct
    resp, _ = VideoCheckpointResponse.objects.update_or_create(
        student=request.user,
        checkpoint_quiz=checkpoint,
        defaults={
            "lesson": lesson,
            "selected_answer_index": int(selected_answer_index),
        }
    )

    # Determine the next unanswered quiz at the same timestamp for this student
    ts = int(checkpoint.timestamp_seconds)
    quizzes_at_ts = list(
        VideoCheckpointQuiz.objects.filter(lesson=lesson, timestamp_seconds=ts).order_by('id')
    )
    answered_ids = set(
        VideoCheckpointResponse.objects.filter(
            student=request.user,
            checkpoint_quiz__in=quizzes_at_ts
        ).values_list('checkpoint_quiz_id', flat=True)
    )

    correct_count = VideoCheckpointResponse.objects.filter(
        student=request.user,
        checkpoint_quiz__in=quizzes_at_ts,
        is_correct=True
    ).count()
    total_in_ts = len(quizzes_at_ts)
    all_answered = len(answered_ids) >= total_in_ts
    score_in_ts = round((correct_count / total_in_ts) * 100, 2) if total_in_ts else 0.0

    next_quiz_id = None
    # Prefer the next quiz after the current one at this timestamp
    passed_current = False
    for q in quizzes_at_ts:
        if q.id == checkpoint.id:
            passed_current = True
            continue
        if passed_current and q.id not in answered_ids:
            next_quiz_id = q.id
            break
    # If none found after current, consider earlier ones at this timestamp that are unanswered
    if next_quiz_id is None:
        for q in quizzes_at_ts:
            if q.id not in answered_ids:
                next_quiz_id = q.id
                break

    response_payload = {
        "checkpoint_quiz_id": checkpoint.id,
        "is_correct": bool(resp.is_correct),
        "timestamp_seconds": ts,
        "next_quiz_id": next_quiz_id,
        "answered_count_in_timestamp": len(answered_ids),
        "total_in_timestamp": total_in_ts,
        "correct_count_in_timestamp": correct_count,
        "score_in_timestamp": score_in_ts,
        "all_answered_in_timestamp": all_answered,
    }
    # Optionally return explanation after answering
    if getattr(checkpoint, "explanation", None):
        response_payload["explanation"] = checkpoint.explanation

    # Reveal the correct answer upon submission (but never in the GET payload)
    try:
        response_payload["correct_answer_index"] = int(checkpoint.correct_answer_index)
        opts = checkpoint.options or []
        if isinstance(opts, list) and 0 <= checkpoint.correct_answer_index < len(opts):
            response_payload["correct_answer"] = opts[checkpoint.correct_answer_index]
    except Exception:
        pass

    return Response({"success": True, "data": response_payload, "message": "Answer submitted."}, status=status.HTTP_200_OK)

    payload = {
        "id": lesson.id,
        "title": video.title or lesson.title,
        "video_url": get_video_url(),
        "duration": format_duration(video.duration or lesson.duration),
        "checkpoint_quizzes": checkpoint_quizzes,
    }

    return Response({"success": True, "data": payload, "message": "Video player data retrieved successfully."}, status=status.HTTP_200_OK)