"""
Notification views for accessing and managing user notifications.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q

from courses.models import Notification
from courses.services.notification_service import (
    get_user_notifications,
    mark_notification_as_read,
    mark_all_notifications_as_read,
    get_unread_notification_count
)
from courses.serializers import DynamicFieldSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_notifications_view(request):
    """
    Get all notifications for the authenticated user.
    Query parameters:
    - is_read: Filter by read status (true/false)
    - notification_type: Filter by notification type
    - limit: Limit number of results
    """
    is_read = request.query_params.get('is_read')
    notification_type = request.query_params.get('notification_type')
    limit = request.query_params.get('limit')
    
    notifications = get_user_notifications(
        user=request.user,
        is_read=bool(is_read.lower() == 'true') if is_read else None,
        limit=int(limit) if limit and limit.isdigit() else None
    )
    
    # Filter by notification type if provided
    if notification_type:
        notifications = notifications.filter(notification_type=notification_type)
    
    serializer = DynamicFieldSerializer(notifications, many=True, model_name="notification")
    
    return Response({
        "success": True,
        "data": serializer.data,
        "count": notifications.count()
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_unread_notifications_view(request):
    """Get unread notifications for the authenticated user."""
    notifications = get_user_notifications(user=request.user, is_read=False)
    serializer = DynamicFieldSerializer(notifications, many=True, model_name="notification")
    
    return Response({
        "success": True,
        "data": serializer.data,
        "count": notifications.count()
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_unread_count_view(request):
    """Get count of unread notifications for the authenticated user."""
    count = get_unread_notification_count(request.user)
    
    return Response({
        "success": True,
        "data": {"unread_count": count}
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_notification_read_view(request, notification_id):
    """Mark a specific notification as read."""
    success, message = mark_notification_as_read(notification_id, request.user)
    
    if success:
        return Response({
            "success": True,
            "message": message
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            "success": False,
            "message": message
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read_view(request):
    """Mark all notifications as read for the authenticated user."""
    count = mark_all_notifications_as_read(request.user)
    
    return Response({
        "success": True,
        "message": f"Marked {count} notification(s) as read.",
        "data": {"marked_count": count}
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_notification_view(request, notification_id):
    """Get a specific notification by ID."""
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
        serializer = DynamicFieldSerializer(notification, model_name="notification")
        
        return Response({
            "success": True,
            "data": serializer.data
        }, status=status.HTTP_200_OK)
    except Notification.DoesNotExist:
        return Response({
            "success": False,
            "message": "Notification not found."
        }, status=status.HTTP_404_NOT_FOUND)

