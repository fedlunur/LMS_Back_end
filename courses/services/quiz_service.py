from django.utils import timezone

from courses.services.progress_service import mark_lesson_completed
from ..models import Enrollment, Lesson, QuizQuestion, QuizAnswer, QuizAttempt, QuizResponse, LessonProgress, ModuleProgress, Module
from .access_service import is_lesson_accessible

def evaluate_question_answer(question, response_data):
    """
    Evaluate a student's answer for a question.
    Returns: (is_correct, points_earned)
    """
    answer_id = response_data.get('answer_id')
    # Support multi-select for MCQ: list of selected answer IDs
    answer_ids = response_data.get('answer_ids') or response_data.get('selected_answer_ids')
    answer_text = (response_data.get('answer_text') or '').strip()
    # Support multiple blanks texts for fill-blank/short-answer
    answer_texts = response_data.get('answer_texts')
    drag_drop_response = response_data.get('drag_drop_response', {})
    
    is_correct = False
    points_earned = 0.0
    
    if question.question_type in ['multiple-choice', 'true-false']:
        # Multi-select takes precedence if provided
        if answer_ids and isinstance(answer_ids, (list, tuple)):
            try:
                correct_ids = list(
                    QuizAnswer.objects.filter(question=question, is_correct=True).values_list('id', flat=True)
                )
                selected_set = set(map(int, answer_ids))
                correct_set = set(map(int, correct_ids))
                if selected_set == correct_set and len(correct_set) > 0:
                    is_correct = True
                    points_earned = question.points
            except Exception:
                pass
        elif answer_id:
            try:
                answer = QuizAnswer.objects.get(id=answer_id, question=question)
                is_correct = answer.is_correct
                if is_correct:
                    points_earned = question.points
            except QuizAnswer.DoesNotExist:
                pass
    
    elif question.question_type == 'fill-blank':
        # Support multiple blanks (all must match in order)
        correct_answers = [b.lower().strip() for b in (question.blanks or [])]
        if answer_texts and isinstance(answer_texts, (list, tuple)) and correct_answers:
            student = [str(x).lower().strip() for x in answer_texts]
            if len(student) == len(correct_answers) and all(
                (student[i] == correct_answers[i]) for i in range(len(correct_answers))
            ):
                is_correct = True
                points_earned = question.points
        elif answer_text:
            if correct_answers and answer_text.lower().strip() in correct_answers:
                is_correct = True
                points_earned = question.points
    
    elif question.question_type == 'drag-drop-text':
        # Check cloze answers
        student_answers = drag_drop_response.get('answers', [])
        correct_answers = question.cloze_answers if question.cloze_answers else []
        
        if len(student_answers) == len(correct_answers):
            all_correct = True
            for i, student_answer in enumerate(student_answers):
                if i < len(correct_answers):
                    if student_answer.lower().strip() != correct_answers[i].lower().strip():
                        all_correct = False
                        break
            
            if all_correct:
                is_correct = True
                points_earned = question.points
    
    elif question.question_type == 'drag-drop-image':
        # Check image mappings
        student_mappings = drag_drop_response.get('mappings', {})
        correct_mappings = question.image_correct_mappings if question.image_correct_mappings else {}
        
        if student_mappings == correct_mappings:
            is_correct = True
            points_earned = question.points
    
    elif question.question_type == 'drag-drop-matching':
        # Check matching pairs
        student_pairs = drag_drop_response.get('pairs', [])
        correct_pairs = question.matching_correct_pairs if question.matching_correct_pairs else []
        
        # Normalize pairs for comparison
        def normalize_pair(pair):
            return {'left_id': pair.get('left_id'), 'right_id': pair.get('right_id')}
        
        student_pairs_normalized = [normalize_pair(p) for p in student_pairs]
        correct_pairs_normalized = [normalize_pair(p) for p in correct_pairs]
        
        if len(student_pairs_normalized) == len(correct_pairs_normalized):
            if all(pair in correct_pairs_normalized for pair in student_pairs_normalized):
                is_correct = True
                points_earned = question.points
    
    elif question.question_type == 'drag-drop-sequencing':
        # Check sequence order
        student_order = drag_drop_response.get('order', [])
        correct_order = question.sequencing_correct_order if question.sequencing_correct_order else []
        
        if student_order == correct_order:
            is_correct = True
            points_earned = question.points
    
    elif question.question_type == 'drag-drop-categorization':
        # Check categorization mappings
        student_mappings = drag_drop_response.get('mappings', {})
        correct_mappings = question.categorization_correct_mappings if question.categorization_correct_mappings else {}
        
        if student_mappings == correct_mappings:
            is_correct = True
            points_earned = question.points

    elif question.question_type == 'short-answer':
        # Basic auto-grading: match against provided acceptable answers in blanks
        if answer_text:
            acceptable = [b.lower().strip() for b in (question.blanks or [])]
            if acceptable and answer_text.lower().strip() in acceptable:
                is_correct = True
                points_earned = question.points
    
    return is_correct, points_earned


def get_quiz_questions(lesson, randomize=False):
    """
    Get quiz questions for a lesson, optionally randomized.
    Returns queryset of questions.
    """
    questions = QuizQuestion.objects.filter(lesson=lesson).order_by('order')
    
    if randomize:
        questions = list(questions)
        import random
        random.shuffle(questions)
        # Convert back to queryset-like behavior
        return questions
    
    return questions


def start_quiz_attempt(user, lesson_id):
    """
    Start a new quiz attempt for a student.
    Returns: (success, message, attempt_data)
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        enrollment = Enrollment.objects.get(student=user, course=lesson.course)
        
        if enrollment.payment_status != 'completed':
            return False, "Payment not completed for this course.", None
        
        if lesson.content_type != Lesson.ContentType.QUIZ:
            return False, "This lesson is not a quiz.", None
        
        # Get quiz configuration
        quiz_config = getattr(lesson, 'quiz_config', None)
        quiz_lesson = getattr(lesson, 'quiz', None)
        
        # Check attempts
        completed_attempts = QuizAttempt.objects.filter(
            student=user,
            lesson=lesson,
            is_in_progress=False
        ).count()
        
        max_attempts = quiz_config.max_attempts if quiz_config else (quiz_lesson.attempts if quiz_lesson else 3)
        if completed_attempts >= max_attempts:
            return False, f"Maximum attempts ({max_attempts}) reached for this quiz.", None
        
        # Check if there's an in-progress attempt
        in_progress = QuizAttempt.objects.filter(
            student=user,
            lesson=lesson,
            is_in_progress=True
        ).first()
        
        if in_progress:
            return True, "Resuming existing attempt.", {
                'attempt_id': in_progress.id,
                'started_at': in_progress.started_at,
                'time_limit': quiz_config.time_limit if quiz_config else (quiz_lesson.time_limit if quiz_lesson else 30)
            }
        
        # Create new attempt
        attempt_number = completed_attempts + 1
        attempt = QuizAttempt.objects.create(
            student=user,
            lesson=lesson,
            total_questions=0,
            correct_answers=0,
            total_points=0.0,
            earned_points=0.0,
            attempt_number=attempt_number,
            is_in_progress=True
        )
        
        return True, "Quiz attempt started.", {
            'attempt_id': attempt.id,
            'started_at': attempt.started_at,
            'time_limit': quiz_config.time_limit if quiz_config else (quiz_lesson.time_limit if quiz_lesson else 30)
        }
    
    except Lesson.DoesNotExist:
        return False, "Lesson not found.", None
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course.", None


def submit_quiz(user, lesson_id, responses, start_time=None):
    """
    Submit quiz answers for a lesson.
    responses: list of dicts with 'question_id', and optionally:
        - 'answer_id' (single-select for MCQ/True-False)
        - 'answer_ids' (multi-select for MCQ)
        - 'answer_text' (for single fill-blank/short-answer)
        - 'answer_texts' (for multiple blanks)
        - 'drag_drop_response' (for drag & drop questions)
    start_time: datetime when quiz was started (optional)
    Returns: (success, message, attempt_data)
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        enrollment = Enrollment.objects.get(student=user, course=lesson.course)

        if enrollment.payment_status != 'completed':
            return False, "Payment not completed for this course.", None

        if lesson.content_type != Lesson.ContentType.QUIZ:
            return False, "This lesson is not a quiz.", None

        # Ensure the lesson is unlocked for the student
        if not is_lesson_accessible(user, lesson):
            return False, "This quiz is locked. Please complete the previous lesson first.", None

        # Get quiz configuration
        quiz_config = getattr(lesson, 'quiz_config', None)
        quiz_lesson = getattr(lesson, 'quiz', None)
        if not quiz_config and not quiz_lesson:
            return False, "Quiz configuration not found.", None

        # Check attempts (only count completed attempts)
        completed_attempts = QuizAttempt.objects.filter(
            student=user,
            lesson=lesson,
            is_in_progress=False
        ).count()

        max_attempts = quiz_config.max_attempts if quiz_config else (quiz_lesson.attempts if quiz_lesson else 3)
        if completed_attempts >= max_attempts:
            return False, f"Maximum attempts ({max_attempts}) reached for this quiz.", None

        # Get all questions for this quiz to calculate total points
        all_questions = QuizQuestion.objects.filter(lesson=lesson)
        total_points = sum(q.points for q in all_questions)

        # Create or get in-progress attempt
        attempt = QuizAttempt.objects.filter(
            student=user,
            lesson=lesson,
            is_in_progress=True
        ).first()

        if not attempt:
            attempt_number = completed_attempts + 1
            attempt = QuizAttempt.objects.create(
                student=user,
                lesson=lesson,
                total_questions=len(all_questions),
                correct_answers=0,
                total_points=total_points,
                earned_points=0.0,
                attempt_number=attempt_number,
                started_at=start_time or timezone.now()
            )

        # Process responses
        earned_points = 0.0
        correct_count = 0

        for response_data in responses:
            question_id = response_data.get('question_id')

            try:
                question = QuizQuestion.objects.get(id=question_id, lesson=lesson)

                # Evaluate answer
                is_correct, points_earned = evaluate_question_answer(question, response_data)

                if is_correct:
                    correct_count += 1
                    earned_points += points_earned

                # Merge/normalize persisted response payload
                persisted_drag_payload = response_data.get('drag_drop_response', {}) or {}
                # Persist multi-select for MCQ if present
                if response_data.get('answer_ids') or response_data.get('selected_answer_ids'):
                    persisted_drag_payload = {
                        **persisted_drag_payload,
                        'selected_answer_ids': response_data.get('answer_ids') or response_data.get('selected_answer_ids')
                    }
                # Persist multiple blanks if present
                if response_data.get('answer_texts'):
                    persisted_drag_payload = {
                        **persisted_drag_payload,
                        'answer_texts': response_data.get('answer_texts')
                    }

                # Create or update response
                QuizResponse.objects.update_or_create(
                    attempt=attempt,
                    question=question,
                    defaults={
                        'answer_id': response_data.get('answer_id'),
                        'answer_text': response_data.get('answer_text', ''),
                        'drag_drop_response': persisted_drag_payload,
                        'is_correct': is_correct,
                        'points_earned': points_earned
                    }
                )

            except QuizQuestion.DoesNotExist:
                continue

        # Update attempt
        attempt.total_questions = len(all_questions)
        attempt.correct_answers = correct_count
        attempt.earned_points = earned_points
        attempt.total_points = total_points
        attempt.completed_at = timezone.now()
        attempt.is_in_progress = False
        attempt.calculate_score()

        # Mark lesson as completed if passed
        passing_score = quiz_config.passing_score if quiz_config else (quiz_lesson.passing_score if quiz_lesson else 70)
        if attempt.passed:
            mark_lesson_completed(user, lesson_id)
        else:
            # If not passed and attempts exhausted, reset previous lessons in module to force relearn
            used_attempts = QuizAttempt.objects.filter(
                student=user, lesson=lesson, is_in_progress=False
            ).count()
            max_attempts = quiz_config.max_attempts if quiz_config else (quiz_lesson.attempts if quiz_lesson else 3)
            if used_attempts >= max_attempts and lesson.module:
                # Find lessons before this quiz within the same module
                prior_lessons = Lesson.objects.filter(module=lesson.module, order__lt=lesson.order)
                # Reset their progress
                for prior in prior_lessons:
                    try:
                        lp = LessonProgress.objects.get(enrollment=enrollment, lesson=prior)
                        lp.completed = False
                        lp.progress = 0.0
                        lp.completed_at = None
                        lp.save(update_fields=["completed", "progress", "completed_at"])
                    except LessonProgress.DoesNotExist:
                        # If no progress exists, nothing to reset
                        continue
                # Recalculate module progress (will set incomplete)
                try:
                    mp = ModuleProgress.objects.get(enrollment=enrollment, module=lesson.module)
                    mp.calculate_progress()
                except ModuleProgress.DoesNotExist:
                    pass

        return True, "Quiz submitted successfully.", {
            'attempt_id': attempt.id,
            'score': attempt.score,
            'passed': attempt.passed,
            'correct_answers': attempt.correct_answers,
            'total_questions': attempt.total_questions,
            'earned_points': attempt.earned_points,
            'total_points': attempt.total_points,
            'attempt_number': attempt.attempt_number,
            'completed_at': attempt.completed_at
        }

    except Lesson.DoesNotExist:
        return False, "Lesson not found.", None
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course.", None
