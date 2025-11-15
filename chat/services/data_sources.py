from typing import Tuple, List, Optional
from django.db.models import Q
from courses.models import Course, Lesson, CourseFAQ, CourseAnnouncement, Enrollment
import logging

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

        # Use vector search if available and has content
        if self.use_vector_search and self.vector_store:
            stats = self.vector_store.get_collection_stats()
            if stats["total_documents"] > 0:
                chunks, used_sources = self._get_vector_context(query, user, requested_sources)
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

        # Determine what to search
        search_all = "all" in requested_sources or len(requested_sources) == 0
        search_courses = search_all or "courses" in requested_sources
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
            results = self.vector_store.search(query=query, n_results=10)
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
                    # For other types, just use type filter
                    filter_meta = {"type": doc_type}
                    search_results = self.vector_store.search(
                        query=query,
                        n_results=5,  # Get more results per type
                        filter_metadata=filter_meta
                    )
                    results.extend(search_results)

        # Format results into chunks
        seen_ids = set()
        for result in results[:10]:  # Limit to top 10 results
            doc_id = result.get("metadata", {}).get("id")
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                content = result.get("content", "")
                metadata = result.get("metadata", {})
                doc_type = metadata.get("type", "unknown")

                # Format chunk with metadata
                if doc_type == "course":
                    course_title = metadata.get("title", "Course")
                    chunk = f"Course: {course_title}\n{content}"
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

        # Fallback if no results
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

        # Basic keyword search in courses
        if search_all or "courses" in requested_sources:
            courses = Course.objects.filter(
                Q(title__icontains=query) | Q(description__icontains=query),
                status="published"
            )[:3]
            for course in courses:
                chunks.append(f"Course: {course.title}\n{course.description[:200]}")
                used_sources.append("courses")

        # Basic keyword search in FAQs
        if search_all or "faqs" in requested_sources:
            faqs = CourseFAQ.objects.filter(
                Q(question__icontains=query) | Q(answer__icontains=query)
            )[:3]
            for faq in faqs:
                chunks.append(f"FAQ: {faq.question}\n{faq.answer[:200]}")
                used_sources.append("faqs")

        if not chunks:
            chunks.append(
                "Emerald LMS lets you browse courses, enroll, watch lessons, take quizzes, "
                "submit assignments, and chat with instructors."
            )
            used_sources.append("platform_help")

        return chunks, used_sources


