from rest_framework.response import Response
from rest_framework import status

def success_response(data=None, message="Success", status_code=status.HTTP_200_OK):
    return Response({"success": True, "data": data, "message": message}, status=status_code)

def failure_response(message="Error", status_code=status.HTTP_400_BAD_REQUEST):
    return Response({"success": False, "message": message}, status=status_code)