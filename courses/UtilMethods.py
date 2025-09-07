from django.http import JsonResponse
from rest_framework import status
from django.core.serializers import serialize
from rest_framework.response import Response
from django.utils import timezone 
from rest_framework.pagination import PageNumberPagination
from user_managment.models import User
from .models import Level,Category,Course
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
        

class CustomPagination(PageNumberPagination):
    page_size = 10                      # default number of items per page
    page_size_query_param = 'page_size' # allow client to set page_size
    max_page_size = 100     
    

from django.utils import timezone
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from rest_framework.response import Response
from rest_framework import status

def handle_course_create_or_update(request, serializer_class, get_serializer):
    try:
        # Extract IDs from request
        instructor_id = request.data.get("instructor")
        category_id = request.data.get("category")
        level_id = request.data.get("level")
        course_id = request.data.get("id")  # optional for update

        if not instructor_id:
            return Response(
                {"success": False, "message": "Instructor ID is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Lookup related objects
        try:
            instructor = User.objects.get(pk=instructor_id)
            category = Category.objects.get(pk=category_id)
            level = Level.objects.get(pk=level_id)
        except User.DoesNotExist:
            return Response({"success": False, "message": "Instructor not found"}, status=status.HTTP_404_NOT_FOUND)
        except Category.DoesNotExist:
            return Response({"success": False, "message": "Category not found"}, status=status.HTTP_404_NOT_FOUND)
        except Level.DoesNotExist:
            return Response({"success": False, "message": "Level not found"}, status=status.HTTP_404_NOT_FOUND)

        # Handle status as object, default to 'draft'
        status_code = request.data.get("status", "draft")

        # Prepare save arguments
        save_kwargs = {
            "instructor": instructor,
            "category": category,
            "level": level,
            "status": status_code,
        }

        # Handle thumbnail file from FormData
        thumbnail = request.FILES.get("thumbnail")
        if thumbnail:
            save_kwargs["thumbnail"] = thumbnail

        # CREATE OR UPDATE COURSE
        if course_id:
            try:
                # Update existing course
                instance = Course.objects.get(id=course_id, instructor=instructor)
                serializer = serializer_class(instance, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                instance = serializer.save(**save_kwargs)
                message = "Course updated successfully"
            except Course.DoesNotExist:
                serializer = serializer_class(data=request.data)
                serializer.is_valid(raise_exception=True)
                instance = serializer.save(**save_kwargs)
                message = "Course created successfully"
        else:
            serializer = serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save(**save_kwargs)
            message = "Course created successfully"

        # Ensure instance is fully saved and ID is available
        instance.refresh_from_db()

        # Handle published status
        if status_code == "published":
            instance.submitted_for_approval_at = timezone.now()
            instance.save()
            message = "Course submitted for admin approval! You will be notified when reviewed."

        # Serialize response including course ID
        data = get_serializer(instance).data
        return Response({"success": True, "data": data, "message": message}, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response(
            {"success": False, "message": f"Failed to create or update course: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
