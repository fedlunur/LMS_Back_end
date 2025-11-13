from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save  # helps
from django.dispatch import receiver
from django.utils import timezone

# Create your models here.
class UserManager(BaseUserManager):
    def create_user(self, email, first_name, middle_name=None, password=None, **extra_fields):
        """
        Creates and returns a regular user with the given email, first name, and password.
        """
        if not email:
            raise ValueError('The email field must be set')
        if not first_name:
            raise ValueError('The First Name field must be set')

 
        user = self.model(
            email=email,
            first_name=first_name,
            middle_name=middle_name,
            
            **extra_fields
        )
        if password:
            user.set_password(password)  # Hash the password
        else:
            user.set_unusable_password()  # Prevent login if no password is provided

        user.save(using=self._db)
        return user

    def create_superuser(self, email, first_name, password=None, **extra_fields):
        """
        Creates and returns a superuser with the given email, first name, and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, first_name, password=password, **extra_fields)

class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def clean(self):
        super().clean()
        if self.name:
            normalized = self.name.strip().lower()
            # Canonicalize known aliases
            if normalized in ('instructor',):
                normalized = 'teacher'
            if normalized in ('students',):
                normalized = 'student'

            # Check for case-insensitive duplicates
            qs = Role.objects.filter(name__iexact=normalized)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({'name': 'Role with this name already exists.'})

            # Assign normalized name after validation
            self.name = normalized

    def save(self, *args, **kwargs):
        # Just save — validation happens via clean() in admin/forms
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name



class User(AbstractUser):
    first_name = models.CharField(max_length=255, null=False)
    middle_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    email= models.EmailField( max_length=254,unique=True)
    photo = models.CharField(max_length=255, blank=True, null=True)
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True,blank=True, related_name='users')
    status = models.CharField(max_length=255, default='Active')
    removed = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    is_email_verified = models.BooleanField(default=False)
    created = models.DateTimeField(default=timezone.now)
    isLoggedIn = models.IntegerField(default=0)
    # Instructor-specific fields
    title = models.CharField(max_length=200, blank=True, null=True, help_text="Professional title (e.g., 'Senior Software Engineer')")
    bio = models.TextField(max_length=500, blank=True, null=True, help_text="Instructor biography")
    
    def get_full_name(self):
        """Get full name"""
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        if self.last_name:
            parts.append(self.last_name)
        return ' '.join(parts)
    USERNAME_FIELD = 'email'  # Use phone as the username
    REQUIRED_FIELDS = ['first_name',]
    objects = UserManager()
   
    def save(self, *args, **kwargs):
    # Generate a unique username if not set
        if not self.username:
            base_username = self.email.split('@')[0]
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            self.username = username

        # Set default password if not set
        if not self.password:
            self.set_password("changeme")

        super().save(*args, **kwargs)


    def __str__(self):
        return f'{self.first_name}'

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'
        

class EmailVerificationToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verification_tokens",
    )
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "code"]),
            models.Index(fields=["expires_at"]),
        ]

    def mark_used(self, commit: bool = True):
        self.is_used = True
        if commit:
            self.save(update_fields=["is_used"])

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self):
        status = "used" if self.is_used else "pending"
        return f"{self.user.email} - {self.code} ({status})"


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
   
    class Meta:
        unique_together = ('user', 'role')   
    
    def __str__(self):
        return f'{self.user.first_name} - {self.role.name}'


class UserLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    def __str__(self):
        return f"{self.user} - {self.action} at {self.timestamp}"
   
    
    