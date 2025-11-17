from django.urls import path, re_path
from django.contrib import admin
from django.urls import path,include
from django.conf.urls.static import static

from user_managment.useroTpUtils import VerifyOTPView
from user_managment.views import *
from courses.views import *
from courses.constants import *
from django.urls import path, include
from courses.course_access import *
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
    'NewModel'
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
    
    re_path("^api/verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    re_path(r'^api/login/?$', UserLogin.as_view(), name='login'),
    re_path(r'^api/user_logout/?$', UserLogout.as_view(), name='user_logout'),
    # Generics
    re_path("api/", include(router.urls)),
    re_path("api/constants/", constants_view, name="constants"),
    # password change 
    re_path(r'^api/change-password/', PasswordChangeView.as_view(), name='change-password'),
    re_path("api/counts/", get_counts, name="counts"),
    ] 
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns +=  static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)   