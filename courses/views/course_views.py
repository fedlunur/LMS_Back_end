from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from courses.services.enrollment_service import enroll_user_in_course
from courses.services.pagination import paginate_queryset_or_list
from ..serializers import DynamicFieldSerializer
from rest_framework.response import Response
from rest_framework import status
from ..models import Course, Enrollment


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def enroll_in_course_view(request, course_id):
    """
    Enroll the authenticated user in a course.
    """
    try:
        course = Course.objects.get(id=course_id)
        success, message = enroll_user_in_course(request.user, course)
        if success:
            enrollment = Enrollment.objects.get(student=request.user, course=course)
            serializer = DynamicFieldSerializer(enrollment, model_name="enrollment")
            return Response({
                "success": True,
                "message": message,
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({"success": False, "message": message}, status=status.HTTP_400_BAD_REQUEST)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_published_courses_view(request):
    """
    Get all published courses available for enrollment (for all authenticated users).
    Includes course overview and enrollment status for the current user.
    """
    courses = Course.objects.filter(
        status='published'
    ).select_related('instructor', 'category', 'level').prefetch_related('overview', 'modules', 'lessons')
    
    # Check which courses the user is enrolled in
    enrolled_course_ids = set(
        Enrollment.objects.filter(
            student=request.user,
            payment_status='completed'
        ).values_list('course_id', flat=True)
    )
    
    courses_data = []
    
    for course in courses:
        course_serializer = DynamicFieldSerializer(course, model_name="course")
        course_dict = course_serializer.data
        
        # Add course overview if exists
        if hasattr(course, 'overview'):
            overview_serializer = DynamicFieldSerializer(course.overview, model_name="course_overview")
            course_dict['overview'] = overview_serializer.data
        else:
            course_dict['overview'] = None
        
        # Add enrollment status
        course_dict['is_enrolled'] = course.id in enrolled_course_ids
        
        # Get enrollment info if enrolled
        if course.id in enrolled_course_ids:
            enrollment = Enrollment.objects.get(student=request.user, course=course)
            course_dict['enrollment'] = {
                'id': enrollment.id,
                'progress': float(enrollment.progress),
                'is_completed': enrollment.is_completed,
                'enrolled_at': enrollment.enrolled_at
            }
        else:
            course_dict['enrollment'] = None
        
        courses_data.append(course_dict)
    
    # Apply pagination
    return paginate_queryset_or_list(request, courses_data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_course_overview_view(request, course_id):
    """
    Get course overview for a published course (for all authenticated users).
    If user is enrolled, also includes their progress.
    """
    try:
        course = Course.objects.select_related('instructor', 'category', 'level').prefetch_related('overview').get(id=course_id)
        
        # Check if course is published
        if course.status != 'published':
            return Response({
                "success": False,
                "message": "Course is not published."
            }, status=status.HTTP_403_FORBIDDEN)
        
        course_serializer = DynamicFieldSerializer(course, model_name="course")
        course_dict = course_serializer.data
        
        # Add course overview
        if hasattr(course, 'overview'):
            overview_serializer = DynamicFieldSerializer(course.overview, model_name="course_overview")
            course_dict['overview'] = overview_serializer.data
        else:
            course_dict['overview'] = None
        
        # Check if user is enrolled
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=course,
            payment_status='completed'
        ).first()
        
        if enrollment:
            course_dict['is_enrolled'] = True
            course_dict['enrollment'] = {
                'id': enrollment.id,
                'progress': float(enrollment.progress),
                'is_completed': enrollment.is_completed,
                'enrolled_at': enrollment.enrolled_at
            }
        else:
            course_dict['is_enrolled'] = False
            course_dict['enrollment'] = None
        
        return Response({
            "success": True,
            "data": course_dict,
            "message": "Course overview retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response({
            "success": False,
            "message": "Course not found."
        }, status=status.HTTP_404_NOT_FOUND)


