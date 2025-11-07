from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from courses.models import Course, Enrollment, CourseRating
from courses.serializers import DynamicFieldSerializer

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rate_course_view(request, course_id):
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)

    enrollment = Enrollment.objects.filter(student=request.user, course=course, payment_status='completed').first()
    if not enrollment or not enrollment.is_completed:
        return Response({"success": False, "message": "You can rate a course only after completing it."}, status=status.HTTP_403_FORBIDDEN)

    try:
        rating_value = int(request.data.get('rating'))
    except (TypeError, ValueError):
        return Response({"success": False, "message": "Valid rating (1-5) is required."}, status=status.HTTP_400_BAD_REQUEST)
    if rating_value < 1 or rating_value > 5:
        return Response({"success": False, "message": "Rating must be between 1 and 5."}, status=status.HTTP_400_BAD_REQUEST)

    review_title = request.data.get('review_title', '')
    review_text = request.data.get('review_text', '')

    rating_obj, created = CourseRating.objects.update_or_create(
        course=course,
        student=request.user,
        defaults={
            'enrollment': enrollment,
            'rating': rating_value,
            'review_title': review_title,
            'review_text': review_text,
            'is_verified_purchase': True,
        }
    )

    ser = DynamicFieldSerializer(rating_obj, model_name='courserating')
    return Response({"success": True, "data": ser.data, "message": "Rating submitted successfully."}, status=status.HTTP_200_OK)
