from django.forms import ValidationError
from rest_framework import serializers
from collections import defaultdict

from .models import *
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework.validators import UniqueValidator
from .validations import *

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name']

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name']

class UserRoleSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()  # or use serializers.PrimaryKeyRelatedField()
    role = serializers.StringRelatedField()  # or use serializers.PrimaryKeyRelatedField()

    class Meta:
        model = UserRole
        fields = ['id', 'user', 'role']


#used to create access token and refresh once valid user found 
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['first_name'] = user.first_name
     
        token['id'] = str(user.id)
        token['status'] = user.status
   
        token['email'] = user.email
   
        #Group permissions by model
        permissions = user.user_permissions.all()
        grouped_permissions = defaultdict(list)
        for perm in permissions:
            model = perm.content_type.model
            grouped_permissions[model].append(perm.codename)

        token['permissions'] = grouped_permissions

        # Add user roles
        token['roles'] = [{'id': role.role.id, 'name': role.role.name} for role in user.userrole_set.all()]

        return token

#Account creation Serializers

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('email', 'username', 'password', 'password2')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError(
                {"password": "Password fields didn't match."})

        return attrs

    def create(self, validated_data):
        user = User.objects.create(
          
            email=validated_data['email']

        )
        
       #beacuse we need to hash so this set password 
       
        user.set_password(validated_data['password'])
        user.save()

        return user
    
    
User = get_user_model()

class UserRegisterSerializer(serializers.ModelSerializer):
    email = serializers.CharField(required=True)
    middle_name = serializers.CharField(required=False, allow_blank=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password]
    )
    password2 = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'middle_name', 'isLoggedIn', 'password', 'password2')

    def validate(self, attrs):
        # Check if passwords match
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        
        # Optionally, check if the phone number already exists
        if User.objects.filter(email=attrs['email']).exists():
            raise serializers.ValidationError({"email": "A user with this email already exists."})
        
        return attrs

    def create(self, validated_data):
        # Remove password2 from the validated data as it's not needed for user creation
        validated_data.pop('password2', None)
        
        # Get or create the default "Student" role
        role, _ = Role.objects.get_or_create(name='student')

        # Create the user
        user = User.objects.create(
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            middle_name=validated_data.get('middle_name', ''),
            last_name=validated_data.get('last_name', ''),
            role=role,
            is_staff=False  # Students should not be staff
        )
        
        # Set the password securely
        user.set_password(validated_data['password'])
        user.isLoggedIn=1
        user.save()
        print("User is saved !!!!!!!")
        return user
    
    
    
    
class UserLoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField()

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            raise serializers.ValidationError("Email and password are required.")

        # Check if user exists first
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("No account found with this email.")

        # Now check if the user is active
        if not user.is_active:
            raise serializers.ValidationError(
                "Your account is not activated. Please verify your email."
            )

        # If active, authenticate
        user = authenticate(email=email, password=password)
        if not user:
            raise serializers.ValidationError("Incorrect password. Please try again.")

        return {'user': user}


# Exclude sensitive information from user details
class UserDetailSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    class Meta:
        model = User
        exclude = ('password','isLoggedIn', 'is_superuser', 'is_staff', 'groups', 'user_permissions')
        
        
# serializers.py
from rest_framework import serializers

class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6)
        