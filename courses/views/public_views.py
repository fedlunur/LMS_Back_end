from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta

from courses.models import Course, Enrollment, Certificate, CourseRating, CourseBadge


@api_view(['GET'])
@permission_classes([AllowAny])
def get_public_statistics_view(request):
    """
    Public endpoint to retrieve LMS statistics for the frontend.
    Returns statistics about active learners, courses, certificates, ratings, and success rate.
    """
    try:
        # Active Learners: Count of distinct students with active enrollments
        active_learners = Enrollment.objects.filter(
            is_enrolled=True,
            payment_status='completed'
        ).values('student').distinct().count()
        
        # Expert Courses: Count of published courses
        expert_courses = Course.objects.filter(status='published').count()
        
        # Certificates Issued: Total count of certificates
        certificates_issued = Certificate.objects.count()
        
        # Average Rating: Average of all course ratings
        avg_rating_result = CourseRating.objects.filter(
            is_public=True,
            is_approved=True
        ).aggregate(avg_rating=Avg('rating'))
        
        average_rating = round(avg_rating_result['avg_rating'] or 0.0, 1)
        
        # Success Rate: Percentage of completed enrollments
        total_enrollments = Enrollment.objects.filter(
            payment_status='completed',
            is_enrolled=True
        ).count()
        
        completed_enrollments = Enrollment.objects.filter(
            payment_status='completed',
            is_enrolled=True,
            is_completed=True
        ).count()
        
        success_rate = round((completed_enrollments / total_enrollments * 100), 1) if total_enrollments > 0 else 0.0
        
        # Format numbers with K+ notation for display
        def format_number(num):
            if num >= 1000:
                return f"{num / 1000:.0f}K+"
            return str(num)
        
        statistics = {
            "active_learners": {
                "value": format_number(active_learners),
                "raw_value": active_learners,
                "label": "Active Learners"
            },
            "expert_courses": {
                "value": format_number(expert_courses),
                "raw_value": expert_courses,
                "label": "Expert Courses"
            },
            "certificates_issued": {
                "value": format_number(certificates_issued),
                "raw_value": certificates_issued,
                "label": "Certificates Issued"
            },
            "average_rating": {
                "value": f"{average_rating}/5",
                "raw_value": average_rating,
                "label": "Average Rating"
            },
            "success_rate": {
                "value": f"{success_rate}%",
                "raw_value": success_rate,
                "label": "Success Rate"
            }
        }
        
        return Response({
            "success": True,
            "data": statistics,
            "message": "Statistics retrieved successfully."
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "success": False,
            "message": f"Error retrieving statistics: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_top_rated_courses_view(request):
    """
    Public endpoint to retrieve exactly 3 top rated courses for the frontend.
    Returns courses with detailed information including ratings, enrollments, duration, etc.
    Always returns exactly 3 courses - fills with other published courses if needed.
    """
    try:
        # First, get top rated courses (with ratings)
        top_rated_courses = Course.objects.filter(
            status='published'
        ).annotate(
            avg_rating=Avg('ratings__rating', filter=Q(ratings__is_public=True, ratings__is_approved=True)),
            review_count=Count('ratings', filter=Q(ratings__is_public=True, ratings__is_approved=True)),
            enrollment_count=Count('enrollments', filter=Q(enrollments__payment_status='completed', enrollments__is_enrolled=True))
        ).filter(
            avg_rating__isnull=False
        ).select_related('category', 'level', 'instructor').prefetch_related('badges').order_by(
            '-avg_rating', '-review_count'
        )
        
        # Get top rated courses (up to 3)
        rated_courses = list(top_rated_courses[:3])
        course_ids = [c.id for c in rated_courses]
        
        # If we have fewer than 3 courses with ratings, fill with other published courses
        if len(rated_courses) < 3:
            remaining_count = 3 - len(rated_courses)
            
            # Get other published courses ordered by enrollment count, then creation date
            additional_courses = Course.objects.filter(
                status='published'
            ).exclude(
                id__in=course_ids
            ).annotate(
                avg_rating=Avg('ratings__rating', filter=Q(ratings__is_public=True, ratings__is_approved=True)),
                review_count=Count('ratings', filter=Q(ratings__is_public=True, ratings__is_approved=True)),
                enrollment_count=Count('enrollments', filter=Q(enrollments__payment_status='completed', enrollments__is_enrolled=True))
            ).select_related('category', 'level', 'instructor').prefetch_related('badges').order_by(
                '-enrollment_count', '-created_at'
            )[:remaining_count]
            
            rated_courses.extend(list(additional_courses))
            course_ids.extend([c.id for c in additional_courses])
        
        # Final check: ensure exactly 3 courses (slice to be safe)
        courses = rated_courses[:3]
        
        courses_data = []
        
        # Check for "new" courses (created within last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        for course in courses:
            # Get badge (bestseller, new, etc.)
            badge = None
            active_badges = course.badges.filter(is_active=True)
            
            # Check for bestseller badge
            bestseller_badge = active_badges.filter(badge_type__icontains='bestseller').first()
            if bestseller_badge:
                badge = "Bestseller"
            # Check if course is new (created within 30 days)
            elif course.created_at >= thirty_days_ago:
                badge = "New"
            else:
                # Check for other badges
                other_badge = active_badges.exclude(badge_type__icontains='bestseller').first()
                if other_badge:
                    badge = other_badge.badge_type.title() if other_badge.badge_type else None
            
            # Get skills/tags from what_you_will_learn or requirements
            skills = []
            if course.what_you_will_learn and isinstance(course.what_you_will_learn, list):
                # Extract first few items as skills, limit to 3
                skills = [str(skill) for skill in course.what_you_will_learn[:3]]
            elif course.requirements and isinstance(course.requirements, list):
                skills = [str(req) for req in course.requirements[:3]]
            
            # If no skills found, use empty list
            if not skills:
                skills = []
            
            # Format numbers
            def format_number(num):
                if num >= 1000:
                    return f"{num / 1000:.0f}K"
                return str(num)
            
            # Calculate discount if original price exists (for now, we'll use a simple calculation)
            # If price is less than a threshold, assume there's a discount
            original_price = None
            current_price = float(course.price)
            # Simple heuristic: if price < 1000, assume 50% discount
            if current_price < 1000 and current_price > 0:
                original_price = current_price * 2
            
            # Get rating and review count
            avg_rating = round(course.avg_rating or 0.0, 1)
            review_count = course.review_count or 0
            enrollment_count = course.enrollment_count or 0
            
            # Format price display (current price first, then original if exists)
            price_display = f"${int(current_price)}"
            if original_price:
                price_display = f"${int(current_price)}${int(original_price)}"
            
            course_data = {
                "id": course.id,
                "title": course.title,
                "badge": badge,
                "level": course.level.name.title() if course.level else None,
                "category": course.category.name if course.category else None,
                "rating": {
                    "value": avg_rating,
                    "review_count": format_number(review_count),
                    "raw_review_count": review_count,
                    "display": f"{avg_rating}({format_number(review_count)})"
                },
                "description": course.description[:150] + "..." if len(course.description) > 150 else course.description,
                "student_count": {
                    "value": format_number(enrollment_count),
                    "raw_value": enrollment_count,
                    "display": f"{format_number(enrollment_count)} students"
                },
                "duration": course.total_duration if hasattr(course, 'total_duration') else "0h 0m",
                "skills": skills,
                "price": {
                    "current": current_price,
                    "original": original_price,
                    "display": price_display
                },
                "thumbnail": course.thumbnail.url if course.thumbnail else None,
                "instructor": {
                    "id": course.instructor.id,
                    "name": course.instructor.get_full_name() or course.instructor.first_name,
                    "email": course.instructor.email
                }
            }
            
            courses_data.append(course_data)
        
        return Response({
            "success": True,
            "data": courses_data,
            "message": "Top rated courses retrieved successfully."
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "success": False,
            "message": f"Error retrieving top rated courses: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

