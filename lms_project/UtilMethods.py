from django.http import JsonResponse
from rest_framework import status
from django.core.serializers import serialize
from rest_framework.response import Response
from django.utils import timezone 

def success_response(self, data, message, status_code=status.HTTP_200_OK):
        return Response({
            'success': True,
            'data': data,  # Use 'data' instead of 'result'
            'message': message
        }, status=status_code)
def failure_response(self, message, status_code=status.HTTP_400_BAD_REQUEST):
        return Response({
            'success': False,
            'message': message
        }, status=status_code)        
        

