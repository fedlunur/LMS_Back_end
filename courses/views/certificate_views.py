from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from courses.models import Enrollment, Certificate
from courses.serializers import DynamicFieldSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_certificate_view(request, enrollment_id):
    """Get certificate for an enrollment (for students and instructors)."""
    try:
        enrollment = Enrollment.objects.get(id=enrollment_id)
        if enrollment.student != request.user and enrollment.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view this certificate."
            }, status=status.HTTP_403_FORBIDDEN)
        
        certificate = getattr(enrollment, 'certificate', None)
        if not certificate:
            return Response({
                "success": False,
                "message": "Certificate not found. Complete the course and pass the final assessment to receive a certificate."
            }, status=status.HTTP_404_NOT_FOUND)
        
        serializer = DynamicFieldSerializer(certificate, model_name="certificate")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Certificate retrieved successfully."
        }, status=status.HTTP_200_OK)
    except Enrollment.DoesNotExist:
        return Response({"success": False, "message": "Enrollment not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([AllowAny])
def verify_certificate_view(request, certificate_number):
    cert = Certificate.objects.filter(certificate_number=certificate_number).select_related('enrollment__student', 'enrollment__course').first()
    if not cert:
        return Response({"success": False, "message": "Certificate not found."}, status=status.HTTP_404_NOT_FOUND)
    data = {
        'certificate_number': cert.certificate_number,
        'issued_date': cert.issued_date,
        'grade': cert.grade,
        'student': {
            'id': cert.enrollment.student_id,
            'name': cert.enrollment.student.get_full_name(),
            'email': cert.enrollment.student.email,
        },
        'course': {
            'id': cert.enrollment.course_id,
            'title': cert.enrollment.course.title,
        }
    }
    return Response({"success": True, "data": data, "message": "Certificate verified."}, status=status.HTTP_200_OK)

