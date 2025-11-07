from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from courses.UtilMethods import get_quiz_questions, start_quiz_attempt, is_lesson_accessible
from courses.models import Enrollment, Lesson, QuizAttempt, QuizQuestion, QuizConfiguration, Enrollment
from courses.serializers import DynamicFieldSerializer
from courses.UtilMethods import submit_quiz
from django.db.models import Avg, Max, Min

        
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_quiz_view(request, lesson_id):
    """
    Submit quiz answers for a lesson.
    Expected payload: {
        "responses": [
            {"question_id": 1, "answer_id": 2},  // for multiple-choice/true-false
            {"question_id": 2, "answer_text": "Jupiter"},  // for fill-blank
            {"question_id": 3, "drag_drop_response": {"mappings": {...}}},  // for drag & drop
        ],
        "start_time": "2024-01-01T00:00:00Z"  // optional
    }
    """
    
    from django.utils.dateparse import parse_datetime
    
    responses = request.data.get('responses', [])
    if not responses:
        return Response({
            "success": False,
            "message": "Responses are required."
        }, status=status.HTTP_400_BAD_REQUEST)
    
    start_time_str = request.data.get('start_time')
    start_time = None
    if start_time_str:
        start_time = parse_datetime(start_time_str)
    
    success, message, attempt_data = submit_quiz(request.user, lesson_id, responses, start_time=start_time)
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
        
        response_serializer = DynamicFieldSerializer(responses, many=True, model_name="quizresponse")
        
        result_data = {
            "attempt": {
                "id": attempt.id,
                "score": attempt.score,
                "correct_answers": attempt.correct_answers,
                "total_questions": attempt.total_questions,
                "earned_points": attempt.earned_points,
                "total_points": attempt.total_points,
                "passed": attempt.passed,
                "attempt_number": attempt.attempt_number,
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

 

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_quiz_attempt_view(request, lesson_id):
    """
    Start a new quiz attempt for a student.
    """
    
    # Ensure lesson is unlocked before starting
    try:
        lesson_obj = Lesson.objects.get(id=lesson_id)
        if not is_lesson_accessible(request.user, lesson_obj):
            return Response({
                "success": False,
                "message": "This quiz is locked. Please complete the previous lesson first."
            }, status=status.HTTP_403_FORBIDDEN)
    except Lesson.DoesNotExist:
        return Response({"success": False, "message": "Lesson not found."}, status=status.HTTP_404_NOT_FOUND)
    success, message, attempt_data = start_quiz_attempt(request.user, lesson_id)
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
def get_quiz_questions_view(request, lesson_id):
    """
    Get quiz questions for a lesson (with randomization if enabled).
    For students only - excludes correct answers and internal settings.
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        enrollment = Enrollment.objects.get(student=request.user, course=lesson.course)
        
        if enrollment.payment_status != 'completed':
            return Response({
                "success": False,
                "message": "Payment not completed for this course."
            }, status=status.HTTP_403_FORBIDDEN)
        
        if lesson.content_type != Lesson.ContentType.QUIZ:
            return Response({
                "success": False,
                "message": "This lesson is not a quiz."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Ensure unlock
        if not is_lesson_accessible(request.user, lesson):
            return Response({
                "success": False,
                "message": "This quiz is locked. Please complete the previous lesson first."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get quiz configuration
        quiz_config = getattr(lesson, 'quiz_config', None)
        quiz_lesson = getattr(lesson, 'quiz', None)
        
        # Get questions
        randomize = quiz_config.randomize_questions if quiz_config else (quiz_lesson.randomize_questions if quiz_lesson else False)
        questions = get_quiz_questions(lesson, randomize=randomize)
        
        # Serialize questions (without correct answers)
        question_data = []
        for q in questions:
            q_data = DynamicFieldSerializer(q, model_name="quizquestion").data
            q_type = q.question_type

            # Structure per question type
            if q_type in ['multiple-choice', 'true-false']:
                q_data['answers'] = [{'id': ans.id, 'answer_text': ans.answer_text} for ans in q.answers.all()]
                # Remove backend-only fields
                for field in [
                    'blanks', 'cloze_text', 'cloze_answers', 'cloze_options', 'background_image',
                    'image_drop_zones', 'image_drag_items', 'image_correct_mappings',
                    'matching_left_items', 'matching_right_items', 'matching_correct_pairs',
                    'sequencing_items', 'sequencing_correct_order', 'categorization_items',
                    'categorization_categories', 'categorization_correct_mappings',
                    'drag_items', 'drop_zones', 'drag_drop_mappings', 'option_images'
                ]:
                    q_data.pop(field, None)

            elif q_type == 'fill-blank':
                q_data['blanks_count'] = len(q.blanks) if hasattr(q, 'blanks') and q.blanks else 1
                for field in [
                    'answers', 'blanks', 'cloze_text', 'cloze_answers', 'cloze_options',
                    'background_image', 'image_drop_zones', 'image_drag_items', 'image_correct_mappings',
                    'matching_left_items', 'matching_right_items', 'matching_correct_pairs',
                    'sequencing_items', 'sequencing_correct_order', 'categorization_items',
                    'categorization_categories', 'categorization_correct_mappings',
                    'drag_items', 'drop_zones', 'drag_drop_mappings', 'option_images'
                ]:
                    q_data.pop(field, None)

            elif any(t in q_type for t in ['drag-drop', 'matching', 'sequencing', 'categorization']):
                for field in [
                    'cloze_answers', 'image_correct_mappings', 'matching_correct_pairs',
                    'sequencing_correct_order', 'categorization_correct_mappings',
                    'answers', 'blanks'
                ]:
                    q_data.pop(field, None)
            else:
                for field in [
                    'answers', 'blanks', 'cloze_answers', 'image_correct_mappings',
                    'matching_correct_pairs', 'sequencing_correct_order', 'categorization_correct_mappings'
                ]:
                    q_data.pop(field, None)

            question_data.append(q_data)
        
        # Build safe quiz configuration
        safe_quiz_config = {
            "time_limit": quiz_config.time_limit if quiz_config else (quiz_lesson.time_limit if quiz_lesson else 30),
            "passing_score": quiz_config.passing_score if quiz_config else (quiz_lesson.passing_score if quiz_lesson else 70),
            "max_attempts": quiz_config.max_attempts if quiz_config else (quiz_lesson.attempts if quiz_lesson else 3),
        }

        # Calculate total marks
        total_marks = lesson.calculate_total_marks()

        return Response({
            "success": True,
            "data": {
                "quiz_config": safe_quiz_config,
                "total_marks": total_marks,
                "total_questions": len(questions),
                "questions": question_data
            },
            "message": "Quiz questions retrieved successfully."
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_quiz_attempt_history_view(request, lesson_id):
    """
    Get all quiz attempts for a student for a specific lesson.
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        enrollment = Enrollment.objects.get(student=request.user, course=lesson.course)
        
        attempts = QuizAttempt.objects.filter(
            student=request.user,
            lesson=lesson
        ).order_by('-completed_at', '-started_at')
        
        attempt_data = []
        for attempt in attempts:
            attempt_dict = DynamicFieldSerializer(attempt, model_name="quizattempt").data
            attempt_data.append(attempt_dict)
        
        # Get final score based on grading policy
        quiz_config = getattr(lesson, 'quiz_config', None)
        final_score = quiz_config.calculate_final_score(request.user) if quiz_config else attempts.first().score if attempts.exists() else 0.0
        
        return Response({
            "success": True,
            "data": {
                "attempts": attempt_data,
                "final_score": final_score,
                "total_attempts": attempts.count()
            },
            "message": "Quiz attempt history retrieved successfully."
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



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_quiz_view(request, lesson_id):
    """
    Create a quiz configuration for a lesson.
    Only the course instructor can create quizzes.
    Expected payload: {
        "time_limit": 30,
        "passing_score": 70,
        "max_attempts": 3,
        "randomize_questions": false,
        "show_correct_answers": true,
        "grading_policy": "highest"
    }
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        
        # Check authorization
        if lesson.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to create quizzes for this lesson."
            }, status=status.HTTP_403_FORBIDDEN)
        
        if lesson.content_type != Lesson.ContentType.QUIZ:
            return Response({
                "success": False,
                "message": "This lesson is not a quiz lesson."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if config already exists
      
        quiz_config, created = QuizConfiguration.objects.get_or_create(
            lesson=lesson,
            defaults={
                'time_limit': request.data.get('time_limit', 30),
                'passing_score': request.data.get('passing_score', 70),
                'max_attempts': request.data.get('max_attempts', 3),
                'randomize_questions': request.data.get('randomize_questions', False),
                'show_correct_answers': request.data.get('show_correct_answers', True),
                'grading_policy': request.data.get('grading_policy', 'highest')
            }
        )
        
        if not created:
            # Update existing config
            quiz_config.time_limit = request.data.get('time_limit', quiz_config.time_limit)
            quiz_config.passing_score = request.data.get('passing_score', quiz_config.passing_score)
            quiz_config.max_attempts = request.data.get('max_attempts', quiz_config.max_attempts)
            quiz_config.randomize_questions = request.data.get('randomize_questions', quiz_config.randomize_questions)
            quiz_config.show_correct_answers = request.data.get('show_correct_answers', quiz_config.show_correct_answers)
            quiz_config.grading_policy = request.data.get('grading_policy', quiz_config.grading_policy)
            quiz_config.save()
        
        serializer = DynamicFieldSerializer(quiz_config, model_name="quizconfiguration")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Quiz configuration created successfully." if created else "Quiz configuration updated successfully."
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
    
    except Lesson.DoesNotExist:
        return Response({
            "success": False,
            "message": "Lesson not found."
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_quiz_analytics_view(request, lesson_id):
    """
    Get quiz analytics for teachers.
    Shows statistics about all student attempts.
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        
        # Check authorization
        if lesson.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view analytics for this quiz."
            }, status=status.HTTP_403_FORBIDDEN)
        
        if lesson.content_type != Lesson.ContentType.QUIZ:
            return Response({
                "success": False,
                "message": "This lesson is not a quiz."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get all attempts
        attempts = QuizAttempt.objects.filter(lesson=lesson, is_in_progress=False)
        
        # Calculate statistics
        total_attempts = attempts.count()
        avg_score = attempts.aggregate(Avg('score'))['score__avg'] or 0.0
        max_score = attempts.aggregate(Max('score'))['score__max'] or 0.0
        min_score = attempts.aggregate(Min('score'))['score__min'] or 0.0
        
        # Count passed attempts
        quiz_config = getattr(lesson, 'quiz_config', None)
        passing_score = quiz_config.passing_score if quiz_config else 70
        passed_attempts = attempts.filter(score__gte=passing_score).count()
        passed_percentage = (passed_attempts / total_attempts * 100) if total_attempts > 0 else 0.0
        
        # Get unique students
        unique_students = attempts.values('student').distinct().count()
        
        # Get enrollment count
        enrollment_count = Enrollment.objects.filter(course=lesson.course, payment_status='completed').count()
        completion_rate = (unique_students / enrollment_count * 100) if enrollment_count > 0 else 0.0
        
        # Get total marks
        total_marks = lesson.calculate_total_marks()
        
        return Response({
            "success": True,
            "data": {
                "quiz_info": {
                    "lesson_id": lesson.id,
                    "lesson_title": lesson.title,
                    "total_marks": total_marks,
                    "total_questions": QuizQuestion.objects.filter(lesson=lesson).count(),
                    "passing_score": passing_score
                },
                "statistics": {
                    "total_attempts": total_attempts,
                    "unique_students": unique_students,
                    "enrollment_count": enrollment_count,
                    "completion_rate": round(completion_rate, 2),
                    "average_score": round(avg_score, 2),
                    "max_score": round(max_score, 2),
                    "min_score": round(min_score, 2),
                    "passed_attempts": passed_attempts,
                    "passed_percentage": round(passed_percentage, 2)
                }
            },
            "message": "Quiz analytics retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    except Lesson.DoesNotExist:
        return Response({
            "success": False,
            "message": "Lesson not found."
        }, status=status.HTTP_404_NOT_FOUND)

