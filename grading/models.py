from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from courses.models import Course, Lesson, FinalCourseAssessment

class GradingConfiguration(models.Model):
    """
    Configuration for course grading.
    Defines passing criteria and potentially grade scales (A, B, C...).
    """
    course = models.OneToOneField(
        Course, 
        on_delete=models.CASCADE, 
        related_name='grading_configuration'
    )
    passing_percentage = models.FloatField(
        default=60.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Minimum total percentage required to pass the course."
    )
    # We could add grade scale logic here later (e.g., JSONField for A=90, B=80...)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Grading Config - {self.course.title}"


class LessonWeight(models.Model):
    """
    Defines the weight of a specific lesson (Quiz/Assignment) in the final grade.
    """
    lesson = models.OneToOneField(
        Lesson, 
        on_delete=models.CASCADE, 
        related_name='grading_weight'
    )
    weight = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0)],
        help_text="Weight of this lesson in the final score calculation."
    )
    
    class Meta:
        verbose_name = "Lesson Weight"
        verbose_name_plural = "Lesson Weights"

    def __str__(self):
        return f"{self.lesson.title} (Weight: {self.weight})"


class FinalAssessmentWeight(models.Model):
    """
    Defines the weight of the final course assessment.
    """
    assessment = models.OneToOneField(
        FinalCourseAssessment,
        on_delete=models.CASCADE,
        related_name='grading_weight'
    )
    weight = models.FloatField(
        default=1.0,
        validators=[MinValueValidator(0.0)],
        help_text="Weight of the final assessment in the final score calculation."
    )

    class Meta:
        verbose_name = "Final Assessment Weight"
        verbose_name_plural = "Final Assessment Weights"


class StudentLessonGrade(models.Model):
    """
    Stores the finalized/current score for a student in a specific lesson.
    Acts as a cache and allows for manual overrides by teachers.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('graded', 'Graded'),
        ('failed', 'Failed'),
        ('passed', 'Passed'), # Usually passed/failed is determined by score vs passing criteria
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='lesson_grades'
    )
    lesson = models.ForeignKey(
        Lesson, 
        on_delete=models.CASCADE, 
        related_name='student_grades'
    )
    
    # The raw score obtained (e.g., 20 out of 25 questions, or 80 out of 100)
    raw_score = models.FloatField(default=0.0) 
    
    # The maximum possible score for this lesson at the time of grading
    max_score = models.FloatField(default=100.0)
    
    # The score converted to a percentage (0-100)
    score_percentage = models.FloatField(default=0.0)
    
    is_override = models.BooleanField(default=False, help_text="If True, this score was manually set by a teacher.")
    feedback = models.TextField(blank=True)
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'lesson']
        indexes = [
            models.Index(fields=['student', 'lesson']),
        ]

    def __str__(self):
        return f"{self.student.email} - {self.lesson.title}: {self.score_percentage}%"
        
    def save(self, *args, **kwargs):
        # Ensure percentage is correct
        if self.max_score > 0:
            self.score_percentage = (self.raw_score / self.max_score) * 100
        else:
            self.score_percentage = 0.0
        super().save(*args, **kwargs)


class StudentFinalAssessmentGrade(models.Model):
    """
    Stores the grade for the final course assessment.
    """
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='final_assessment_grades'
    )
    assessment = models.ForeignKey(
        FinalCourseAssessment,
        on_delete=models.CASCADE,
        related_name='student_grades'
    )
    
    raw_score = models.FloatField(default=0.0)
    max_score = models.FloatField(default=100.0) # Usually calculated from questions
    score_percentage = models.FloatField(default=0.0)
    
    is_override = models.BooleanField(default=False)
    feedback = models.TextField(blank=True)
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'assessment']

    def save(self, *args, **kwargs):
        if self.max_score > 0:
            self.score_percentage = (self.raw_score / self.max_score) * 100
        else:
            self.score_percentage = 0.0
        super().save(*args, **kwargs)


class StudentCourseGrade(models.Model):
    """
    Stores the calculated final grade for the course.
    """
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('incomplete', 'Incomplete'),
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='course_grades'
    )
    course = models.ForeignKey(
        Course, 
        on_delete=models.CASCADE, 
        related_name='student_grades'
    )
    
    total_weighted_score = models.FloatField(default=0.0) # The sum of weighted scores
    total_possible_weighted_score = models.FloatField(default=0.0) # The sum of all weights
    
    final_score_percentage = models.FloatField(default=0.0, help_text="Final calculated grade out of 100%")
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='in_progress'
    )
    
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'course']
        verbose_name = "Student Course Grade"
        verbose_name_plural = "Student Course Grades"

    def __str__(self):
        return f"{self.student.email} - {self.course.title}: {self.final_score_percentage}% ({self.status})"
