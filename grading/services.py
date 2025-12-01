from django.db.models import Sum
from django.shortcuts import get_object_or_404
from .models import (
    GradingConfiguration, LessonWeight, FinalAssessmentWeight,
    StudentLessonGrade, StudentFinalAssessmentGrade, StudentCourseGrade
)
from courses.models import (
    Course, Module, Lesson, QuizAttempt, AssignmentSubmission, 
    AssessmentAttempt, FinalCourseAssessment, QuizQuestion, AssessmentQuestion
)

class GradingService:
    
    @staticmethod
    def get_lesson_max_score(lesson):
        """
        Calculate max score for a lesson based on its type.
        - Quiz: sum of all question points
        - Assignment: max_score from AssignmentLesson config
        """
        if lesson.content_type == Lesson.ContentType.QUIZ:
            total = QuizQuestion.objects.filter(lesson=lesson).aggregate(
                total=Sum('points')
            )['total']
            return total or 0
        elif lesson.content_type == Lesson.ContentType.ASSIGNMENT:
            assignment = getattr(lesson, 'assignment', None)
            if assignment:
                return assignment.max_score
            return 100
        return 0

    @staticmethod
    def get_assessment_max_score(assessment):
        """Calculate max score for final assessment from questions."""
        total = AssessmentQuestion.objects.filter(assessment=assessment).aggregate(
            total=Sum('points')
        )['total']
        return total or 0

    @staticmethod
    def get_lesson_weight(lesson):
        """Helper to get weight or default to 1.0"""
        try:
            if hasattr(lesson, 'grading_weight') and lesson.grading_weight:
                return lesson.grading_weight.weight
        except:
            pass
        return 1.0

    @staticmethod
    def has_taken_lesson(student, lesson):
        """Check if student has attempted the lesson (quiz or assignment)."""
        if lesson.content_type == Lesson.ContentType.QUIZ:
            return QuizAttempt.objects.filter(
                student=student, lesson=lesson, is_in_progress=False
            ).exists()
        elif lesson.content_type == Lesson.ContentType.ASSIGNMENT:
            return AssignmentSubmission.objects.filter(
                student=student, lesson=lesson
            ).exclude(status='draft').exists()
        return False

    @staticmethod
    def has_taken_assessment(student, assessment):
        """Check if student has attempted the final assessment."""
        return AssessmentAttempt.objects.filter(
            student=student, assessment=assessment
        ).exists()

    @staticmethod
    def sync_student_grades(student, course):
        """
        Ensures all graded items have a StudentLessonGrade entry 
        based on the latest attempts/submissions.
        Then recalculates the course grade.
        """
        # 1. Sync Quizzes and Assignments
        modules = course.modules.all()
        lessons = Lesson.objects.filter(
            module__in=modules,
            content_type__in=[Lesson.ContentType.QUIZ, Lesson.ContentType.ASSIGNMENT]
        )

        for lesson in lessons:
            # We attempt to sync regardless, but update_lesson_grade_from_source checks for attempts
            if GradingService.has_taken_lesson(student, lesson):
                GradingService.update_lesson_grade_from_source(student, lesson)

        # 2. Sync Final Assessment
        if hasattr(course, 'final_assessment'):
            assessment = course.final_assessment
            if GradingService.has_taken_assessment(student, assessment):
                GradingService.update_assessment_grade_from_source(student, assessment)

        # 3. Recalculate Total
        return GradingService.calculate_final_course_grade(student, course)

    @staticmethod
    def update_lesson_grade_from_source(student, lesson):
        """
        Updates StudentLessonGrade from QuizAttempt or AssignmentSubmission
        unless an override exists.
        """
        grade_entry, created = StudentLessonGrade.objects.get_or_create(
            student=student,
            lesson=lesson,
            defaults={'max_score': GradingService.get_lesson_max_score(lesson)}
        )

        # Always update max_score to keep it fresh
        grade_entry.max_score = GradingService.get_lesson_max_score(lesson)

        # If manually overridden, do not overwrite raw_score, but save max_score update
        if grade_entry.is_override:
            grade_entry.save()
            return grade_entry

        if lesson.content_type == Lesson.ContentType.QUIZ:
            # Get best score based on policy
            config = getattr(lesson, 'quiz_config', None)
            policy = config.grading_policy if config else 'highest'
            
            attempts = QuizAttempt.objects.filter(student=student, lesson=lesson, is_in_progress=False)
            
            if not attempts.exists():
                grade_entry.save()
                return grade_entry

            if policy == 'highest':
                best_attempt = attempts.order_by('-earned_points').first()
            elif policy == 'latest':
                best_attempt = attempts.order_by('-completed_at').first()
            elif policy == 'first':
                best_attempt = attempts.order_by('completed_at').first()
            elif policy == 'average':
                avg_points = attempts.aggregate(avg=Sum('earned_points'))['avg']
                grade_entry.raw_score = avg_points or 0
                grade_entry.save()
                return grade_entry
            else:
                best_attempt = attempts.order_by('-earned_points').first()

            if best_attempt:
                grade_entry.raw_score = best_attempt.earned_points
                grade_entry.save()

        elif lesson.content_type == Lesson.ContentType.ASSIGNMENT:
            submission = AssignmentSubmission.objects.filter(
                student=student, 
                lesson=lesson
            ).order_by('-submitted_at').first()

            if submission and submission.status in ['graded', 'peer_reviewed']:
                grade_entry.raw_score = submission.final_score if submission.final_score is not None else (submission.score or 0)
                grade_entry.save()
            else:
                pass

        return grade_entry

    @staticmethod
    def update_assessment_grade_from_source(student, assessment):
        grade_entry, created = StudentFinalAssessmentGrade.objects.get_or_create(
            student=student,
            assessment=assessment,
            defaults={'max_score': GradingService.get_assessment_max_score(assessment)}
        )
        
        # Always update max_score
        grade_entry.max_score = GradingService.get_assessment_max_score(assessment)

        if grade_entry.is_override:
            grade_entry.save()
            return grade_entry

        attempts = AssessmentAttempt.objects.filter(student=student, assessment=assessment).order_by('-earned_points')
        best_attempt = attempts.first()

        if best_attempt:
            grade_entry.raw_score = best_attempt.earned_points
            grade_entry.save()
        
        return grade_entry

    @staticmethod
    def calculate_final_course_grade(student, course):
        """
        Calculates the final course grade based on TOTAL POINTS.
        Final % = Total Earned Points / Total Possible Points
        """
        
        # Get all graded lessons
        modules = course.modules.all()
        lessons = Lesson.objects.filter(
            module__in=modules,
            content_type__in=[Lesson.ContentType.QUIZ, Lesson.ContentType.ASSIGNMENT]
        )

        total_earned_points = 0.0
        total_possible_points = 0.0

        # 1. Lessons
        for lesson in lessons:
            max_score = GradingService.get_lesson_max_score(lesson)
            if max_score <= 0:
                continue
            
            total_possible_points += max_score
            
            # Check if grade entry exists to get score. 
            try:
                grade_entry = StudentLessonGrade.objects.get(student=student, lesson=lesson)
                total_earned_points += grade_entry.raw_score
            except StudentLessonGrade.DoesNotExist:
                pass

        # 2. Final Assessment
        if hasattr(course, 'final_assessment'):
            assessment = course.final_assessment
            max_score = GradingService.get_assessment_max_score(assessment)
            if max_score > 0:
                total_possible_points += max_score
                try:
                    grade_entry = StudentFinalAssessmentGrade.objects.get(student=student, assessment=assessment)
                    total_earned_points += grade_entry.raw_score
                except StudentFinalAssessmentGrade.DoesNotExist:
                    pass

        # Calculate Final
        final_percent = 0.0
        if total_possible_points > 0:
            final_percent = (total_earned_points / total_possible_points) * 100.0
        
        # Update StudentCourseGrade
        course_grade, created = StudentCourseGrade.objects.get_or_create(
            student=student,
            course=course
        )
        course_grade.total_weighted_score = total_earned_points 
        course_grade.total_possible_weighted_score = total_possible_points 
        course_grade.final_score_percentage = round(final_percent, 2)
        
        # Determine Status
        config = getattr(course, 'grading_configuration', None)
        passing_score = config.passing_percentage if config else 60.0
        
        if course_grade.final_score_percentage >= passing_score:
            course_grade.status = 'passed'
        else:
            course_grade.status = 'failed'
            
        course_grade.save()
        return course_grade

    @staticmethod
    def get_teacher_grading_table(course_id):
        """
        Returns the grading table in the requested JSON format.
        """
        course = Course.objects.get(pk=course_id)
        
        # 1. Build Lessons Array
        lessons_metadata = []
        modules = course.modules.all().order_by('order')
        
        for module in modules:
            mod_lessons = module.lessons.filter(
                content_type__in=[Lesson.ContentType.QUIZ, Lesson.ContentType.ASSIGNMENT]
            ).order_by('order')
            
            for lesson in mod_lessons:
                lessons_metadata.append({
                    "id": lesson.id, 
                    "title": f"{module.title}: {lesson.title}",
                    "max_score": GradingService.get_lesson_max_score(lesson),
                    "type": lesson.content_type # "quiz" or "assignment"
                })
        
        if hasattr(course, 'final_assessment'):
            assessment = course.final_assessment
            lessons_metadata.append({
                "id": "final",
                "title": "Final Assessment",
                "max_score": GradingService.get_assessment_max_score(assessment),
                "type": "final"
            })

        # 2. Build Students Array
        enrollments = course.enrollments.filter(is_enrolled=True).select_related('student')
        students_data = []
        
        for enrollment in enrollments:
            student = enrollment.student
            student_row = GradingService.get_student_row_data(student, course)
            students_data.append(student_row)

        # 3. Passing Percentage
        config = getattr(course, 'grading_configuration', None)
        passing_percentage = config.passing_percentage if config else 60.0
        
        return {
            "passing_percentage": passing_percentage,
            "lessons": lessons_metadata,
            "students": students_data
        }

    @staticmethod
    def get_student_row_data(student, course):
        """
        Returns the row data for a single student for the teacher table.
        """
        # Sync grades to ensure fresh data (re-calculates StudentCourseGrade)
        GradingService.sync_student_grades(student, course)
        
        scores_list = []
        modules = course.modules.all().order_by('order')
        
        # Lesson Scores
        for module in modules:
            mod_lessons = module.lessons.filter(
                content_type__in=[Lesson.ContentType.QUIZ, Lesson.ContentType.ASSIGNMENT]
            ).order_by('order')
            for lesson in mod_lessons:
                score_val = 0
                feedback_val = ""
                try:
                    lg = StudentLessonGrade.objects.get(student=student, lesson=lesson)
                    score_val = lg.raw_score
                    feedback_val = lg.feedback
                except StudentLessonGrade.DoesNotExist:
                    pass
                
                scores_list.append({
                    "lesson_id": lesson.id,
                    "score": score_val,
                    "feedback": feedback_val
                })
        
        # Assessment Score
        if hasattr(course, 'final_assessment'):
            assessment = course.final_assessment
            score_val = 0
            feedback_val = ""
            try:
                ag = StudentFinalAssessmentGrade.objects.get(student=student, assessment=assessment)
                score_val = ag.raw_score
                feedback_val = ag.feedback
            except StudentFinalAssessmentGrade.DoesNotExist:
                pass
            scores_list.append({
                "lesson_id": "final",
                "score": score_val,
                "feedback": feedback_val
            })

        # Fetch Final Course Grade (calculated in sync step)
        try:
            course_grade = StudentCourseGrade.objects.get(student=student, course=course)
            earned_points = course_grade.total_weighted_score
            possible_points = course_grade.total_possible_weighted_score
            percentage = course_grade.final_score_percentage
            status = course_grade.status
        except StudentCourseGrade.DoesNotExist:
            earned_points = 0.0
            possible_points = 0.0
            percentage = 0.0
            status = "in_progress"

        return {
            "id": student.id,
            "name": student.get_full_name(),
            "scores": scores_list,
            "earned_points": earned_points,
            "possible_points": possible_points,
            "percentage": percentage,
            "status": status
        }

    @staticmethod
    def get_student_grading_report(student, course_id):
        """
        Returns the grading report for a single student.
        """
        course = Course.objects.get(pk=course_id)
        
        # Sync grades first
        course_grade = GradingService.sync_student_grades(student, course)
        
        report = {
            "course_title": course.title,
            "total_score": course_grade.final_score_percentage,
            "status": course_grade.status,
            "modules": [],
            "final_assessment": None
        }

        modules = course.modules.all().order_by('order')
        for module in modules:
            module_data = {
                "id": module.id,
                "title": module.title,
                "lessons": []
            }
            
            lessons = module.lessons.filter(
                content_type__in=[Lesson.ContentType.QUIZ, Lesson.ContentType.ASSIGNMENT]
            ).order_by('order')
            
            for lesson in lessons:
                score_val = 0
                feedback_val = ""
                taken = False
                
                if GradingService.has_taken_lesson(student, lesson):
                    taken = True
                    try:
                        lg = StudentLessonGrade.objects.get(student=student, lesson=lesson)
                        score_val = lg.raw_score
                        feedback_val = lg.feedback
                    except StudentLessonGrade.DoesNotExist:
                        pass
                
                module_data["lessons"].append({
                    "id": lesson.id,
                    "title": lesson.title,
                    "type": lesson.content_type,
                    "max_score": GradingService.get_lesson_max_score(lesson),
                    "score": score_val if taken else 0,
                    "feedback": feedback_val,
                    "is_taken": taken
                })
            
            if module_data["lessons"]:
                report["modules"].append(module_data)

        if hasattr(course, 'final_assessment'):
            assessment = course.final_assessment
            score_val = 0
            feedback_val = ""
            taken = False
            
            if GradingService.has_taken_assessment(student, assessment):
                taken = True
                try:
                    ag = StudentFinalAssessmentGrade.objects.get(student=student, assessment=assessment)
                    score_val = ag.raw_score
                    feedback_val = ag.feedback
                except StudentFinalAssessmentGrade.DoesNotExist:
                    pass
            
            report["final_assessment"] = {
                "id": assessment.id,
                "title": assessment.title,
                "max_score": GradingService.get_assessment_max_score(assessment),
                "score": score_val if taken else 0,
                "feedback": feedback_val,
                "is_taken": taken
            }
            
        return report