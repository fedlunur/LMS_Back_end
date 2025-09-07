from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from courses.models import Course,Lesson
from courses.serializers import DynamicFieldSerializer
from courses.views import GenericModelViewSet

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response


# class CourseViewSet(GenericModelViewSet):
#     queryset = Course.objects.all()  # always use Course

#     # Override get_queryset to ignore GenericModelViewSet's model_mapping
#     def get_queryset(self):
#         return Course.objects.all()

#     # Use DynamicFieldSerializer for Course
#     def get_serializer(self, *args, **kwargs):
#         if "model_name" not in kwargs:
#             kwargs["model_name"] = "course"
#         return DynamicFieldSerializer(*args, **kwargs)

#     @action(detail=True, methods=["get"], url_path="with-lessons")
#     def with_lessons(self, request, pk=None):
#         """
#         Return all lessons for a specific course
#         """
#         try:
#             course = self.get_queryset().get(pk=pk)
#         except Course.DoesNotExist:
#             return Response(
#                 {"success": False, "message": "Course not found"},
#                 status=status.HTTP_404_NOT_FOUND
#             )

#         # Get all lessons for this course
#         lessons = Lesson.objects.filter(course_id=course.id).order_by("order")

#         # Serialize lessons using DynamicFieldSerializer with model_name='lesson'
#         serializer = DynamicFieldSerializer(
#             lessons,
#             many=True,
#             context={"request": request},
#             model_name="lesson"
#         )

#         return Response(
#             {"success": True, "data": serializer.data, "message": "Lessons retrieved successfully."},
#             status=status.HTTP_200_OK
#         )


from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from courses.models import Course, Lesson
from courses.serializers import DynamicFieldSerializer
from courses.views import GenericModelViewSet
class CourseViewSet(GenericModelViewSet):
    queryset = Course.objects.all()
    serializer_class = DynamicFieldSerializer  # your dynamic serializer

    # Ignore GenericModelViewSet's model_mapping
    def get_queryset(self):
        return Course.objects.all()

    def get_serializer(self, *args, **kwargs):
        kwargs["model_name"] = "course"  # fixed for Course
        return DynamicFieldSerializer(*args, **kwargs)

    @action(detail=True, methods=["get"], url_path="with-lessons")
    def with_lessons(self, request, pk=None):
        from courses.models import Lesson
        try:
            course = self.get_queryset().get(pk=pk)
            lessons = Lesson.objects.filter(course_id=course.id).order_by("order")

            sections = [{
                "id": 1,
                "title": "All Lessons",
                "lessons": [
                    {
                        "id": l.id,
                        "title": l.title,
                        "content_type": l.content_type,
                        "duration": l.duration,
                        "order": l.order,
                        "completed": False,
                    } for l in lessons
                ]
            }]

            course_data = {
                "id": course.id,
                "title": course.title,
                "description": course.description,
                "instructor_name": f"{course.instructor.first_name} {course.instructor.last_name}" if course.instructor else "",
                "category": course.category.name if course.category else "",
                "thumbnail": course.thumbnail.url if course.thumbnail else None,
                "rating": 0,
                "total_lessons": lessons.count(),
                "duration": "0:00",
                "progress": 0,
                "completed": False,
                "sections": sections,
            }

            return Response({"success": True, "data": course_data, "message": "Course retrieved successfully."})

        except Course.DoesNotExist:
            return Response({"success": False, "message": "Course not found."}, status=404)
