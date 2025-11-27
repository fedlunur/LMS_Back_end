from django.urls import path, re_path
from django.contrib import admin
from django.urls import path,include
from django.conf.urls.static import static

from user_managment.views import *
from courses.views import (
    GenericModelViewSet,
    mark_lesson_completed_view,
    get_video_player_data_view,
    submit_video_checkpoint_answer_view,
    enroll_in_course_view,
    get_enrolled_courses_view,
    get_published_courses_view,
    get_course_overview_view,
    list_course_lessons_view,
    get_lesson_detail_view,
    submit_quiz_view,
    submit_assignment_view,
    submit_assignment_and_complete_view,
    student_assignment_history_view,
    get_final_assessment_view,
    submit_final_assessment_view,
    get_course_progress_view,
    get_student_analytics_view,
    get_quiz_results_view,
    get_teacher_dashboard_overview_view,
    get_teacher_recent_activities_view,
    get_teacher_dashboard_summary_view,
    get_teacher_course_enrollments_detail_view,
    get_teacher_students_overview_view,
    get_teacher_students_list_view,
    get_instructor_courses_view,
    get_course_students_view,
    get_student_progress_view,
    get_assignment_submissions_view,
    grade_assignment_view,
    get_certificate_view,
    list_course_modules_view,
    list_module_lessons_view,
    rate_course_view,
    verify_certificate_view,
    # New quiz endpoints
    start_quiz_attempt_view,
    get_quiz_questions_view,
    get_quiz_attempt_history_view,
    create_quiz_view,
    get_quiz_analytics_view,
    get_all_student_attempts_view,
    # Event views
    get_student_calendar_view,
    # Notification views
    get_notifications_view,
    get_unread_notifications_view,
    get_unread_count_view,
    mark_notification_read_view,
    mark_all_notifications_read_view,
    get_notification_view,
    # Question bank views
    question_banks_list_create_view,
    question_bank_detail_view,
    question_bank_questions_list_create_view,
    question_bank_question_detail_view,
    export_questions_to_quiz_lesson_view,
    export_questions_to_assessment_view,
    import_questions_from_quiz_lesson_view,
    import_questions_from_assessment_view,
    # Public views
    get_public_statistics_view,
    get_top_rated_courses_view,
)
from courses.views.assignment_views import (
    get_peer_review_view,
    submit_peer_review_view,
    teacher_get_submissions_view,
    teacher_get_submission_detail_view,
    teacher_grade_submission_view,
)
from courses.views.assessment_views import (
    get_final_assessment_status_view,
    get_course_structure_view,
    get_assessment_attempts_view,
    start_final_assessment_view,
)
from courses.views.analytics_views import (
    get_teacher_earnings_overview_view,
    get_teacher_revenue_history_view,
    get_teacher_monthly_revenue_trend_view,
    get_teacher_student_engagement_metrics_view,
    get_teacher_top_performers_view,
    get_teacher_progress_distribution_view,
    get_teacher_students_analytics_overview_view,
    get_teacher_dashboard_overview_view,
    get_teacher_recent_activities_view,
    get_teacher_dashboard_summary_view,
    get_teacher_students_overview_view,
    get_teacher_recent_student_activity_view,
    get_teacher_course_performance_view,
    get_teacher_content_engagement_view,
    get_teacher_recent_assignments_view,
    get_teacher_quiz_analytics_view,
)
from courses.constants import *
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.conf import settings
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from chat.views import (
    ChatbotAPIView, 
    CreateChatRoomAPIView, 
    ListUserRoomsAPIView, 
    ListRoomMessagesAPIView,
    UploadChatFileAPIView,
    MarkMessagesAsReadAPIView,
    GetUnreadCountAPIView
)
from rest_framework.routers import DefaultRouter
router = DefaultRouter()
""" structure Routes """
# setting

from payments.views import create_checkout_session_view, stripe_webhook_view, confirm_checkout_session_view


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
    "articlelessonattachment",
    "lessonresource",
    "Certificate",
    "CourseBadge",
    "CourseQA",
    "courseresource",
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
    "event",
    "eventtype",
    "notification",
    "questionbank",
    "questionbankquestion",
    "questionbankanswer",
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
    re_path(r'^api/register/verify/?$', VerifyEmailOTP.as_view(), name='verify_email'),
    re_path(r'^api/register/resend-otp/?$', ResendEmailOTP.as_view(), name='resend_email_otp'),
    re_path(r'^api/forgot-password/request/?$', ForgotPasswordRequest.as_view(), name='forgot_password_request'),
    re_path(r'^api/forgot-password/reset/?$', ForgotPasswordReset.as_view(), name='forgot_password_reset'),
    re_path(r'^api/login/?$', UserLogin.as_view(), name='login'),
    re_path(r'^api/google-login/?$', GoogleLoginView.as_view(), name='google_login'),
    re_path(r'^api/user_logout/?$', UserLogout.as_view(), name='user_logout'),
    re_path(r'^api/mark-lesson-completed/(?P<lesson_id>\d+)/$', mark_lesson_completed_view, name='mark_lesson_completed'),
    
    # Public endpoints
    re_path(r'^api/public/statistics/?$', get_public_statistics_view, name='public_statistics'),
    re_path(r'^api/public/top-rated-courses/?$', get_top_rated_courses_view, name='top_rated_courses'),
    
    # Course browsing endpoints (for all authenticated users)
    re_path(r'^api/published-courses/$', get_published_courses_view, name='published_courses'),
    re_path(r'^api/courses-published/$', get_published_courses_view, name='published_courses_legacy'),
    re_path(r'^api/course-overview/(?P<course_id>\d+)/$', get_course_overview_view, name='course_overview'),
    re_path(r'^api/course-modules/(?P<course_id>\d+)/$', list_course_modules_view, name='course_modules'),
    re_path(r'^api/module-lessons/(?P<module_id>\d+)/$', list_module_lessons_view, name='module_lessons'),
    re_path(r'^api/course-lessons/(?P<course_id>\d+)/$', list_course_lessons_view, name='course_lessons'),
    re_path(r'^api/lesson-detail/(?P<lesson_id>\d+)/$', get_lesson_detail_view, name='lesson_detail'),
    re_path(r'^api/video-player/(?P<lesson_id>\d+)/$', get_video_player_data_view, name='video_player_data'),
    re_path(r'^api/video-player/submit/(?P<lesson_id>\d+)/$', submit_video_checkpoint_answer_view, name='video_checkpoint_submit'),
    
    # Enrollment endpoints
    re_path(r'^api/enroll-course/(?P<course_id>\d+)/$', enroll_in_course_view, name='enroll_course'),
    re_path(r'^api/enrolled-courses/$', get_enrolled_courses_view, name='enrolled_courses'),
    re_path(r'^api/rate-course/(?P<course_id>\d+)/$', rate_course_view, name='rate_course'),
    
    # Quiz endpoints - Students
    re_path(r'^api/quiz/start/(?P<lesson_id>\d+)/$', start_quiz_attempt_view, name='start_quiz_attempt'),
    re_path(r'^api/quiz/questions/(?P<lesson_id>\d+)/$', get_quiz_questions_view, name='get_quiz_questions'),
    re_path(r'^api/submit-quiz/(?P<lesson_id>\d+)/$', submit_quiz_view, name='submit_quiz'),
    re_path(r'^api/quiz-results/(?P<lesson_id>\d+)/$', get_quiz_results_view, name='quiz_results'),
    re_path(r'^api/quiz/attempts/(?P<lesson_id>\d+)/$', get_quiz_attempt_history_view, name='quiz_attempt_history'),
    
    # Quiz endpoints - Teachers
    re_path(r'^api/quiz/create/(?P<lesson_id>\d+)/$', create_quiz_view, name='create_quiz'),
    re_path(r'^api/quiz/analytics/(?P<lesson_id>\d+)/$', get_quiz_analytics_view, name='quiz_analytics'),
    re_path(r'^api/quiz/student-attempts/(?P<lesson_id>\d+)/$', get_all_student_attempts_view, name='all_student_attempts'),
    
    # Assignment endpoints
    re_path(r'^api/submit-assignment/(?P<lesson_id>\d+)/$', submit_assignment_view, name='submit_assignment'),
    re_path(r'^api/submit-assignment-complete/(?P<lesson_id>\d+)/$', submit_assignment_and_complete_view, name='submit_assignment_complete'),
    path('api/assignment-history/', student_assignment_history_view, name='student_assignment_history'),
    
    # Peer Review endpoints (Student)
    re_path(r'^api/peer-review/(?P<lesson_id>\d+)/$', get_peer_review_view, name='get_peer_review'),
    re_path(r'^api/peer-review/submit/(?P<peer_review_id>\d+)/$', submit_peer_review_view, name='submit_peer_review'),
    
    # Teacher Assignment Review endpoints
    re_path(r'^api/teacher/assignment-submissions/(?P<lesson_id>\d+)/$', teacher_get_submissions_view, name='teacher_assignment_submissions'),
    re_path(r'^api/teacher/submission/(?P<submission_id>\d+)/$', teacher_get_submission_detail_view, name='teacher_submission_detail'),
    re_path(r'^api/teacher/submission/(?P<submission_id>\d+)/grade/$', teacher_grade_submission_view, name='teacher_grade_submission'),
    
    # Final Assessment endpoints
    re_path(r'^api/final-assessment/(?P<course_id>\d+)/$', get_final_assessment_view, name='get_final_assessment'),
    re_path(r'^api/final-assessment/start/(?P<course_id>\d+)/$', start_final_assessment_view, name='start_final_assessment'),
    re_path(r'^api/submit-final-assessment/(?P<course_id>\d+)/$', submit_final_assessment_view, name='submit_final_assessment'),
    re_path(r'^api/final-assessment/status/(?P<course_id>\d+)/$', get_final_assessment_status_view, name='get_final_assessment_status'),
    re_path(r'^api/final-assessment/attempts/(?P<course_id>\d+)/$', get_assessment_attempts_view, name='get_assessment_attempts'),
    re_path(r'^api/course-structure/(?P<course_id>\d+)/$', get_course_structure_view, name='get_course_structure'),
    
    # Progress endpoints
    re_path(r'^api/course-progress/(?P<course_id>\d+)/$', get_course_progress_view, name='course_progress'),
    re_path(r'^api/student-analytics/$', get_student_analytics_view, name='student_analytics'),
    
    # Teacher/Instructor endpoints
    re_path(r'^api/teacher/courses/?$', get_instructor_courses_view, name='teacher_courses'),
    re_path(r'^api/teacher/dashboard/overview/?$', get_teacher_dashboard_overview_view, name='teacher_dashboard_overview'),
    re_path(r'^api/teacher/dashboard/overview/(?P<course_id>\d+)/?$', get_teacher_dashboard_overview_view, name='teacher_dashboard_overview_by_course'),
    path('api/teacher/dashboard/overview/<int:course_id>/', get_teacher_dashboard_overview_view, name='teacher_dashboard_overview_by_course_path'),
    re_path(r'^api/teacher/dashboard/activities/?$', get_teacher_recent_activities_view, name='teacher_recent_activities'),
    re_path(r'^api/teacher/dashboard/summary/?$', get_teacher_dashboard_summary_view, name='teacher_dashboard_summary'),
    re_path(r'^api/teacher/courses/enrollments/(?P<course_id>\d+)/?$', get_teacher_course_enrollments_detail_view, name='teacher_course_enrollments_detail'),
    re_path(r'^api/teacher/students/overview/?$', get_teacher_students_overview_view, name='teacher_students_overview'),
    re_path(r'^api/teacher/students/list/?$', get_teacher_students_list_view, name='teacher_students_list'),
    re_path(r'^api/teacher/earnings/overview/?$', get_teacher_earnings_overview_view, name='teacher_earnings_overview'),
    re_path(r'^api/teacher/earnings/revenue-history/?$', get_teacher_revenue_history_view, name='teacher_revenue_history'),
    re_path(r'^api/teacher/analytics/monthly-revenue-trend/?$', get_teacher_monthly_revenue_trend_view, name='teacher_monthly_revenue_trend'),
    re_path(r'^api/teacher/analytics/student-engagement/?$', get_teacher_student_engagement_metrics_view, name='teacher_student_engagement_metrics'),
    re_path(r'^api/teacher/analytics/top-performers/?$', get_teacher_top_performers_view, name='teacher_top_performers'),
    re_path(r'^api/teacher/analytics/progress-distribution/?$', get_teacher_progress_distribution_view, name='teacher_progress_distribution'),
    re_path(r'^api/teacher/analytics/students-overview/?$', get_teacher_students_analytics_overview_view, name='teacher_students_analytics_overview'),
    re_path(r'^api/teacher/analytics/course-performance/?$', get_teacher_course_performance_view, name='teacher_course_performance'),
    re_path(r'^api/teacher/analytics/content-engagement/?$', get_teacher_content_engagement_view, name='teacher_content_engagement'),
    re_path(r'^api/teacher/analytics/recent-assignments/?$', get_teacher_recent_assignments_view, name='teacher_recent_assignments'),
    re_path(r'^api/teacher/analytics/quiz-analytics/?$', get_teacher_quiz_analytics_view, name='teacher_quiz_analytics'),
    re_path(r'^api/teacher/dashboard/recent-student-activity/?$', get_teacher_recent_student_activity_view, name='teacher_recent_student_activity'),
    re_path(r'^api/course-students/(?P<course_id>\d+)/$', get_course_students_view, name='course_students'),
    re_path(r'^api/student-progress/(?P<course_id>\d+)/(?P<student_id>\d+)/$', get_student_progress_view, name='student_progress'),
    re_path(r'^api/assignment-submissions/(?P<lesson_id>\d+)/$', get_assignment_submissions_view, name='assignment_submissions'),
    re_path(r'^api/grade-assignment/(?P<submission_id>\d+)/$', grade_assignment_view, name='grade_assignment'),
    re_path(r'^api/certificate/(?P<enrollment_id>\d+)/$', get_certificate_view, name='get_certificate'),
    re_path(r'^api/verify-certificate/(?P<certificate_number>[-A-Z0-9]+)/$', verify_certificate_view, name='verify_certificate'),

    # User profile
    re_path(r'^api/profile/?$', UserView.as_view(), name='get_profile'),
    re_path(r'^api/profile/update/$', UpdateProfileView.as_view(), name='update_profile'),
    re_path(r'^api/teacher/(?P<user_id>\d+)/$', TeacherDetailView.as_view(), name='teacher_detail'),
    re_path(r'^api/user/(?P<user_id>\d+)/?$', UserDetailView.as_view(), name='user_detail'),
    
    # Question Bank endpoints (place before router to ensure proper matching)
    # With /api/ prefix (standard)
    re_path(r'^api/question-banks/?$', question_banks_list_create_view, name='question_banks_list_create'),
    re_path(r'^api/question-banks/(?P<bank_id>\d+)/?$', question_bank_detail_view, name='question_bank_detail'),
    re_path(r'^api/question-banks/(?P<bank_id>\d+)/questions/?$', question_bank_questions_list_create_view, name='question_bank_questions_list_create'),
    re_path(r'^api/question-banks/(?P<bank_id>\d+)/questions/(?P<question_id>\d+)/?$', question_bank_question_detail_view, name='question_bank_question_detail'),
    re_path(r'^api/question-banks/(?P<bank_id>\d+)/export-to-quiz/(?P<lesson_id>\d+)/?$', export_questions_to_quiz_lesson_view, name='export_questions_to_quiz_lesson'),
    re_path(r'^api/question-banks/(?P<bank_id>\d+)/export-to-assessment/(?P<course_id>\d+)/?$', export_questions_to_assessment_view, name='export_questions_to_assessment'),
    re_path(r'^api/question-banks/(?P<bank_id>\d+)/import-from-quiz/(?P<lesson_id>\d+)/?$', import_questions_from_quiz_lesson_view, name='import_questions_from_quiz_lesson'),
    re_path(r'^api/question-banks/(?P<bank_id>\d+)/import-from-assessment/(?P<course_id>\d+)/?$', import_questions_from_assessment_view, name='import_questions_from_assessment'),
    
    # Without /api/ prefix (fallback for reverse proxy scenarios)
    re_path(r'^question-banks/?$', question_banks_list_create_view, name='question_banks_list_create_no_prefix'),
    re_path(r'^question-banks/(?P<bank_id>\d+)/?$', question_bank_detail_view, name='question_bank_detail_no_prefix'),
    re_path(r'^question-banks/(?P<bank_id>\d+)/questions/?$', question_bank_questions_list_create_view, name='question_bank_questions_list_create_no_prefix'),
    re_path(r'^question-banks/(?P<bank_id>\d+)/questions/(?P<question_id>\d+)/?$', question_bank_question_detail_view, name='question_bank_question_detail_no_prefix'),
    re_path(r'^question-banks/(?P<bank_id>\d+)/export-to-quiz/(?P<lesson_id>\d+)/?$', export_questions_to_quiz_lesson_view, name='export_questions_to_quiz_lesson_no_prefix'),
    re_path(r'^question-banks/(?P<bank_id>\d+)/export-to-assessment/(?P<course_id>\d+)/?$', export_questions_to_assessment_view, name='export_questions_to_assessment_no_prefix'),
    re_path(r'^question-banks/(?P<bank_id>\d+)/import-from-quiz/(?P<lesson_id>\d+)/?$', import_questions_from_quiz_lesson_view, name='import_questions_from_quiz_lesson_no_prefix'),
    re_path(r'^question-banks/(?P<bank_id>\d+)/import-from-assessment/(?P<course_id>\d+)/?$', import_questions_from_assessment_view, name='import_questions_from_assessment_no_prefix'),

    # Generics
    re_path("api/", include(router.urls)),
    re_path("api/constants/", constants_view, name="constants"),

    # Payments
    re_path(r'^api/payments/create-checkout-session/(?P<course_id>\d+)/$', create_checkout_session_view, name='create_checkout_session'),
    # Alias to match frontend expectation
    re_path(r'^api/payments/checkout/(?P<course_id>\d+)/$', create_checkout_session_view, name='checkout_alias'),
    re_path(r'^api/payments/stripe/webhook/$', stripe_webhook_view, name='stripe_webhook'),
    # Success page can call this to finalize by session_id
    re_path(r'^api/payments/checkout/session/(?P<session_id>[^/]+)/confirm/$', confirm_checkout_session_view, name='confirm_checkout_session'),
  

    # Chat app
    re_path(r'^api/chat/chatbot/?$', ChatbotAPIView.as_view(), name='chatbot'),
    re_path(r'^api/chat/room/create/?$', CreateChatRoomAPIView.as_view(), name='chat_create_room'),
    re_path(r'^api/chat/rooms/?$', ListUserRoomsAPIView.as_view(), name='chat_list_rooms'),
    re_path(r'^api/chat/messages/(?P<room_number>[^/]+)/?$', ListRoomMessagesAPIView.as_view(), name='chat_list_messages'),
    re_path(r'^api/chat/upload/(?P<room_number>[^/]+)/?$', UploadChatFileAPIView.as_view(), name='chat_upload_file'),
    re_path(r'^api/chat/mark-read/(?P<room_number>[^/]+)/?$', MarkMessagesAsReadAPIView.as_view(), name='chat_mark_read'),
    re_path(r'^api/chat/unread-count/(?P<room_number>[^/]+)/?$', GetUnreadCountAPIView.as_view(), name='chat_unread_count'),
    
    # Events - Student calendar endpoint (special formatted view)
    re_path(r'^api/events/calendar/?$', get_student_calendar_view, name='student_calendar'),
    
    # Notification endpoints
    re_path(r'^api/notifications/?$', get_notifications_view, name='get_notifications'),
    re_path(r'^api/notifications/unread/?$', get_unread_notifications_view, name='get_unread_notifications'),
    re_path(r'^api/notifications/unread-count/?$', get_unread_count_view, name='get_unread_count'),
    re_path(r'^api/notifications/(?P<notification_id>\d+)/read/?$', mark_notification_read_view, name='mark_notification_read'),
    re_path(r'^api/notifications/read-all/?$', mark_all_notifications_read_view, name='mark_all_notifications_read'),
    re_path(r'^api/notifications/(?P<notification_id>\d+)/?$', get_notification_view, name='get_notification'),
    ] 
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns +=  static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)   