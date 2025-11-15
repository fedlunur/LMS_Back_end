# Default:

import logging
import os
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.conf import settings
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken, TokenError, AccessToken
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import login, logout
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import IntegrityError

from .models import EmailVerificationToken, PasswordResetToken, User
from .serializers import *
from .services.email_verification import send_email_verification
from .services.password_reset import send_password_reset_email
from django.contrib.auth.password_validation import validate_password

logger = logging.getLogger(__name__)
class TokenCheckView(APIView):
    permission_classes = [AllowAny]  # No authentication required to check token

    def get(self, request, *args, **kwargs):
        token = request.headers.get("Authorization", "").split("Bearer ")[-1]

        if not token or token == "Bearer":
            return Response({"error": "Token missing"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Decode the token
            decoded_token = AccessToken(token)
            return Response({"message": "success", "user_id": decoded_token["user_id"]}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": "Token is invalid or expired"}, status=status.HTTP_401_UNAUTHORIZED)
class UserRolesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        roles = [role.name for role in request.user.groups.all()]
        return Response({'roles': roles})

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Support JWT logout by blacklisting refresh token if provided, and
        also clear Django session to cover session-auth cases.
        Accepts either 'refresh' or 'refresh_token' in the body.
        """
        refresh_token = request.data.get("refresh") or request.data.get("refresh_token")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                return Response(
                    {"success": False, "message": "Invalid or expired refresh token."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        # End session (no-op for pure JWT clients, safe to call)
        logout(request)
        return Response({"success": True, "message": "Logged out successfully."}, status=status.HTTP_200_OK)


import traceback


# class UserRegister(APIView):
#     permission_classes = [AllowAny]

#     def post(self, request):
#         clean_data = self.custom_validation(request.data)
#         serializer = UserRegisterSerializer(data=clean_data)
#         if serializer.is_valid(raise_exception=True):
#             user = serializer.save()
#             return Response(serializer.data, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     def custom_validation(self, data):
#         # Implement your custom validation logic here
#         return data  # Returning the cleaned data
class UserRegister(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        logger.debug("Incoming registration request: %s", request.data)

        try:
            clean_data = self.custom_validation(request.data)
            logger.debug("Registration payload after custom validation: %s", clean_data)
        except ValidationError as exc:
            logger.warning("Custom validation failed: %s", exc)
            return Response(
                {
                    "success": False,
                    "message": "Validation failed.",
                    "errors": getattr(exc, "message_dict", exc.messages if hasattr(exc, "messages") else str(exc)),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = UserRegisterSerializer(data=clean_data)
        if not serializer.is_valid():
            logger.debug("Serializer validation errors: %s", serializer.errors)
            return Response(
                {
                    "success": False,
                    "message": "Validation failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = serializer.save()
            logger.info("User %s created successfully", user.email)
        except IntegrityError as e:
            logger.exception("Integrity error while creating user")
            return Response(
                {
                    "success": False,
                    "message": "A database error occurred. Please try again."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.exception("Unexpected error while creating user")
            return Response(
                {
                    "success": False,
                    "message": "An unexpected error occurred. Please try again later."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            send_email_verification(user)
        except Exception:
            logger.exception("Failed to send verification email to %s", user.email)
            return Response(
                {
                    "success": False,
                    "message": "Account created but failed to send verification email. Please contact support.",
                    "code": "verification_email_failed",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "success": True,
                "result": {
                    "id": user.id,
                    "email": user.email,
                    "is_email_verified": user.is_email_verified,
                },
                "message": "Account created. Please check your email for the verification code.",
            },
            status=status.HTTP_201_CREATED,
        )

    def custom_validation(self, data):
        logger.debug("Running custom validation for registration payload.")

        # Ensure password length is valid
        password = data.get('password', '').strip()
        if len(password) < 3:
            raise ValidationError({"password": ["Password must be at least 3 characters."]})

        # Append a default role if not provided
        # if "role" not in data or not data["role"]:
        #     from .models import Role  # Import inside the function to avoid circular import
        #     default_role = Role.objects.first()  # Get the first available role
        #     if default_role:
        #         data["role"] = default_role.id
        #     else:
        #         raise ValidationError({"role": ["No role found. Please create a role first."]})

        # The serializer will handle role creation, so we don't need to validate it here.

        return data


class VerifyEmailOTP(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        code = request.data.get("code", "").strip()

        if not email or not code:
            return Response(
                {
                    "success": False,
                    "message": "Both email and code are required.",
                    "code": "missing_fields",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "No account found with this email address.",
                    "code": "account_not_found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.is_email_verified:
            refresh = RefreshToken.for_user(user)
            return Response(
                {
                    "success": True,
                    "message": "Email already verified.",
                    "result": {
                        "id": user.id,
                        "email": user.email,
                        "is_email_verified": user.is_email_verified,
                        "access_token": str(refresh.access_token),
                        "refresh_token": str(refresh),
                    },
                },
                status=status.HTTP_200_OK,
            )

        token = (
            EmailVerificationToken.objects.filter(
                user=user, code=code, is_used=False
            )
            .order_by("-created_at")
            .first()
        )

        if not token:
            return Response(
                {
                    "success": False,
                    "message": "Invalid verification code.",
                    "code": "invalid_code",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if token.is_expired:
            token.mark_used()
            return Response(
                {
                    "success": False,
                    "message": "Verification code has expired. Please request a new code.",
                    "code": "code_expired",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        token.mark_used()

        user.is_email_verified = True
        user.enabled = True
        if not user.is_active:
            user.is_active = True
        user.isLoggedIn = 1
        user.save(update_fields=["is_email_verified", "enabled", "is_active", "isLoggedIn"])

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "success": True,
                "message": "Email verified successfully.",
                "result": {
                    "id": user.id,
                    "email": user.email,
                    "is_email_verified": user.is_email_verified,
                    "access_token": str(refresh.access_token),
                    "refresh_token": str(refresh),
                },
            },
            status=status.HTTP_200_OK,
        )

class ResendEmailOTP(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        if not email:
            return Response({"success": False, "message": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"success": False, "message": "No account found with this email address."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.is_email_verified:
            return Response({"success": True, "message": "Email already verified."}, status=status.HTTP_200_OK)

        try:
            token = send_email_verification(user)
        except Exception:
            logger.exception("Failed to resend verification email to %s", user.email)
            return Response(
                {"success": False, "message": "Failed to send verification email. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        payload = {"success": True, "message": "Verification code resent to your email."}

        return Response(payload, status=status.HTTP_200_OK)


class ForgotPasswordRequest(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        if not email:
            return Response({"success": False, "message": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Do not reveal account existence
            return Response({"success": True, "message": "If an account exists, an OTP has been sent."}, status=status.HTTP_200_OK)

        try:
            send_password_reset_email(user)
        except Exception:
            logger.exception("Failed to send password reset email to %s", user.email)
            # Still return generic success to avoid user enumeration
            return Response({"success": True, "message": "If an account exists, an OTP has been sent."}, status=status.HTTP_200_OK)

        return Response({"success": True, "message": "If an account exists, an OTP has been sent."}, status=status.HTTP_200_OK)


class ForgotPasswordReset(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        code = request.data.get("code", "").strip()
        new_password = request.data.get("new_password", "")
        new_password2 = request.data.get("confirm_password") or request.data.get("new_password2") or ""

        if not email or not code or not new_password or not new_password2:
            return Response(
                {"success": False, "message": "Email, code and both password fields are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_password != new_password2:
            return Response({"success": False, "message": "Passwords do not match."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(new_password)
        except Exception as e:
            return Response(
                {"success": False, "message": "Password does not meet requirements.", "errors": getattr(e, "messages", [str(e)])},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Avoid account enumeration
            return Response({"success": False, "message": "Invalid code or email."}, status=status.HTTP_400_BAD_REQUEST)

        token = (
            PasswordResetToken.objects.filter(user=user, code=code, is_used=False)
            .order_by("-created_at").first()
        )

        if not token:
            return Response({"success": False, "message": "Invalid code or email."}, status=status.HTTP_400_BAD_REQUEST)

        if token.is_expired:
            token.mark_used()
            return Response({"success": False, "message": "Code has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)

        # Use token and reset password
        token.mark_used()
        user.set_password(new_password)
        user.save()

        return Response({"success": True, "message": "Password has been reset. You can now log in."}, status=status.HTTP_200_OK)

class UserLogin(APIView):
    permission_classes = [AllowAny]

    @method_decorator(csrf_exempt)
    def post(self, request):
        data = request.data
        serializer = UserLoginSerializer(data=data)

        if not serializer.is_valid():
            return Response(
                {'success': False, 'message': 'Incorrect email number or password', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        email = data.get('email')
        password = data.get('password')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {'success': False, 'message': 'No account found with this email number.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        user = authenticate(request, email=email, password=password)
        print("%% The user will be checked ",user);
        if user is None:
            return Response(
                {'success': False, 'message': 'Incorrect password. Please try again.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_email_verified:
            return Response(
                {
                    'success': False,
                    'message': 'Email not verified. Please verify your email address to continue.',
                    'code': 'email_not_verified',
                },
                status=status.HTTP_403_FORBIDDEN
            )

        if not user.enabled:
            return Response(
                {'success': False, 'message': 'Your account has been deactivated. Contact support for assistance.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Generate JWT tokens (access + refresh)
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        login(request, user)

        # Update login status
        user.isLoggedIn = 1
        user.save()

        return Response({
            'success': True,
            'result': { 
                
                
                 "id": user.id,
                # "accessToken": token.get("access", ""),
                # "refreshToken": token.get("refresh", ""),
                "access_token":access_token,
                "refresh_token": refresh_token,
                "name":user.first_name ,
                "first_name": user.first_name,
                "middle_name": user.middle_name,
                "last_name": user.last_name,
                "role": (user.role.name.lower() if user.role and user.role.name else ""),
                "status": "Active",
                "email": user.email,
                "isLoggedIn": 1,
                
                # 'id': user.id,
                # 'accessToken': access_token,
                # 'refreshToken': refresh_token,  # Now included
                # "FirstName": user.first_name,
                # "LastName": user.middle_name,
                # "role":user.role.name,
                # 'status': user.status,
                # 'email': user.email,
                # 'isLoggedIn': user.isLoggedIn, 
            },
            'message': 'Login successful! Welcome back.',
        }, status=status.HTTP_200_OK)

class UserLogout(APIView):
    permission_classes = [AllowAny]  

    def post(self, request):
        refresh_token = request.data.get("refresh") or request.data.get("refresh_token")
        if not refresh_token:
            return Response(
                {"success": False, "message": "Refresh token required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()  
            return Response(
                {"success": True, "message": "You have been successfully logged out."},
                status=status.HTTP_200_OK,
            )
        except TokenError:
            return Response(
                {"success": False, "message": "Invalid or expired refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

            
class UserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'success': True,
            'data': UserDetailSerializer(request.user, context={'request': request}).data,
            'message': 'User profile retrieved.'
        }, status=status.HTTP_200_OK)


class UpdateProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def _handle_photo_upload(self, request, user):
        """Handle photo file upload and return the path to store"""
        photo_file = request.FILES.get('photo')
        
        if photo_file:
            # Validate file type
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
            file_ext = os.path.splitext(photo_file.name)[1].lower()
            
            if file_ext not in allowed_extensions:
                raise ValidationError(
                    f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}"
                )
            
            # Validate file size (max 5MB)
            max_size = 5 * 1024 * 1024  # 5MB
            if photo_file.size > max_size:
                raise ValidationError("File size exceeds 5MB limit.")
            
            # Generate unique filename
            filename = f"{uuid4().hex}{file_ext}"
            upload_path = os.path.join('user_photos', filename)
            
            # Delete old photo if exists
            if user.photo:
                old_path = user.photo
                # Handle different path formats
                # If it's a full URL, skip deletion (external URL)
                if old_path.startswith(('http://', 'https://')):
                    pass  # Don't delete external URLs
                else:
                    # Remove /media/ prefix if present
                    if old_path.startswith(settings.MEDIA_URL):
                        old_path = old_path[len(settings.MEDIA_URL):].lstrip('/')
                    # Remove leading slash if present
                    old_path = old_path.lstrip('/')
                    # Build full path
                    old_full_path = os.path.join(settings.MEDIA_ROOT, old_path)
                    if os.path.exists(old_full_path):
                        try:
                            os.remove(old_full_path)
                        except Exception as e:
                            logger.warning(f"Failed to delete old photo: {e}")
            
            # Save the file
            file_path = default_storage.save(upload_path, photo_file)
            # Return path relative to MEDIA_ROOT (will be stored in photo field)
            return file_path
        
        # If photo is sent as a string (URL or path), return it
        elif 'photo' in request.data:
            photo_value = request.data.get('photo')
            # If it's None or empty string, allow clearing the photo
            if photo_value == '' or photo_value is None:
                return None
            # If it's a string path/URL, return as-is
            return photo_value
        
        return None

    def patch(self, request):
        try:
            user = request.user
            allowed_fields = ['first_name', 'middle_name', 'last_name', 'phone', 'title', 'bio']
            
            # Handle photo upload separately
            if 'photo' in request.data or 'photo' in request.FILES:
                photo_path = self._handle_photo_upload(request, user)
                if photo_path is not None:
                    user.photo = photo_path
                elif photo_path is None and 'photo' in request.data:
                    # Clear photo if explicitly set to None or empty
                    user.photo = None
            
            # Update other allowed fields
            for field in allowed_fields:
                if field in request.data:
                    setattr(user, field, request.data.get(field))
            
            user.save()
            
            return Response({
                'success': True,
                'data': UserDetailSerializer(user, context={'request': request}).data,
                'message': 'Profile updated successfully.'
            }, status=status.HTTP_200_OK)
        
        except ValidationError as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Error updating user profile")
            return Response({
                'success': False,
                'message': 'An error occurred while updating your profile.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Allow full update via PUT with same allowed fields
    def put(self, request):
        return self.patch(request)

class TeacherDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id):
        try:
            teacher = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"success": False, "message": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        # Ensure role is teacher
        role_name = (teacher.role.name.lower() if teacher.role else '')
        if role_name not in ['teacher', 'instructor']:
            return Response({"success": False, "message": "User is not a teacher."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'success': True,
            'data': UserDetailSerializer(teacher, context={'request': request}).data,
            'message': 'Teacher profile retrieved.'
        }, status=status.HTTP_200_OK)


class UserDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"success": False, "message": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'success': True,
            'data': UserDetailSerializer(user, context={'request': request}).data,
            'message': 'User profile retrieved.'
        }, status=status.HTTP_200_OK)

