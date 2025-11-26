from django.utils import timezone
from courses.models import Event, Enrollment


def _is_instructor(user):
	"""Check if user is an instructor (staff or has teacher role)"""
	return bool(getattr(user, 'is_staff', False) or (getattr(user, 'role', None) and getattr(user.role, 'name', '').lower() == 'teacher'))


def get_student_enrolled_courses(user):
	"""
	Get list of course IDs that the student is enrolled in.
	Returns only courses with completed payment and active enrollment.
	"""
	enrollments = Enrollment.objects.filter(
		student=user,
		payment_status='completed',
		is_enrolled=True
	).values_list('course_id', flat=True)
	
	return list(enrollments)


def format_event_for_calendar(event, now=None):
	"""
	Format an event for calendar display with relative dates.
	Returns a dict with formatted date/time strings.
	"""
	if now is None:
		now = timezone.now()
	
	start = event.start_datetime
	if not start:
		return None
	
	# Calculate time difference
	time_diff = start - now
	days_diff = time_diff.days
	
	# Format date
	if days_diff == 0:
		date_str = "Today"
	elif days_diff == 1:
		date_str = "Tomorrow"
	elif days_diff == -1:
		date_str = "Yesterday"
	else:
		# Format as "Dec 18" or "Dec 18, 2025" if different year
		if start.year == now.year:
			date_str = start.strftime("%b %d")
		else:
			date_str = start.strftime("%b %d, %Y")
	
	# Format time
	time_str = start.strftime("%I:%M %p")
	if time_str.startswith('0'):
		time_str = time_str[1:]  # "2:00 PM" instead of "02:00 PM"
	
	return {
		"event_id": event.id,
		"title": event.title,
		"course_title": event.course.title if event.course else None,
		"course_id": event.course.id if event.course else None,
		"event_type": event.event_type.name if event.event_type else None,
		"event_type_id": event.event_type.id if event.event_type else None,
		"event_type_display": event.event_type.display_name if event.event_type else "General Event",
		"description": event.description,
		"date_str": date_str,
		"time_str": time_str,
		"start_datetime": start.isoformat(),
		"end_datetime": event.end_datetime.isoformat() if event.end_datetime else None,
		"is_today": days_diff == 0,
		"is_tomorrow": days_diff == 1,
		"is_past": days_diff < 0,
		"days_until": days_diff,
	}


def get_calendar_events_for_student(user, limit=None):
	"""
	Get upcoming events formatted for calendar display.
	Returns events from enrolled courses, formatted with relative dates.
	"""
	enrolled_course_ids = get_student_enrolled_courses(user)
	if not enrolled_course_ids:
		return []
	
	now = timezone.now()
	
	# Get upcoming events (including today)
	events = Event.objects.filter(
		course_id__in=enrolled_course_ids,
		start_datetime__gte=now.replace(hour=0, minute=0, second=0, microsecond=0)  # From start of today
	).select_related('course', 'event_type').order_by('start_datetime')
	
	if limit:
		events = events[:limit]
	
	# Format events for calendar
	formatted_events = []
	for event in events:
		formatted = format_event_for_calendar(event, now)
		if formatted:
			formatted_events.append(formatted)
	
	return formatted_events
