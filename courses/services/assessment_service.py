

from courses.models import AssessmentAnswer, AssessmentAttempt, AssessmentQuestion, AssessmentResponse, Certificate, Enrollment, Lesson, LessonProgress


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

