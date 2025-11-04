# models.py
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from user_managment.models import User 
from .choices import *
from django.utils.text import slugify
import string, random 

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
    class Meta:
        verbose_name_plural = "Category"
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
    class Meta:
        verbose_name_plural = "Level"
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
    issue_certificate=models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Courses"
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

    @property
    def total_lessons(self):
        return self.lessons.count()

    @property
    def total_duration(self):
        from datetime import timedelta
        total = sum((lesson.duration for lesson in self.lessons.all() if lesson.duration), timedelta())
        hours = total.seconds // 3600
        minutes = (total.seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    @property
    def average_rating(self):
        ratings = self.ratings.all()
        if ratings:
            return round(sum(r.rating for r in ratings) / len(ratings), 1)
        return 0.0

    @property
    def total_reviews(self):
        return self.ratings.count()


class Module(models.Model):
    """Optional grouping of lessons inside a course"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    duration = models.CharField(max_length=50, default="", help_text="e.g., '2h 30m'")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "Modules"
        ordering = ["id", "order"]
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
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="Lessons")
    module = models.ForeignKey(Module, on_delete=models.SET_NULL, null=True, blank=True, related_name="Lessons")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    content_type = models.CharField(max_length=20, choices=ContentType.choices, default=ContentType.VIDEO)
    order = models.PositiveIntegerField(default=0)
    duration = models.DurationField(null=True, blank=True)  # better for arithmetic
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Lesson"
        ordering = ["module", "order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=['module', 'order'],
                name='unique_lesson_order_per_module',
                condition=models.Q(module__isnull=False)
            ),
        ]

    def __str__(self):
        return f"{self.course.title} — {self.title}"
    
class VideoLesson(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name="video")
    video_file = models.FileField(upload_to='lesson_videos/', null=True, blank=True)
    youtube_url = models.URLField(max_length=500, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    attachments =  models.FileField(upload_to='lesson_file_attachments/', null=True, blank=True)
    transcript = models.TextField(blank=True)
    chapters =  models.JSONField(default=list, blank=True)  # list of chapter names/timestamps
    duration = models.DurationField(null=True, blank=True)
    class Meta:
        verbose_name_plural = "VideoLesson"

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
    class Meta:
        verbose_name_plural = "QuizLesson"
class QuizQuestion(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('multiple-choice', 'Multiple Choice'),
        ('true-false', 'True/False'),
        ('fill-blank', 'Fill in Blank'),
        ('drag-drop', 'Drag & Drop'),
        ('short-answer', 'Short Answer'),
    ]
    
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='quiz_questions')
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='multiple-choice')
    question_text = models.TextField()
    question_image = models.ImageField(upload_to='quiz_questions/', null=True, blank=True)
    explanation = models.TextField(blank=True)
    points = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    
    # Fill in blank specific fields
    blanks = models.JSONField(default=list, blank=True, help_text="List of correct answers for blanks")
    
    # Drag and drop specific fields
    drag_items = models.JSONField(default=list, blank=True, help_text="List of draggable items")
    drop_zones = models.JSONField(default=list, blank=True, help_text="List of drop zones")
    drag_drop_mappings = models.JSONField(default=dict, blank=True, help_text="Correct drag-drop mappings")
    
    # Image support for advanced question types
    option_images = models.JSONField(default=list, blank=True, help_text="List of image URLs/paths for multiple choice options")
    drag_item_images = models.JSONField(default=list, blank=True, help_text="List of image URLs/paths for drag items")
    drop_zone_images = models.JSONField(default=list, blank=True, help_text="List of image URLs/paths for drop zones")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
    
        verbose_name_plural = "QuizQuestion"
    def __str__(self):
        return f"{self.lesson.title} - Question {self.order + 1}"


class QuizAnswer(models.Model):
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.CharField(max_length=500)
    answer_image = models.ImageField(upload_to='quiz_answers/', null=True, blank=True)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
        verbose_name_plural = "QuizAnswer"
    
    def __str__(self):
        return f"{self.question.question_text[:50]} - {self.answer_text}"


class QuizAttempt(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_attempt_student')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='quiz_lesson')
    score = models.FloatField(default=0.0)  # Percentage score (0-100)
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(auto_now_add=True)
    time_taken = models.DurationField(null=True, blank=True)  # Time taken to complete
    
    class Meta:
        # Allow multiple attempts per student per lesson
        ordering = ['-completed_at']
        verbose_name_plural = "QuizAttempt"
    
    def calculate_score(self):
        """Calculate the score based on correct answers"""
        if self.total_questions > 0:
            self.score = (self.correct_answers / self.total_questions) * 100
        else:
            self.score = 0.0
        self.save()
        return self.score
    
    def __str__(self):
        return f"{self.student.email} - {self.lesson.title} - {self.score}%"


class QuizConfiguration(models.Model):
    """Quiz settings and configuration for lessons"""
    GRADING_POLICY_CHOICES = [
        ('highest', 'Highest Score'),
        ('latest', 'Latest Attempt'),
        ('average', 'Average Score'),
        ('first', 'First Attempt'),
    ]
    
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name='quiz_config')
    time_limit = models.PositiveIntegerField(default=30, help_text="Time limit in minutes")
    passing_score = models.PositiveIntegerField(default=70, help_text="Passing score percentage")
    max_attempts = models.PositiveIntegerField(default=3, help_text="Maximum attempts allowed")
    randomize_questions = models.BooleanField(default=False)
    show_correct_answers = models.BooleanField(default=True)
    grading_policy = models.CharField(max_length=20, choices=GRADING_POLICY_CHOICES, default='highest')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
       
        verbose_name_plural = "QuizConfiguration"
    def __str__(self):
        return f"Quiz Config - {self.lesson.title}"
    
class AssignmentLesson(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name="assignment")
    instructions = models.TextField(blank=True)
    tasks = models.JSONField(default=list, blank=True, help_text='List of tasks for the assignment')
    # Use JSONField (list) instead of Postgres ArrayField for cross-DB compatibility.
    submission_types = models.JSONField(default=list, blank=True, help_text='List of submission types, e.g. ["file", "text"]')
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
    
    class Meta:
       
        verbose_name_plural = "AssignmentLesson"

class ArticleLesson(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE, related_name="article")
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    content = models.TextField(blank=True)
    estimated_read_time = models.PositiveIntegerField(default=0, help_text="Auto-calculated based on word count")
    external_links = models.JSONField(default=list, blank=True)  # id, title, url, description
    
    class Meta:
        verbose_name_plural = "ArticleLesson"
    
    def save(self, *args, **kwargs):
        # Auto-calculate estimated read time (average reading speed: 200-250 words per minute)
        if self.content:
            word_count = len(self.content.split())
            # Use 225 words per minute as average
            self.estimated_read_time = max(1, round(word_count / 225))
        super().save(*args, **kwargs)

class LessonResource(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="resources")
    title = models.CharField(max_length=200)
    type = models.CharField(max_length=50)
    file = models.FileField(upload_to='lesson_resources/', null=True, blank=True)  
    class Meta:
       
        verbose_name_plural = "LessonResource"

class Enrollment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
    ]
    
    student = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='enrollments', db_index=True
    )
    course = models.ForeignKey(
        'Course', on_delete=models.CASCADE, related_name='enrollments', db_index=True
    )
    is_enrolled = models.BooleanField(default=True)
    is_unlocked = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    completed_lessons = models.PositiveIntegerField(default=0)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    progress = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)  # 0.00 to 100.00
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='completed'
    )
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
  
    class Meta:
        unique_together = ['student', 'course']
        ordering = ['-enrolled_at']
        indexes = [
            models.Index(fields=['student', 'course']),
            models.Index(fields=['is_completed']),
        ]
        verbose_name_plural = "Enrollment"
    def calculate_progress(self):
        """Calculate course progress based on completed lessons"""
        total_lessons = Lesson.objects.filter(course=self.course).count()
        if total_lessons == 0:
            self.progress = 0.0
            self.completed_lessons = 0
            self.is_completed = True
            self.completed_at = timezone.now()
        else:
            completed_lessons = LessonProgress.objects.filter(
                enrollment=self, completed=True
            ).count()
            self.completed_lessons = completed_lessons
            self.progress = round((completed_lessons / total_lessons) * 100, 2)
            if completed_lessons == total_lessons:
                self.is_completed = True
                if not self.completed_at:
                    self.completed_at = timezone.now()
            else:
                self.is_completed = False
                self.completed_at = None
        self.save(update_fields=['progress', 'completed_lessons', 'is_completed', 'completed_at'])
        return self.progress
    
    def unlock_first_module(self):
        """Unlock the first module when student enrolls"""
        first_module = Module.objects.filter(course=self.course).order_by('order').first()
        if first_module:
            ModuleProgress.objects.get_or_create(
                enrollment=self,
                module=first_module,
                defaults={'progress': 0.0, 'completed': False}
            )

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
    # The above code is a comment in Python. Comments are used to provide explanations or notes within
    # the code for better understanding. In this case, the comment indicates that the code has been
    # completed.
    completed = models.BooleanField(default=False)
    first_accessed = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_spent = models.DurationField(null=True, blank=True)

    class Meta:
        unique_together = ['enrollment', 'lesson']
        ordering = ['lesson__order']
        verbose_name_plural = "LessonProgress"
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
    
       
        verbose_name_plural = "ResourceProgress"

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
    class Meta:
       
        verbose_name_plural = "Certificate"
    def save(self, *args, **kwargs):
        if not self.certificate_number:
            course_prefix = (self.enrollment.course.title[:3].upper() if len(self.enrollment.course.title) >= 3 else 'CRS')
            self.certificate_number = f"EMR-{course_prefix}-{''.join(random.choices(string.digits, k=8))}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Certificate {self.certificate_number} - {self.enrollment.student.email}"
class CourseBadge(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='badges')
    badge_type = models.CharField(max_length=20, blank=True,null=True)
    awarded_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # Optional expiration date
    is_active = models.BooleanField(default=True)
    # Metrics that led to this badge (optional, for record-keeping)
    enrollment_count = models.IntegerField(null=True, blank=True)  # For bestseller/popular badges
    average_rating = models.FloatField(null=True, blank=True)  # For top rated badges
    view_count = models.IntegerField(null=True, blank=True)  # For trending badges
    
    class Meta:
        unique_together = ['course', 'badge_type']  # One badge type per course
        indexes = [
            models.Index(fields=['course', 'badge_type']),
            models.Index(fields=['badge_type', 'is_active']),
        ]
        
       
        verbose_name_plural = "LessonCourseBadge"
    def __str__(self):
        return f"{self.get_badge_type_display()} - {self.course.title}"

class CourseQA(models.Model):
    """Q&A section for courses where students can ask questions"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='qa_questions')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_questions')
    
    # Question content
    question_title = models.CharField(max_length=200)
    question_text = models.TextField()
    
    # Answer content
    answer_text = models.TextField(blank=True)
    answered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='course_answers')
    answered_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    is_answered = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)  # Pin important questions
    is_public = models.BooleanField(default=True)  # Make question visible to all students
    
    # Voting/Helpful system
    helpful_votes = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_pinned', '-created_at']
      
       
        verbose_name_plural = "CourseQA"
    
    def __str__(self):
        return f"Q&A: {self.question_title} - {self.course.title}"

class CourseResource(models.Model):
    """Additional resources for courses (separate from lesson resources)"""
    RESOURCE_TYPE_CHOICES = [
        ('pdf', 'PDF'),
        ('doc', 'Document'),
        ('link', 'External Link'),
        ('video', 'Video'),
        ('image', 'Image'),
        ('other', 'Other'),
    ]
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='additional_resources')
    
    # Resource information
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPE_CHOICES, default='pdf')
    
    # File or URL
    file = models.FileField(upload_to='course_resources/', null=True, blank=True)
    url = models.URLField(blank=True)
    
    # Organization
    category = models.CharField(max_length=100, blank=True, help_text="e.g., 'Reference Materials', 'Additional Reading'")
    order = models.PositiveIntegerField(default=0)
    
    # Access control
    is_public = models.BooleanField(default=True)  # Visible to all enrolled students
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        
       
        verbose_name_plural = "Course Resources"
    
    def __str__(self):
        return f"{self.title} - {self.course.title}"


class CourseAnnouncement(models.Model):
    """Course announcements from instructors"""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='announcements')
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_announcements')
    
    # Announcement content
    title = models.CharField(max_length=200)
    content = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    
    # Scheduling
    published_at = models.DateTimeField(null=True, blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    
    # Status
    is_published = models.BooleanField(default=True)
    is_pinned = models.BooleanField(default=False)
    send_notification = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_pinned', '-published_at', '-created_at']
       
       
        verbose_name_plural = "Course Announcement"
    
    def __str__(self):
        return f"Announcement: {self.title} - {self.course.title}"


class CheckpointQuizResponse(models.Model):
    """Student responses to checkpoint quizzes embedded in video/text lessons"""
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='checkpoint_responses')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='checkpoint_responses')
    
    # Response data
    selected_answer_index = models.IntegerField()  # Index of selected answer
    is_correct = models.BooleanField(default=False)
    
    # Timing
    responded_at = models.DateTimeField(auto_now_add=True)
    time_taken = models.DurationField(null=True, blank=True)
    
    class Meta:
        unique_together = ['student', 'lesson']  # One response per student per lesson
        ordering = ['-responded_at']
        
       
        verbose_name_plural = "Check Point Response"
    
    def __str__(self):
        return f"{self.student.email} - {self.lesson.title} - {'Correct' if self.is_correct else 'Incorrect'}"

 

class VideoCheckpointQuiz(models.Model):
    """Individual checkpoint quiz questions that appear at specific times during video playback"""
    QUESTION_TYPE_CHOICES = [
        ('multiple-choice', 'Multiple Choice'),
        ('true-false', 'True/False'),
    ]
    
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='video_checkpoint_quizzes')
    
    # Question details
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='multiple-choice')
    options = models.JSONField(default=list, help_text="List of answer options")
    correct_answer_index = models.IntegerField(help_text="Index of correct answer (0-based)")
    explanation = models.TextField(blank=True, help_text="Explanation shown after answering")
    
    # Video timing
    timestamp_seconds = models.IntegerField(help_text="Time in seconds when quiz should appear")
    
    # Display settings
    title = models.CharField(max_length=200, blank=True, help_text="Optional title for the checkpoint quiz")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['timestamp_seconds']
        unique_together = ['lesson', 'timestamp_seconds']  # One quiz per timestamp per lesson
        
       
        verbose_name_plural = "Video Check point Quiz"
    
    def __str__(self):
        return f"{self.lesson.title} - Checkpoint at {self.timestamp_seconds}s"


class VideoCheckpointResponse(models.Model):
    """Student responses to video checkpoint quizzes"""
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='video_checkpoint_responses')
    checkpoint_quiz = models.ForeignKey(VideoCheckpointQuiz, on_delete=models.CASCADE, related_name='responses')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='video_checkpoint_responses')
    
    # Response data
    selected_answer_index = models.IntegerField()  # Index of selected answer
    is_correct = models.BooleanField(default=False)
    
    # Timing
    responded_at = models.DateTimeField(auto_now_add=True)
    time_taken = models.DurationField(null=True, blank=True)
    
    class Meta:
        unique_together = ['student', 'checkpoint_quiz']  # One response per student per checkpoint
        ordering = ['-responded_at']
    
       
        verbose_name_plural = "Video Checkpoint Responses"
    
    def save(self, *args, **kwargs):
        # Auto-calculate if answer is correct
        if self.checkpoint_quiz and hasattr(self.checkpoint_quiz, 'correct_answer_index'):
            self.is_correct = self.selected_answer_index == self.checkpoint_quiz.correct_answer_index
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.student.email} - {self.checkpoint_quiz.lesson.title} checkpoint"


class CourseRating(models.Model):
    """Student ratings and reviews for courses"""
    RATING_CHOICES = [
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    ]
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='ratings')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_ratings')
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='rating', null=True, blank=True)
    
    # Rating data
    rating = models.IntegerField(choices=RATING_CHOICES)
    review_title = models.CharField(max_length=200, blank=True)
    review_text = models.TextField(blank=True)
    
    # Specific rating aspects
    content_quality = models.IntegerField(choices=RATING_CHOICES, null=True, blank=True)
    instructor_quality = models.IntegerField(choices=RATING_CHOICES, null=True, blank=True)
    difficulty_level = models.IntegerField(choices=RATING_CHOICES, null=True, blank=True)
    value_for_money = models.IntegerField(choices=RATING_CHOICES, null=True, blank=True)
    
    # Review metadata
    is_public = models.BooleanField(default=True)
    is_verified_purchase = models.BooleanField(default=False)  # Based on enrollment
    helpful_votes = models.IntegerField(default=0)
    
    # Moderation
    is_approved = models.BooleanField(default=True)
    moderated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderated_ratings')
    moderation_notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['course', 'student']  # One rating per student per course
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['course', 'rating']),
            models.Index(fields=['course', 'is_public', 'is_approved']),
        ]
      
       
        verbose_name_plural = "Course Rating"
    
    def save(self, *args, **kwargs):
        # Set verified purchase based on enrollment
        if self.enrollment or Enrollment.objects.filter(course=self.course, student=self.student).exists():
            self.is_verified_purchase = True
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.student.email} - {self.course.title} - {self.rating} stars"


class Conversation(models.Model):
    """Conversation between teacher and student"""
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='teacher_conversations')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='student_conversations')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='conversations', null=True, blank=True)
    
    # Conversation metadata
    subject = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Last message info for sorting
    last_message_at = models.DateTimeField(auto_now_add=True)
    last_message_sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='last_message_conversations')
    
    class Meta:
        unique_together = ['teacher', 'student']  # One conversation per teacher-student pair
        ordering = ['-last_message_at']
     
       
        verbose_name_plural = "Conversation "
    def __str__(self):
        course_name = self.course.title if self.course else "General"
        return f"{self.teacher.get_full_name()} - {self.student.get_full_name()} - {course_name}"


class Message(models.Model):
    """Individual message in a conversation"""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    
    # Message content
    content = models.TextField()
    message_type = models.CharField(max_length=20, choices=[
        ('text', 'Text'),
        ('assignment_question', 'Assignment Question'),
        ('course_question', 'Course Question'),
        ('general', 'General'),
    ], default='text')
    
    # Message metadata
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    
    # Optional reference to course content
    related_lesson = models.ForeignKey(Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name='related_messages')
    class Meta:
        ordering = ['sent_at']
     
       
        verbose_name_plural = "Message"
    def save(self, *args, **kwargs):
        # Update conversation's last message info
        super().save(*args, **kwargs)
        self.conversation.last_message_at = self.sent_at
        self.conversation.last_message_sender = self.sender
        self.conversation.save()
        
    def mark_as_read(self):
        """Mark message as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()
    
    def __str__(self):
        return f"{self.sender.get_full_name()} to {self.receiver.get_full_name()} - {self.sent_at.strftime('%Y-%m-%d %H:%M')}"


# ------------ Additional Models for Course Details ------------ #

class CourseOverview(models.Model):
    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name="overview")
    total_enrollments = models.PositiveIntegerField(default=0)
    average_rating = models.FloatField(default=0.0)
    completion_rate = models.FloatField(default=0.0)
    title = models.CharField(max_length=200, blank=True)
    subtitle = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    objective = models.JSONField(default=list, blank=True)  # ["Build React apps", ...]
    what_you_will_learn = models.JSONField(default=list, blank=True)
    requirements = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"Overview for {self.course.title}"


class CourseFAQ(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="faqs")
    question = models.CharField(max_length=300)
    answer = models.TextField()

    class Meta:
        verbose_name_plural = "Course FAQ"
        ordering = ["id"]

    def __str__(self):
        return f"FAQ for {self.course.title}: {self.question}"


# ============ Additional Models for LMS Functionality ============

class LessonAttachment(models.Model):
    """Multiple attachments for VideoLesson and ArticleLesson"""
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to='lesson_attachments/')
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Lesson Attachments"
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.lesson.title} - {self.title or self.file.name}"


class QuizResponse(models.Model):
    """Student responses to quiz questions"""
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='responses')
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='student_responses')
    answer = models.ForeignKey(QuizAnswer, on_delete=models.CASCADE, null=True, blank=True, related_name='selected_in_responses')
    answer_text = models.TextField(blank=True, help_text="For fill-in-blank or short answer questions")
    is_correct = models.BooleanField(default=False)
    points_earned = models.FloatField(default=0.0)
    
    class Meta:
        unique_together = ['attempt', 'question']
        verbose_name_plural = "Quiz Responses"
    
    def __str__(self):
        return f"{self.attempt.student.email} - {self.question.question_text[:50]}"


class AssignmentSubmission(models.Model):
    """Student submissions for assignment lessons"""
    SUBMISSION_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('returned', 'Returned'),
    ]
    
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignment_submissions')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='submissions')
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='assignment_submissions')
    
    # Submission content
    submission_text = models.TextField(blank=True)
    submission_file = models.FileField(upload_to='assignment_submissions/', null=True, blank=True)
    submission_url = models.URLField(blank=True)
    github_repo = models.URLField(blank=True, help_text="GitHub repository URL")
    
    # Status and grading
    status = models.CharField(max_length=20, choices=SUBMISSION_STATUS_CHOICES, default='draft')
    score = models.FloatField(null=True, blank=True)
    max_score = models.FloatField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_submissions')
    graded_at = models.DateTimeField(null=True, blank=True)
    
    # Timing
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_late = models.BooleanField(default=False)
    attempt_number = models.PositiveIntegerField(default=1)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-submitted_at']
        verbose_name_plural = "Assignment Submissions"
    
    def save(self, *args, **kwargs):
        # Check if submission is late
        if self.lesson.assignment and self.lesson.assignment.due_date and self.submitted_at:
            if self.submitted_at > self.lesson.assignment.due_date:
                self.is_late = True
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.student.email} - {self.lesson.title} - {self.status}"


class ModuleProgress(models.Model):
    """Track student progress through modules"""
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='module_progress')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='student_progress')
    progress = models.FloatField(default=0.0)  # Percentage 0-100
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    first_accessed = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['enrollment', 'module']
        ordering = ['module__order']
        verbose_name_plural = "Module Progress"
    
    def calculate_progress(self):
        """Calculate progress based on completed lessons in this module"""
        total_lessons = Lesson.objects.filter(module=self.module).count()
        if total_lessons == 0:
            self.progress = 100.0
            self.completed = True
            if not self.completed_at:
                self.completed_at = timezone.now()
        else:
            completed_lessons = LessonProgress.objects.filter(
                enrollment=self.enrollment,
                lesson__module=self.module,
                completed=True
            ).count()
            self.progress = round((completed_lessons / total_lessons) * 100, 2)
            if completed_lessons == total_lessons:
                self.completed = True
                if not self.completed_at:
                    self.completed_at = timezone.now()
            else:
                self.completed = False
                self.completed_at = None
        self.save(update_fields=['progress', 'completed', 'completed_at'])
        return self.progress
    
    def __str__(self):
        return f"{self.enrollment.student.email} - {self.module.title} - {self.progress}%"


class FinalCourseAssessment(models.Model):
    """Final assessment for a course"""
    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name='final_assessment')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    passing_score = models.PositiveIntegerField(default=70, help_text="Passing score percentage")
    max_attempts = models.PositiveIntegerField(default=3, help_text="Maximum attempts allowed")
    time_limit = models.PositiveIntegerField(default=60, help_text="Time limit in minutes")
    randomize_questions = models.BooleanField(default=True)
    show_correct_answers = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Final Course Assessments"
    
    def __str__(self):
        return f"Final Assessment - {self.course.title}"


class AssessmentQuestion(models.Model):
    """Questions for final course assessment"""
    QUESTION_TYPE_CHOICES = [
        ('multiple-choice', 'Multiple Choice'),
        ('true-false', 'True/False'),
        ('fill-blank', 'Fill in Blank'),
        ('short-answer', 'Short Answer'),
    ]
    
    assessment = models.ForeignKey(FinalCourseAssessment, on_delete=models.CASCADE, related_name='questions')
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='multiple-choice')
    question_text = models.TextField()
    question_image = models.ImageField(upload_to='assessment_questions/', null=True, blank=True)
    explanation = models.TextField(blank=True)
    points = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    
    # Fill in blank specific fields
    blanks = models.JSONField(default=list, blank=True, help_text="List of correct answers for blanks")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        verbose_name_plural = "Assessment Questions"
    
    def __str__(self):
        return f"{self.assessment.course.title} - Question {self.order + 1}"


class AssessmentAnswer(models.Model):
    """Answers for assessment questions"""
    question = models.ForeignKey(AssessmentQuestion, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.CharField(max_length=500)
    answer_image = models.ImageField(upload_to='assessment_answers/', null=True, blank=True)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
        verbose_name_plural = "Assessment Answers"
    
    def __str__(self):
        return f"{self.question.question_text[:50]} - {self.answer_text}"


class AssessmentAttempt(models.Model):
    """Student attempts for final course assessment"""
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assessment_attempts')
    assessment = models.ForeignKey(FinalCourseAssessment, on_delete=models.CASCADE, related_name='attempts')
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='assessment_attempts')
    
    score = models.FloatField(default=0.0)  # Percentage score (0-100)
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    total_points = models.FloatField(default=0.0)
    earned_points = models.FloatField(default=0.0)
    passed = models.BooleanField(default=False)
    
    completed_at = models.DateTimeField(auto_now_add=True)
    time_taken = models.DurationField(null=True, blank=True)
    attempt_number = models.PositiveIntegerField(default=1)
    
    class Meta:
        ordering = ['-completed_at']
        verbose_name_plural = "Assessment Attempts"
    
    def calculate_score(self):
        """Calculate the score based on earned points"""
        if self.total_points > 0:
            self.score = (self.earned_points / self.total_points) * 100
            self.passed = self.score >= self.assessment.passing_score
        else:
            self.score = 0.0
            self.passed = False
        self.save()
        return self.score
    
    def __str__(self):
        return f"{self.student.email} - {self.assessment.course.title} - {self.score}% - Attempt {self.attempt_number}"


class AssessmentResponse(models.Model):
    """Student responses to assessment questions"""
    attempt = models.ForeignKey(AssessmentAttempt, on_delete=models.CASCADE, related_name='responses')
    question = models.ForeignKey(AssessmentQuestion, on_delete=models.CASCADE, related_name='student_responses')
    answer = models.ForeignKey(AssessmentAnswer, on_delete=models.CASCADE, null=True, blank=True, related_name='selected_in_responses')
    answer_text = models.TextField(blank=True, help_text="For fill-in-blank or short answer questions")
    is_correct = models.BooleanField(default=False)
    points_earned = models.FloatField(default=0.0)
    
    class Meta:
        unique_together = ['attempt', 'question']
        verbose_name_plural = "Assessment Responses"
    
    def __str__(self):
        return f"{self.attempt.student.email} - {self.question.question_text[:50]}"

    