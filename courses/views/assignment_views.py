from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count
from courses.services.progress_service import mark_lesson_completed
from courses.services.assignment_service import (
    submit_assignment, get_peer_review_assignment, submit_peer_review,
    grade_assignment, get_submission_with_peer_review, get_all_submissions_for_lesson
)
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
        "files": [<file1>, <file2>, ...],  # up to 5 files
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
    
    # Handle multiple file uploads (max 5)
    files = request.FILES.getlist('files')
    
    success, message, submission = submit_assignment(request.user, lesson_id, submission_data, files=files)
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
    
    files = request.FILES.getlist('files')
    
    success, message, submission = submit_assignment(request.user, lesson_id, submission_data, files=files)
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


# ============== PEER REVIEW ENDPOINTS ==============

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_peer_review_view(request, lesson_id):
    """
    Get the peer review assignment for the current student.
    Returns anonymized submission to review.
    Student must have submitted their own assignment first.
    """
    data, error = get_peer_review_assignment(request.user, lesson_id)
    
    if error:
        return Response({
            "success": False,
            "message": error
        }, status=status.HTTP_400_BAD_REQUEST)
    
    return Response({
        "success": True,
        "data": data
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_peer_review_view(request, peer_review_id):
    """
    Submit peer review evaluation.
    Expected payload: {
        "evaluations": [
            {
                "criterion_name": "Code Quality",
                "criterion_description": "...",
                "max_points": 10,
                "points_awarded": 8,
                "feedback": "Good work on..."
            },
            ...
        ]
    }
    """
    evaluations = request.data.get('evaluations', [])
    
    if not evaluations:
        return Response({
            "success": False,
            "message": "Evaluations are required."
        }, status=status.HTTP_400_BAD_REQUEST)
    
    success, message = submit_peer_review(request.user, peer_review_id, evaluations)
    
    if success:
        return Response({
            "success": True,
            "message": message
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            "success": False,
            "message": message
        }, status=status.HTTP_400_BAD_REQUEST)


# ============== TEACHER GRADING ENDPOINTS ==============

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_get_submissions_view(request, lesson_id):
    """
    Teacher: Get all submissions for a lesson with peer review scores.
    """
    data, error = get_all_submissions_for_lesson(request.user, lesson_id)
    
    if error:
        return Response({
            "success": False,
            "message": error
        }, status=status.HTTP_400_BAD_REQUEST)
    
    return Response({
        "success": True,
        "data": data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_get_submission_detail_view(request, submission_id):
    """
    Teacher: Get detailed submission with peer review data.
    """
    data, error = get_submission_with_peer_review(request.user, submission_id)
    
    if error:
        return Response({
            "success": False,
            "message": error
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Serialize the submission
    submission = data['submission']
    serializer = DynamicFieldSerializer(submission, model_name="assignmentsubmission")
    
    return Response({
        "success": True,
        "data": {
            "submission": serializer.data,
            "peer_review": data['peer_review'],
            "is_late": data['is_late'],
            "late_deduction": data['late_deduction'],
            "files": data['files']
        }
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def teacher_grade_submission_view(request, submission_id):
    """
    Teacher: Grade a student's submission.
    Expected payload: {
        "score": 85.0,
        "feedback": "Great work..."
    }
    """
    score = request.data.get('score')
    feedback = request.data.get('feedback', '')
    
    if score is None:
        return Response({
            "success": False,
            "message": "Score is required."
        }, status=status.HTTP_400_BAD_REQUEST)
    
    success, message, submission = grade_assignment(request.user, submission_id, score, feedback)
    
    if success:
        serializer = DynamicFieldSerializer(submission, model_name="assignmentsubmission")
        return Response({
            "success": True,
            "message": message,
            "data": serializer.data
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            "success": False,
            "message": message
        }, status=status.HTTP_400_BAD_REQUEST)
