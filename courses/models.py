# models.py
import uuid
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from user_managment.models import User 
from .choices import *
from django.contrib.postgres.fields import ArrayField,JSONField
from django.utils.text import slugify

class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Frontend icon identifier, e.g., 'BookOpen', 'Code', etc."
    )
    count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            # Auto-generate slug from name if not provided
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name



class Level(models.Model):
   
    name = models.CharField(max_length=50, unique=True)  # e.g., "Beginner"
    code = models.SlugField(max_length=50, unique=True)   # e.g., "beginner"

    def __str__(self):
        return self.name

class Course(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, null=True, blank=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="courses"
    )
    level = models.ForeignKey(Level, on_delete=models.SET_NULL, null=True, blank=True, related_name="courses")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)])
    thumbnail = models.ImageField(upload_to="course_thumbnails/", null=True, blank=True)
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="courses")
    status = models.CharField(max_length=10,choices=STATUS_CHOICES,default="draft")
    # Approval / moderation
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_courses")
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    submitted_for_approval_at = models.DateTimeField(null=True, blank=True)

    # Moderation flags
    is_flagged = models.BooleanField(default=False)
    flagged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="flagged_courses")
    flagged_at = models.DateTimeField(null=True, blank=True)
    flag_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["instructor", "created_at"]),
        ]

    def __str__(self):
        return self.title

    @property
    def is_visible(self):
        return (
            self.status and self.status.code == "published"
            and not self.hidden_from_students
            and not self.is_flagged
        )


class Module(models.Model):
    """Optional grouping of lessons inside a course"""
  
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["course", "order"], name="unique_module_order_per_course")
        ]

    def __str__(self):
        return f"{self.course.title} - {self.title}"


# The `Lesson` class defines a model with fields for course, module, title, description, content type,
# order, duration, created and updated timestamps, and a unique constraint on course and order.
class Lesson(models.Model):
    class ContentType(models.TextChoices):
        VIDEO = "video", "Video"
        TEXT = "text", "Text"
        QUIZ = "quiz", "Quiz"
        ASSIGNMENT = "assignment", "Assignment"
        ARTICLE='article'
        FILE = "file", "File"
        URL = "url", "URL/Link"
     

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    module = models.ForeignKey(Module, on_delete=models.SET_NULL, null=True, blank=True, related_name="lessons")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    content_type = models.CharField(max_length=20, choices=ContentType.choices, default=ContentType.VIDEO)
    order = models.PositiveIntegerField(default=0)
    duration = models.DurationField(null=True, blank=True)  # better for arithmetic
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["course", "order"], name="unique_lesson_order_per_course")
        ]

    def __str__(self):
        return f"{self.course.title} — {self.title}"
    
class VideoLesson(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name="video")
    video_file = models.FileField(upload_to='lesson_videos/', null=True, blank=True)
    youtube_url = models.URLField(max_length=500, blank=True)
    transcript = models.TextField(blank=True)
    chapters =  models.JSONField(default=list, blank=True)  # list of chapter names/timestamps
    duration = models.DurationField(null=True, blank=True)


class QuizLesson(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name="quiz")
    type = models.CharField(max_length=50, default="multiple-choice")
    time_limit = models.PositiveIntegerField(default=30)  # minutes
    passing_score = models.PositiveIntegerField(default=70)
    attempts = models.PositiveIntegerField(default=3)
    randomize_questions = models.BooleanField(default=False)
    show_correct_answers = models.BooleanField(default=True)
    grading_policy = models.CharField(max_length=20, default="highest")
    questions =  models.JSONField(default=list, blank=True)  # store question objects like TS template


class AssignmentLesson(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name="assignment")
    instructions = models.TextField(blank=True)
    submission_types = ArrayField(models.CharField(max_length=10), default=list, blank=True)  # ["file", "text"]
    due_date = models.DateTimeField(null=True, blank=True)
    due_days = models.PositiveIntegerField(null=True, blank=True)
    max_score = models.FloatField(default=100)
    max_attempts = models.PositiveIntegerField(default=1)
    rubric = models.TextField(blank=True)
    rubric_criteria =  models.JSONField(default=list, blank=True)
    peer_review = models.BooleanField(default=False)
    word_limit = models.PositiveIntegerField(null=True, blank=True)
    allow_late_submission = models.BooleanField(default=True)
    late_deduction = models.FloatField(default=10.0)


class ArticleLesson(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name="article")
    content = models.TextField(blank=True)
    estimated_read_time = models.PositiveIntegerField(default=0)
    attachments =  models.JSONField(default=list, blank=True)  # id, title, type, url/file
    external_links =  models.JSONField(default=list, blank=True)  # id, title, url, description


class LessonResource(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="resources")
    title = models.CharField(max_length=200)
    type = models.CharField(max_length=50)
    file = models.FileField(upload_to='lesson_resources/', null=True, blank=True)  


class Enrollment(models.Model):
    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='enrollments', db_index=True
    )
    course = models.ForeignKey(
        'Course', on_delete=models.CASCADE, related_name='enrollments', db_index=True
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    progress = models.FloatField(default=0.0)  # Overall course progress %
    last_accessed = models.DateTimeField(auto_now=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['student', 'course']
        ordering = ['-enrolled_at']

    def calculate_progress(self):
        """Calculate overall course progress based on lesson completions."""
        total_lessons = self.course.lessons.count()
        if total_lessons == 0:
            self.progress = 0.0
        else:
            completed_lessons = self.lesson_progress.filter(completed=True).count()
            self.progress = (completed_lessons / total_lessons) * 100

        if self.progress >= 100 and not self.completed:
            self.completed = True
            self.completed_at = timezone.now()

        self.save(update_fields=['progress', 'completed', 'completed_at'])
        return self.progress

    def __str__(self):
        return f"{self.student.email} - {self.course.title}"


class LessonProgress(models.Model):
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name='lesson_progress', db_index=True
    )
    lesson = models.ForeignKey(
        'Lesson', on_delete=models.CASCADE, related_name='student_progress', db_index=True
    )
    progress = models.FloatField(default=0.0)  # Lesson progress %
    completed = models.BooleanField(default=False)
    first_accessed = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_spent = models.DurationField(null=True, blank=True)

    class Meta:
        unique_together = ['enrollment', 'lesson']
        ordering = ['lesson__order']

    def mark_completed(self, progress=100.0):
        self.progress = progress
        self.completed = True
        if not self.completed_at:
            self.completed_at = timezone.now()
        self.save(update_fields=['progress', 'completed', 'completed_at'])

        # Cascade update to enrollment
        self.enrollment.calculate_progress()
        return self

    def __str__(self):
        return f"{self.enrollment.student.email} - {self.lesson.title} - {self.progress}%"


class ResourceProgress(models.Model):
    lesson_progress = models.ForeignKey(
        LessonProgress, on_delete=models.CASCADE, related_name='resource_progress', db_index=True
    )
    resource = models.ForeignKey(
        'LessonResource', on_delete=models.CASCADE, related_name='student_progress', db_index=True
    )
    completed = models.BooleanField(default=False)
    accessed_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['lesson_progress', 'resource']
        

    def mark_completed(self):
        self.completed = True
        if not self.completed_at:
            self.completed_at = timezone.now()
        self.save(update_fields=['completed', 'completed_at'])

        # Cascade update to lesson progress
        self.lesson_progress.mark_completed()
        return self

    def __str__(self):
        return f"{self.lesson_progress.enrollment.student.email} - {self.resource.name}"


class Certificate(models.Model):
    enrollment = models.OneToOneField(
        Enrollment, on_delete=models.CASCADE, related_name='certificate', db_index=True
    )
    certificate_number = models.CharField(max_length=100, unique=True)
    issued_date = models.DateTimeField(auto_now_add=True)
    grade = models.CharField(max_length=2, default='A')  # A, B, C, etc.

    def save(self, *args, **kwargs):
        if not self.certificate_number:
            course_prefix = (self.enrollment.course.title[:3].upper() if len(self.enrollment.course.title) >= 3 else 'CRS')
            self.certificate_number = f"EMR-{course_prefix}-{''.join(random.choices(string.digits, k=8))}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Certificate {self.certificate_number} - {self.enrollment.student.email}"







