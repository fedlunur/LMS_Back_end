from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Q

from courses.models import Event, Course
from courses.services.events_service import (
	_is_instructor,
	can_create_event,
	get_events_for_student,
	get_events_for_instructor,
	get_calendar_events_for_student,
)
from courses.serializers import DynamicFieldSerializer


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_event_view(request):
	"""
	Create a new event (instructors only).
	Instructors can create events for their courses.
	"""
	# Check if user can create events
	can_create, error_message = can_create_event(request.user, request.data.get('course'))
	if not can_create:
		return Response({
			"success": False,
			"message": error_message
		}, status=status.HTTP_403_FORBIDDEN)
	
	# Validate required fields
	title = request.data.get('title')
	start_datetime = request.data.get('start_datetime')
	course_id = request.data.get('course')
	
	if not title:
		return Response({
			"success": False,
			"message": "Title is required."
		}, status=status.HTTP_400_BAD_REQUEST)
	
	if not start_datetime:
		return Response({
			"success": False,
			"message": "Start datetime is required."
		}, status=status.HTTP_400_BAD_REQUEST)
	
	# Validate course if provided
	course = None
	if course_id:
		try:
			course = Course.objects.get(id=course_id)
			# Double-check permission
			if course.instructor != request.user and not request.user.is_staff:
				return Response({
					"success": False,
					"message": "You can only create events for your own courses."
				}, status=status.HTTP_403_FORBIDDEN)
		except Course.DoesNotExist:
			return Response({
				"success": False,
				"message": "Course not found."
			}, status=status.HTTP_404_NOT_FOUND)
	
	# Create event
	try:
		event = Event.objects.create(
			title=title,
			description=request.data.get('description', ''),
			event_type=request.data.get('event_type', 'general'),
			start_datetime=start_datetime,
			end_datetime=request.data.get('end_datetime'),
			course=course
		)
		
		# Serialize the event
		event_data = DynamicFieldSerializer(event, model_name="event").data
		
		return Response({
			"success": True,
			"data": event_data,
			"message": "Event created successfully."
		}, status=status.HTTP_201_CREATED)
	
	except Exception as e:
		return Response({
			"success": False,
			"message": f"Error creating event: {str(e)}"
		}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_events_view(request):
	"""
	List events based on user role with enhanced filtering:
	- Students: see events for courses they are enrolled in
	- Instructors: see events for courses they teach
	
	Query Parameters:
	- course_id: Filter by specific course
	- filter: 'all', 'upcoming', 'past' (default: 'all')
	- event_type: Filter by event type (live_session, deadline, qa_session, meeting, general)
	- start_date: Filter events starting from this date (YYYY-MM-DD)
	- end_date: Filter events ending before this date (YYYY-MM-DD)
	"""
	course_id = request.query_params.get('course_id')
	
	if _is_instructor(request.user):
		# Instructor view
		events = get_events_for_instructor(request.user, course_id=course_id)
	else:
		# Student view - only enrolled courses
		if course_id:
			# Verify student is enrolled in this course
			from courses.models import Enrollment
			is_enrolled = Enrollment.objects.filter(
				student=request.user,
				course_id=course_id,
				payment_status='completed',
				is_enrolled=True
			).exists()
			
			if not is_enrolled:
				return Response({
					"success": False,
					"message": "You are not enrolled in this course."
				}, status=status.HTTP_403_FORBIDDEN)
			
			events = Event.objects.filter(course_id=course_id).select_related('course')
		else:
			events = get_events_for_student(request.user)
	
	# Calculate metadata counts before applying filters (for frontend info)
	now = timezone.now()
	base_events = events  # Keep reference to base queryset for metadata
	total_count = base_events.count()
	upcoming_count = base_events.filter(start_datetime__gte=now).count()
	past_count = base_events.filter(start_datetime__lt=now).count()
	
	# Filter by upcoming/past if requested
	filter_type = request.query_params.get('filter', 'all')
	
	if filter_type == 'upcoming':
		events = events.filter(start_datetime__gte=now)
	elif filter_type == 'past':
		events = events.filter(start_datetime__lt=now)
	
	# Filter by event type
	event_type = request.query_params.get('event_type')
	if event_type:
		events = events.filter(event_type=event_type)
	
	# Filter by date range
	start_date = request.query_params.get('start_date')
	end_date = request.query_params.get('end_date')
	
	if start_date:
		try:
			from datetime import datetime
			start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
			events = events.filter(start_datetime__gte=start_datetime)
		except ValueError:
			pass
	
	if end_date:
		try:
			from datetime import datetime
			end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
			# Include events that end on or before this date
			events = events.filter(
				Q(end_datetime__lte=end_datetime) | 
				Q(end_datetime__isnull=True, start_datetime__lte=end_datetime)
			)
		except ValueError:
			pass
	
	# Order by start_datetime
	events = events.order_by('start_datetime')
	
	# Serialize events
	events_data = []
	for event in events:
		event_dict = DynamicFieldSerializer(event, model_name="event").data
		# Add computed fields for frontend convenience
		event_dict['is_upcoming'] = event.start_datetime >= now if event.start_datetime else False
		event_dict['is_past'] = event.start_datetime < now if event.start_datetime else False
		events_data.append(event_dict)
	
	return Response({
		"success": True,
		"data": events_data,
		"metadata": {
			"total": total_count,
			"upcoming": upcoming_count,
			"past": past_count
		},
		"message": "Events retrieved successfully."
	}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_event_detail_view(request, event_id):
	"""
	Get details of a specific event.
	Students can only see events for courses they are enrolled in.
	Instructors can see events for courses they teach.
	"""
	try:
		event = Event.objects.select_related('course').get(id=event_id)
	except Event.DoesNotExist:
		return Response({
			"success": False,
			"message": "Event not found."
		}, status=status.HTTP_404_NOT_FOUND)
	
	# Check permissions
	if _is_instructor(request.user):
		# Instructor: check if they teach the course
		if event.course and event.course.instructor != request.user and not request.user.is_staff:
			return Response({
				"success": False,
				"message": "You are not authorized to view this event."
			}, status=status.HTTP_403_FORBIDDEN)
	else:
		# Student: check if enrolled in the course
		if event.course:
			from courses.models import Enrollment
			is_enrolled = Enrollment.objects.filter(
				student=request.user,
				course=event.course,
				payment_status='completed',
				is_enrolled=True
			).exists()
			
			if not is_enrolled:
				return Response({
					"success": False,
					"message": "You are not enrolled in this course."
				}, status=status.HTTP_403_FORBIDDEN)
	
	# Serialize event
	event_data = DynamicFieldSerializer(event, model_name="event").data
	
	return Response({
		"success": True,
		"data": event_data,
		"message": "Event retrieved successfully."
	}, status=status.HTTP_200_OK)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_event_view(request, event_id):
	"""
	Update an event (instructors only, for their own courses).
	"""
	try:
		event = Event.objects.select_related('course').get(id=event_id)
	except Event.DoesNotExist:
		return Response({
			"success": False,
			"message": "Event not found."
		}, status=status.HTTP_404_NOT_FOUND)
	
	# Check permissions
	if not _is_instructor(request.user):
		return Response({
			"success": False,
			"message": "Only instructors can update events."
		}, status=status.HTTP_403_FORBIDDEN)
	
	if event.course and event.course.instructor != request.user and not request.user.is_staff:
		return Response({
			"success": False,
			"message": "You can only update events for your own courses."
		}, status=status.HTTP_403_FORBIDDEN)
	
	# Update fields
	if 'title' in request.data:
		event.title = request.data['title']
	if 'description' in request.data:
		event.description = request.data['description']
	if 'event_type' in request.data:
		event.event_type = request.data['event_type']
	if 'start_datetime' in request.data:
		event.start_datetime = request.data['start_datetime']
	if 'end_datetime' in request.data:
		event.end_datetime = request.data.get('end_datetime')
	if 'course' in request.data:
		course_id = request.data['course']
		if course_id:
			try:
				course = Course.objects.get(id=course_id)
				if course.instructor != request.user and not request.user.is_staff:
					return Response({
						"success": False,
						"message": "You can only assign events to your own courses."
					}, status=status.HTTP_403_FORBIDDEN)
				event.course = course
			except Course.DoesNotExist:
				return Response({
					"success": False,
					"message": "Course not found."
				}, status=status.HTTP_404_NOT_FOUND)
		else:
			event.course = None
	
	event.save()
	
	# Serialize updated event
	event_data = DynamicFieldSerializer(event, model_name="event").data
	
	return Response({
		"success": True,
		"data": event_data,
		"message": "Event updated successfully."
	}, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_event_view(request, event_id):
	"""
	Delete an event (instructors only, for their own courses).
	"""
	try:
		event = Event.objects.select_related('course').get(id=event_id)
	except Event.DoesNotExist:
		return Response({
			"success": False,
			"message": "Event not found."
		}, status=status.HTTP_404_NOT_FOUND)
	
	# Check permissions
	if not _is_instructor(request.user):
		return Response({
			"success": False,
			"message": "Only instructors can delete events."
		}, status=status.HTTP_403_FORBIDDEN)
	
	if event.course and event.course.instructor != request.user and not request.user.is_staff:
		return Response({
			"success": False,
			"message": "You can only delete events for your own courses."
		}, status=status.HTTP_403_FORBIDDEN)
	
	event.delete()
	
	return Response({
		"success": True,
		"message": "Event deleted successfully."
	}, status=status.HTTP_200_OK)


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

