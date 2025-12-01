# courses/admin.py
from django.contrib import admin
from .models import (
    Category, Level, Course, Module, Lesson,
    VideoLesson, QuizLesson, AssignmentLesson, ArticleLesson,
    VideoLessonAttachment, ArticleLessonAttachment, ArticleLessonExternalLink,
    LessonResource, LessonAttachment,
    QuizConfiguration, QuizQuestion, QuizAnswer, QuizAttempt, QuizResponse,
    Enrollment, LessonProgress, ResourceProgress, ModuleProgress,
    Certificate, CourseBadge, CourseQA, CourseResource, CourseAnnouncement,
    VideoCheckpointQuiz, VideoCheckpointResponse, CheckpointQuizResponse,
    CourseRating, Conversation, Message,
    CourseOverview, CourseFAQ, AssignmentSubmission,
    AssignmentSubmissionFile, PeerReviewAssignment, PeerRubricEvaluation, PeerReviewSummary,
    FinalCourseAssessment, AssessmentQuestion, AssessmentAnswer,
    AssessmentAttempt, AssessmentResponse, Event, EventType,
    Notification, QuestionBank, QuestionBankQuestion, QuestionBankAnswer,
)


# ================================
# INLINES – QUIZ (attached to Lesson)
# ================================

class QuizConfigurationInline(admin.StackedInline):
    model = QuizConfiguration
    can_delete = False
    extra = 0
    max_num = 1
    fields = (
        "time_limit", "passing_score", "max_attempts",
        "randomize_questions", "show_correct_answers", "grading_policy"
    )
    verbose_name = "Quiz Configuration"
    verbose_name_plural = "Quiz Configuration"




class QuizAnswerInline(admin.TabularInline):
    model = QuizAnswer
    extra = 1
    fields = ("answer_text", "answer_image", "is_correct", "order")

class QuizQuestionInline(admin.TabularInline):
    model = QuizQuestion
    extra = 1

 

# ================================
# OTHER INLINES
# ================================

class VideoLessonAttachmentInline(admin.TabularInline):
    model = VideoLessonAttachment
    extra = 1
    readonly_fields = ("uploaded_at",)


class ArticleLessonAttachmentInline(admin.TabularInline):
    model = ArticleLessonAttachment
    extra = 1
    readonly_fields = ("uploaded_at",)


class ArticleLessonExternalLinkInline(admin.TabularInline):
    model = ArticleLessonExternalLink
    extra = 1


class ResourceProgressInline(admin.TabularInline):
    model = ResourceProgress
    extra = 0
    readonly_fields = ("completed", "accessed_at", "completed_at")


class LessonProgressInline(admin.TabularInline):
    model = LessonProgress
    extra = 0
    readonly_fields = ("progress", "completed", "first_accessed", "last_accessed",
                       "completed_at", "time_spent")
    inlines = [ResourceProgressInline]


class AssessmentAnswerInline(admin.TabularInline):
    model = AssessmentAnswer
    extra = 2


class QuestionBankAnswerInline(admin.TabularInline):
    model = QuestionBankAnswer
    extra = 1
    fields = ("answer_text", "answer_image", "is_correct", "order")


class QuestionBankQuestionInline(admin.TabularInline):
    model = QuestionBankQuestion
    extra = 1
    fields = ("question_type", "question_text", "question_image", "explanation", "points", "order", "blanks")


# ================================
# ADMIN CLASSES
# ================================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")
    prepopulated_fields = {"code": ("name",)}


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "level", "price", "instructor",
                    "status", "created_at")
    list_filter = ("category", "level", "status", "created_at")
    search_fields = ("title", "description", "slug")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("-created_at",)
    autocomplete_fields = ("category", "level", "instructor", "approved_by")


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "order")
    list_filter = ("course",)
    search_fields = ("title",)
    ordering = ("course", "order")
    autocomplete_fields = ("course",)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "module", "content_type", "order", "created_at")
    list_filter = ("course", "content_type", "created_at")
    search_fields = ("title", "description")
    ordering = ("course", "module", "order")
    autocomplete_fields = ("course", "module")
    # Quiz inlines **stay here** – they belong to Lesson
    inlines = [QuizConfigurationInline, QuizQuestionInline]


@admin.register(VideoLesson)
class VideoLessonAdmin(admin.ModelAdmin):
    list_display = ("lesson", "youtube_url", "duration")
    search_fields = ("lesson__title",)
    inlines = [VideoLessonAttachmentInline]

@admin.register(QuizLesson)
class QuizLessonAdmin(admin.ModelAdmin):
    list_display = ("id", "lesson", "type", "time_limit", "passing_score", "attempts", "question_count")
    list_filter = ("type",)
    search_fields = ("lesson__title", "lesson__description")
    autocomplete_fields = ("lesson",)

    fieldsets = (
        ("Lesson Link", {"fields": ("lesson",)}),
        ("Settings", {
            "fields": (
                "time_limit",
                "passing_score",
                "attempts",
                "randomize_questions",
                "show_correct_answers",
                "grading_policy",
            ),
        }),
    )

    def question_count(self, obj):
        return obj.lesson.quiz_questions.count()

    question_count.short_description = "Questions"


    # def save_formset(self, request, form, formset, change):
    #     instances = formset.save(commit=False)
    #     for obj in instances:
    #         if isinstance(obj, QuizQuestion):
    #             # Auto-link question.lesson to quiz_lesson.lesson
    #             if obj.quiz_lesson and not obj.lesson:
    #                 obj.lesson = obj.quiz_lesson.lesson
    #         obj.save()
    #     formset.save_m2m()


@admin.register(AssignmentLesson)
class AssignmentLessonAdmin(admin.ModelAdmin):
    list_display = ("lesson", "due_date", "max_score")
    search_fields = ("lesson__title",)


@admin.register(ArticleLesson)
class ArticleLessonAdmin(admin.ModelAdmin):
    list_display = ("lesson", "title", "estimated_read_time")
    search_fields = ("lesson__title",)
    inlines = [ArticleLessonAttachmentInline, ArticleLessonExternalLinkInline]


@admin.register(LessonResource)
class LessonResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "lesson", "type")
    list_filter = ("type",)
    search_fields = ("title", "lesson__title")


# ------------------------------------------------------------------ #
# The rest of the admin registrations stay exactly the same as before
# ------------------------------------------------------------------ #

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "payment_status", "progress", "is_completed", "enrolled_at")
    list_filter = ("is_completed", "payment_status")
    search_fields = ("student__email", "course__title")
    readonly_fields = ("progress", "is_completed", "enrolled_at", "last_accessed", "completed_at")
    inlines = [LessonProgressInline]


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "lesson", "progress", "completed")
    list_filter = ("completed",)
    search_fields = ("enrollment__student__email", "lesson__title")
    inlines = [ResourceProgressInline]


@admin.register(ResourceProgress)
class ResourceProgressAdmin(admin.ModelAdmin):
    list_display = ("lesson_progress", "resource", "completed")
    list_filter = ("completed",)


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "certificate_number", "issued_date")
    search_fields = ("certificate_number", "enrollment__student__email")
    readonly_fields = ("certificate_number", "issued_date")


@admin.register(CourseBadge)
class CourseBadgeAdmin(admin.ModelAdmin):
    list_display = ("course", "badge_type", "is_active")
    list_filter = ("badge_type", "is_active")


@admin.register(CourseQA)
class CourseQAAdmin(admin.ModelAdmin):
    list_display = ("course", "student", "question_title", "is_answered")
    list_filter = ("is_answered", "is_pinned")


@admin.register(CourseResource)
class CourseResourceAdmin(admin.ModelAdmin):
    list_display = ("course", "title", "resource_type", "is_public")
    list_filter = ("resource_type", "is_public")


@admin.register(CourseAnnouncement)
class CourseAnnouncementAdmin(admin.ModelAdmin):
    list_display = ("course", "title", "priority", "is_published")
    list_filter = ("priority", "is_published")


@admin.register(VideoCheckpointQuiz)
class VideoCheckpointQuizAdmin(admin.ModelAdmin):
    list_display = ("lesson", "question_text", "timestamp_seconds")
    list_filter = ("lesson",)


@admin.register(VideoCheckpointResponse)
class VideoCheckpointResponseAdmin(admin.ModelAdmin):
    list_display = ("student", "checkpoint_quiz", "is_correct")
    list_filter = ("is_correct",)


@admin.register(CourseRating)
class CourseRatingAdmin(admin.ModelAdmin):
    list_display = ("course", "student", "rating", "is_approved")
    list_filter = ("rating", "is_approved")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("teacher", "student", "course", "last_message_at")
    search_fields = ("teacher__email", "student__email")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "sender", "sent_at", "is_read")
    list_filter = ("is_read", "message_type")


# ================================
# QUIZ SYSTEM (standalone)
# ================================

@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "lesson", "question_type", "question_text_snippet", "points")
    list_filter = ("question_type", "lesson")
    search_fields = ("question_text",)
    inlines = [QuizAnswerInline]

    def question_text_snippet(self, obj):
        txt = obj.question_text
        return txt[:50] + ("..." if len(txt) > 50 else "")
    question_text_snippet.short_description = "Question"


@admin.register(QuizAnswer)
class QuizAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "answer_text", "is_correct")
    list_filter = ("is_correct",)


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "lesson", "score", "passed", "attempt_number")
    list_filter = ("passed", "lesson")


@admin.register(QuizConfiguration)
class QuizConfigurationAdmin(admin.ModelAdmin):
    list_display = ("id", "lesson", "time_limit", "passing_score", "max_attempts")
    search_fields = ("lesson__title",)


@admin.register(QuizResponse)
class QuizResponseAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct")
    list_filter = ("is_correct",)


# ================================
# FINAL ASSESSMENT
# ================================

@admin.register(FinalCourseAssessment)
class FinalCourseAssessmentAdmin(admin.ModelAdmin):
    list_display = ("course", "title", "passing_score", "is_active")
    list_filter = ("is_active",)


@admin.register(AssessmentQuestion)
class AssessmentQuestionAdmin(admin.ModelAdmin):
    list_display = ("assessment", "question_type", "question_text_snippet", "points")
    list_filter = ("question_type",)
    inlines = [AssessmentAnswerInline]

    def question_text_snippet(self, obj):
        txt = obj.question_text
        return txt[:50] + ("..." if len(txt) > 50 else "")
    question_text_snippet.short_description = "Question"


@admin.register(AssessmentAnswer)
class AssessmentAnswerAdmin(admin.ModelAdmin):
    list_display = ("question", "answer_text", "is_correct")


@admin.register(AssessmentAttempt)
class AssessmentAttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "assessment", "score", "passed")
    list_filter = ("passed",)


@admin.register(AssessmentResponse)
class AssessmentResponseAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct")
    list_filter = ("is_correct",)


# ================================
# ATTACHMENTS & SUBMISSIONS
# ================================

@admin.register(LessonAttachment)
class LessonAttachmentAdmin(admin.ModelAdmin):
    list_display = ("lesson", "title", "uploaded_at")
    list_filter = ("uploaded_at",)


class AssignmentSubmissionFileInline(admin.TabularInline):
    model = AssignmentSubmissionFile
    extra = 0
    readonly_fields = ("uploaded_at", "file_size")


class PeerReviewAssignmentInline(admin.TabularInline):
    model = PeerReviewAssignment
    extra = 0
    readonly_fields = ("reviewer", "is_completed", "completed_at", "created_at")
    fk_name = "submission"


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "lesson", "status", "score", "final_score", "is_late", "late_deduction_applied")
    list_filter = ("status", "is_late")
    inlines = [AssignmentSubmissionFileInline, PeerReviewAssignmentInline]


@admin.register(AssignmentSubmissionFile)
class AssignmentSubmissionFileAdmin(admin.ModelAdmin):
    list_display = ("submission", "original_filename", "file_size", "uploaded_at")
    list_filter = ("uploaded_at",)
    search_fields = ("original_filename", "submission__student__email")


@admin.register(PeerReviewAssignment)
class PeerReviewAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "submission", "reviewer", "lesson", "is_completed", "completed_at")
    list_filter = ("is_completed", "lesson")
    search_fields = ("reviewer__email", "submission__student__email")


class PeerRubricEvaluationInline(admin.TabularInline):
    model = PeerRubricEvaluation
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(PeerRubricEvaluation)
class PeerRubricEvaluationAdmin(admin.ModelAdmin):
    list_display = ("peer_review", "criterion_name", "points_awarded", "max_points")
    list_filter = ("peer_review__lesson",)
    search_fields = ("criterion_name",)


@admin.register(PeerReviewSummary)
class PeerReviewSummaryAdmin(admin.ModelAdmin):
    list_display = ("submission", "total_rubric_score", "max_rubric_score", "reviewed_at")
    list_filter = ("reviewed_at",)
    search_fields = ("submission__student__email",)


@admin.register(ModuleProgress)
class ModuleProgressAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "module", "progress", "completed")
    list_filter = ("completed",)


@admin.register(CourseOverview)
class CourseOverviewAdmin(admin.ModelAdmin):
    list_display = ("course", "total_enrollments", "average_rating")
    readonly_fields = ("total_enrollments", "average_rating", "completion_rate")


@admin.register(CourseFAQ)
class CourseFAQAdmin(admin.ModelAdmin):
    list_display = ("course", "question")
    search_fields = ("question",)


@admin.register(EventType)
class EventTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "display_name", "icon", "color", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "display_name", "description")
    ordering = ("display_name",)
    fieldsets = (
        ("Event Type Information", {
            "fields": ("name", "display_name", "description")
        }),
        ("Display Settings", {
            "fields": ("icon", "color", "is_active")
        }),
    )


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "event_type", "start_datetime", "end_datetime", "created_at")
    list_filter = ("event_type", "start_datetime", "created_at")
    search_fields = ("title", "description", "course__title")
    date_hierarchy = "start_datetime"
    ordering = ("-start_datetime",)
    autocomplete_fields = ("course", "event_type")
    fieldsets = (
        ("Event Information", {
            "fields": ("title", "description", "event_type", "course")
        }),
        ("Schedule", {
            "fields": ("start_datetime", "end_datetime")
        }),
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("user__email", "title", "message")
    readonly_fields = ("created_at", "updated_at", "read_at")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    autocomplete_fields = ("user",)
    
    fieldsets = (
        ("Notification Information", {
            "fields": ("user", "notification_type", "title", "message")
        }),
        ("Related Content", {
            "fields": ("content_type", "object_id", "action_url", "icon")
        }),
        ("Status", {
            "fields": ("is_read", "read_at")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )


# ================================
# QUESTION BANK
# ================================

@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "teacher", "course", "is_active", "total_questions", "created_at")
    list_filter = ("is_active", "course", "created_at")
    search_fields = ("name", "description", "teacher__email", "course__title")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "total_questions")
    autocomplete_fields = ("teacher", "course")
    inlines = [QuestionBankQuestionInline]
    
    fieldsets = (
        ("Question Bank Information", {
            "fields": ("name", "description", "teacher", "course")
        }),
        ("Status", {
            "fields": ("is_active",)
        }),
        ("Statistics", {
            "fields": ("total_questions",),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def total_questions(self, obj):
        return obj.questions.count()
    total_questions.short_description = "Total Questions"


@admin.register(QuestionBankQuestion)
class QuestionBankQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "question_bank", "question_type", "question_text_snippet", "points", "order", "created_at")
    list_filter = ("question_type", "question_bank", "created_at")
    search_fields = ("question_text", "question_bank__name")
    ordering = ("question_bank", "order", "created_at")
    autocomplete_fields = ("question_bank",)
    inlines = [QuestionBankAnswerInline]
    
    fieldsets = (
        ("Question Information", {
            "fields": ("question_bank", "question_type", "question_text", "question_image", "explanation", "points", "order")
        }),
        ("Fill in Blank Settings", {
            "fields": ("blanks",),
            "classes": ("collapse",),
            "description": "For fill-in-blank and short-answer questions"
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    readonly_fields = ("created_at", "updated_at")
    
    def question_text_snippet(self, obj):
        txt = obj.question_text
        return txt[:50] + ("..." if len(txt) > 50 else "")
    question_text_snippet.short_description = "Question"


@admin.register(QuestionBankAnswer)
class QuestionBankAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "answer_text_snippet", "is_correct", "order")
    list_filter = ("is_correct", "question__question_bank")
    search_fields = ("answer_text", "question__question_text", "question__question_bank__name")
    ordering = ("question", "order")
    autocomplete_fields = ("question",)
    
    fieldsets = (
        ("Answer Information", {
            "fields": ("question", "answer_text", "answer_image", "is_correct", "order")
        }),
    )
    
    def answer_text_snippet(self, obj):
        txt = obj.answer_text
        return txt[:50] + ("..." if len(txt) > 50 else "")
    answer_text_snippet.short_description = "Answer"