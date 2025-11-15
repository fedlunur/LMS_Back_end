from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404
from django.db.models import Q

from .serializers import ChatbotRequestSerializer, CreateRoomSerializer
from .services import ChatbotService
from .services.data_sources import ChatbotDataFetcher
from .services.gemini import GeminiError
from .models import ChatRoom, ChatMessage
from user_managment.models import User
from courses.models import Course, Enrollment


class ChatbotAPIView(APIView):
    """
    Exposes an endpoint for interacting with the Emerald chatbot.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """
        Returns metadata about the chatbot configuration.
        """
        data_fetcher = ChatbotDataFetcher()
        return Response(
            {
                "available_data_sources": data_fetcher.available_sources(),
            }
        )

    def post(self, request):
        serializer = ChatbotRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = ChatbotService()
        validated = serializer.validated_data
        try:
            response_payload = service.handle_query(
                query=validated["query"],
                session_id=validated.get("session_id"),
                user=request.user if request.user and request.user.is_authenticated else None,
                include_sources=validated.get("include_sources", False),
                requested_sources=validated.get("data_sources"),
            )
        except ImproperlyConfigured as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except GeminiError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(response_payload, status=status.HTTP_200_OK)


class CreateChatRoomAPIView(APIView):
    """
    Create (or return existing) discussion room between student and teacher for a course.
    - If caller is student: create room with course.instructor
    - If caller is teacher: require student_id and create room with that student
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreateRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course_id = serializer.validated_data["course_id"]
        student_id = serializer.validated_data.get("student_id")

        course = get_object_or_404(Course, id=course_id)
        instructor: User = course.instructor
        caller: User = request.user

        # Determine buyer/seller roles in ChatRoom
        if caller.id == instructor.id:
            # Teacher initiating; need student_id
            if not student_id:
                return Response({"detail": "student_id is required for teachers."}, status=status.HTTP_400_BAD_REQUEST)
            buyer = get_object_or_404(User, id=student_id)
            seller = instructor
        else:
            # Student initiating; validate enrollment
            buyer = caller
            seller = instructor
            if not Enrollment.objects.filter(student=buyer, course=course, is_enrolled=True).exists():
                return Response({"detail": "You must be enrolled in this course to start a discussion."}, status=status.HTTP_403_FORBIDDEN)

        # Tie room to course via GenericForeignKey
        course_ct = ContentType.objects.get_for_model(Course)

        # Reuse existing room if any
        existing = ChatRoom.objects.filter(
            contenttype=course_ct,
            objectid=course.id,
            seller=seller,
            buyer=buyer,
        ).select_related('seller', 'buyer').first()
        if existing:
            return Response(
                {
                    "room_number": str(existing.room_number),
                    "course_id": course.id,
                    "course_title": course.title,
                    "teacher_id": seller.id,
                    "teacher_name": seller.get_full_name() or seller.first_name,
                    "student_id": buyer.id,
                    "student_name": buyer.get_full_name() or buyer.first_name,
                    "created": existing.created.isoformat(),
                },
                status=status.HTTP_200_OK,
            )

        room = ChatRoom.objects.create(
            product_id=str(course.id),
            seller=seller,
            buyer=buyer,
            contenttype=course_ct,
            objectid=course.id,
        )
        return Response(
            {
                "room_number": str(room.room_number),
                "course_id": course.id,
                "course_title": course.title,
                "teacher_id": seller.id,
                "teacher_name": seller.get_full_name() or seller.first_name,
                "student_id": buyer.id,
                "student_name": buyer.get_full_name() or buyer.first_name,
                "created": room.created.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class ListUserRoomsAPIView(APIView):
    """
    List rooms for the current user (as seller/teacher or buyer/student).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user: User = request.user
        rooms = ChatRoom.objects.filter(
            Q(seller=user) | Q(buyer=user)
        ).select_related('seller', 'buyer', 'contenttype').order_by("-created")
        
        out = []
        for r in rooms:
            # Get course info if available
            course_info = {}
            if r.contenttype and r.objectid:
                try:
                    course = r.item
                    if course:
                        course_info = {
                            "course_id": course.id,
                            "course_title": course.title,
                        }
                except:
                    pass
            
            # Get other participant info
            other_user = r.buyer if r.seller == user else r.seller
            last_message = r.messages.order_by('-timestamp').first()
            
            out.append({
                "room_number": str(r.room_number),
                "created": r.created.isoformat(),
                "course_id": int(r.product_id) if str(r.product_id).isdigit() else None,
                "teacher_id": r.seller_id,
                "teacher_name": r.seller.get_full_name() or r.seller.first_name,
                "student_id": r.buyer_id,
                "student_name": r.buyer.get_full_name() or r.buyer.first_name,
                "other_user_id": other_user.id,
                "other_user_name": other_user.get_full_name() or other_user.first_name,
                "last_message": {
                    "content": last_message.content if last_message else None,
                    "sender_id": last_message.sender_id if last_message else None,
                    "timestamp": last_message.timestamp.isoformat() if last_message else None,
                } if last_message else None,
                "unread_count": r.messages.filter(
                    sender__id=other_user.id,
                    timestamp__gt=user.last_login if hasattr(user, 'last_login') and user.last_login else r.created
                ).count() if hasattr(user, 'last_login') else 0,
                **course_info,
            })
        return Response(out, status=status.HTTP_200_OK)


class ListRoomMessagesAPIView(APIView):
    """
    List last N messages in a room.
    Query params: limit (default 50), offset (default 0)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, room_number: str):
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))

        room = get_object_or_404(ChatRoom, room_number=room_number)
        # Only participants can view
        if request.user.id not in (room.seller_id, room.buyer_id):
            return Response({"detail": "Not authorized for this room."}, status=status.HTTP_403_FORBIDDEN)

        qs = ChatMessage.objects.filter(room=room).select_related("sender").order_by("-timestamp")
        total = qs.count()
        items = list(qs[offset: offset + limit])[::-1]  # return in ascending order
        messages = [
            {
                "sender_id": m.sender_id,
                "sender_name": m.sender.get_full_name() or m.sender.first_name,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
                "timestamp_display": self._time_ago(m.timestamp),
                "message_id": m.id,
            }
            for m in items
        ]
        return Response({"total": total, "messages": messages}, status=status.HTTP_200_OK)
    
    @staticmethod
    def _time_ago(timestamp):
        """Format timestamp as relative time."""
        from datetime import datetime, timezone
        
        if isinstance(timestamp, str):
            # Convert string timestamp to datetime object
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        now = datetime.now(timezone.utc)
        diff = now - timestamp

        if diff.total_seconds() < 60:
            return "Just now"
        elif diff.total_seconds() < 3600:
            return f"{int(diff.total_seconds() // 60)} minutes ago"
        elif diff.total_seconds() < 86400:
            return f"{int(diff.total_seconds() // 3600)} hours ago"
        else:
            return timestamp.strftime("%b %d, %Y")  # Example: "Nov 15, 2025"
