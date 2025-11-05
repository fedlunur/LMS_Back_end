from django.urls import path, re_path
from django.contrib import admin
from django.urls import path,include
from django.conf.urls.static import static

from user_managment.views import *
from courses.views import (
    GenericModelViewSet,
    mark_lesson_completed_view,
    enroll_in_course_view,
    get_enrolled_courses_view,
    get_published_courses_view,
    get_course_overview_view,
    submit_quiz_view,
    submit_assignment_view,
    submit_assignment_and_complete_view,
    get_final_assessment_view,
    submit_final_assessment_view,
    get_course_progress_view,
    get_student_analytics_view,
    get_quiz_results_view,
    get_course_students_view,
    get_student_progress_view,
    get_assignment_submissions_view,
    grade_assignment_view,
    get_certificate_view,
    list_course_modules_view,
    list_module_lessons_view,
    rate_course_view,
    verify_certificate_view
)
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
    "course_overview",
    "course_faq",
    "lessonattachment",
    "quizquestion",
    "quizanswer",
    "quizattempt",
    "quizresponse",
    "quizconfiguration",
    "assignmentsubmission",
    "moduleprogress",
    "finalcourseassessment",
    "assessmentquestion",
    "assessmentanswer",
    "assessmentattempt",
    "assessmentresponse",
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
    re_path(r'^api/mark-lesson-completed/(?P<lesson_id>\d+)/$', mark_lesson_completed_view, name='mark_lesson_completed'),
    
    # Course browsing endpoints (for all authenticated users)
    re_path(r'^api/published-courses/$', get_published_courses_view, name='published_courses'),
    re_path(r'^api/course-overview/(?P<course_id>\d+)/$', get_course_overview_view, name='course_overview'),
    re_path(r'^api/course-modules/(?P<course_id>\d+)/$', list_course_modules_view, name='course_modules'),
    re_path(r'^api/module-lessons/(?P<module_id>\d+)/$', list_module_lessons_view, name='module_lessons'),
    
    # Enrollment endpoints
    re_path(r'^api/enroll-course/(?P<course_id>\d+)/$', enroll_in_course_view, name='enroll_course'),
    re_path(r'^api/enrolled-courses/$', get_enrolled_courses_view, name='enrolled_courses'),
    re_path(r'^api/rate-course/(?P<course_id>\d+)/$', rate_course_view, name='rate_course'),
    
    # Quiz endpoints
    re_path(r'^api/submit-quiz/(?P<lesson_id>\d+)/$', submit_quiz_view, name='submit_quiz'),
    re_path(r'^api/quiz-results/(?P<lesson_id>\d+)/$', get_quiz_results_view, name='quiz_results'),
    
    # Assignment endpoints
    re_path(r'^api/submit-assignment/(?P<lesson_id>\d+)/$', submit_assignment_view, name='submit_assignment'),
    re_path(r'^api/submit-assignment-complete/(?P<lesson_id>\d+)/$', submit_assignment_and_complete_view, name='submit_assignment_complete'),
    
    # Final Assessment endpoints
    re_path(r'^api/final-assessment/(?P<course_id>\d+)/$', get_final_assessment_view, name='get_final_assessment'),
    re_path(r'^api/submit-final-assessment/(?P<course_id>\d+)/$', submit_final_assessment_view, name='submit_final_assessment'),
    
    # Progress endpoints
    re_path(r'^api/course-progress/(?P<course_id>\d+)/$', get_course_progress_view, name='course_progress'),
    re_path(r'^api/student-analytics/$', get_student_analytics_view, name='student_analytics'),
    
    # Teacher/Instructor endpoints
    re_path(r'^api/course-students/(?P<course_id>\d+)/$', get_course_students_view, name='course_students'),
    re_path(r'^api/student-progress/(?P<course_id>\d+)/(?P<student_id>\d+)/$', get_student_progress_view, name='student_progress'),
    re_path(r'^api/assignment-submissions/(?P<lesson_id>\d+)/$', get_assignment_submissions_view, name='assignment_submissions'),
    re_path(r'^api/grade-assignment/(?P<submission_id>\d+)/$', grade_assignment_view, name='grade_assignment'),
    re_path(r'^api/certificate/(?P<enrollment_id>\d+)/$', get_certificate_view, name='get_certificate'),
    re_path(r'^api/verify-certificate/(?P<certificate_number>[-A-Z0-9]+)/$', verify_certificate_view, name='verify_certificate'),

    # User profile
    re_path(r'^api/profile/update/$', UpdateProfileView.as_view(), name='update_profile'),
    re_path(r'^api/teacher/(?P<user_id>\d+)/$', TeacherDetailView.as_view(), name='teacher_detail'),
    
    # Generics
    re_path("api/", include(router.urls)),
    re_path("api/constants/", constants_view, name="constants"),
  
    ] 
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns +=  static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)   