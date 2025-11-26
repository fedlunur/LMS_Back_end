from typing import Tuple, List, Optional
from django.db.models import Q
from courses.models import Course, Lesson, CourseFAQ, CourseAnnouncement, Enrollment
import logging
import re

logger = logging.getLogger(__name__)


class ChatbotDataFetcher:
    """
    Fetches context from database using vector search for semantic similarity.
    Searches courses, lessons, FAQs, announcements, and user-specific data.
    """

    def __init__(self):
        try:
            from .vector_store import get_vector_store
            # Use singleton pattern to avoid reloading embedding model
            self.vector_store = get_vector_store()
            self.use_vector_search = True
            # Check if vector store has content (only log once)
            stats = self.vector_store.get_collection_stats()
            if stats["total_documents"] == 0:
                logger.warning("Vector store is empty. Run 'python manage.py index_content' to index database content.")
        except Exception as e:
            logger.warning(f"Vector store not available, falling back to basic search: {e}")
            self.vector_store = None
            self.use_vector_search = False

    def available_sources(self) -> list[str]:
        return [
            "courses",
            "lessons",
            "faqs",
            "announcements",
            "enrollments",
            "platform_help",
            "all"  # Search all sources
        ]

    def get_context(
        self,
        user=None,
        requested_sources: List[str] | None = None,
        query: str = ""
    ) -> Tuple[list[str], list[str]]:
        """
        Get context chunks based on query and requested sources.
        
        Args:
            user: Current user (for personalized results)
            requested_sources: List of source types to search
            query: The user's query (for semantic search)
        """
        requested_sources = requested_sources or []
        used_sources: list[str] = []
        chunks: list[str] = []

        # If no query provided, return basic platform help
        if not query or not query.strip():
            chunks.append(
                "Emerald LMS lets you browse courses, enroll, watch lessons, take quizzes, "
                "submit assignments, and chat with instructors."
            )
            used_sources.append("platform_help")
            return chunks, used_sources

        # Check if this is a course catalog query
        is_course_catalog_query = self._is_course_catalog_query(query)
        
        # Use vector search if available and has content
        if self.use_vector_search and self.vector_store:
            stats = self.vector_store.get_collection_stats()
            if stats["total_documents"] > 0:
                chunks, used_sources = self._get_vector_context(query, user, requested_sources)
                # For course catalog queries, verify courses were found
                if is_course_catalog_query:
                    has_course_chunks = any('Course:' in chunk or 'course:' in chunk.lower() for chunk in chunks)
                    if not has_course_chunks:
                        # No courses found in vector results, use basic search instead
                        logger.info("Course catalog query but no courses in vector results, using basic search")
                        chunks, used_sources = self._get_basic_context(query, user, requested_sources)
            else:
                # Vector store is empty, use basic search
                logger.warning("Vector store is empty. Using basic keyword search.")
                chunks, used_sources = self._get_basic_context(query, user, requested_sources)
        else:
            # Fallback to basic keyword search
            chunks, used_sources = self._get_basic_context(query, user, requested_sources)

        return chunks, used_sources

    def _get_vector_context(
        self,
        query: str,
        user: Optional[object],
        requested_sources: List[str]
    ) -> Tuple[list[str], list[str]]:
        """Get context using vector semantic search."""
        chunks: list[str] = []
        used_sources: list[str] = []

        # Check if this is a course catalog query (needs more results)
        is_course_catalog_query = self._is_course_catalog_query(query)

        # Determine what to search
        search_all = "all" in requested_sources or len(requested_sources) == 0
        search_courses = search_all or "courses" in requested_sources or is_course_catalog_query
        search_lessons = search_all or "lessons" in requested_sources
        search_faqs = search_all or "faqs" in requested_sources
        search_announcements = search_all or "announcements" in requested_sources
        search_enrollments = search_all or "enrollments" in requested_sources

        # Build metadata filters
        filters = []
        if search_courses:
            filters.append({"type": "course"})
        if search_lessons:
            filters.append({"type": "lesson"})
        if search_faqs:
            filters.append({"type": "faq"})
        if search_announcements:
            filters.append({"type": "announcement"})
        if search_enrollments and user:
            filters.append({"type": "enrollment", "user_id": user.id})

        # Search vector store - optimize by searching all at once if no specific filters
        results = []
        if not filters or len(filters) == 0:
            # Search all without filters (faster)
            n_results = 20 if is_course_catalog_query else 10
            results = self.vector_store.search(query=query, n_results=n_results)
        else:
            # Search with filters - but combine similar types to reduce queries
            type_groups = {}
            for filter_meta in filters:
                doc_type = filter_meta.get("type")
                if doc_type not in type_groups:
                    type_groups[doc_type] = []
                type_groups[doc_type].append(filter_meta)
            
            # Search each type group
            for doc_type, type_filters in type_groups.items():
                # For enrollment type, we need user_id
                if doc_type == "enrollment" and user:
                    filter_meta = {"type": "enrollment"}
                    search_results = self.vector_store.search(
                        query=query,
                        n_results=3,
                        filter_metadata=filter_meta,
                        user_id=user.id
                    )
                    results.extend(search_results)
                else:
                    # For course catalog queries, get more course results
                    n_results = 20 if (doc_type == "course" and is_course_catalog_query) else 5
                    # For other types, just use type filter
                    filter_meta = {"type": doc_type}
                    search_results = self.vector_store.search(
                        query=query,
                        n_results=n_results,
                        filter_metadata=filter_meta
                    )
                    results.extend(search_results)

        # Format results into chunks
        seen_ids = set()
        # For course catalog queries, show more results (up to 20)
        max_results = 20 if is_course_catalog_query else 10
        for result in results[:max_results]:
            doc_id = result.get("metadata", {}).get("id")
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                content = result.get("content", "")
                metadata = result.get("metadata", {})
                doc_type = metadata.get("type", "unknown")

                # Format chunk with metadata
                if doc_type == "course":
                    course_title = metadata.get("title", "Course")
                    # Try to get price and instructor from metadata first
                    price = metadata.get("price")
                    instructor_name = metadata.get("instructor_name")
                    
                    # If not in metadata, fetch from database
                    if not price or not instructor_name:
                        course_id = metadata.get("course_id")
                        if course_id:
                            try:
                                course = Course.objects.select_related('instructor').get(id=course_id)
                                price = str(course.price) if course.price else "0.00"
                                instructor_name = course.instructor.get_full_name() or course.instructor.first_name or course.instructor.username
                            except Course.DoesNotExist:
                                pass
                    
                    # Format price
                    try:
                        price_float = float(price) if price else 0.0
                        price_str = f"${price_float:.2f}" if price_float > 0 else "Free"
                    except (ValueError, TypeError):
                        price_str = "Free"
                    
                    # Build enhanced chunk with price and instructor
                    chunk = f"Course: {course_title}\nPrice: {price_str}\nInstructor: {instructor_name or 'Not specified'}\n{content}"
                    if "courses" not in used_sources:
                        used_sources.append("courses")
                elif doc_type == "lesson":
                    lesson_title = metadata.get("title", "Lesson")
                    chunk = f"Lesson: {lesson_title}\n{content}"
                    if "lessons" not in used_sources:
                        used_sources.append("lessons")
                elif doc_type == "faq":
                    chunk = f"FAQ: {content}"
                    if "faqs" not in used_sources:
                        used_sources.append("faqs")
                elif doc_type == "announcement":
                    chunk = f"Announcement: {content}"
                    if "announcements" not in used_sources:
                        used_sources.append("announcements")
                elif doc_type == "enrollment":
                    chunk = f"Your Enrollment: {content}"
                    if "enrollments" not in used_sources:
                        used_sources.append("enrollments")
                else:
                    chunk = content

                chunks.append(chunk)

        # Check if course catalog query but no course chunks found
        has_course_chunks = any('Course:' in chunk or 'course:' in chunk.lower() for chunk in chunks)
        if is_course_catalog_query and not has_course_chunks:
            # For course catalog queries, if no course chunks found, fallback to basic search
            logger.info("Course catalog query but no course chunks in vector results, falling back to basic search")
            return self._get_basic_context(query, user, requested_sources)
        
        # Fallback if no results at all
        if not chunks:
            chunks.append(
                "Emerald LMS lets you browse courses, enroll, watch lessons, take quizzes, "
                "submit assignments, and chat with instructors."
            )
            used_sources.append("platform_help")

        return chunks, used_sources

    def _get_basic_context(
        self,
        query: str,
        user: Optional[object],
        requested_sources: List[str]
    ) -> Tuple[list[str], list[str]]:
        """Fallback basic keyword search when vector store is unavailable."""
        chunks: list[str] = []
        used_sources: list[str] = []

        search_all = "all" in requested_sources or len(requested_sources) == 0
        
        # Check if query is asking about personal data
        is_personal_query = self._is_personal_data_query(query)
        
        # Check if query is asking for course catalog (list, show, available courses)
        is_course_catalog_query = self._is_course_catalog_query(query)

        # If user is asking about personal data, fetch their enrollments
        if user and (search_all or "enrollments" in requested_sources or is_personal_query):
            enrollments = Enrollment.objects.filter(
                student=user,
                is_enrolled=True
            ).select_related('course', 'course__instructor')[:10]
            
            for enrollment in enrollments:
                course = enrollment.course
                progress = float(enrollment.progress) if enrollment.progress else 0.0
                completed_lessons = enrollment.completed_lessons or 0
                is_completed = enrollment.is_completed
                
                # Format enrollment info
                enrollment_info = (
                    f"Your Enrollment: {course.title}\n"
                    f"Progress: {progress:.1f}%\n"
                    f"Completed Lessons: {completed_lessons}\n"
                    f"Status: {'Completed' if is_completed else 'In Progress'}\n"
                    f"Enrolled: {enrollment.enrolled_at.strftime('%Y-%m-%d') if enrollment.enrolled_at else 'N/A'}"
                )
                if enrollment.completed_at:
                    enrollment_info += f"\nCompleted: {enrollment.completed_at.strftime('%Y-%m-%d')}"
                
                chunks.append(enrollment_info)
                if "enrollments" not in used_sources:
                    used_sources.append("enrollments")

        # Handle course queries - fetch all courses if catalog query, otherwise keyword search
        if search_all or "courses" in requested_sources or is_course_catalog_query:
            # Check cache for course catalog first
            from .cache_service import ChatbotCacheService
            
            if is_course_catalog_query:
                # Try cache first for course catalog
                cached_courses = ChatbotCacheService.get_course_catalog()
                if cached_courses:
                    logger.info(f"Cache HIT for course catalog, using {len(cached_courses)} cached courses")
                    # Convert cached data to chunks
                    for course_data in cached_courses:
                        chunks.append(course_data)
                    if "courses" not in used_sources:
                        used_sources.append("courses")
                else:
                    # For catalog queries (list all courses), fetch all published courses
                    courses = Course.objects.filter(
                        status="published"
                    ).select_related('instructor', 'category', 'level').order_by('-created_at')[:20]
                    
                    course_count = 0
                    course_data_list = []
                    
                    for course in courses:
                        course_count += 1
                        # Format price
                        try:
                            price_float = float(course.price) if course.price else 0.0
                            price_str = f"${price_float:.2f}" if price_float > 0 else "Free"
                        except (ValueError, TypeError):
                            price_str = "Free"
                        # Get instructor name
                        instructor_name = course.instructor.get_full_name() or course.instructor.first_name or course.instructor.username if course.instructor else "Not specified"
                        # Get category and level if available
                        category_name = course.category.name if course.category else None
                        level_name = course.level.name if course.level else None
                        
                        # Build course chunk with all information in a clear format
                        course_info = f"Course {course_count}: {course.title}\nPrice: {price_str}\nInstructor: {instructor_name}"
                        if category_name:
                            course_info += f"\nCategory: {category_name}"
                        if level_name:
                            course_info += f"\nLevel: {level_name}"
                        if course.description:
                            course_info += f"\nDescription: {course.description[:200]}"
                        
                        chunks.append(course_info)
                        course_data_list.append(course_info)
                        if "courses" not in used_sources:
                            used_sources.append("courses")
                    
                    # Cache the course catalog data
                    if course_data_list:
                        ChatbotCacheService.set_course_catalog(course_data_list)
                        logger.info(f"Cached {len(course_data_list)} courses for catalog query")
                    
                    # Log for debugging
                    if course_count > 0:
                        logger.info(f"Fetched {course_count} courses for catalog query: {query[:100]}")
                    else:
                        logger.warning(f"No published courses found in database for query: {query[:100]}")
            else:
                # For specific queries, do keyword search
                courses = Course.objects.filter(
                    Q(title__icontains=query) | Q(description__icontains=query),
                    status="published"
                ).select_related('instructor', 'category', 'level')[:10]
                
                course_count = 0
                for course in courses:
                    course_count += 1
                    # Format price
                    try:
                        price_float = float(course.price) if course.price else 0.0
                        price_str = f"${price_float:.2f}" if price_float > 0 else "Free"
                    except (ValueError, TypeError):
                        price_str = "Free"
                    # Get instructor name
                    instructor_name = course.instructor.get_full_name() or course.instructor.first_name or course.instructor.username if course.instructor else "Not specified"
                    # Get category and level if available
                    category_name = course.category.name if course.category else None
                    level_name = course.level.name if course.level else None
                    
                    # Build course chunk with all information in a clear format
                    course_info = f"Course {course_count}: {course.title}\nPrice: {price_str}\nInstructor: {instructor_name}"
                    if category_name:
                        course_info += f"\nCategory: {category_name}"
                    if level_name:
                        course_info += f"\nLevel: {level_name}"
                    if course.description:
                        course_info += f"\nDescription: {course.description[:200]}"
                    
                    chunks.append(course_info)
                    if "courses" not in used_sources:
                        used_sources.append("courses")
                
                # Log for debugging (keyword search)
                if course_count > 0:
                    logger.info(f"Fetched {course_count} courses for keyword search: {query[:100]}")

        # Basic keyword search in FAQs
        if search_all or "faqs" in requested_sources:
            faqs = CourseFAQ.objects.filter(
                Q(question__icontains=query) | Q(answer__icontains=query)
            )[:3]
            for faq in faqs:
                chunks.append(f"FAQ: {faq.question}\n{faq.answer[:200]}")
                if "faqs" not in used_sources:
                    used_sources.append("faqs")

        if not chunks:
            chunks.append(
                "Emerald LMS lets you browse courses, enroll, watch lessons, take quizzes, "
                "submit assignments, and chat with instructors."
            )
            used_sources.append("platform_help")

        return chunks, used_sources

    @staticmethod
    def _is_personal_data_query(query: str) -> bool:
        """
        Detects if the query is asking for personal user data.
        This helps determine if we need to fetch user-specific context.
        """
        personal_keywords = [
            r'\bmy\b', r'\bme\b', r'\bi\b', r'\bmyself\b',
            r'\bprogress\b', r'\benrolled\b',
            r'\blessons?\b', r'\bassignments?\b', r'\bquizzes?\b',
            r'\bcertificate\b', r'\bcompletion\b', r'\bcompleted\b',
            r'\bwhat.*my\b', r'\bshow.*my\b', r'\blist.*my\b',
            r'\bhow.*my\b', r'\bwhere.*my\b'
        ]
        query_lower = query.lower()
        # Don't match "courses" alone - only when combined with "my"
        for pattern in personal_keywords:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        # Check for "my courses" specifically
        if re.search(r'\bmy\s+courses?\b', query_lower, re.IGNORECASE):
            return True
        return False

    @staticmethod
    def _is_course_catalog_query(query: str) -> bool:
        """
        Detects if the query is asking to list/show all courses (catalog query).
        This triggers fetching all published courses instead of keyword search.
        """
        query_lower = query.lower()
        
        # Simple keyword checks first (faster)
        has_courses = 'course' in query_lower
        has_available = 'avail' in query_lower  # Matches "available" or "avilable" (typo)
        has_list = 'list' in query_lower
        has_show = 'show' in query_lower or 'display' in query_lower
        has_what = 'what' in query_lower and has_courses
        has_price = 'price' in query_lower
        has_instructor = 'instructor' in query_lower or 'teacher' in query_lower
        
        # If query mentions courses + (list/show/available/what) OR (price + instructor)
        if has_courses and (has_list or has_show or has_available or has_what or (has_price and has_instructor)):
            return True
        
        # Detailed regex patterns for more specific matching
        catalog_keywords = [
            r'\blist\s+(all\s+)?(available\s+)?courses?\b',
            r'\bshow\s+(all\s+)?(available\s+)?courses?\b',
            r'\b(all\s+)?available\s+courses?\b',
            r'\bwhat\s+courses?\s+.*?(are|do|available)',
            r'\bcourses?\s+.*?(available|are)',
            r'\bcourse\s+catalog\b',
            r'\bcourses?\s+with\s+(prices?|instructors?)',
            r'\bdisplay\s+(all\s+)?courses?\b',
            r'\bget\s+(all\s+)?courses?\b',
            r'\bsee\s+(all\s+)?courses?\b',
            r'\bcourses?\s+.*?price.*?instructor',
            r'\bcourses?\s+.*?instructor.*?price',
        ]
        
        for pattern in catalog_keywords:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        return False


