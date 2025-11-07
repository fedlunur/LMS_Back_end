from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from courses.models import Course, Enrollment, Lesson, LessonProgress, Module, ModuleProgress, QuizAttempt, AssignmentSubmission
from rest_framework.response import Response
from rest_framework import status
from courses.serializers import DynamicFieldSerializer
from django.utils import timezone

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_student_attempts_view(request, lesson_id):
    """
    Get all student attempts for a quiz (for teachers).
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        
        # Check authorization
        if lesson.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view student attempts for this quiz."
            }, status=status.HTTP_403_FORBIDDEN)
        
        if lesson.content_type != Lesson.ContentType.QUIZ:
            return Response({
                "success": False,
                "message": "This lesson is not a quiz."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        attempts = QuizAttempt.objects.filter(
            lesson=lesson,
            is_in_progress=False
        ).select_related('student').order_by('-completed_at')
        
        attempt_data = []
        for attempt in attempts:
            attempt_dict = DynamicFieldSerializer(attempt, model_name="quizattempt").data
            attempt_dict['student'] = {
                'id': attempt.student.id,
                'email': attempt.student.email,
                'name': attempt.student.get_full_name()
            }
            attempt_data.append(attempt_dict)
        
        return Response({
            "success": True,
            "data": attempt_data,
            "message": "Student attempts retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    except Lesson.DoesNotExist:
        return Response({
            "success": False,
            "message": "Lesson not found."
        }, status=status.HTTP_404_NOT_FOUND)




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_course_students_view(request, course_id):
    """Get all students enrolled in a course (for instructors)."""
    try:
        course = Course.objects.get(id=course_id)
        if course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view students for this course."
            }, status=status.HTTP_403_FORBIDDEN)
        
        enrollments = Enrollment.objects.filter(
            course=course,
            payment_status='completed'
        ).select_related('student')
        
        serializer = DynamicFieldSerializer(enrollments, many=True, model_name="enrollment")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Course students retrieved successfully."
        }, status=status.HTTP_200_OK)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_student_progress_view(request, course_id, student_id):
    """Get detailed progress for a specific student in a course (for instructors)."""
    try:
        course = Course.objects.get(id=course_id)
        if course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view this student's progress."
            }, status=status.HTTP_403_FORBIDDEN)
        
        from user_managment.models import User
        student = User.objects.get(id=student_id)
        enrollment = Enrollment.objects.get(student=student, course=course)
        
        module_progress_list = ModuleProgress.objects.filter(enrollment=enrollment).select_related('module')
        lesson_progress_list = LessonProgress.objects.filter(enrollment=enrollment).select_related('lesson', 'lesson__module')
        
        module_serializer = DynamicFieldSerializer(module_progress_list, many=True, model_name="moduleprogress")
        lesson_serializer = DynamicFieldSerializer(lesson_progress_list, many=True, model_name="lessonprogress")
        
        return Response({
            "success": True,
            "data": {
                "student": {"id": student.id, "email": student.email, "name": student.get_full_name()},
                "enrollment": {
                    "progress": float(enrollment.progress),
                    "completed_lessons": enrollment.completed_lessons,
                    "is_completed": enrollment.is_completed,
                    "enrolled_at": enrollment.enrolled_at
                },
                "module_progress": module_serializer.data,
                "lesson_progress": lesson_serializer.data
            },
            "message": "Student progress retrieved successfully."
        }, status=status.HTTP_200_OK)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)
    except Enrollment.DoesNotExist:
        return Response({"success": False, "message": "Student is not enrolled in this course."}, status=status.HTTP_404_NOT_FOUND)




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_assignment_submissions_view(request, lesson_id):
    """Get all submissions for an assignment lesson (for instructors)."""
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        if lesson.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view submissions for this lesson."
            }, status=status.HTTP_403_FORBIDDEN)
        
        if lesson.content_type != Lesson.ContentType.ASSIGNMENT:
            return Response({
                "success": False,
                "message": "This lesson is not an assignment."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        submissions = AssignmentSubmission.objects.filter(lesson=lesson).select_related('student', 'enrollment').order_by('-submitted_at')
        
        serializer = DynamicFieldSerializer(submissions, many=True, model_name="assignmentsubmission")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Assignment submissions retrieved successfully."
        }, status=status.HTTP_200_OK)
    except Lesson.DoesNotExist:
        return Response({"success": False, "message": "Lesson not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def grade_assignment_view(request, submission_id):
    """Grade an assignment submission (for instructors). Expected payload: {"score": 85.0, "feedback": "Great work!", "status": "graded"}"""
    try:
        submission = AssignmentSubmission.objects.get(id=submission_id)
        if submission.lesson.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to grade this submission."
            }, status=status.HTTP_403_FORBIDDEN)
        
        score = request.data.get('score')
        feedback = request.data.get('feedback', '')
        status_val = request.data.get('status', 'graded')
        
        if score is None:
            return Response({"success": False, "message": "Score is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        if submission.max_score and score > submission.max_score:
            return Response({
                "success": False,
                "message": f"Score cannot exceed maximum score of {submission.max_score}."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        submission.score = float(score)
        submission.feedback = feedback
        submission.status = status_val
        submission.graded_by = request.user
        submission.graded_at = timezone.now()
        submission.save()
        
        serializer = DynamicFieldSerializer(submission, model_name="assignmentsubmission")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Assignment graded successfully."
        }, status=status.HTTP_200_OK)
    except AssignmentSubmission.DoesNotExist:
        return Response({"success": False, "message": "Submission not found."}, status=status.HTTP_404_NOT_FOUND)
