from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from courses.services.progress_service import mark_lesson_completed
from courses.services.assignment_service import submit_assignment
from ..serializers import DynamicFieldSerializer

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_assignment_view(request, lesson_id):
    """
    Submit assignment for a lesson.
    Expected payload: {
        "submission_text": "...",
        "submission_file": <file>,
        "submission_url": "...",
        "github_repo": "...",
        "code_snippet": "..."
    }
    """
    submission_data = {
        'submission_text': request.data.get('submission_text', ''),
        'submission_file': request.FILES.get('submission_file'),
        'submission_url': request.data.get('submission_url', ''),
        'github_repo': request.data.get('github_repo', ''),
        'code_snippet': request.data.get('code_snippet', '')
    }
    
    success, message, submission = submit_assignment(request.user, lesson_id, submission_data)
    if success:
        serializer = DynamicFieldSerializer(submission, model_name="assignmentsubmission")
        return Response({
            "success": True,
            "message": message,
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            "success": False,
            "message": message
        }, status=status.HTTP_400_BAD_REQUEST)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_assignment_and_complete_view(request, lesson_id):
    """
    Submit assignment and mark lesson as completed.
    """
    # First submit the assignment
    submission_data = {
        'submission_text': request.data.get('submission_text', ''),
        'submission_file': request.FILES.get('submission_file'),
        'submission_url': request.data.get('submission_url', ''),
        'github_repo': request.data.get('github_repo', ''),
        'code_snippet': request.data.get('code_snippet', '')
    }
    
    success, message, submission = submit_assignment(request.user, lesson_id, submission_data)
    if not success:
        return Response({
            "success": False,
            "message": message
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Mark lesson as completed
    success, message = mark_lesson_completed(request.user, lesson_id)
    if success:
        serializer = DynamicFieldSerializer(submission, model_name="assignmentsubmission")
        return Response({
            "success": True,
            "message": "Assignment submitted and lesson marked as completed.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            "success": False,
            "message": f"Assignment submitted but failed to mark lesson complete: {message}"
        }, status=status.HTTP_400_BAD_REQUEST)



