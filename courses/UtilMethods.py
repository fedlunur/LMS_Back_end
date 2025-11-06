from django.http import JsonResponse
from rest_framework import status
from django.core.serializers import serialize
from rest_framework.response import Response
from django.utils import timezone 
from rest_framework.pagination import PageNumberPagination
from user_managment.models import User
from .models import (
    Enrollment, LessonProgress, Lesson, Module, Category, Level, Course,
    QuizAttempt, QuizResponse, QuizQuestion, QuizAnswer,
    AssignmentSubmission, ModuleProgress,
    FinalCourseAssessment, AssessmentAttempt, AssessmentResponse, AssessmentQuestion, AssessmentAnswer,
    Certificate
)


def success_response(self, data, message, status_code=status.HTTP_200_OK):
        return Response({
            'success': True,
            'data': data,  # Use 'data' instead of 'result'
            'message': message
        }, status=status_code)
def failure_response(self, message, status_code=status.HTTP_400_BAD_REQUEST):
        return Response({
            'success': False,
            'message': message
        }, status=status_code)        
        

class CustomPagination(PageNumberPagination):
    page_size = 10                      # default number of items per page
    page_size_query_param = 'page_size' # allow client to set page_size
    max_page_size = 100     
    

def handle_course_create_or_update(request, serializer_class, get_serializer):
    try:
        # Extract IDs from request
        instructor_id = request.data.get("instructor")
        category_id = request.data.get("category")
        level_id = request.data.get("level")
        course_id = request.data.get("id")  # optional for update

        if not instructor_id:
            return Response(
                {"success": False, "message": "Instructor ID is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Lookup related objects
        try:
            instructor = User.objects.get(pk=instructor_id)
            category = Category.objects.get(pk=category_id)
            level = Level.objects.get(pk=level_id)
        except User.DoesNotExist:
            return Response({"success": False, "message": "Instructor not found"}, status=status.HTTP_404_NOT_FOUND)
        except Category.DoesNotExist:
            return Response({"success": False, "message": "Category not found"}, status=status.HTTP_404_NOT_FOUND)
        except Level.DoesNotExist:
            return Response({"success": False, "message": "Level not found"}, status=status.HTTP_404_NOT_FOUND)

        # Handle status as object, default to 'draft'
        status_code = request.data.get("status", "draft")

        # Prepare save arguments
        save_kwargs = {
            "instructor": instructor,
            "category": category,
            "level": level,
            "status": status_code,
        }

        # Handle thumbnail file from FormData
        thumbnail = request.FILES.get("thumbnail")
        if thumbnail:
            save_kwargs["thumbnail"] = thumbnail

        # CREATE OR UPDATE COURSE
        if course_id:
            try:
                # Update existing course
                instance = Course.objects.get(id=course_id, instructor=instructor)
                serializer = serializer_class(instance, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                instance = serializer.save(**save_kwargs)
                message = "Course updated successfully"
            except Course.DoesNotExist:
                serializer = serializer_class(data=request.data)
                serializer.is_valid(raise_exception=True)
                instance = serializer.save(**save_kwargs)
                message = "Course created successfully"
        else:
            serializer = serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save(**save_kwargs)
            message = "Course created successfully"

        # Ensure instance is fully saved and ID is available
        instance.refresh_from_db()

        # Handle published status
        if status_code == "published":
            instance.submitted_for_approval_at = timezone.now()
            instance.save()
            message = "Course submitted for admin approval! You will be notified when reviewed."

        # Serialize response including course ID
        data = get_serializer(instance).data
        return Response({"success": True, "data": data, "message": message}, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response(
            {"success": False, "message": f"Failed to create or update course: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

def is_lesson_accessible(user, lesson):
    """
    Check if a lesson is accessible for the given user.
    A lesson is accessible if:
    - User is enrolled in the course
    - Module containing the lesson is accessible
    - It's the first lesson in the module, or the previous lesson in the same module is completed
    """
    if not user.is_authenticated:
        return False
    
    try:
        enrollment = Enrollment.objects.get(student=user, course=lesson.course)
    except Enrollment.DoesNotExist:
        return False
    
    # Check payment status
    if enrollment.payment_status != 'completed':
        return False
    
    # If lesson has a module, check if module is accessible
    if lesson.module:
        if not is_module_accessible(user, lesson.module):
            return False
        
        # First lesson in module is always accessible
        first_lesson_in_module = Lesson.objects.filter(
            module=lesson.module
        ).order_by('order').first()
        
        if lesson == first_lesson_in_module:
            return True
        
        # Find previous lesson in the same module
        previous_lesson = Lesson.objects.filter(
            module=lesson.module,
            order__lt=lesson.order
        ).order_by('-order').first()
        
        if not previous_lesson:
            return True  # Safeguard
        
        # Check if previous lesson is completed
        try:
            progress = LessonProgress.objects.get(enrollment=enrollment, lesson=previous_lesson)
            return progress.completed
        except LessonProgress.DoesNotExist:
            return False
    else:
        # Lesson without module - check course-level ordering
        first_lesson = Lesson.objects.filter(
            course=lesson.course,
            module__isnull=True
        ).order_by('order').first()
        
        if lesson == first_lesson:
            return True
        
        # Find previous lesson without module
        previous_lesson = Lesson.objects.filter(
            course=lesson.course,
            module__isnull=True,
            order__lt=lesson.order
        ).order_by('-order').first()
        
        if not previous_lesson:
            return True
        
        try:
            progress = LessonProgress.objects.get(enrollment=enrollment, lesson=previous_lesson)
            return progress.completed
        except LessonProgress.DoesNotExist:
            return False

def is_module_accessible(user, module):
    """
    Check if a module is accessible for the given user.
    A module is accessible if:
    - User is enrolled in the course
    - It's the first module, or all lessons in the previous module are completed
    """
    if not user.is_authenticated:
        return False
    
    try:
        enrollment = Enrollment.objects.get(student=user, course=module.course)
    except Enrollment.DoesNotExist:
        return False
    
    # Check payment status
    if enrollment.payment_status != 'completed':
        return False
    
    # First module is always accessible
    first_module = Module.objects.filter(course=module.course).order_by('order').first()
    if module == first_module:
        return True
    
    # Find previous module
    previous_module = Module.objects.filter(
        course=module.course,
        order__lt=module.order
    ).order_by('-order').first()
    
    if not previous_module:
        return True  # Safeguard
    
    # Check if all lessons in previous module are completed
    previous_lessons = Lesson.objects.filter(module=previous_module)
    if not previous_lessons.exists():
        return True  # Empty module, allow access
    
    for lesson in previous_lessons:
        try:
            progress = LessonProgress.objects.get(enrollment=enrollment, lesson=lesson)
            if not progress.completed:
                return False
        except LessonProgress.DoesNotExist:
            return False
    return True

def enroll_user_in_course(user, course):
    """
    Handle user enrollment in a course.
    For free courses: enroll immediately with payment_status='completed'.
    For paid courses: require payment (future implementation), set payment_status='pending'.
    """
    if course.price > 0:
        # Future: Check payment status
        # For now, create enrollment with pending payment
        enrollment, created = Enrollment.objects.get_or_create(
            student=user,
            course=course,
            defaults={
                'progress': 0.0,
                'payment_status': 'pending'
            }
        )
        if not created:
            return False, "Enrollment already exists."
        return False, "Payment required for this course. Enrollment created with pending payment status."
    
    # Free course: enroll immediately
    if Enrollment.objects.filter(student=user, course=course).exists():
        return False, "Already enrolled in this course."
    
    enrollment = Enrollment.objects.create(
        student=user,
        course=course,
        progress=0.0,
        payment_status='completed',
        is_enrolled=True
    )
    enrollment.calculate_progress()
    # Unlock first module
    enrollment.unlock_first_module()
    return True, "Successfully enrolled in the course."

def complete_payment(enrollment_id):
    """
    Mark payment as completed for an enrollment.
    This function can be called from payment webhooks or admin actions in the future.
    """
    try:
        enrollment = Enrollment.objects.get(id=enrollment_id)
        if enrollment.payment_status == 'completed':
            return False, "Payment already completed."
        
        enrollment.payment_status = 'completed'
        enrollment.save()
        enrollment.calculate_progress()
        return True, "Payment completed successfully. Enrollment is now active."
    except Enrollment.DoesNotExist:
        return False, "Enrollment not found."

def mark_lesson_completed(user, lesson_id):
    """
    Mark a lesson as completed for the user.
    Updates lesson progress and cascades to enrollment and module progress.
    Also unlocks next lesson if available.
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        enrollment = Enrollment.objects.get(student=user, course=lesson.course)
        
        if enrollment.payment_status != 'completed':
            return False, "Payment not completed for this course."
        
        # Check if lesson is accessible
        if not is_lesson_accessible(user, lesson):
            return False, "Lesson is not accessible yet."
        
        # Get or create lesson progress
        progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson,
            defaults={'progress': 0.0}
        )
        
        # Mark as completed
        progress.mark_completed(100.0)
        
        # Update module progress if lesson has a module
        if lesson.module:
            module_progress, _ = ModuleProgress.objects.get_or_create(
                enrollment=enrollment,
                module=lesson.module
            )
            module_progress.calculate_progress()
            
            # If module is completed, unlock next module
            if module_progress.completed:
                next_module = Module.objects.filter(
                    course=lesson.course,
                    order__gt=lesson.module.order
                ).order_by('order').first()
                
                if next_module:
                    ModuleProgress.objects.get_or_create(
                        enrollment=enrollment,
                        module=next_module,
                        defaults={'progress': 0.0, 'completed': False}
                    )
        
        # Determine next lesson to unlock info
        next_lesson = None
        if lesson.module:
            # Next lesson in same module
            next_lesson = Lesson.objects.filter(
                module=lesson.module,
                order__gt=lesson.order
            ).order_by('order').first()
            # If none, first lesson of next module
            if not next_lesson:
                next_module = Module.objects.filter(
                    course=lesson.course,
                    order__gt=lesson.module.order
                ).order_by('order').first()
                if next_module:
                    next_lesson = Lesson.objects.filter(module=next_module).order_by('order').first()
        else:
            # Lessons without module: next by order within course
            next_lesson = Lesson.objects.filter(
                course=lesson.course,
                module__isnull=True,
                order__gt=lesson.order
            ).order_by('order').first()

        return True, "Lesson marked as completed successfully.", (next_lesson.id if next_lesson else None)
    
    except Lesson.DoesNotExist:
        return False, "Lesson not found."
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course."


def evaluate_question_answer(question, response_data):
    """
    Evaluate a student's answer for a question.
    Returns: (is_correct, points_earned)
    """
    answer_id = response_data.get('answer_id')
    answer_text = response_data.get('answer_text', '').strip()
    drag_drop_response = response_data.get('drag_drop_response', {})
    
    is_correct = False
    points_earned = 0.0
    
    if question.question_type in ['multiple-choice', 'true-false']:
        if answer_id:
            try:
                answer = QuizAnswer.objects.get(id=answer_id, question=question)
                is_correct = answer.is_correct
                if is_correct:
                    points_earned = question.points
            except QuizAnswer.DoesNotExist:
                pass
    
    elif question.question_type == 'fill-blank':
        # Check against blanks (case-insensitive)
        if answer_text:
            correct_answers = [b.lower().strip() for b in question.blanks] if question.blanks else []
            if answer_text.lower().strip() in correct_answers:
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
    
    return is_correct, points_earned


def submit_quiz(user, lesson_id, responses, start_time=None):
    """
    Submit quiz answers for a lesson.
    responses: list of dicts with 'question_id', and optionally:
        - 'answer_id' (for multiple-choice/true-false)
        - 'answer_text' (for fill-blank)
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
                
                # Create or update response
                QuizResponse.objects.update_or_create(
                    attempt=attempt,
                    question=question,
                    defaults={
                        'answer_id': response_data.get('answer_id'),
                        'answer_text': response_data.get('answer_text', ''),
                        'drag_drop_response': response_data.get('drag_drop_response', {}),
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


def submit_assignment(user, lesson_id, submission_data):
    """
    Submit assignment for a lesson.
    submission_data: dict with 'submission_text', 'submission_file', 'submission_url', 'github_repo'
    Returns: (success, message, submission)
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        enrollment = Enrollment.objects.get(student=user, course=lesson.course)
        
        if enrollment.payment_status != 'completed':
            return False, "Payment not completed for this course.", None
        
        if lesson.content_type != Lesson.ContentType.ASSIGNMENT:
            return False, "This lesson is not an assignment.", None
        
        assignment_lesson = getattr(lesson, 'assignment', None)
        if not assignment_lesson:
            return False, "Assignment configuration not found.", None
        
        # Check attempt number
        existing_submissions = AssignmentSubmission.objects.filter(
            student=user,
            lesson=lesson
        ).count()
        
        max_attempts = assignment_lesson.max_attempts
        if existing_submissions >= max_attempts:
            return False, f"Maximum attempts ({max_attempts}) reached for this assignment.", None
        
        # Create submission
        submission = AssignmentSubmission.objects.create(
            student=user,
            lesson=lesson,
            enrollment=enrollment,
            submission_text=submission_data.get('submission_text', ''),
            submission_file=submission_data.get('submission_file'),
            submission_url=submission_data.get('submission_url', ''),
            github_repo=submission_data.get('github_repo', ''),
            status='submitted',
            submitted_at=timezone.now(),
            attempt_number=existing_submissions + 1,
            max_score=assignment_lesson.max_score
        )
        
        return True, "Assignment submitted successfully.", submission
    
    except Lesson.DoesNotExist:
        return False, "Lesson not found.", None
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course.", None


def can_take_final_assessment(user, course_id):
    """
    Check if user can take final assessment (all lessons and modules completed)
    """
    try:
        enrollment = Enrollment.objects.get(student=user, course_id=course_id)
        
        if enrollment.payment_status != 'completed':
            return False, "Payment not completed."
        
        # Check if all lessons are completed
        total_lessons = Lesson.objects.filter(course_id=course_id).count()
        completed_lessons = LessonProgress.objects.filter(
            enrollment=enrollment,
            completed=True
        ).count()
        
        if completed_lessons < total_lessons:
            return False, "Please complete all lessons before taking the final assessment."
        
        return True, "Eligible for final assessment."
    
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course."


def submit_final_assessment(user, course_id, responses):
    """
    Submit final course assessment.
    responses: list of dicts with 'question_id', 'answer_id' (optional), 'answer_text' (optional)
    Returns: (success, message, attempt_data)
    """
    try:
        enrollment = Enrollment.objects.get(student=user, course_id=course_id)
        
        if enrollment.payment_status != 'completed':
            return False, "Payment not completed for this course.", None
        
        # Check eligibility
        can_take, message = can_take_final_assessment(user, course_id)
        if not can_take:
            return False, message, None
        
        # Get assessment
        assessment = getattr(enrollment.course, 'final_assessment', None)
        if not assessment:
            return False, "Final assessment not found for this course.", None
        
        if not assessment.is_active:
            return False, "Final assessment is not active.", None
        
        # Check attempts
        existing_attempts = AssessmentAttempt.objects.filter(
            student=user,
            assessment=assessment
        ).count()
        
        if existing_attempts >= assessment.max_attempts:
            return False, f"Maximum attempts ({assessment.max_attempts}) reached.", None
        
        # Create attempt
        attempt = AssessmentAttempt.objects.create(
            student=user,
            assessment=assessment,
            enrollment=enrollment,
            total_questions=len(responses),
            correct_answers=0,
            attempt_number=existing_attempts + 1
        )
        
        total_points = 0.0
        earned_points = 0.0
        
        # Process responses
        for response_data in responses:
            question_id = response_data.get('question_id')
            answer_id = response_data.get('answer_id')
            answer_text = response_data.get('answer_text', '')
            
            try:
                question = AssessmentQuestion.objects.get(id=question_id, assessment=assessment)
                total_points += question.points
                
                is_correct = False
                points_earned = 0.0
                
                if question.question_type in ['multiple-choice', 'true-false']:
                    if answer_id:
                        answer = AssessmentAnswer.objects.get(id=answer_id, question=question)
                        is_correct = answer.is_correct
                        if is_correct:
                            points_earned = question.points
                            attempt.correct_answers += 1
                elif question.question_type == 'fill-blank':
                    if answer_text and answer_text.lower().strip() in [b.lower().strip() for b in question.blanks]:
                        is_correct = True
                        points_earned = question.points
                        attempt.correct_answers += 1
                
                # Create response
                AssessmentResponse.objects.create(
                    attempt=attempt,
                    question=question,
                    answer_id=answer_id if answer_id else None,
                    answer_text=answer_text,
                    is_correct=is_correct,
                    points_earned=points_earned
                )
                
                earned_points += points_earned
                
            except AssessmentQuestion.DoesNotExist:
                continue
            except AssessmentAnswer.DoesNotExist:
                continue
        
        # Calculate score
        attempt.total_points = total_points
        attempt.earned_points = earned_points
        attempt.calculate_score()
        
        # Issue certificate if passed
        if attempt.passed and enrollment.course.issue_certificate:
            Certificate.objects.get_or_create(
                enrollment=enrollment,
                defaults={'grade': 'A' if attempt.score >= 90 else 'B' if attempt.score >= 80 else 'C'}
            )
        
        return True, "Assessment submitted successfully.", {
            'score': attempt.score,
            'passed': attempt.passed,
            'correct_answers': attempt.correct_answers,
            'total_questions': attempt.total_questions,
            'attempt_number': attempt.attempt_number
        }
    
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course.", None


