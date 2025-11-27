from django.db import transaction
from courses.models import (
    AssessmentAnswer, AssessmentAttempt, AssessmentQuestion, AssessmentResponse, 
    Certificate, Enrollment, Lesson, LessonProgress, FinalCourseAssessment,
    Module, ModuleProgress
)


def can_take_final_assessment(user, course_id):
    """
    Check if user can take final assessment.
    Requirements:
    - Must be enrolled with completed payment
    - Must complete ALL lessons in ALL modules
    - Course must require final assessment
    """
    try:
        enrollment = Enrollment.objects.get(student=user, course_id=course_id)
        
        if enrollment.payment_status != 'completed':
            return False, "Payment not completed."
        
        # Check if course requires final assessment
        course = enrollment.course
        if not course.requires_final_assessment:
            return False, "This course does not require a final assessment."
        
        # Check if final assessment exists
        if not hasattr(course, 'final_assessment'):
            return False, "Final assessment has not been created yet."
        
        # Check if all lessons are completed
        total_lessons = Lesson.objects.filter(course_id=course_id).count()
        completed_lessons = LessonProgress.objects.filter(
            enrollment=enrollment,
            completed=True
        ).count()
        
        if completed_lessons < total_lessons:
            remaining = total_lessons - completed_lessons
            return False, f"Please complete all lessons before taking the final assessment. {remaining} lesson(s) remaining."
        
        return True, "Eligible for final assessment."
    
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course."


def get_final_assessment_status(user, course_id):
    """
    Get the status of final assessment for a student.
    Returns info about eligibility, attempts, and best score.
    """
    try:
        enrollment = Enrollment.objects.get(student=user, course_id=course_id)
        course = enrollment.course
        
        if not course.requires_final_assessment:
            return {
                'required': False,
                'message': 'This course does not require a final assessment.'
            }
        
        assessment = getattr(course, 'final_assessment', None)
        if not assessment:
            return {
                'required': True,
                'available': False,
                'message': 'Final assessment has not been created yet.'
            }
        
        # Check eligibility
        can_take, eligibility_message = can_take_final_assessment(user, course_id)
        
        # Get attempt history
        attempts = AssessmentAttempt.objects.filter(
            student=user,
            assessment=assessment
        ).order_by('-completed_at')
        
        best_attempt = attempts.order_by('-score').first()
        has_passed = attempts.filter(passed=True).exists()
        
        return {
            'required': True,
            'available': assessment.is_active,
            'can_take': can_take,
            'eligibility_message': eligibility_message,
            'assessment': {
                'id': assessment.id,
                'title': assessment.title,
                'description': assessment.description,
                'passing_score': assessment.passing_score,
                'time_limit': assessment.time_limit,
                'unlimited_attempts': assessment.has_unlimited_attempts,
                'max_attempts': assessment.max_attempts if not assessment.has_unlimited_attempts else None,
            },
            'attempts_count': attempts.count(),
            'has_passed': has_passed,
            'best_score': best_attempt.score if best_attempt else None,
            'last_attempt': {
                'score': attempts.first().score,
                'passed': attempts.first().passed,
                'completed_at': attempts.first().completed_at
            } if attempts.exists() else None
        }
    
    except Enrollment.DoesNotExist:
        return {
            'required': False,
            'message': 'You are not enrolled in this course.'
        }


def submit_final_assessment(user, course_id, responses):
    """
    Submit final course assessment.
    responses: list of dicts with 'question_id', 'answer_id' (optional), 'answer_text' (optional)
    Returns: (success, message, attempt_data)
    
    No attempt limit - students can retake until they pass.
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
        
        # Check attempts only if max_attempts > 0 (0 = unlimited)
        existing_attempts = AssessmentAttempt.objects.filter(
            student=user,
            assessment=assessment
        ).count()
        
        if assessment.max_attempts > 0 and existing_attempts >= assessment.max_attempts:
            return False, f"Maximum attempts ({assessment.max_attempts}) reached.", None
        
        with transaction.atomic():
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
            
            # Issue certificate if passed and course issues certificates
            if attempt.passed and enrollment.course.issue_certificate:
                Certificate.objects.get_or_create(
                    enrollment=enrollment,
                    defaults={'grade': 'A' if attempt.score >= 90 else 'B' if attempt.score >= 80 else 'C'}
                )
        
        # Prepare enriched payload including certificate and student details if available
        cert = getattr(enrollment, 'certificate', None)
        student = enrollment.student
        course = enrollment.course

        payload = {
            'score': attempt.score,
            'passed': attempt.passed,
            'correct_answers': attempt.correct_answers,
            'total_questions': attempt.total_questions,
            'attempt_number': attempt.attempt_number,
            'enrollment_id': enrollment.id,
            'can_retake': True,  # Always can retake (unlimited attempts)
            'student': {
                'id': student.id,
                'name': student.get_full_name(),
                'email': student.email,
            },
            'course': {
                'id': course.id,
                'title': course.title,
            },
        }
        if cert:
            payload['certificate'] = {
                'certificate_number': cert.certificate_number,
                'issued_date': cert.issued_date,
                'grade': cert.grade,
            }

        return True, "Assessment submitted successfully.", payload
    
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course.", None


def get_course_structure_with_assessment(user, course_id):
    """
    Get course structure with modules, lessons, and final assessment at the bottom.
    Used for displaying the course content with final assessment as last item.
    """
    try:
        enrollment = Enrollment.objects.get(student=user, course_id=course_id)
        course = enrollment.course
        
        # Get modules with lessons
        modules = Module.objects.filter(course=course).order_by('order').prefetch_related('lessons')
        
        modules_data = []
        for module in modules:
            lessons = module.lessons.all().order_by('order')
            
            # Get progress for each lesson
            lessons_data = []
            for lesson in lessons:
                progress = LessonProgress.objects.filter(
                    enrollment=enrollment,
                    lesson=lesson
                ).first()
                
                lessons_data.append({
                    'id': lesson.id,
                    'title': lesson.title,
                    'content_type': lesson.content_type,
                    'order': lesson.order,
                    'completed': progress.completed if progress else False,
                    'progress': float(progress.progress) if progress else 0
                })
            
            # Get module progress
            module_progress = ModuleProgress.objects.filter(
                enrollment=enrollment,
                module=module
            ).first()
            
            modules_data.append({
                'id': module.id,
                'title': module.title,
                'description': module.description,
                'order': module.order,
                'lessons': lessons_data,
                'completed': module_progress.completed if module_progress else False,
                'progress': module_progress.progress if module_progress else 0
            })
        
        # Add final assessment info if required
        final_assessment_data = None
        if course.requires_final_assessment:
            assessment_status = get_final_assessment_status(user, course_id)
            final_assessment_data = assessment_status
        
        return {
            'course': {
                'id': course.id,
                'title': course.title,
                'requires_final_assessment': course.requires_final_assessment
            },
            'modules': modules_data,
            'final_assessment': final_assessment_data,
            'overall_progress': float(enrollment.progress),
            'is_completed': enrollment.is_completed
        }
    
    except Enrollment.DoesNotExist:
        return None
