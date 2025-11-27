from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from courses.models import Course, Lesson, FinalCourseAssessment
from user_managment.models import User
from .services import GradingService
from .models import StudentLessonGrade, StudentFinalAssessmentGrade, LessonWeight, FinalAssessmentWeight

class TeacherGradingTableView(APIView):
    permission_classes = [permissions.IsAuthenticated] 

    def get(self, request, course_id):
        """
        Returns the dynamic grading table for a course.
        Includes schema (columns) and student data (rows).
        """
        # Add permission check: ensure user is instructor of the course
        course = get_object_or_404(Course, pk=course_id)
        if course.instructor != request.user and not request.user.is_superuser:
             return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)

        data = GradingService.get_teacher_grading_table(course_id)
        return Response(data)

class UpdateStudentGradeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        Updates a student's grade for a specific lesson or final assessment.
        Body: {
            "student_id": int,
            "course_id": int,
            "lesson_id": int (optional),
            "assessment_id": int (optional),
            "score": float,  # Raw score (e.g., 20.5 out of 25)
            "feedback": string (optional)
        }
        """
        student_id = request.data.get('student_id')
        course_id = request.data.get('course_id')
        lesson_id = request.data.get('lesson_id')
        assessment_id = request.data.get('assessment_id')
        score_val = request.data.get('score') # Changed from score_percentage to score (raw)
        
        if score_val is None:
             return Response({"error": "score is required"}, status=status.HTTP_400_BAD_REQUEST)
             
        try:
            score_val = float(score_val)
            if score_val < 0:
                return Response({"error": "Score cannot be negative"}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
             return Response({"error": "Invalid score format"}, status=status.HTTP_400_BAD_REQUEST)

        student = get_object_or_404(User, pk=student_id)
        course = get_object_or_404(Course, pk=course_id)

        # Authorization check
        if course.instructor != request.user and not request.user.is_superuser:
             return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)

        if lesson_id:
            lesson = get_object_or_404(Lesson, pk=lesson_id)
            grade_entry, _ = StudentLessonGrade.objects.get_or_create(student=student, lesson=lesson)
            
            # Ensure max_score is current
            current_max = GradingService.get_lesson_max_score(lesson)
            grade_entry.max_score = current_max
            
            # Update score (Raw Score)
            grade_entry.raw_score = score_val
            # Percentage is auto-calculated in model.save()
            
            grade_entry.is_override = True
            if 'feedback' in request.data:
                grade_entry.feedback = request.data['feedback']
            grade_entry.save()
            
        elif assessment_id:
            assessment = get_object_or_404(FinalCourseAssessment, pk=assessment_id)
            grade_entry, _ = StudentFinalAssessmentGrade.objects.get_or_create(student=student, assessment=assessment)
            
            # Ensure max_score is current
            current_max = GradingService.get_assessment_max_score(assessment)
            grade_entry.max_score = current_max
            
            # Update score (Raw Score)
            grade_entry.raw_score = score_val
            
            grade_entry.is_override = True
            if 'feedback' in request.data:
                grade_entry.feedback = request.data['feedback']
            grade_entry.save()
        else:
            return Response({"error": "Either lesson_id or assessment_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Recalculate total course grade
        GradingService.calculate_final_course_grade(student, course)

        # Fetch updated student row data
        student_data = GradingService.get_student_row_data(student, course)

        return Response({
            "message": "Grade updated successfully", 
            "student": student_data
        })

class StudentGradingReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, course_id):
        """
        Returns the score report for the requesting student.
        """
        course = get_object_or_404(Course, pk=course_id)
        student = request.user

        report = GradingService.get_student_grading_report(student, course_id)
        
        return Response(report)
