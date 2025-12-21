import resend
from django.conf import settings
# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import EmailOTP
from .serializers import OTPVerifySerializer

resend.api_key = settings.RESEND_API_KEY

def send_otp_email(to_email, otp_code):
    print(f"📧 Sending OTP to {to_email} via Resend...")
    print(f"    OTP Code: {otp_code}")
    params = {
        # "from": "noreply@emerald.edu.et",
        "from_email":"onboarding@resend.dev",
        "to": [to_email],
        "subject": "Your OTP Code",
        "html": f"<p>Your OTP code is <strong>{otp_code}</strong>.</p>",
    }

    # If you have a dev/test mode, you can skip actual send or adjust accordingly
    try:
        response = resend.Emails.send(params)
        return True
    except Exception as e:
        print("❌ Error sending OTP via Resend:", e)
        return False




User = get_user_model()

class VerifyOTPView(APIView):
    permission_classes = []

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp_code']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"success": False, "message": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        otp_entry = EmailOTP.objects.filter(user=user, code=otp_code).order_by('-created_at').first()
        if not otp_entry:
            return Response(
                {"success": False, "message": "Invalid OTP."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if otp_entry.is_expired():
            return Response(
                {"success": False, "message": "OTP expired. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ✅ OTP valid → activate user
        user.is_active = True
        user.save()

        # Optional: Delete old OTPs
        EmailOTP.objects.filter(user=user).delete()

        return Response(
            {"success": True, "message": "OTP verified successfully. Your account is now active."},
            status=status.HTTP_200_OK
        )
