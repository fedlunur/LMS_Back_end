"""
Management command to index LMS content into the vector database.
Run this command to populate the vector store with courses, lessons, FAQs, etc.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from courses.models import Course, Lesson, CourseFAQ, CourseAnnouncement, Enrollment
from chat.services.vector_store import VectorStore
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Index LMS content (courses, lessons, FAQs, announcements) into vector database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing vector store before indexing',
        )
        parser.add_argument(
            '--type',
            type=str,
            choices=['courses', 'lessons', 'faqs', 'announcements', 'all'],
            default='all',
            help='Type of content to index (default: all)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting content indexing...'))

        try:
            vector_store = VectorStore()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to initialize vector store: {e}'))
            return

        # Clear if requested
        if options['clear']:
            self.stdout.write(self.style.WARNING('Clearing existing vector store...'))
            # Note: ChromaDB doesn't have a simple clear method, so we'll delete by type
            # For a full clear, you'd need to delete the collection and recreate it
            self.stdout.write(self.style.WARNING('Note: Full clear requires manual collection deletion'))

        index_type = options['type']
        total_indexed = 0

        # Index courses
        if index_type in ['courses', 'all']:
            total_indexed += self._index_courses(vector_store)

        # Index lessons
        if index_type in ['lessons', 'all']:
            total_indexed += self._index_lessons(vector_store)

        # Index FAQs
        if index_type in ['faqs', 'all']:
            total_indexed += self._index_faqs(vector_store)

        # Index announcements
        if index_type in ['announcements', 'all']:
            total_indexed += self._index_announcements(vector_store)

        # Get stats
        stats = vector_store.get_collection_stats()
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Successfully indexed {total_indexed} items. '
                f'Total documents in vector store: {stats["total_documents"]}'
            )
        )

    def _index_courses(self, vector_store: VectorStore) -> int:
        """Index published courses."""
        self.stdout.write('Indexing courses...')
        courses = Course.objects.filter(status='published').select_related('instructor', 'category', 'level')
        
        documents = []
        metadatas = []
        ids = []

        for course in courses:
            # Build course text content
            content_parts = [
                f"Title: {course.title}",
                f"Description: {course.description}" if course.description else "",
            ]
            
            # Add price information
            price_str = f"${float(course.price):.2f}" if course.price else "Free"
            content_parts.append(f"Price: {price_str}")
            
            # Add instructor information
            instructor_name = course.instructor.get_full_name() or course.instructor.first_name or course.instructor.username
            content_parts.append(f"Instructor: {instructor_name}")
            
            if course.category:
                content_parts.append(f"Category: {course.category.name}")
            if course.level:
                content_parts.append(f"Level: {course.level.name}")
            if course.objective:
                objectives = course.objective if isinstance(course.objective, list) else []
                if objectives:
                    content_parts.append(f"Objectives: {', '.join(objectives)}")
            if course.what_you_will_learn:
                learn_items = course.what_you_will_learn if isinstance(course.what_you_will_learn, list) else []
                if learn_items:
                    content_parts.append(f"What you'll learn: {', '.join(learn_items)}")
            if course.requirements:
                reqs = course.requirements if isinstance(course.requirements, list) else []
                if reqs:
                    content_parts.append(f"Requirements: {', '.join(reqs)}")

            content = "\n".join([p for p in content_parts if p])
            if not content.strip():
                continue

            documents.append(content)
            metadatas.append({
                "type": "course",
                "id": f"course_{course.id}",
                "course_id": course.id,
                "title": course.title,
                "instructor_id": course.instructor.id,
                "instructor_name": instructor_name,
                "price": str(course.price),
            })
            ids.append(f"course_{course.id}")

        if documents:
            vector_store.add_documents(documents, metadatas, ids)
            self.stdout.write(self.style.SUCCESS(f'  ✓ Indexed {len(documents)} courses'))
            return len(documents)
        return 0

    def _index_lessons(self, vector_store: VectorStore) -> int:
        """Index lessons from published courses."""
        self.stdout.write('Indexing lessons...')
        lessons = Lesson.objects.filter(
            course__status='published'
        ).select_related('course', 'module')

        documents = []
        metadatas = []
        ids = []

        for lesson in lessons:
            content_parts = [
                f"Title: {lesson.title}",
                f"Description: {lesson.description}" if lesson.description else "",
                f"Course: {lesson.course.title}",
                f"Type: {lesson.get_content_type_display()}",
            ]

            # Add lesson-specific content based on type
            if lesson.content_type == Lesson.ContentType.ARTICLE:
                try:
                    article = lesson.article
                    if article.content:
                        content_parts.append(f"Content: {article.content[:500]}")
                except:
                    pass
            elif lesson.content_type == Lesson.ContentType.VIDEO:
                try:
                    video = lesson.video
                    if video.description:
                        content_parts.append(f"Description: {video.description}")
                    if video.transcript:
                        content_parts.append(f"Transcript: {video.transcript[:500]}")
                except:
                    pass

            content = "\n".join([p for p in content_parts if p])
            if not content.strip():
                continue

            documents.append(content)
            metadatas.append({
                "type": "lesson",
                "id": f"lesson_{lesson.id}",
                "lesson_id": lesson.id,
                "course_id": lesson.course.id,
                "title": lesson.title,
                "content_type": lesson.content_type,
            })
            ids.append(f"lesson_{lesson.id}")

        if documents:
            vector_store.add_documents(documents, metadatas, ids)
            self.stdout.write(self.style.SUCCESS(f'  ✓ Indexed {len(documents)} lessons'))
            return len(documents)
        return 0

    def _index_faqs(self, vector_store: VectorStore) -> int:
        """Index course FAQs."""
        self.stdout.write('Indexing FAQs...')
        faqs = CourseFAQ.objects.all().select_related('course')

        documents = []
        metadatas = []
        ids = []

        for faq in faqs:
            content = f"Question: {faq.question}\n\nAnswer: {faq.answer}"
            
            documents.append(content)
            metadatas.append({
                "type": "faq",
                "id": f"faq_{faq.id}",
                "faq_id": faq.id,
                "course_id": faq.course.id,
                "title": faq.question[:100],  # Use question as title (truncated)
            })
            ids.append(f"faq_{faq.id}")

        if documents:
            vector_store.add_documents(documents, metadatas, ids)
            self.stdout.write(self.style.SUCCESS(f'  ✓ Indexed {len(documents)} FAQs'))
            return len(documents)
        return 0

    def _index_announcements(self, vector_store: VectorStore) -> int:
        """Index course announcements."""
        self.stdout.write('Indexing announcements...')
        announcements = CourseAnnouncement.objects.filter(
            is_published=True
        ).select_related('course', 'instructor')

        documents = []
        metadatas = []
        ids = []

        for announcement in announcements:
            content = f"Title: {announcement.title}\n{announcement.content}"
            
            documents.append(content)
            metadatas.append({
                "type": "announcement",
                "id": f"announcement_{announcement.id}",
                "announcement_id": announcement.id,
                "course_id": announcement.course.id,
                "title": announcement.title,
                "priority": announcement.priority,
            })
            ids.append(f"announcement_{announcement.id}")

        if documents:
            vector_store.add_documents(documents, metadatas, ids)
            self.stdout.write(self.style.SUCCESS(f'  ✓ Indexed {len(documents)} announcements'))
            return len(documents)
        return 0

