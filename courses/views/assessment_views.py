from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from courses.models import Enrollment, FinalCourseAssessment, AssessmentAttempt
from courses.services.assessment_service import (
    can_take_final_assessment, 
    submit_final_assessment,
    get_final_assessment_status,
    get_course_structure_with_assessment
)
from ..serializers import DynamicFieldSerializer


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
        
        # Get questions
        questions = assessment.questions.all()
        
        # Randomize if enabled
        if assessment.randomize_questions:
            questions = questions.order_by('?')
        
        question_serializer = DynamicFieldSerializer(questions, many=True, model_name="assessmentquestion")
        
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
                    "total_questions": questions.count()
                },
                "questions": question_serializer.data,
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
