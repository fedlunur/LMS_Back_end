from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from courses.models import Enrollment
from ..UtilMethods import can_take_final_assessment, submit_final_assessment
from ..serializers import DynamicFieldSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_final_assessment_view(request, course_id):
    """
    Get final assessment for a course (with randomized questions if enabled).
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
                "message": message
            }, status=status.HTTP_400_BAD_REQUEST)
        
        assessment = getattr(enrollment.course, 'final_assessment', None)
        if not assessment:
            return Response({
                "success": False,
                "message": "Final assessment not found for this course."
            }, status=status.HTTP_404_NOT_FOUND)
        
        if not assessment.is_active:
            return Response({
                "success": False,
                "message": "Final assessment is not active."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get questions
        questions = assessment.questions.all()
        
        # Randomize if enabled
        if assessment.randomize_questions:
            questions = questions.order_by('?')
        
        question_serializer = DynamicFieldSerializer(questions, many=True, model_name="assessmentquestion")
        
        return Response({
            "success": True,
            "data": {
                "assessment": {
                    "id": assessment.id,
                    "title": assessment.title,
                    "description": assessment.description,
                    "time_limit": assessment.time_limit,
                    "max_attempts": assessment.max_attempts,
                    "show_correct_answers": assessment.show_correct_answers
                },
                "questions": question_serializer.data
            },
            "message": "Final assessment retrieved successfully."
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

