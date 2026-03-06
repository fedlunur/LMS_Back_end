from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

from user_managment.models import User


class FeedbackForm(models.Model):
    """
    Standalone feedback form not directly tied to courses.
    Can still store a generic target_type/target_id pair if needed,
    but there is no foreign key to Course.
    """

    TARGET_TYPE_CHOICES = [
        ("global", "Global"),
        ("custom", "Custom"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_feedback_forms"
    )
    target_type = models.CharField(
        max_length=50,
        choices=TARGET_TYPE_CHOICES,
        default="global",
        help_text="Optional logical grouping for this form (no FK).",
    )
    target_id = models.PositiveIntegerField(
        default=0,
        help_text="Optional numeric identifier, meaning depends on target_type.",
    )
    is_published = models.BooleanField(default=False)
    allow_anonymous = models.BooleanField(default=False)
    allow_multiple_submissions = models.BooleanField(default=False)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Feedback Forms"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_by", "created_at"]),
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["is_published", "start_at", "end_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_active(self) -> bool:
        """Return True when the form is within its configured availability window."""
        now = timezone.now()
        if self.start_at and now < self.start_at:
            return False
        if self.end_at and now > self.end_at:
            return False
        return True


class FeedbackQuestion(models.Model):
    """
    Question belonging to a feedback form.
    """

    QUESTION_TYPE_CHOICES = [
        ("text", "Short Text"),
        ("textarea", "Long Text"),
        ("single_choice", "Single Choice"),
        ("multi_choice", "Multiple Choice"),
        ("rating", "Rating"),
        ("yes_no", "Yes/No"),
    ]

    form = models.ForeignKey(
        FeedbackForm, on_delete=models.CASCADE, related_name="questions"
    )
    question_text = models.TextField()
    question_type = models.CharField(max_length=50, choices=QUESTION_TYPE_CHOICES)
    is_required = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    settings_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Feedback Questions"
        ordering = ["form_id", "sort_order", "id"]
        indexes = [
            models.Index(fields=["form", "sort_order"]),
        ]

    def __str__(self) -> str:
        return f"{self.form.title} - {self.question_text[:50]}"


class FeedbackQuestionOption(models.Model):
    """
    Options for choice-based feedback questions.
    """

    question = models.ForeignKey(
        FeedbackQuestion, on_delete=models.CASCADE, related_name="options"
    )
    option_label = models.CharField(max_length=255)
    option_value = models.CharField(
        max_length=255,
        help_text="Machine-readable value submitted when this option is selected.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Feedback Question Options"
        ordering = ["question_id", "sort_order", "id"]
        indexes = [
            models.Index(fields=["question", "sort_order"]),
        ]

    def __str__(self) -> str:
        return f"{self.option_label} ({self.option_value})"


class FeedbackSubmission(models.Model):
    """
    A single submission of a feedback form by a student (or anonymous).
    """

    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("draft", "Draft"),
    ]

    form = models.ForeignKey(
        FeedbackForm, on_delete=models.CASCADE, related_name="submissions"
    )
    student = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_submissions",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="submitted"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Feedback Submissions"
        ordering = ["-submitted_at", "-created_at"]
        indexes = [
            models.Index(fields=["form", "student"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"Feedback for {self.form.title} by {getattr(self.student, 'email', 'anonymous')}"

    def clean(self):
        """
        Enforce at the application level that a student can only submit
        once for a given form when that form does not allow multiple submissions.
        """
        super().clean()

        if self.student_id and not self.form.allow_multiple_submissions:
            existing = FeedbackSubmission.objects.filter(
                form=self.form,
                student=self.student,
            )
            if self.pk:
                existing = existing.exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError(
                    {
                        "student": "You have already submitted feedback for this form."
                    }
                )


class FeedbackAnswer(models.Model):
    """
    Answer to a single feedback question within a submission.
    Stores multiple representations to support different question types.
    """

    submission = models.ForeignKey(
        FeedbackSubmission, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(
        FeedbackQuestion, on_delete=models.CASCADE, related_name="answers"
    )
    answer_text = models.TextField(blank=True)
    answer_number = models.FloatField(null=True, blank=True)
    answer_bool = models.BooleanField(null=True, blank=True)
    answer_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Feedback Answers"
        unique_together = [("submission", "question")]
        indexes = [
            models.Index(fields=["submission", "question"]),
        ]

    def __str__(self) -> str:
        return f"Answer to Q{self.question_id} in submission {self.submission_id}"


