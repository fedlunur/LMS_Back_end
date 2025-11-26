from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count
from courses.services.progress_service import mark_lesson_completed
from courses.services.assignment_service import submit_assignment
from ..serializers import DynamicFieldSerializer
from ..models import AssignmentSubmission, Lesson

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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_assignment_history_view(request):
    """
    Get student's assignment submission history and counts.
    Optional query params:
        - lesson_id: Filter by specific lesson
        - course_id: Filter by specific course
    """
    user = request.user
    lesson_id = request.query_params.get('lesson_id')
    course_id = request.query_params.get('course_id')
    
    submissions = AssignmentSubmission.objects.filter(student=user).select_related('lesson', 'lesson__course')
    
    if lesson_id:
        submissions = submissions.filter(lesson_id=lesson_id)
    if course_id:
        submissions = submissions.filter(lesson__course_id=course_id)
    
    # Get counts by status
    status_counts = submissions.values('status').annotate(count=Count('id'))
    status_summary = {item['status']: item['count'] for item in status_counts}
    
    # Serialize submissions
    serializer = DynamicFieldSerializer(submissions.order_by('-submitted_at'), many=True, model_name="assignmentsubmission")
    
    return Response({
        "success": True,
        "data": {
            "total_submissions": submissions.count(),
            "status_summary": status_summary,
            "submissions": serializer.data
        }
    }, status=status.HTTP_200_OK)
