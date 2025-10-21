from django.urls import path, re_path
from django.contrib import admin
from django.urls import path,include
from django.conf.urls.static import static

from user_managment.views import *
from courses.views import *
from courses.constants import *
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.conf import settings
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from rest_framework.routers import DefaultRouter
router = DefaultRouter()
""" structure Routes """
# setting



router = DefaultRouter()           
for name in [
    "category",
    "level",
    "course",
    "module",
    "lesson",
    "enrollment",
    "videolesson",
    "quizlesson",
    "assignmentlesson",
    "articleLesson",
    "lessonresource",
    "Certificate",
    "CourseBadge",
    "CourseQA",
    "CourseResource",
    "CourseAnnouncement",
    "CheckpointQuizResponse",
    "VideoCheckpointQuiz",
    "VideoCheckpointResponse",
    "CourseRating",
    "Conversation",
    "Message",
]:
    router.register(name, GenericModelViewSet, basename=name)


urlpatterns = router.urls

urlpatterns = [
    path('api/admin/', admin.site.urls),
    re_path(r'^api/token/?$', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    re_path(r'^api/token/refresh/?$', TokenRefreshView.as_view(), name='token_refresh'),
    re_path(r'^api/token/check/?$', TokenCheckView.as_view(), name='token_check'),
    re_path(r'^api/logout/?$', LogoutView.as_view(), name='logout'),
    re_path(r'^api/register/?$', UserRegister.as_view(), name='register'),
    re_path(r'^api/login/?$', UserLogin.as_view(), name='login'),
    re_path(r'^api/user_logout/?$', UserLogout.as_view(), name='user_logout'),
    # Generics
    re_path("api/", include(router.urls)),
    re_path("api/constants/", constants_view, name="constants"),
    # /courses/1/with-lessons/

#    re_path(r"^api/coursewithlesson/(?P<pk>\d+)/with-lessons/$", course_with_lessons, name="course-with-lessons"),
     
    # re_path(r'^api/(?P<model_name>\w+)/list/?$', GenericListAPIView.as_view(), name='generic-list'),
    # re_path(r'^api/(?P<model_name>\w+)/search/?$', GenericListAPIView.as_view(), name='generic-list'),
    #  re_path(r'^api/(?P<model_name>\w+)/advanced-list/?$', advanced_list, name='advanced-paginated-list'),
  
     # re_path(r'^api/download/(?P<image_type>[A-Za-z0-9_]+)/(?P<file_path>.+)$', download_file, name='download_file'),
] 
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns +=  static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)   