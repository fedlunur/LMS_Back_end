from django.http import JsonResponse
from rest_framework import status
from django.core.serializers import serialize
from rest_framework.response import Response
from django.utils import timezone 
from rest_framework.pagination import PageNumberPagination
from user_managment.models import User
from .models import Enrollment, LessonProgress, Lesson, Module, Category, Level, Course


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

def is_lesson_accessible(user, lesson):
    """
    Check if a lesson is accessible for the given user.
    A lesson is accessible if:
    - User is enrolled in the course
    - It's the first lesson, or the previous lesson is completed
    """
    if not user.is_authenticated:
        return False
    
    try:
        enrollment = Enrollment.objects.get(student=user, course=lesson.course)
    except Enrollment.DoesNotExist:
        return False
    
    # Check payment status
    if enrollment.payment_status != 'completed':
        return False
    
    # First lesson is always accessible
    first_lesson = Lesson.objects.filter(course=lesson.course).order_by('order').first()
    if lesson == first_lesson:
        return True
    
    # Find previous lesson
    previous_lesson = Lesson.objects.filter(
        course=lesson.course,
        order__lt=lesson.order
    ).order_by('-order').first()
    
    if not previous_lesson:
        return True  # Should not happen, but safeguard
    
    # Check if previous lesson is completed
    try:
        progress = LessonProgress.objects.get(enrollment=enrollment, lesson=previous_lesson)
        return progress.completed
    except LessonProgress.DoesNotExist:
        return False

def is_module_accessible(user, module):
    """
    Check if a module is accessible for the given user.
    A module is accessible if:
    - User is enrolled in the course
    - It's the first module, or all lessons in the previous module are completed
    """
    if not user.is_authenticated:
        return False
    
    try:
        enrollment = Enrollment.objects.get(student=user, course=module.course)
    except Enrollment.DoesNotExist:
        return False
    
    # Check payment status
    if enrollment.payment_status != 'completed':
        return False
    
    # First module is always accessible
    first_module = Module.objects.filter(course=module.course).order_by('order').first()
    if module == first_module:
        return True
    
    # Find previous module
    previous_module = Module.objects.filter(
        course=module.course,
        order__lt=module.order
    ).order_by('-order').first()
    
    if not previous_module:
        return True  # Safeguard
    
    # Check if all lessons in previous module are completed
    previous_lessons = previous_module.lessons.all()
    for lesson in previous_lessons:
        try:
            progress = LessonProgress.objects.get(enrollment=enrollment, lesson=lesson)
            if not progress.completed:
                return False
        except LessonProgress.DoesNotExist:
            return False
    return True

def enroll_user_in_course(user, course):
    """
    Handle user enrollment in a course.
    For free courses: enroll immediately with payment_status='completed'.
    For paid courses: require payment (future implementation), set payment_status='pending'.
    """
    if course.price > 0:
        # Future: Check payment status
        # For now, create enrollment with pending payment
        enrollment, created = Enrollment.objects.get_or_create(
            student=user,
            course=course,
            defaults={
                'progress': 0.0,
                'payment_status': 'pending'
            }
        )
        if not created:
            return False, "Enrollment already exists."
        return False, "Payment required for this course. Enrollment created with pending payment status."
    
    # Free course: enroll immediately
    if Enrollment.objects.filter(student=user, course=course).exists():
        return False, "Already enrolled in this course."
    
    enrollment = Enrollment.objects.create(
        student=user,
        course=course,
        progress=0.0,
        payment_status='completed'
    )
    enrollment.calculate_progress()
    return True, "Successfully enrolled in the course."

def complete_payment(enrollment_id):
    """
    Mark payment as completed for an enrollment.
    This function can be called from payment webhooks or admin actions in the future.
    """
    try:
        enrollment = Enrollment.objects.get(id=enrollment_id)
        if enrollment.payment_status == 'completed':
            return False, "Payment already completed."
        
        enrollment.payment_status = 'completed'
        enrollment.save()
        enrollment.calculate_progress()
        return True, "Payment completed successfully. Enrollment is now active."
    except Enrollment.DoesNotExist:
        return False, "Enrollment not found."

def mark_lesson_completed(user, lesson_id):
    """
    Mark a lesson as completed for the user.
    Updates lesson progress and cascades to enrollment progress.
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        enrollment = Enrollment.objects.get(student=user, course=lesson.course)
        
        if enrollment.payment_status != 'completed':
            return False, "Payment not completed for this course."
        
        # Check if lesson is accessible
        if not is_lesson_accessible(user, lesson):
            return False, "Lesson is not accessible yet."
        
        # Get or create lesson progress
        progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson,
            defaults={'progress': 0.0}
        )
        
        # Mark as completed
        progress.mark_completed(100.0)
        
        return True, "Lesson marked as completed successfully."
    
    except Lesson.DoesNotExist:
        return False, "Lesson not found."
    except Enrollment.DoesNotExist:
        return False, "You are not enrolled in this course."


