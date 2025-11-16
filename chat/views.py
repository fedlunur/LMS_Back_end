from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
import os

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
            last_message = r.messages.select_related('sender', 'reply_to', 'reply_to__sender').order_by('-timestamp').first()
            
            # Calculate unread count properly using is_read field
            unread_count = ChatMessage.objects.filter(
                room=r,
                sender=other_user,
                is_read=False
            ).count()
            
            # Get file info for last message if exists
            last_message_file_info = None
            if last_message and last_message.file:
                last_message_file_info = {
                    "file_url": last_message.file.url,
                    "file_name": last_message.file_name,
                    "file_size": last_message.file_size,
                    "file_type": last_message.file_type,
                }
            
            # Get reply info for last message if exists
            last_message_reply_to = None
            if last_message and last_message.reply_to:
                last_message_reply_to = {
                    "message_id": last_message.reply_to.id,
                    "sender_id": last_message.reply_to.sender_id,
                    "sender_name": last_message.reply_to.sender.get_full_name() or last_message.reply_to.sender.first_name,
                    "content": last_message.reply_to.content[:100] if last_message.reply_to.content else None,
                    "file_info": {
                        "file_name": last_message.reply_to.file_name,
                        "file_type": last_message.reply_to.file_type,
                    } if last_message.reply_to.file else None,
                }
            
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
                    "file_info": last_message_file_info,
                    "is_read": last_message.is_read if last_message else None,
                    "reply_to": last_message_reply_to,
                } if last_message else None,
                "unread_count": unread_count,
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

        qs = ChatMessage.objects.filter(room=room).select_related("sender", "reply_to", "reply_to__sender").order_by("-timestamp")
        total = qs.count()
        items = list(qs[offset: offset + limit])[::-1]  # return in ascending order
        
        # Get unread count for this room
        other_user = room.buyer if room.seller_id == request.user.id else room.seller
        unread_count = ChatMessage.objects.filter(
            room=room,
            sender=other_user,
            is_read=False
        ).count()
        
        messages = []
        for m in items:
            # Get file info if exists
            file_info = None
            if m.file:
                file_info = {
                    "file_url": m.file.url,
                    "file_name": m.file_name,
                    "file_size": m.file_size,
                    "file_type": m.file_type,
                }
            
            # Get reply information if exists
            reply_to_info = None
            if m.reply_to:
                reply_to_info = {
                    "message_id": m.reply_to.id,
                    "sender_id": m.reply_to.sender_id,
                    "sender_name": m.reply_to.sender.get_full_name() or m.reply_to.sender.first_name,
                    "content": m.reply_to.content[:100] if m.reply_to.content else None,  # Preview
                    "file_info": {
                        "file_name": m.reply_to.file_name,
                        "file_type": m.reply_to.file_type,
                    } if m.reply_to.file else None,
                }
            
            # Determine if message is read for current user
            # If current user is sender, it's always "read"
            is_read_for_user = True if m.sender_id == request.user.id else m.is_read
            
            messages.append({
                "sender_id": m.sender_id,
                "sender_name": m.sender.get_full_name() or m.sender.first_name,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
                "timestamp_display": self._time_ago(m.timestamp),
                "message_id": m.id,
                "file_info": file_info,
                "is_read": is_read_for_user,
                "read_at": m.read_at.isoformat() if m.read_at else None,
                "reply_to": reply_to_info,
            })
        
        return Response({
            "total": total, 
            "messages": messages,
            "unread_count": unread_count,
        }, status=status.HTTP_200_OK)
    
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


class UploadChatFileAPIView(APIView):
    """
    Upload a file for chat message.
    Returns message_id that can be used to send the file via WebSocket.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, room_number: str):
        room = get_object_or_404(ChatRoom, room_number=room_number)
        
        # Only participants can upload files
        if request.user.id not in (room.seller_id, room.buyer_id):
            return Response({"detail": "Not authorized for this room."}, status=status.HTTP_403_FORBIDDEN)
        
        if 'file' not in request.FILES:
            return Response({"detail": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)
        
        uploaded_file = request.FILES['file']
        content = request.data.get('content', '')  # Optional caption/text
        reply_to_id = request.data.get('reply_to_id')  # Optional reply to message ID
        
        # Get file info
        file_name = uploaded_file.name
        file_size = uploaded_file.size
        file_type = uploaded_file.content_type or 'application/octet-stream'
        
        # Get reply_to message if provided
        reply_to_msg = None
        reply_to_info = None
        if reply_to_id:
            try:
                reply_to_msg = ChatMessage.objects.select_related('sender').get(
                    id=reply_to_id,
                    room=room
                )
                reply_to_info = {
                    "message_id": reply_to_msg.id,
                    "sender_id": reply_to_msg.sender_id,
                    "sender_name": reply_to_msg.sender.get_full_name() or reply_to_msg.sender.first_name,
                    "content": reply_to_msg.content[:100] if reply_to_msg.content else None,
                    "file_info": {
                        "file_name": reply_to_msg.file_name,
                        "file_type": reply_to_msg.file_type,
                    } if reply_to_msg.file else None,
                }
            except ChatMessage.DoesNotExist:
                return Response({"detail": "Reply to message not found."}, status=status.HTTP_404_NOT_FOUND)
        
        # Create message with file
        message = ChatMessage.objects.create(
            room=room,
            sender=request.user,
            content=content,
            file=uploaded_file,
            file_name=file_name,
            file_size=file_size,
            file_type=file_type,
            reply_to=reply_to_msg,
        )
        
        return Response({
            "message_id": message.id,
            "file_id": message.id,  # Alias for clarity when using via WebSocket
            "file_url": message.file.url,
            "file_name": message.file_name,
            "file_size": message.file_size,
            "file_type": message.file_type,
            "content": message.content,
            "timestamp": message.timestamp.isoformat(),
            "reply_to": reply_to_info,
        }, status=status.HTTP_201_CREATED)


class MarkMessagesAsReadAPIView(APIView):
    """
    Mark messages as read.
    POST body: {"message_ids": [1, 2, 3]}
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, room_number: str):
        room = get_object_or_404(ChatRoom, room_number=room_number)
        
        # Only participants can mark messages as read
        if request.user.id not in (room.seller_id, room.buyer_id):
            return Response({"detail": "Not authorized for this room."}, status=status.HTTP_403_FORBIDDEN)
        
        message_ids = request.data.get('message_ids', [])
        if not message_ids:
            return Response({"detail": "message_ids is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Only mark messages that belong to this room and are not sent by current user
        messages = ChatMessage.objects.filter(
            id__in=message_ids,
            room=room,
        ).exclude(sender=request.user)
        
        now = timezone.now()
        updated_count = messages.update(is_read=True, read_at=now)
        
        return Response({
            "updated_count": updated_count,
            "message_ids": list(messages.values_list('id', flat=True)),
        }, status=status.HTTP_200_OK)


class GetUnreadCountAPIView(APIView):
    """
    Get unread message count for a room.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, room_number: str):
        room = get_object_or_404(ChatRoom, room_number=room_number)
        
        # Only participants can view unread count
        if request.user.id not in (room.seller_id, room.buyer_id):
            return Response({"detail": "Not authorized for this room."}, status=status.HTTP_403_FORBIDDEN)
        
        # Count unread messages sent by the other user
        other_user = room.buyer if room.seller_id == request.user.id else room.seller
        unread_count = ChatMessage.objects.filter(
            room=room,
            sender=other_user,
            is_read=False
        ).count()
        
        return Response({
            "unread_count": unread_count,
            "room_number": str(room.room_number),
        }, status=status.HTTP_200_OK)
