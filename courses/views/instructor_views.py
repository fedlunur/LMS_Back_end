from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from courses.models import Course, Enrollment, Lesson, LessonProgress, Module, ModuleProgress, QuizAttempt, AssignmentSubmission, CourseQA, CourseRating, Certificate, LessonResource, CourseResource, AssignmentLesson
from rest_framework.response import Response
from rest_framework import status
from courses.serializers import DynamicFieldSerializer
from django.utils import timezone
from django.utils.timesince import timesince
from django.db.models import Count, Avg, Q
from django.db.models import Sum

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_monthly_revenue_trend_view(request):
	"""
	Monthly revenue trend for an instructor for the last 12 months (including current month).
	For each month returns:
	- month_label (e.g., 'January 2025')
	- students (count of completed enrollments in that month)
	- revenue (sum of course prices for completed enrollments in that month)
	- change_pct_mom (revenue percent change month-over-month)
	"""
	# Only instructors (role.name == 'teacher') or staff can access
	if not (getattr(request.user, 'is_staff', False) or (getattr(request.user, 'role', None) and getattr(request.user.role, 'name', '').lower() == 'teacher')):
		return Response({
			"success": False,
			"message": "You are not authorized to access instructor analytics."
		}, status=status.HTTP_403_FORBIDDEN)

	instructor = request.user
	now = timezone.now()

	# Helper to get start of month
	def start_of_month(dt):
		return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

	# Build a list of month windows (start, end) for last 12 months
	months = []
	cur = start_of_month(now)
	for _ in range(12):
		months.append(cur)
		# Go back one month safely
		year = cur.year if cur.month > 1 else cur.year - 1
		month = cur.month - 1 if cur.month > 1 else 12
		cur = cur.replace(year=year, month=month)
	months = list(reversed(months))  # chronological order

	# Preload base enrollments for instructor
	base_enroll_qs = Enrollment.objects.filter(
		course__instructor=instructor,
		payment_status='completed',
		is_enrolled=True
	)

	trend = []
	prev_revenue = None
	for month_start in months:
		# Compute end as next month start - 1 sec
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

	return Response({
		"success": True,
		"data": trend,
		"message": "Instructor monthly revenue trend retrieved successfully."
	}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_student_engagement_metrics_view(request):
	"""
	Student engagement metrics for an instructor across all their courses:
	- video_completion_rate: completed lesson progresses / total lesson progresses
	- assignment_submission_rate: distinct students with a submission / total students
	- discussion_participation_rate: distinct students who posted in Q&A / total students
	- quiz_performance_avg: average score across quiz attempts (0-100)
	Also includes targets and status relative to target.
	"""
	# Only instructors (role.name == 'teacher') or staff can access
	if not (getattr(request.user, 'is_staff', False) or (getattr(request.user, 'role', None) and getattr(request.user.role, 'name', '').lower() == 'teacher')):
		return Response({
			"success": False,
			"message": "You are not authorized to access instructor analytics."
		}, status=status.HTTP_403_FORBIDDEN)

	instructor = request.user

	# Base enrollments for instructor's courses
	base_enroll_qs = Enrollment.objects.filter(
		course__instructor=instructor,
		payment_status='completed',
		is_enrolled=True
	).select_related('student', 'course')

	total_students = base_enroll_qs.values('student_id').distinct().count()

	# Video completion rate
	lp_qs = LessonProgress.objects.filter(enrollment__in=base_enroll_qs)
	total_lp = lp_qs.count()
	completed_lp = lp_qs.filter(completed=True).count()
	video_completion_rate = round((completed_lp / total_lp) * 100.0, 1) if total_lp > 0 else 0.0

	# Assignment submission rate (students with at least one submission / total students)
	as_qs = AssignmentSubmission.objects.filter(lesson__course__instructor=instructor)
	students_with_submission = as_qs.values('student_id').distinct().count()
	assignment_submission_rate = round((students_with_submission / total_students) * 100.0, 1) if total_students > 0 else 0.0

	# Discussion participation rate (students who asked at least one question / total students)
	qa_qs = CourseQA.objects.filter(course__instructor=instructor)
	students_in_discussion = qa_qs.values('student_id').distinct().count()
	discussion_participation_rate = round((students_in_discussion / total_students) * 100.0, 1) if total_students > 0 else 0.0

	# Quiz performance average (average score across attempts, 0-100)
	attempt_qs = QuizAttempt.objects.filter(lesson__course__instructor=instructor, is_in_progress=False)
	avg_score = attempt_qs.aggregate(avg=Avg('score')).get('avg') or 0.0
	quiz_performance_avg = round(float(avg_score), 1)

	# Targets: fixed default 70% for now (same for all metrics)
	targets = {
		"video_completion_rate": 70.0,
		"assignment_submission_rate": 70.0,
		"discussion_participation_rate": 70.0,
		"quiz_performance_avg": 70.0,
	}

	def status_label(value, target):
		return "Target met" if value >= target else "Below target"

	payload = {
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

	return Response({
		"success": True,
		"data": payload,
		"message": "Instructor student engagement metrics retrieved successfully."
	}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_earnings_overview_view(request):
	"""
	Earnings overview for an instructor:
	- total_earnings (sum of prices for completed enrollments)
	- this_month_earnings
	- total_enrolled_students (distinct across instructor courses)
	- active_courses (published with at least one completed enrollment)
	"""
	# Only instructors (role.name == 'teacher') or staff can access
	if not (getattr(request.user, 'is_staff', False) or (getattr(request.user, 'role', None) and getattr(request.user.role, 'name', '').lower() == 'teacher')):
		return Response({
			"success": False,
			"message": "You are not authorized to access instructor earnings."
		}, status=status.HTTP_403_FORBIDDEN)

	instructor = request.user
	now = timezone.now()
	start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

	# Completed enrollments for instructor's courses
	base_enroll_qs = Enrollment.objects.filter(
		course__instructor=instructor,
		payment_status='completed',
		is_enrolled=True
	).select_related('course')

	# Earnings
	total_earnings_val = base_enroll_qs.aggregate(total=Sum('course__price')).get('total') or 0
	this_month_earnings_val = base_enroll_qs.filter(enrolled_at__gte=start_of_month).aggregate(total=Sum('course__price')).get('total') or 0

	# Distinct students and active courses
	total_enrolled_students = base_enroll_qs.values('student_id').distinct().count()
	active_courses = Course.objects.filter(instructor=instructor, status='published', enrollments__in=base_enroll_qs).distinct().count()

	payload = {
		"total_earnings": round(float(total_earnings_val), 2),
		"this_month_earnings": round(float(this_month_earnings_val), 2),
		"currency": "USD",
		"total_enrolled_students": total_enrolled_students,
		"active_courses": active_courses
	}

	return Response({
		"success": True,
		"data": payload,
		"message": "Instructor earnings overview retrieved successfully."
	}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_revenue_history_view(request):
	"""
	Revenue history per course for an instructor.
	Returns a list of items sorted by last_paid_at desc:
	- course_id, course_title
	- students_enrolled (completed enrollments count)
	- amount (sum of course price for completed enrollments)
	- last_paid_at (datetime of the most recent completed enrollment)
	"""
	# Only instructors (role.name == 'teacher') or staff can access
	if not (getattr(request.user, 'is_staff', False) or (getattr(request.user, 'role', None) and getattr(request.user.role, 'name', '').lower() == 'teacher')):
		return Response({
			"success": False,
			"message": "You are not authorized to access instructor revenue history."
		}, status=status.HTTP_403_FORBIDDEN)

	instructor = request.user

	# Pull all instructor courses
	courses_qs = Course.objects.filter(instructor=instructor)

	# Pre-fetch completed enrollments per course
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

	# Sort by most recent payment
	revenue_items.sort(key=lambda item: item.get("last_paid_at") or timezone.datetime.min.replace(tzinfo=timezone.utc), reverse=True)

	return Response({
		"success": True,
		"data": revenue_items,
		"message": "Instructor revenue history retrieved successfully."
	}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_student_attempts_view(request, lesson_id):
    """
    Get all student attempts for a quiz (for teachers).
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        
        # Check authorization
        if lesson.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view student attempts for this quiz."
            }, status=status.HTTP_403_FORBIDDEN)
        
        if lesson.content_type != Lesson.ContentType.QUIZ:
            return Response({
                "success": False,
                "message": "This lesson is not a quiz."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        attempts = QuizAttempt.objects.filter(
            lesson=lesson,
            is_in_progress=False
        ).select_related('student').order_by('-completed_at')
        
        attempt_data = []
        for attempt in attempts:
            attempt_dict = DynamicFieldSerializer(attempt, model_name="quizattempt").data
            attempt_dict['student'] = {
                'id': attempt.student.id,
                'email': attempt.student.email,
                'name': attempt.student.get_full_name()
            }
            attempt_data.append(attempt_dict)
        
        return Response({
            "success": True,
            "data": attempt_data,
            "message": "Student attempts retrieved successfully."
        }, status=status.HTTP_200_OK)
    
    except Lesson.DoesNotExist:
        return Response({
            "success": False,
            "message": "Lesson not found."
        }, status=status.HTTP_404_NOT_FOUND)




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_course_students_view(request, course_id):
    """Get all students enrolled in a course (for instructors)."""
    try:
        course = Course.objects.get(id=course_id)
        if course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view students for this course."
            }, status=status.HTTP_403_FORBIDDEN)
        
        enrollments = Enrollment.objects.filter(
            course=course,
            payment_status='completed'
        ).select_related('student')
        
        serializer = DynamicFieldSerializer(enrollments, many=True, model_name="enrollment")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Course students retrieved successfully."
        }, status=status.HTTP_200_OK)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_student_progress_view(request, course_id, student_id):
    """Get detailed progress for a specific student in a course (for instructors)."""
    try:
        course = Course.objects.get(id=course_id)
        if course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view this student's progress."
            }, status=status.HTTP_403_FORBIDDEN)
        
        from user_managment.models import User
        student = User.objects.get(id=student_id)
        enrollment = Enrollment.objects.get(student=student, course=course)
        
        module_progress_list = ModuleProgress.objects.filter(enrollment=enrollment).select_related('module')
        lesson_progress_list = LessonProgress.objects.filter(enrollment=enrollment).select_related('lesson', 'lesson__module')
        
        module_serializer = DynamicFieldSerializer(module_progress_list, many=True, model_name="moduleprogress")
        lesson_serializer = DynamicFieldSerializer(lesson_progress_list, many=True, model_name="lessonprogress")
        
        return Response({
            "success": True,
            "data": {
                "student": {"id": student.id, "email": student.email, "name": student.get_full_name()},
                "enrollment": {
                    "progress": float(enrollment.progress),
                    "completed_lessons": enrollment.completed_lessons,
                    "is_completed": enrollment.is_completed,
                    "enrolled_at": enrollment.enrolled_at
                },
                "module_progress": module_serializer.data,
                "lesson_progress": lesson_serializer.data
            },
            "message": "Student progress retrieved successfully."
        }, status=status.HTTP_200_OK)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)
    except Enrollment.DoesNotExist:
        return Response({"success": False, "message": "Student is not enrolled in this course."}, status=status.HTTP_404_NOT_FOUND)




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_assignment_submissions_view(request, lesson_id):
    """Get all submissions for an assignment lesson (for instructors)."""
    try:
        lesson = Lesson.objects.get(id=lesson_id)
        if lesson.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to view submissions for this lesson."
            }, status=status.HTTP_403_FORBIDDEN)
        
        if lesson.content_type != Lesson.ContentType.ASSIGNMENT:
            return Response({
                "success": False,
                "message": "This lesson is not an assignment."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        submissions = AssignmentSubmission.objects.filter(lesson=lesson).select_related('student', 'enrollment').order_by('-submitted_at')
        
        serializer = DynamicFieldSerializer(submissions, many=True, model_name="assignmentsubmission")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Assignment submissions retrieved successfully."
        }, status=status.HTTP_200_OK)
    except Lesson.DoesNotExist:
        return Response({"success": False, "message": "Lesson not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def grade_assignment_view(request, submission_id):
    """Grade an assignment submission (for instructors). Expected payload: {"score": 85.0, "feedback": "Great work!", "status": "graded"}"""
    try:
        submission = AssignmentSubmission.objects.get(id=submission_id)
        if submission.lesson.course.instructor != request.user and not request.user.is_staff:
            return Response({
                "success": False,
                "message": "You are not authorized to grade this submission."
            }, status=status.HTTP_403_FORBIDDEN)
        
        score = request.data.get('score')
        feedback = request.data.get('feedback', '')
        status_val = request.data.get('status', 'graded')
        
        if score is None:
            return Response({"success": False, "message": "Score is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        if submission.max_score and score > submission.max_score:
            return Response({
                "success": False,
                "message": f"Score cannot exceed maximum score of {submission.max_score}."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        submission.score = float(score)
        submission.feedback = feedback
        submission.status = status_val
        submission.graded_by = request.user
        submission.graded_at = timezone.now()
        submission.save()
        
        serializer = DynamicFieldSerializer(submission, model_name="assignmentsubmission")
        
        return Response({
            "success": True,
            "data": serializer.data,
            "message": "Assignment graded successfully."
        }, status=status.HTTP_200_OK)
    except AssignmentSubmission.DoesNotExist:
        return Response({"success": False, "message": "Submission not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_dashboard_overview_view(request):
    """
    Aggregated overview for an instructor:
    - For each course created by the instructor: total students, completion rate, average rating.
    """
    
    if not (getattr(request.user, 'is_staff', False) or (getattr(request.user, 'role', None) and getattr(request.user.role, 'name', '').lower() == 'teacher')):
        return Response({
            "success": False,
            "message": "You are not authorized to access instructor dashboard."
        }, status=status.HTTP_403_FORBIDDEN)

    instructor = request.user

    courses = Course.objects.filter(instructor=instructor).prefetch_related('enrollments', 'ratings')

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

    return Response({
        "success": True,
        "data": data,
        "message": "Instructor dashboard overview retrieved successfully."
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_students_overview_view(request):
    """
    Overall students and analytics across all courses created by the instructor.
    Returns:
    - metrics: total_students, active_students (last 30d), avg_performance(progress), total_views, completion_rate, avg_session_hours, avg_rating, revenue_total
    - students: list of distinct students with aggregates (courses_count, avg_progress, last_accessed, is_active)
    """
    # Only instructors (role.name == 'teacher') or staff can access
    if not (getattr(request.user, 'is_staff', False) or (getattr(request.user, 'role', None) and getattr(request.user.role, 'name', '').lower() == 'teacher')):
        return Response({
            "success": False,
            "message": "You are not authorized to access instructor students overview."
        }, status=status.HTTP_403_FORBIDDEN)

    instructor = request.user
    now = timezone.now()
    last_30_days = now - timezone.timedelta(days=30)

    # Base enrollments for this instructor
    base_enroll_qs = Enrollment.objects.filter(
        course__instructor=instructor,
        payment_status='completed',
        is_enrolled=True
    ).select_related('student', 'course')

    # Distinct students
    total_students = base_enroll_qs.values('student_id').distinct().count()

    # Active students (last 30 days)
    active_students = base_enroll_qs.filter(last_accessed__gte=last_30_days).values('student_id').distinct().count()

    # Average performance (average enrollment progress)
    avg_progress_val = base_enroll_qs.aggregate(avg=Avg('progress')).get('avg') or 0.0
    avg_performance = round(float(avg_progress_val), 1)

    # Total views across lessons (use LessonProgress rows as views proxy)
    lesson_progress_qs = LessonProgress.objects.filter(enrollment__in=base_enroll_qs)
    total_views = lesson_progress_qs.count()

    # Completion rate overall
    total_enrollments = base_enroll_qs.count()
    completed_count = base_enroll_qs.filter(is_completed=True).count()
    completion_rate = round((completed_count / total_enrollments) * 100.0, 1) if total_enrollments > 0 else 0.0

    # Average session length (average time_spent across lesson progress entries with time data)
    time_total = lesson_progress_qs.aggregate(total=Sum('time_spent')).get('total')
    sessions_with_time = lesson_progress_qs.filter(time_spent__isnull=False).count()
    avg_session_hours = 0.0
    if time_total and sessions_with_time > 0:
        total_seconds = time_total.total_seconds()
        avg_seconds = total_seconds / sessions_with_time
        avg_session_hours = round(avg_seconds / 3600.0, 1)

    # Average rating across teacher's courses
    avg_rating_val = CourseRating.objects.filter(
        course__instructor=instructor,
        is_public=True,
        is_approved=True
    ).aggregate(avg=Avg('rating')).get('avg') or 0.0
    avg_rating = round(float(avg_rating_val), 1)

    # Revenue overview (sum of course price over all completed enrollments)
    revenue_total_val = base_enroll_qs.aggregate(total=Sum('course__price')).get('total') or 0
    revenue_total = round(float(revenue_total_val), 2)

    # Build student list with aggregates
    students_map = {}
    # Preload last_accessed and progress per enrollment then roll-up per student
    for e in base_enroll_qs.order_by('-last_accessed'):
        sid = e.student_id
        if sid not in students_map:
            students_map[sid] = {
                "student_id": sid,
                "name": e.student.get_full_name() or e.student.email,
                "email": e.student.email,
                "courses_count": 0,
                "avg_progress": 0.0,
                "last_accessed": e.last_accessed,
                "is_active": e.last_accessed and e.last_accessed >= last_30_days,
                "_progress_sum": 0.0
            }
        entry = students_map[sid]
        entry["courses_count"] += 1
        entry["_progress_sum"] += float(e.progress)
        # Keep max last_accessed
        if e.last_accessed and (entry["last_accessed"] is None or e.last_accessed > entry["last_accessed"]):
            entry["last_accessed"] = e.last_accessed
            entry["is_active"] = e.last_accessed >= last_30_days

    # Finalize avg_progress
    students = []
    for sid, entry in students_map.items():
        if entry["courses_count"] > 0:
            entry["avg_progress"] = round(entry["_progress_sum"] / entry["courses_count"], 1)
        del entry["_progress_sum"]
        students.append(entry)

    # Sort students by last_accessed desc
    students.sort(key=lambda s: (s["last_accessed"] or timezone.datetime.min.replace(tzinfo=timezone.utc)), reverse=True)

    data = {
        "metrics": {
            "total_enrollments": total_enrollments,
            "total_students": total_students,
            "active_students": active_students,
            "avg_performance": avg_performance,  # percentage 0-100
            "total_views": total_views,
            "completion_rate": completion_rate,   # percentage 0-100
            "avg_session_hours": avg_session_hours,
            "avg_rating": avg_rating,
            "revenue_total": revenue_total,
            "currency": "USD"
        },
        "students": students
    }

    return Response({
        "success": True,
        "data": data,
        "message": "Instructor students and analytics overview retrieved successfully."
    }, status=status.HTTP_200_OK)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_recent_activities_view(request):
    """
    Recent activities for an instructor across their courses.
    Returns a normalized list with type, labels, timestamps, and CTA suggestions.
    """
    # Only instructors (role.name == 'teacher') or staff can access
    if not (getattr(request.user, 'is_staff', False) or (getattr(request.user, 'role', None) and getattr(request.user.role, 'name', '').lower() == 'teacher')):
        return Response({
            "success": False,
            "message": "You are not authorized to access instructor activities."
        }, status=status.HTTP_403_FORBIDDEN)

    instructor = request.user
    now = timezone.now()

    # Helper to format time ago
    def ago(dt):
        if not dt:
            return None
        return f"{timesince(dt, now)} ago"

    # Courses owned by instructor
    course_ids = list(Course.objects.filter(instructor=instructor).values_list('id', flat=True))

    activities = []

    # New Assignment Submission
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

    # New Question Posted
    questions = CourseQA.objects.filter(
        course_id__in=course_ids,
        is_answered=False
    ).select_related('student', 'course').order_by('-created_at')[:10]
    for q in questions:
        activities.append({
            "type": "question_posted",
            "title": "New Question Posted",
            "user_name": q.student.get_full_name() or q.student.email,
            "course_title": q.course.title,
            "time_ago": ago(q.created_at),
            "status_label": "Unanswered",
            "action_label": "Answer",
            "created_at": q.created_at,
            "meta": {"question_id": q.id, "question_title": q.question_title}
        })

    # Course Completed
    completed_enrollments = Enrollment.objects.filter(
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

    # New Student Enrolled
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

    # New Course Review
    reviews = CourseRating.objects.filter(
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

    # Payment Received (derived from completed enrollments where course price > 0)
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

    # Assignment Deadline Approaching (next 48 hours)
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

    # New Resource Uploaded (LessonResource and CourseResource)
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

    # Sort all activities by created_at desc and cap to 30
    activities.sort(key=lambda x: x.get("created_at") or now, reverse=True)
    activities = activities[:30]

    return Response({
        "success": True,
        "data": activities,
        "message": "Instructor recent activities retrieved successfully."
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_dashboard_summary_view(request):
    """
    KPI summary for an instructor:
    - Total Enrollments (cumulative) with 30d change (%)
    - Course Completion Rate (overall) with month-over-month change (%)
    - Average Rating (overall) with month-over-month delta
    - Monthly Revenue (sum of course prices for completed enrollments this month) with MoM change (%)
    """
    # Only instructors (role.name == 'teacher') or staff can access
    if not (getattr(request.user, 'is_staff', False) or (getattr(request.user, 'role', None) and getattr(request.user.role, 'name', '').lower() == 'teacher')):
        return Response({
            "success": False,
            "message": "You are not authorized to access instructor dashboard."
        }, status=status.HTTP_403_FORBIDDEN)

    instructor = request.user
    now = timezone.now()

    # Period boundaries
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_month_end = start_of_month - timezone.timedelta(seconds=1)
    prev_month_start = prev_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    last_30_days_start = now - timezone.timedelta(days=30)
    prev_30_days_start = now - timezone.timedelta(days=60)
    prev_30_days_end = last_30_days_start - timezone.timedelta(seconds=1)

    # Base queryset: enrollments for instructor's courses with completed payment
    base_enroll_qs = Enrollment.objects.filter(
        course__instructor=instructor,
        payment_status='completed',
        is_enrolled=True
    )

    # Courses breakdown for instructor
    instructor_courses_qs = Course.objects.filter(instructor=instructor)
    total_courses = instructor_courses_qs.count()
    published_courses = instructor_courses_qs.filter(status='published').count()
    draft_courses = instructor_courses_qs.filter(status='draft').count()

    # Total enrollments (cumulative)
    total_enrollments = base_enroll_qs.count()

    # 30-day enrollments and previous 30-day
    enroll_30 = base_enroll_qs.filter(enrolled_at__gte=last_30_days_start).count()
    enroll_prev_30 = base_enroll_qs.filter(enrolled_at__gte=prev_30_days_start, enrolled_at__lte=prev_30_days_end).count()
    enroll_change_pct = 0.0
    if enroll_prev_30 > 0:
        enroll_change_pct = round(((enroll_30 - enroll_prev_30) / enroll_prev_30) * 100.0, 1)
    elif enroll_30 > 0:
        enroll_change_pct = 100.0

    # Completion rate (overall) and month-over-month change
    total_completed = base_enroll_qs.filter(is_completed=True).count()
    completion_rate = round((total_completed / total_enrollments) * 100.0, 1) if total_enrollments > 0 else 0.0

    # Completion rate this month vs last month
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

    # Average rating (overall) and month-over-month delta
    ratings_qs = CourseRating.objects.filter(course__instructor=instructor, is_public=True, is_approved=True)
    avg_rating_overall = round(ratings_qs.aggregate(avg=Avg('rating')).get('avg') or 0.0, 1)

    rating_this_month = ratings_qs.filter(created_at__gte=start_of_month).aggregate(avg=Avg('rating')).get('avg') or 0.0
    rating_prev_month = ratings_qs.filter(created_at__gte=prev_month_start, created_at__lte=prev_month_end).aggregate(avg=Avg('rating')).get('avg') or 0.0
    rating_delta = round((rating_this_month - rating_prev_month), 1)

    # Monthly revenue (sum of course.price for this month's completed enrollments) with MoM change
    month_revenue = base_enroll_qs.filter(enrolled_at__gte=start_of_month).aggregate(total=Sum('course__price')).get('total') or 0
    prev_month_revenue = base_enroll_qs.filter(enrolled_at__gte=prev_month_start, enrolled_at__lte=prev_month_end).aggregate(total=Sum('course__price')).get('total') or 0

    # Normalize to float
    month_revenue_val = float(month_revenue)
    prev_month_revenue_val = float(prev_month_revenue)

    revenue_change_pct = 0.0
    if prev_month_revenue_val > 0:
        revenue_change_pct = round(((month_revenue_val - prev_month_revenue_val) / prev_month_revenue_val) * 100.0, 1)
    elif month_revenue_val > 0:
        revenue_change_pct = 100.0

    payload = {
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

    return Response({
        "success": True,
        "data": payload,
        "message": "Instructor KPI summary retrieved successfully."
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_course_enrollments_detail_view(request, course_id):
    """
    List enrolled students for a specific course belonging to the authenticated instructor.
    """
    # Only instructors (role.name == 'teacher') or staff can access
    if not (getattr(request.user, 'is_staff', False) or (getattr(request.user, 'role', None) and getattr(request.user.role, 'name', '').lower() == 'teacher')):
        return Response({
            "success": False,
            "message": "You are not authorized to access instructor enrollments."
        }, status=status.HTTP_403_FORBIDDEN)

    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return Response({"success": False, "message": "Course not found."}, status=status.HTTP_404_NOT_FOUND)

    if course.instructor != request.user and not request.user.is_staff:
        return Response({"success": False, "message": "You are not authorized to view students for this course."}, status=status.HTTP_403_FORBIDDEN)

    enrollments = Enrollment.objects.filter(
        course=course,
        payment_status='completed',
        is_enrolled=True
    ).select_related('student').order_by('-enrolled_at')

    students = []
    for e in enrollments:
        students.append({
            "student_id": e.student.id,
            "name": e.student.get_full_name() or e.student.email,
            "email": e.student.email,
            "progress_pct": float(e.progress),
            "is_completed": e.is_completed,
            "enrolled_at": e.enrolled_at,
            "completed_at": e.completed_at
        })

    total_students = len(students)
    completed_count = sum(1 for s in students if s["is_completed"])
    completion_rate = round((completed_count / total_students) * 100.0, 2) if total_students > 0 else 0.0
    avg_rating = round(course.ratings.aggregate(avg=Avg('rating')).get('avg') or 0.0, 1)

    return Response({
        "success": True,
        "data": {
            "course_id": course.id,
            "course_title": course.title,
            "total_students": total_students,
            "completion_rate": completion_rate,
            "average_rating": avg_rating,
            "students": students
        },
        "message": "Course enrolled students retrieved successfully."
    }, status=status.HTTP_200_OK)
