from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from courses.services.events_service import (
	_is_instructor,
	get_calendar_events_for_student,
)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_student_calendar_view(request):
	"""
	Get calendar view of upcoming events for enrolled courses (students only).
	Returns events formatted with relative dates (Today, Tomorrow, or date).
	
	Query Parameters:
	- limit: Maximum number of events to return (optional)
	"""
	if _is_instructor(request.user):
		return Response({
			"success": False,
			"message": "This endpoint is for students only."
		}, status=status.HTTP_403_FORBIDDEN)
	
	# Get limit if provided
	try:
		limit_param = request.query_params.get('limit')
		limit = int(limit_param) if limit_param else None
	except (ValueError, TypeError):
		limit = None
	
	# Get formatted calendar events
	events = get_calendar_events_for_student(request.user, limit=limit)
	
	return Response({
		"success": True,
		"data": events,
		"count": len(events),
		"message": "Calendar events retrieved successfully."
	}, status=status.HTTP_200_OK)
