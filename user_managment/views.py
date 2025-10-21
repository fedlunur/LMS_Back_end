from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import login, logout
from .serializers import *
from collections import defaultdict
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import IntegrityError
from rest_framework_simplejwt.tokens import AccessToken

from rest_framework import generics
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
        logout(request)
        return Response(status=status.HTTP_200_OK)


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

    def post(self, request):
        print("📌 Incoming request data:", request.data)  # Log request data

        
        clean_data = self.custom_validation(request.data)  # Validate data first
        print("✅ Data after validation:", clean_data)  # Log validated data
            
        serializer = UserRegisterSerializer(data=clean_data)  # Attempt to create serializer
        print("🛠️ Serializer initialized successfully.")
        try:
            if serializer.is_valid(raise_exception=True):
                user = serializer.save()
                token = self.get_token(user)
                return Response(self.get_user_data(user, token), status=status.HTTP_201_CREATED)

        except ValidationError as e:
            print("⚠️ ValidationError:", e)  # Log error
            errors = serializer.errors if 'serializer' in locals() else {"error": "Serializer failed before validation"}
            return Response(
                {
                    "success": False,
                    "message": "Validation failed.",
                    "errors": errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        except IntegrityError as e:
            print("⚠️ IntegrityError:", e)
            return Response(
                {
                    "success": False,
                    "message": "A database error occurred. Please try again."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            print("❌ Unexpected error:", e)
            return Response(
                {
                    "success": False,
                    "message": "An unexpected error occurred. Please try again later."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def custom_validation(self, data):
        print("🔍 Validating input data...")

        # Ensure password length is valid
        password = data.get('password', '').strip()
        if len(password) < 3:
            raise ValidationError({"password": ["Password must be at least 3 characters."]})

        # Append a default role if not provided
        if "role" not in data or not data["role"]:
            from .models import Role  # Import inside the function to avoid circular import
            default_role = Role.objects.first()  # Get the first available role
            if default_role:
                data["role"] = default_role.id
            else:
                raise ValidationError({"role": ["No role found. Please create a role first."]})

        return data



    def get_token(self, user):
        """
        Generates and returns both access and refresh tokens for the user.
        """
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh)
        }

    def get_user_data(self, user, token):
        return {
            "success": True,
            "result": {
                "id": user.id,
                # "accessToken": token.get("access", ""),
                # "refreshToken": token.get("refresh", ""),
                "access_token": token.get("access", ""),
                "refresh_token": token.get("refresh", ""),
                "name":user.first_name ,
                "first_name": user.first_name,
                "middle_name": user.middle_name,
                "last_name": user.last_name,
                "role":user.role.name,
                "status": "Active",
                "email": user.email,
                "isLoggedIn": 1,
            },
            "message": "Account created successfully!",
        }


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
                "role":user.role.name,
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
        logout(request)
        return Response(status=status.HTTP_200_OK)

class UserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response({'user': serializer.data}, status=status.HTTP_200_OK)

