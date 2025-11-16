from django.utils import timezone
from django.db.models import Avg, Sum

from courses.models import Course, Enrollment, LessonProgress, AssignmentSubmission, CourseQA, QuizAttempt, AssignmentLesson, LessonResource, CourseResource


def _is_instructor(user):
	return bool(getattr(user, 'is_staff', False) or (getattr(user, 'role', None) and getattr(user.role, 'name', '').lower() == 'teacher'))


def _student_display_name(user):
	full_name = ""
	try:
		full_name = user.get_full_name()
	except Exception:
		full_name = ""
	return full_name or getattr(user, "username", None) or getattr(user, "email", "") or f"User {getattr(user, 'id', '')}"


def compute_teacher_earnings_overview(instructor):
	now = timezone.now()
	start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

	base_enroll_qs = Enrollment.objects.filter(
		course__instructor=instructor,
		payment_status='completed',
		is_enrolled=True
	).select_related('course')

	total_earnings_val = base_enroll_qs.aggregate(total=Sum('course__price')).get('total') or 0
	this_month_earnings_val = base_enroll_qs.filter(enrolled_at__gte=start_of_month).aggregate(total=Sum('course__price')).get('total') or 0

	total_enrolled_students = base_enroll_qs.values('student_id').distinct().count()
	active_courses = Course.objects.filter(instructor=instructor, status='published', enrollments__in=base_enroll_qs).distinct().count()

	return {
		"total_earnings": round(float(total_earnings_val), 2),
		"this_month_earnings": round(float(this_month_earnings_val), 2),
		"currency": "USD",
		"total_enrolled_students": total_enrolled_students,
		"active_courses": active_courses
	}


def compute_teacher_revenue_history(instructor):
	courses_qs = Course.objects.filter(instructor=instructor)
	revenue_items = []
	for course in courses_qs:
		enrolls = Enrollment.objects.filter(
			course=course,
			payment_status='completed',
			is_enrolled=True
		).order_by('-enrolled_at')
		if not enrolls.exists():
			continue
		students_enrolled = enrolls.count()
		total_amount = enrolls.aggregate(total=Sum('course__price')).get('total') or 0
		last_paid_at = enrolls.first().enrolled_at
		revenue_items.append({
			"course_id": course.id,
			"course_title": course.title,
			"students_enrolled": students_enrolled,
			"amount": round(float(total_amount), 2),
			"currency": "USD",
			"last_paid_at": last_paid_at
		})
	revenue_items.sort(key=lambda item: item.get("last_paid_at") or timezone.datetime.min.replace(tzinfo=timezone.utc), reverse=True)
	return revenue_items


def compute_teacher_monthly_revenue_trend(instructor):
	now = timezone.now()

	def start_of_month(dt):
		return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

	months = []
	cur = start_of_month(now)
	for _ in range(12):
		months.append(cur)
		year = cur.year if cur.month > 1 else cur.year - 1
		month = cur.month - 1 if cur.month > 1 else 12
		cur = cur.replace(year=year, month=month)
	months = list(reversed(months))

	base_enroll_qs = Enrollment.objects.filter(
		course__instructor=instructor,
		payment_status='completed',
		is_enrolled=True
	)

	trend = []
	prev_revenue = None
	for month_start in months:
		year = month_start.year if month_start.month < 12 else month_start.year + 1
		month = month_start.month + 1 if month_start.month < 12 else 1
		next_month_start = month_start.replace(year=year, month=month)

		month_qs = base_enroll_qs.filter(enrolled_at__gte=month_start, enrolled_at__lt=next_month_start)
		month_students = month_qs.count()
		month_revenue_val = float(month_qs.aggregate(total=Sum('course__price')).get('total') or 0.0)

		change_pct = 0.0
		if prev_revenue is None:
			change_pct = 0.0
		elif prev_revenue > 0.0:
			change_pct = round(((month_revenue_val - prev_revenue) / prev_revenue) * 100.0, 1)
		elif month_revenue_val > 0.0:
			change_pct = 100.0

		trend.append({
			"month_label": month_start.strftime("%B %Y"),
			"students": month_students,
			"revenue": round(month_revenue_val, 2),
			"currency": "USD",
			"change_pct_mom": change_pct
		})
		prev_revenue = month_revenue_val
	return trend


def compute_teacher_student_engagement_metrics(instructor):
	base_enroll_qs = Enrollment.objects.filter(
		course__instructor=instructor,
		payment_status='completed',
		is_enrolled=True
	).select_related('student', 'course')

	total_students = base_enroll_qs.values('student_id').distinct().count()

	lp_qs = LessonProgress.objects.filter(enrollment__in=base_enroll_qs)
	total_lp = lp_qs.count()
	completed_lp = lp_qs.filter(completed=True).count()
	video_completion_rate = round((completed_lp / total_lp) * 100.0, 1) if total_lp > 0 else 0.0

	as_qs = AssignmentSubmission.objects.filter(lesson__course__instructor=instructor)
	students_with_submission = as_qs.values('student_id').distinct().count()
	assignment_submission_rate = round((students_with_submission / total_students) * 100.0, 1) if total_students > 0 else 0.0

	qa_qs = CourseQA.objects.filter(course__instructor=instructor)
	students_in_discussion = qa_qs.values('student_id').distinct().count()
	discussion_participation_rate = round((students_in_discussion / total_students) * 100.0, 1) if total_students > 0 else 0.0

	attempt_qs = QuizAttempt.objects.filter(lesson__course__instructor=instructor, is_in_progress=False)
	avg_score = attempt_qs.aggregate(avg=Avg('score')).get('avg') or 0.0
	quiz_performance_avg = round(float(avg_score), 1)

	targets = {
		"video_completion_rate": 70.0,
		"assignment_submission_rate": 70.0,
		"discussion_participation_rate": 70.0,
		"quiz_performance_avg": 70.0,
	}

	def status_label(value, target):
		return "Target met" if value >= target else "Below target"

	return {
		"video_completion_rate": {
			"value_pct": video_completion_rate,
			"target_pct": targets["video_completion_rate"],
			"status": status_label(video_completion_rate, targets["video_completion_rate"])
		},
		"assignment_submission_rate": {
			"value_pct": assignment_submission_rate,
			"target_pct": targets["assignment_submission_rate"],
			"status": status_label(assignment_submission_rate, targets["assignment_submission_rate"])
		},
		"discussion_participation_rate": {
			"value_pct": discussion_participation_rate,
			"target_pct": targets["discussion_participation_rate"],
			"status": status_label(discussion_participation_rate, targets["discussion_participation_rate"])
		},
		"quiz_performance_avg": {
			"value_pct": quiz_performance_avg,
			"target_pct": targets["quiz_performance_avg"],
			"status": status_label(quiz_performance_avg, targets["quiz_performance_avg"])
		}
	}


def compute_teacher_dashboard_overview(instructor, course_id: int | None = None):
	queryset = Course.objects.filter(instructor=instructor)
	if course_id is not None:
		queryset = queryset.filter(id=course_id)
	courses = queryset.prefetch_related('enrollments', 'ratings')
	data = []
	for course in courses:
		enroll_qs = course.enrollments.filter(payment_status='completed', is_enrolled=True)
		total_students = enroll_qs.values('student_id').distinct().count()
		completed_count = enroll_qs.filter(is_completed=True).count()
		completion_rate = round((completed_count / total_students) * 100, 2) if total_students > 0 else 0.0
		avg_rating = round(course.ratings.aggregate(avg=Avg('rating')).get('avg') or 0.0, 1)
		data.append({
			"course_id": course.id,
			"course_title": course.title,
			"total_students": total_students,
			"completion_rate": completion_rate,
			"average_rating": avg_rating,
		})
	return data


def compute_teacher_top_performers(instructor, limit: int = 5):
	"""
	Top performers across all courses of this instructor.
	- performance_pct: highest enrollment progress across instructor's courses
	- course_title: the course where the student achieved that highest progress
	- assignments_count: number of assignment submissions by the student in instructor's courses
	"""
	from django.db.models import Prefetch

	# Eligible enrollments
	enrollments = (
		Enrollment.objects
		.filter(
			course__instructor=instructor,
			payment_status='completed',
			is_enrolled=True
		)
		.select_related('student', 'course')
	)

	# Aggregate per student
	students_map = {}
	for e in enrollments:
		stu_id = e.student_id
		if stu_id not in students_map:
			students_map[stu_id] = {
				"student": e.student,
				"best_progress": float(e.progress or 0.0),
				"best_course": e.course,
			}
		else:
			cur_best = students_map[stu_id]["best_progress"]
			progress_val = float(e.progress or 0.0)
			if progress_val > cur_best:
				students_map[stu_id]["best_progress"] = progress_val
				students_map[stu_id]["best_course"] = e.course

	if not students_map:
		return []

	# Precompute assignment submission counts per student for this instructor's courses
	assign_counts = (
		AssignmentSubmission.objects
		.filter(lesson__course__instructor=instructor)
		.values('student_id')
		.order_by()
		.annotate(total=Sum(1))  # use Sum(1) as simple count aggregator
	)
	student_to_assign_total = {row['student_id']: int(row['total'] or 0) for row in assign_counts}

	# Build and sort
	items = []
	for stu_id, data in students_map.items():
		student = data["student"]
		best_course = data["best_course"]
		items.append({
			"student_id": stu_id,
			"student_name": _student_display_name(student),
			"course_title": getattr(best_course, "title", None) or "",
			"performance_pct": round(float(data["best_progress"]), 1),
			"assignments_count": student_to_assign_total.get(stu_id, 0),
		})

	items.sort(key=lambda x: (x["performance_pct"], x["assignments_count"]), reverse=True)

	# Add rank
	for idx, item in enumerate(items, start=1):
		item["rank"] = idx

	return items[:limit]

def compute_teacher_recent_activities(instructor):
	now = timezone.now()

	def ago(dt):
		if not dt:
			return None
		from django.utils.timesince import timesince
		return f"{timesince(dt, now)} ago"

	course_ids = list(Course.objects.filter(instructor=instructor).values_list('id', flat=True))
	activities = []

	submissions = AssignmentSubmission.objects.filter(
		lesson__course_id__in=course_ids,
		status='submitted'
	).select_related('student', 'lesson', 'lesson__course').order_by('-submitted_at')[:10]
	for s in submissions:
		activities.append({
			"type": "assignment_submission",
			"title": "New Assignment Submission",
			"user_name": s.student.get_full_name() or s.student.email,
			"course_title": s.lesson.course.title,
			"lesson_title": s.lesson.title,
			"time_ago": ago(s.submitted_at or s.created_at),
			"status_label": "Pending Review",
			"action_label": "Grade",
			"created_at": (s.submitted_at or s.created_at),
			"meta": {"submission_id": s.id}
		})

	from courses.models import Enrollment as EnrollmentModel
	completed_enrollments = EnrollmentModel.objects.filter(
		course_id__in=course_ids,
		is_completed=True,
		payment_status='completed'
	).select_related('student', 'course', 'certificate').order_by('-completed_at')[:10]
	for e in completed_enrollments:
		activities.append({
			"type": "course_completed",
			"title": "Course Completed",
			"user_name": e.student.get_full_name() or e.student.email,
			"course_title": e.course.title,
			"time_ago": ago(e.completed_at or e.updated_at),
			"status_label": "Certificate Ready" if hasattr(e, 'certificate') or getattr(e.course, "issue_certificate", False) else "Completed",
			"action_label": "View",
			"created_at": (e.completed_at or e.updated_at),
			"meta": {"enrollment_id": e.id, "certificate_id": getattr(getattr(e, 'certificate', None), 'id', None)}
		})

	new_enrollments = Enrollment.objects.filter(
		course_id__in=course_ids,
		payment_status='completed',
		is_enrolled=True
	).select_related('student', 'course').order_by('-enrolled_at')[:10]
	for e in new_enrollments:
		activities.append({
			"type": "student_enrolled",
			"title": "New Student Enrolled",
			"user_name": e.student.get_full_name() or e.student.email,
			"course_title": e.course.title,
			"time_ago": ago(e.enrolled_at),
			"status_label": "Welcome Pending",
			"action_label": "Welcome",
			"created_at": e.enrolled_at,
			"meta": {"enrollment_id": e.id}
		})

	from courses.models import CourseRating as CourseRatingModel
	reviews = CourseRatingModel.objects.filter(
		course_id__in=course_ids,
		is_public=True,
		is_approved=True
	).select_related('student', 'course').order_by('-created_at')[:10]
	for r in reviews:
		sentiment = "Positive Review" if r.rating >= 4 else ("Negative Review" if r.rating <= 2 else "Neutral Review")
		activities.append({
			"type": "course_review",
			"title": "New Course Review",
			"user_name": r.student.get_full_name() or r.student.email,
			"course_title": r.course.title,
			"time_ago": ago(r.created_at),
			"status_label": sentiment,
			"action_label": "Read",
			"created_at": r.created_at,
			"meta": {"rating": r.rating, "review_title": r.review_title, "review_id": r.id}
		})

	paid_enrollments = Enrollment.objects.filter(
		course_id__in=course_ids,
		payment_status='completed',
		is_enrolled=True,
		course__price__gt=0
	).select_related('student', 'course').order_by('-enrolled_at')[:10]
	for e in paid_enrollments:
		activities.append({
			"type": "payment_received",
			"title": "Payment Received",
			"user_name": e.student.get_full_name() or e.student.email,
			"course_title": e.course.title,
			"time_ago": ago(e.enrolled_at),
			"status_label": f"USD {e.course.price} received",
			"action_label": "View",
			"created_at": e.enrolled_at,
			"meta": {"enrollment_id": e.id, "amount": float(e.course.price)}
		})

	upcoming_assignments = AssignmentLesson.objects.filter(
		lesson__course_id__in=course_ids,
		due_date__isnull=False,
		due_date__gt=now,
		due_date__lte=now + timezone.timedelta(hours=48)
	).select_related('lesson', 'lesson__course').order_by('due_date')[:10]
	for a in upcoming_assignments:
		activities.append({
			"type": "assignment_deadline",
			"title": "Assignment Deadline Approaching",
			"course_title": a.lesson.course.title,
			"lesson_title": a.lesson.title,
			"due_at": a.due_date,
			"time_ago": ago(a.due_date),
			"status_label": "Due Soon",
			"action_label": "Remind",
			"created_at": a.lesson.created_at,
			"meta": {"lesson_id": a.lesson.id}
		})

	recent_lesson_resources = LessonResource.objects.filter(
		lesson__course_id__in=course_ids
	).select_related('lesson', 'lesson__course').order_by('-id')[:10]
	for r in recent_lesson_resources:
		label = "Video Uploaded" if r.type == 'video' else ("PDF Uploaded" if r.type == 'pdf' else "Resource Uploaded")
		activities.append({
			"type": "resource_uploaded",
			"title": "New Resource Uploaded",
			"course_title": r.lesson.course.title,
			"lesson_title": r.lesson.title,
			"time_ago": ago(getattr(r.lesson, 'created_at', None)),
			"status_label": label,
			"action_label": "View",
			"created_at": getattr(r.lesson, 'created_at', None),
			"meta": {"resource_id": r.id, "resource_type": r.type}
		})

	recent_course_resources = CourseResource.objects.filter(
		course_id__in=course_ids
	).select_related('course').order_by('-created_at')[:10]
	for r in recent_course_resources:
		label = "Video Uploaded" if r.resource_type == 'video' else ("PDF Uploaded" if r.resource_type == 'pdf' else "Resource Uploaded")
		activities.append({
			"type": "course_resource_uploaded",
			"title": "New Resource Uploaded",
			"course_title": r.course.title,
			"time_ago": ago(r.created_at),
			"status_label": label,
			"action_label": "View",
			"created_at": r.created_at,
			"meta": {"resource_id": r.id, "resource_type": r.resource_type}
		})

	activities.sort(key=lambda x: x.get("created_at") or now, reverse=True)
	return activities[:30]


def compute_teacher_dashboard_summary(instructor):
	now = timezone.now()
	start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
	prev_month_end = start_of_month - timezone.timedelta(seconds=1)
	prev_month_start = prev_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

	last_30_days_start = now - timezone.timedelta(days=30)
	prev_30_days_start = now - timezone.timedelta(days=60)
	prev_30_days_end = last_30_days_start - timezone.timedelta(seconds=1)

	base_enroll_qs = Enrollment.objects.filter(
		course__instructor=instructor,
		payment_status='completed',
		is_enrolled=True
	)

	instructor_courses_qs = Course.objects.filter(instructor=instructor)
	total_courses = instructor_courses_qs.count()
	published_courses = instructor_courses_qs.filter(status='published').count()
	draft_courses = instructor_courses_qs.filter(status='draft').count()

	total_enrollments = base_enroll_qs.count()

	enroll_30 = base_enroll_qs.filter(enrolled_at__gte=last_30_days_start).count()
	enroll_prev_30 = base_enroll_qs.filter(enrolled_at__gte=prev_30_days_start, enrolled_at__lte=prev_30_days_end).count()
	enroll_change_pct = 0.0
	if enroll_prev_30 > 0:
		enroll_change_pct = round(((enroll_30 - enroll_prev_30) / enroll_prev_30) * 100.0, 1)
	elif enroll_30 > 0:
		enroll_change_pct = 100.0

	total_completed = base_enroll_qs.filter(is_completed=True).count()
	completion_rate = round((total_completed / total_enrollments) * 100.0, 1) if total_enrollments > 0 else 0.0

	month_enrolls = base_enroll_qs.filter(enrolled_at__gte=start_of_month)
	month_completed = month_enrolls.filter(is_completed=True).count()
	month_total = month_enrolls.count()
	month_rate = (month_completed / month_total) * 100.0 if month_total > 0 else 0.0

	prev_month_enrolls = base_enroll_qs.filter(enrolled_at__gte=prev_month_start, enrolled_at__lte=prev_month_end)
	prev_month_completed = prev_month_enrolls.filter(is_completed=True).count()
	prev_month_total = prev_month_enrolls.count()
	prev_month_rate = (prev_month_completed / prev_month_total) * 100.0 if prev_month_total > 0 else 0.0

	completion_change_pct = 0.0
	if prev_month_rate > 0:
		completion_change_pct = round(((month_rate - prev_month_rate) / prev_month_rate) * 100.0, 1)
	elif month_rate > 0:
		completion_change_pct = 100.0

	from courses.models import CourseRating as CourseRatingModel
	ratings_qs = CourseRatingModel.objects.filter(course__instructor=instructor, is_public=True, is_approved=True)
	avg_rating_overall = round(ratings_qs.aggregate(avg=Avg('rating')).get('avg') or 0.0, 1)

	rating_this_month = ratings_qs.filter(created_at__gte=start_of_month).aggregate(avg=Avg('rating')).get('avg') or 0.0
	rating_prev_month = ratings_qs.filter(created_at__gte=prev_month_start, created_at__lte=prev_month_end).aggregate(avg=Avg('rating')).get('avg') or 0.0
	rating_delta = round((rating_this_month - rating_prev_month), 1)

	month_revenue = base_enroll_qs.filter(enrolled_at__gte=start_of_month).aggregate(total=Sum('course__price')).get('total') or 0
	prev_month_revenue = base_enroll_qs.filter(enrolled_at__gte=prev_month_start, enrolled_at__lte=prev_month_end).aggregate(total=Sum('course__price')).get('total') or 0
	month_revenue_val = float(month_revenue)
	prev_month_revenue_val = float(prev_month_revenue)

	revenue_change_pct = 0.0
	if prev_month_revenue_val > 0:
		revenue_change_pct = round(((month_revenue_val - prev_month_revenue_val) / prev_month_revenue_val) * 100.0, 1)
	elif month_revenue_val > 0:
		revenue_change_pct = 100.0

	return {
		"courses": {
			"total": total_courses,
			"published": published_courses,
			"drafts": draft_courses,
			"label": "Courses"
		},
		"enrollments": {
			"value": total_enrollments,
			"change_pct_30d": enroll_change_pct,
			"label": "Total Enrollments"
		},
		"completion_rate": {
			"value_pct": round(completion_rate, 1),
			"change_pct_mom": completion_change_pct,
			"label": "Course Completion Rate"
		},
		"average_rating": {
			"value": avg_rating_overall,
			"delta_mom": rating_delta,
			"label": "Average Rating"
		},
		"monthly_revenue": {
			"value": round(month_revenue_val, 2),
			"change_pct_mom": revenue_change_pct,
			"currency": "USD",
			"label": "Monthly Revenue"
		}
	}


def compute_teacher_students_overview(instructor):
	now = timezone.now()
	last_30_days = now - timezone.timedelta(days=30)

	base_enroll_qs = Enrollment.objects.filter(
		course__instructor=instructor,
		payment_status='completed',
		is_enrolled=True
	).select_related('student', 'course')

	total_students = base_enroll_qs.values('student_id').distinct().count()
	active_students = base_enroll_qs.filter(last_accessed__gte=last_30_days).values('student_id').distinct().count()

	avg_progress_val = base_enroll_qs.aggregate(avg=Avg('progress')).get('avg') or 0.0
	avg_performance = round(float(avg_progress_val), 1)

	lesson_progress_qs = LessonProgress.objects.filter(enrollment__in=base_enroll_qs)
	total_views = lesson_progress_qs.count()

	total_enrollments = base_enroll_qs.count()
	completed_count = base_enroll_qs.filter(is_completed=True).count()
	completion_rate = round((completed_count / total_enrollments) * 100.0, 1) if total_enrollments > 0 else 0.0

	time_total = lesson_progress_qs.aggregate(total=Sum('time_spent')).get('total')
	sessions_with_time = lesson_progress_qs.filter(time_spent__isnull=False).count()
	avg_session_hours = 0.0
	if time_total and sessions_with_time > 0:
		total_seconds = time_total.total_seconds()
		avg_seconds = total_seconds / sessions_with_time
		avg_session_hours = round(avg_seconds / 3600.0, 1)

	from courses.models import CourseRating as CourseRatingModel
	avg_rating_val = CourseRatingModel.objects.filter(
		course__instructor=instructor,
		is_public=True,
		is_approved=True
	).aggregate(avg=Avg('rating')).get('avg') or 0.0
	avg_rating = round(float(avg_rating_val), 1)

	revenue_total_val = base_enroll_qs.aggregate(total=Sum('course__price')).get('total') or 0
	revenue_total = round(float(revenue_total_val), 2)

	data = {
		"total_enrollments": total_enrollments,
		"total_students": total_students,
		"active_students": active_students,
		"avg_performance": avg_performance,
		"total_views": total_views,
		"completion_rate": completion_rate,
		"avg_session_hours": avg_session_hours,
		"avg_rating": avg_rating,
		"revenue_total": revenue_total,
		"currency": "USD"
	}
	return data


def compute_teacher_progress_distribution(instructor):
	"""
	Calculate the distribution of student progress across different ranges.
	Returns counts and percentages for each progress range.
	"""
	base_enroll_qs = Enrollment.objects.filter(
		course__instructor=instructor,
		payment_status='completed',
		is_enrolled=True
	).select_related('student', 'course')

	total_enrollments = base_enroll_qs.count()

	# Initialize ranges
	ranges = {
		"90_100": {"min": 90, "max": 100, "label": "90-100%", "count": 0},
		"80_89": {"min": 80, "max": 89, "label": "80-89%", "count": 0},
		"70_79": {"min": 70, "max": 79, "label": "70-79%", "count": 0},
		"60_69": {"min": 60, "max": 69, "label": "60-69%", "count": 0},
		"below_60": {"min": 0, "max": 59, "label": "Below 60%", "count": 0},
	}

	# Count enrollments in each range
	for enrollment in base_enroll_qs:
		progress = float(enrollment.progress)
		if 90 <= progress <= 100:
			ranges["90_100"]["count"] += 1
		elif 80 <= progress <= 89:
			ranges["80_89"]["count"] += 1
		elif 70 <= progress <= 79:
			ranges["70_79"]["count"] += 1
		elif 60 <= progress <= 69:
			ranges["60_69"]["count"] += 1
		else:
			ranges["below_60"]["count"] += 1

	# Format response with counts and percentages
	result = []
	for key in ["90_100", "80_89", "70_79", "60_69", "below_60"]:
		range_data = ranges[key]
		count = range_data["count"]
		percentage = round((count / total_enrollments) * 100.0, 1) if total_enrollments > 0 else 0.0
		
		result.append({
			"range_label": range_data["label"],
			"range_min": range_data["min"],
			"range_max": range_data["max"],
			"students_count": count,
			"percentage_of_total": percentage
		})

	return {
		"total_students": total_enrollments,
		"distribution": result
	}


