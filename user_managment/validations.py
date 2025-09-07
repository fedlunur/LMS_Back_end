
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
UserModel = get_user_model()

from rest_framework.exceptions import ValidationError

def custom_validation(data):
    # Ensure the input is a dictionary
    if not isinstance(data, dict):
        raise ValidationError('Expected data to be a dictionary.')
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    # Check if email is provided and not already used
    if not email or UserModel.objects.filter(email=email).exists():
        raise ValidationError('Choose another email.')

    # Check password length
    if not password or len(password) < 8:
        raise ValidationError('Choose another password, min 8 characters.')

    # Ensure username is provided
    if not username:
        raise ValidationError('Choose another username.')

    return data



# def validate_password(data):
#     print("The incoming data is",data);
  
#     password = data.get('password', '').strip()
#     if not password:
#         raise ValidationError('a password is needed')
#     return True
