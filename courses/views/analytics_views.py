from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from courses.services.analytics_service import (
	_is_instructor,
	compute_teacher_top_performers,
	compute_teacher_progress_distribution,
	compute_teacher_earnings_overview,
	compute_teacher_revenue_history,
	compute_teacher_monthly_revenue_trend,
	compute_teacher_student_engagement_metrics,
	compute_teacher_dashboard_overview,
	compute_teacher_recent_activities,
	compute_teacher_dashboard_summary,
	compute_teacher_students_overview,
)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_earnings_overview_view(request):
	if not _is_instructor(request.user):
		return Response({"success": False, "message": "You are not authorized to access instructor earnings."}, status=status.HTTP_403_FORBIDDEN)
	payload = compute_teacher_earnings_overview(request.user)
	return Response({"success": True, "data": payload, "message": "Instructor earnings overview retrieved successfully."}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_revenue_history_view(request):
	if not _is_instructor(request.user):
		return Response({"success": False, "message": "You are not authorized to access instructor revenue history."}, status=status.HTTP_403_FORBIDDEN)
	items = compute_teacher_revenue_history(request.user)
	return Response({"success": True, "data": items, "message": "Instructor revenue history retrieved successfully."}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_monthly_revenue_trend_view(request):
	if not _is_instructor(request.user):
		return Response({"success": False, "message": "You are not authorized to access instructor analytics."}, status=status.HTTP_403_FORBIDDEN)
	trend = compute_teacher_monthly_revenue_trend(request.user)
	return Response({"success": True, "data": trend, "message": "Instructor monthly revenue trend retrieved successfully."}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_student_engagement_metrics_view(request):
	if not _is_instructor(request.user):
		return Response({"success": False, "message": "You are not authorized to access instructor analytics."}, status=status.HTTP_403_FORBIDDEN)
	payload = compute_teacher_student_engagement_metrics(request.user)
	return Response({"success": True, "data": payload, "message": "Instructor student engagement metrics retrieved successfully."}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_dashboard_overview_view(request, course_id: int = None):
	if not _is_instructor(request.user):
		return Response({"success": False, "message": "You are not authorized to access instructor dashboard."}, status=status.HTTP_403_FORBIDDEN)
	data = compute_teacher_dashboard_overview(request.user, course_id=course_id)
	return Response({"success": True, "data": data, "message": "Instructor dashboard overview retrieved successfully."}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_recent_activities_view(request):
	if not _is_instructor(request.user):
		return Response({"success": False, "message": "You are not authorized to access instructor activities."}, status=status.HTTP_403_FORBIDDEN)
	activities = compute_teacher_recent_activities(request.user)
	return Response({"success": True, "data": activities, "message": "Instructor recent activities retrieved successfully."}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_dashboard_summary_view(request):
	if not _is_instructor(request.user):
		return Response({"success": False, "message": "You are not authorized to access instructor dashboard."}, status=status.HTTP_403_FORBIDDEN)
	payload = compute_teacher_dashboard_summary(request.user)
	return Response({"success": True, "data": payload, "message": "Instructor KPI summary retrieved successfully."}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_students_overview_view(request):
	if not _is_instructor(request.user):
		return Response({"success": False, "message": "You are not authorized to access instructor students overview."}, status=status.HTTP_403_FORBIDDEN)
	data = compute_teacher_students_overview(request.user)
	return Response({"success": True, "data": data, "message": "Instructor analytics metrics retrieved successfully."}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_top_performers_view(request):
	if not _is_instructor(request.user):
		return Response({"success": False, "message": "You are not authorized to access instructor analytics."}, status=status.HTTP_403_FORBIDDEN)
	try:
		limit_param = request.query_params.get("limit")
		limit = int(limit_param) if limit_param else 5
	except Exception:
		limit = 5
	items = compute_teacher_top_performers(request.user, limit=limit)
	return Response({"success": True, "data": items, "message": "Top performers retrieved successfully."}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_teacher_progress_distribution_view(request):
	if not _is_instructor(request.user):
		return Response({"success": False, "message": "You are not authorized to access instructor analytics."}, status=status.HTTP_403_FORBIDDEN)
	data = compute_teacher_progress_distribution(request.user)
	return Response({"success": True, "data": data, "message": "Progress distribution retrieved successfully."}, status=status.HTTP_200_OK)


