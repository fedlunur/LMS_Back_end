from django.db import models
from django.utils import timezone
from decimal import Decimal

from user_managment.models import User
from courses.models import Course, Enrollment


class Payment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELED, "Canceled"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="payments")
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=10, default="usd")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # Stripe references
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, default="")
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "course"]),
            models.Index(fields=["status"]),
            models.Index(fields=["stripe_checkout_session_id"]),
            models.Index(fields=["stripe_payment_intent_id"]),
        ]

    def mark_succeeded(self, payment_intent_id: str = "", customer_id: str = "") -> None:
        """
        Mark payment as succeeded and record the completed timestamp.
        """
        self.status = self.STATUS_SUCCEEDED
        if payment_intent_id:
            self.stripe_payment_intent_id = payment_intent_id
        if customer_id:
            self.stripe_customer_id = customer_id
        self.completed_at = timezone.now()
        self.save(update_fields=[
            "status", "stripe_payment_intent_id", "stripe_customer_id", "completed_at", "updated_at"
        ])

    def mark_failed(self) -> None:
        """
        Mark payment as failed.
        """
        self.status = self.STATUS_FAILED
        self.save(update_fields=["status", "updated_at"])

    def mark_canceled(self) -> None:
        """
        Mark payment as canceled.
        """
        self.status = self.STATUS_CANCELED
        self.save(update_fields=["status", "updated_at"])

    def __str__(self) -> str:
        return f"{self.user.email} - {self.course.title} - {self.status}"
