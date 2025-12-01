from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from courses.models import (
    Enrollment, FinalCourseAssessment, AssessmentAttempt, 
    AssessmentQuestion, AssessmentResponse
)
from courses.services.assessment_service import (
    can_take_final_assessment, 
    submit_final_assessment,
    get_final_assessment_status,
    get_course_structure_with_assessment
)
from ..serializers import DynamicFieldSerializer


def format_assessment_questions(questions):
    """
    Format assessment questions like quiz questions for frontend consistency.
    Returns questions with answers formatted properly per question type.
    """
    question_data = []
    for q in questions:
        q_data = {
            'id': q.id,
            'question_type': q.question_type,
            'question_text': q.question_text,
            'question_image': q.question_image.url if q.question_image else None,
            'explanation': q.explanation,
            'points': q.points,
            'order': q.order,
        }
        
        # Structure per question type (like quiz)
        if q.question_type in ['multiple-choice', 'true-false']:
            # Include answers without is_correct flag
            q_data['answers'] = [
                {
                    'id': ans.id, 
                    'answer_text': ans.answer_text,
                    'answer_image': ans.answer_image.url if ans.answer_image else None,
                    'order': ans.order
                } 
                for ans in q.answers.all().order_by('order')
            ]
        
        elif q.question_type == 'fill-blank':
            # For fill-blank, indicate number of blanks without revealing answers
            blanks_count = len(q.blanks) if q.blanks else 1
            q_data['blanks_count'] = blanks_count
            q_data['blanks'] = []  # Empty - don't expose correct answers
        
        elif q.question_type == 'short-answer':
            q_data['blanks_count'] = 1
        
        question_data.append(q_data)
    
    return question_data


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_final_assessment_view(request, course_id):
    """
    Start the final assessment - validates eligibility and returns questions.
    This is the "Start Final Course Assessment" button endpoint.
    """
    try:
        enrollment = Enrollment.objects.get(student=request.user, course_id=course_id)
        
        if enrollment.payment_status != 'completed':
            return Response({
                "success": False,
                "message": "Payment not completed for this course."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check eligibility
        can_take, message = can_take_final_assessment(request.user, course_id)
        if not can_take:
            return Response({
                "success": False,
                "message": message,
                "can_start": False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        assessment = getattr(enrollment.course, 'final_assessment', None)
        if not assessment:
            return Response({
                "success": False,
                "message": "Final assessment not found for this course.",
                "can_start": False
            }, status=status.HTTP_404_NOT_FOUND)
        
        if not assessment.is_active:
            return Response({
                "success": False,
                "message": "Final assessment is not active.",
                "can_start": False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get attempt count
        attempt_count = AssessmentAttempt.objects.filter(
            student=request.user,
            assessment=assessment
        ).count()
        
        # Get questions with prefetch for answers
        questions = assessment.questions.prefetch_related('answers').all()
        
        # Randomize if enabled
        if assessment.randomize_questions:
            questions = list(questions)
            import random
            random.shuffle(questions)
        
        # Format questions like quiz format
        question_data = format_assessment_questions(questions)
        
        # Calculate end time based on time limit
        start_time = timezone.now()
        end_time = None
        if assessment.time_limit:
            from datetime import timedelta
            end_time = start_time + timedelta(minutes=assessment.time_limit)
        
        return Response({
            "success": True,
            "can_start": True,
            "data": {
                "assessment": {
                    "id": assessment.id,
                    "title": assessment.title,
                    "description": assessment.description,
                    "time_limit": assessment.time_limit,
                    "passing_score": assessment.passing_score,
                    "unlimited_attempts": assessment.has_unlimited_attempts,
                    "max_attempts": assessment.max_attempts if not assessment.has_unlimited_attempts else None,
                    "show_correct_answers": assessment.show_correct_answers,
                    "total_questions": len(question_data)
                },
                "questions": question_data,
                "attempt_number": attempt_count + 1,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat() if end_time else None
            },
            "message": "Final assessment started successfully."
        }, status=status.HTTP_200_OK)
    
    except Enrollment.DoesNotExist:
        return Response({
            "success": False,
            "message": "You are not enrolled in this course.",
            "can_start": False
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_final_assessment_view(request, course_id):
    """
    Get final assessment info for a course (without starting it).
    Use start_final_assessment_view to actually start the assessment.
    """
    try:
        enrollment = Enrollment.objects.get(student=request.user, course_id=course_id)
        
        if enrollment.payment_status != 'completed':
            return Response({
                "success": False,
                "message": "Payment not completed for this course."
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check eligibility
        can_take, message = can_take_final_assessment(request.user, course_id)
        
        assessment = getattr(enrollment.course, 'final_assessment', None)
        if not assessment:
            return Response({
                "success": False,
                "message": "Final assessment not found for this course."
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get attempt count and history
        attempts = AssessmentAttempt.objects.filter(
            student=request.user,
            assessment=assessment
        ).order_by('-completed_at')
        
        attempt_count = attempts.count()
        has_passed = attempts.filter(passed=True).exists()
        best_attempt = attempts.order_by('-score').first()
        
        return Response({
            "success": True,
            "data": {
                "assessment": {
                    "id": assessment.id,
                    "title": assessment.title,
                    "description": assessment.description,
                    "time_limit": assessment.time_limit,
                    "passing_score": assessment.passing_score,
                    "unlimited_attempts": assessment.has_unlimited_attempts,
                    "max_attempts": assessment.max_attempts if not assessment.has_unlimited_attempts else None,
                    "show_correct_answers": assessment.show_correct_answers,
                    "is_active": assessment.is_active,
                    "total_questions": assessment.questions.count()
                },
                "can_start": can_take,
                "eligibility_message": message,
                "attempts_count": attempt_count,
                "has_passed": has_passed,
                "best_score": best_attempt.score if best_attempt else None,
                "last_attempt": {
                    "score": attempts.first().score,
                    "passed": attempts.first().passed,
                    "completed_at": attempts.first().completed_at
                } if attempts.exists() else None
            },
            "message": "Final assessment info retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    except Enrollment.DoesNotExist:
        return Response({
            "success": False,
            "message": "You are not enrolled in this course."
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_final_assessment_view(request, course_id):
    """
    Submit final course assessment.
    Expected payload: {"responses": [{"question_id": 1, "answer_id": 2}, ...]}
    
    No attempt limit - students can retake until they pass.
    """
    responses = request.data.get('responses', [])
    if not responses:
        return Response({
            "success": False,
            "message": "Responses are required."
        }, status=status.HTTP_400_BAD_REQUEST)
    
    success, message, attempt_data = submit_final_assessment(request.user, course_id, responses)
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
def get_final_assessment_status_view(request, course_id):
    """
    Get the status of final assessment for the current student.
    Returns eligibility, attempts history, and best score.
    """
    try:
        enrollment = Enrollment.objects.get(student=request.user, course_id=course_id)
        
        if enrollment.payment_status != 'completed':
            return Response({
                "success": False,
                "message": "Payment not completed for this course."
            }, status=status.HTTP_403_FORBIDDEN)
        
        status_data = get_final_assessment_status(request.user, course_id)
        
        return Response({
            "success": True,
            "data": status_data
        }, status=status.HTTP_200_OK)
    
    except Enrollment.DoesNotExist:
        return Response({
            "success": False,
            "message": "You are not enrolled in this course."
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_course_structure_view(request, course_id):
    """
    Get full course structure with modules, lessons, and final assessment at the bottom.
    Final assessment appears as the last item after all modules.
    """
    try:
        enrollment = Enrollment.objects.get(student=request.user, course_id=course_id)
        
        if enrollment.payment_status != 'completed':
            return Response({
                "success": False,
                "message": "Payment not completed for this course."
            }, status=status.HTTP_403_FORBIDDEN)
        
        structure = get_course_structure_with_assessment(request.user, course_id)
        
        if not structure:
            return Response({
                "success": False,
                "message": "Could not retrieve course structure."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            "success": True,
            "data": structure
        }, status=status.HTTP_200_OK)
    
    except Enrollment.DoesNotExist:
        return Response({
            "success": False,
            "message": "You are not enrolled in this course."
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_assessment_attempts_view(request, course_id):
    """
    Get all assessment attempts for a student in a course.
    """
    try:
        enrollment = Enrollment.objects.get(student=request.user, course_id=course_id)
        
        assessment = getattr(enrollment.course, 'final_assessment', None)
        if not assessment:
            return Response({
                "success": False,
                "message": "Final assessment not found for this course."
            }, status=status.HTTP_404_NOT_FOUND)
        
        attempts = AssessmentAttempt.objects.filter(
            student=request.user,
            assessment=assessment
        ).order_by('-completed_at')
        
        attempts_data = []
        for attempt in attempts:
            attempts_data.append({
                'id': attempt.id,
                'attempt_number': attempt.attempt_number,
                'score': attempt.score,
                'passed': attempt.passed,
                'correct_answers': attempt.correct_answers,
                'total_questions': attempt.total_questions,
                'completed_at': attempt.completed_at,
                'time_taken': str(attempt.time_taken) if attempt.time_taken else None
            })
        
        return Response({
            "success": True,
            "data": {
                "assessment": {
                    "id": assessment.id,
                    "title": assessment.title,
                    "passing_score": assessment.passing_score
                },
                "attempts": attempts_data,
                "total_attempts": len(attempts_data),
                "has_passed": any(a['passed'] for a in attempts_data),
                "best_score": max((a['score'] for a in attempts_data), default=0)
            }
        }, status=status.HTTP_200_OK)
    
    except Enrollment.DoesNotExist:
        return Response({
            "success": False,
            "message": "You are not enrolled in this course."
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_assessment_results_view(request, course_id):
    """
    Get assessment results for the latest attempt (with correct answers if enabled).
    Similar to quiz results view.
    """
    try:
        enrollment = Enrollment.objects.get(student=request.user, course_id=course_id)
        
        assessment = getattr(enrollment.course, 'final_assessment', None)
        if not assessment:
            return Response({
                "success": False,
                "message": "Final assessment not found for this course."
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get latest attempt
        attempt = AssessmentAttempt.objects.filter(
            student=request.user,
            assessment=assessment
        ).order_by('-completed_at').first()
        
        if not attempt:
            return Response({
                "success": True,
                "data": {
                    "has_attempt": False,
                    "message": "You haven't taken this assessment yet."
                },
                "message": "No attempts yet."
            }, status=status.HTTP_200_OK)
        
        # Get responses with questions and answers
        responses = AssessmentResponse.objects.filter(
            attempt=attempt
        ).select_related('question', 'answer')
        
        result_data = {
            "has_attempt": True,
            "attempt": {
                "id": attempt.id,
                "score": attempt.score,
                "correct_answers": attempt.correct_answers,
                "total_questions": attempt.total_questions,
                "earned_points": attempt.earned_points,
                "total_points": attempt.total_points,
                "passed": attempt.passed,
                "attempt_number": attempt.attempt_number,
                "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None
            }
        }
        
        return Response({
            "success": True,
            "data": result_data,
            "message": "Assessment results retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    except Enrollment.DoesNotExist:
        return Response({
            "success": False,
            "message": "You are not enrolled in this course."
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_get_assessment_questions_view(request, course_id):
    """
    Teacher: Get all assessment questions with correct answers for editing.
    """
    try:
        from courses.models import Course
        course = Course.objects.get(id=course_id)
        
        # Check if user is the instructor
        if course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view this assessment."
            }, status=status.HTTP_403_FORBIDDEN)
        
        assessment = getattr(course, 'final_assessment', None)
        if not assessment:
            return Response({
                "success": False,
                "message": "Final assessment not found for this course."
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get questions with answers (including correct answers)
        questions = assessment.questions.prefetch_related('answers').all().order_by('order')
        
        questions_data = []
        for q in questions:
            q_data = {
                'id': q.id,
                'question_type': q.question_type,
                'question_text': q.question_text,
                'question_image': q.question_image.url if q.question_image else None,
                'explanation': q.explanation,
                'points': q.points,
                'order': q.order,
                'blanks': q.blanks,
                'created_at': q.created_at.isoformat() if q.created_at else None,
                'updated_at': q.updated_at.isoformat() if q.updated_at else None,
            }
            
            # Include all answers with is_correct flag (for teacher)
            if q.question_type in ['multiple-choice', 'true-false']:
                q_data['answers'] = [
                    {
                        'id': ans.id,
                        'answer_text': ans.answer_text,
                        'answer_image': ans.answer_image.url if ans.answer_image else None,
                        'is_correct': ans.is_correct,
                        'order': ans.order
                    }
                    for ans in q.answers.all().order_by('order')
                ]
            
            questions_data.append(q_data)
        
        return Response({
            "success": True,
            "data": {
                "assessment": {
                    "id": assessment.id,
                    "title": assessment.title,
                    "description": assessment.description,
                    "passing_score": assessment.passing_score,
                    "time_limit": assessment.time_limit,
                    "max_attempts": assessment.max_attempts,
                    "randomize_questions": assessment.randomize_questions,
                    "show_correct_answers": assessment.show_correct_answers,
                    "is_active": assessment.is_active
                },
                "questions": questions_data,
                "total_questions": len(questions_data),
                "total_points": sum(q['points'] for q in questions_data)
            },
            "message": "Assessment questions retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response({
            "success": False,
            "message": "Course not found."
        }, status=status.HTTP_404_NOT_FOUND)
