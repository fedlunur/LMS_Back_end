from django.contrib import admin
from .models import *
from django.contrib import admin
from django.contrib.admin import AdminSite

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    fieldsets = (
        (None, {
            "fields": ("name", "slug", "description", "icon")
        }),
        ("Metadata", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")
    prepopulated_fields = {"code": ("name",)}

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "level", "price", "instructor", "status", "created_at", "updated_at")
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
    ordering = ("course", "order")
    autocomplete_fields = ("course", "module")


class VideoLessonAttachmentInline(admin.TabularInline):
    model = VideoLessonAttachment
    extra = 1

@admin.register(VideoLesson)
class VideoLessonAdmin(admin.ModelAdmin):
    list_display = ("lesson", "youtube_url", "duration")
    search_fields = ("lesson__title",)
    inlines = [VideoLessonAttachmentInline]
    
@admin.register(QuizLesson)
class QuizLessonAdmin(admin.ModelAdmin):
    list_display = ("lesson", "type")
    search_fields = ("lesson__title",)
    # JSONField is editable in admin as raw JSON

@admin.register(AssignmentLesson)
class AssignmentLessonAdmin(admin.ModelAdmin):
    list_display = ("lesson", "due_date", "max_score")
    search_fields = ("lesson__title",)
    readonly_fields = ("rubric_criteria",)  # or keep editable as JSON

@admin.register(ArticleLesson)
class ArticleLessonAdmin(admin.ModelAdmin):
    list_display = ("lesson", "estimated_read_time", "external_links")
    search_fields = ("lesson__title",)


@admin.register(LessonResource)
class LessonResourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'lesson', 'type', 'file')
    list_filter = ('type',)
    search_fields = ('title', 'lesson__title')
    
class ResourceProgressInline(admin.TabularInline):
    model = ResourceProgress
    extra = 0
    readonly_fields = ("completed", "accessed_at", "completed_at")


class LessonProgressInline(admin.TabularInline):
    model = LessonProgress
    extra = 0
    readonly_fields = ("progress", "completed", "first_accessed", "last_accessed", "completed_at", "time_spent")
    inlines = [ResourceProgressInline]


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "student", "course", "progress", "is_completed", "enrolled_at", "last_accessed", "completed_at"
    )
    list_filter = ("is_completed", "payment_status", "enrolled_at", "last_accessed")
    search_fields = ("student__email", "course__title")
    date_hierarchy = "enrolled_at"
    readonly_fields = ("progress", "is_completed", "completed_lessons", "completed_at", "enrolled_at", "last_accessed")
    inlines = [LessonProgressInline]


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = (
        "enrollment", "lesson", "progress", "completed", "first_accessed", "last_accessed", "completed_at"
    )
    list_filter = ("completed", "first_accessed", "last_accessed")
    search_fields = ("enrollment__student__email", "lesson__title")
    readonly_fields = ("first_accessed", "last_accessed", "completed_at", "time_spent")
    inlines = [ResourceProgressInline]


@admin.register(ResourceProgress)
class ResourceProgressAdmin(admin.ModelAdmin):
    list_display = (
        "lesson_progress", "resource", "completed", "accessed_at", "completed_at"
    )
    list_filter = ("completed", "accessed_at")
    search_fields = ("lesson_progress__enrollment__student__email", "resource__name")
    readonly_fields = ("accessed_at", "completed_at")


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "certificate_number", "issued_date", "grade")
    search_fields = ("certificate_number", "enrollment__student__email", "enrollment__course__title")
    list_filter = ("grade", "issued_date")
    readonly_fields = ("certificate_number", "issued_date")


@admin.register(CourseBadge)
class CourseBadgeAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "badge_type", "is_active", "awarded_at", "expires_at")
    list_filter = ("badge_type", "is_active")
    search_fields = ("course__title",)


@admin.register(CourseQA)
class CourseQAAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "student", "question_title", "is_answered", "is_pinned", "created_at")
    list_filter = ("is_answered", "is_pinned", "is_public")
    search_fields = ("question_title", "question_text")


@admin.register(CourseResource)
class CourseResourceAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "title", "resource_type", "is_public", "order")
    list_filter = ("resource_type", "is_public")


@admin.register(CourseAnnouncement)
class CourseAnnouncementAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "instructor", "title", "priority", "is_published", "is_pinned", "published_at")
    list_filter = ("priority", "is_published", "is_pinned")
    search_fields = ("title", "content")


@admin.register(CheckpointQuizResponse)
class CheckpointQuizResponseAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "lesson", "is_correct", "responded_at")
    list_filter = ("is_correct", "lesson")
    search_fields = ("student__email", "lesson__title")


@admin.register(VideoCheckpointQuiz)
class VideoCheckpointQuizAdmin(admin.ModelAdmin):
    list_display = ("id", "lesson", "question_text", "question_type", "timestamp_seconds")
    list_filter = ("question_type", "lesson")
    search_fields = ("question_text",)


@admin.register(VideoCheckpointResponse)
class VideoCheckpointResponseAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "checkpoint_quiz", "lesson", "is_correct", "responded_at")
    list_filter = ("is_correct", "lesson")
    search_fields = ("student__email", "lesson__title")


@admin.register(CourseRating)
class CourseRatingAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "student", "rating", "is_verified_purchase", "is_public", "is_approved", "created_at")
    list_filter = ("rating", "is_verified_purchase", "is_public", "is_approved")
    search_fields = ("student__email", "course__title")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "teacher", "student", "course", "last_message_at")
    search_fields = ("teacher__email", "student__email", "course__title")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "receiver", "message_type", "sent_at", "is_read")
    list_filter = ("message_type", "is_read")
    search_fields = ("content", "sender__email", "receiver__email")


# ----------------------------
# Quiz-related Models
# ----------------------------

class QuizAnswerInline(admin.TabularInline):
    model = QuizAnswer
    extra = 2


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "lesson", "question_type", "question_text_snippet", "points", "order")
    list_filter = ("question_type", "lesson")
    search_fields = ("question_text",)
    inlines = [QuizAnswerInline]

    def question_text_snippet(self, obj):
        return obj.question_text[:50]
    question_text_snippet.short_description = "Question"


@admin.register(QuizAnswer)
class QuizAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "answer_text", "is_correct", "order")
    list_filter = ("is_correct",)
    search_fields = ("answer_text", "question__question_text")


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "lesson", "score", "total_questions", "correct_answers", "completed_at")
    list_filter = ("lesson",)
    search_fields = ("student__email", "lesson__title")


@admin.register(QuizConfiguration)
class QuizConfigurationAdmin(admin.ModelAdmin):
    list_display = ("id", "lesson", "time_limit", "passing_score", "max_attempts", "grading_policy")
    list_filter = ("grading_policy",)
    search_fields = ("lesson__title",)    
    

@admin.register(CourseOverview)
class CourseOverviewAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "title", "subtitle", "total_enrollments", "average_rating", "completion_rate")
    search_fields = ("course__title",)
    readonly_fields = ("total_enrollments", "average_rating", "completion_rate")

@admin.register(CourseFAQ)
class CourseFAQAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "question", "answer")
    search_fields = ("course__title", "question")


# ============ New Models Admin ============

@admin.register(LessonAttachment)
class LessonAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "lesson", "title", "uploaded_at")
    search_fields = ("lesson__title", "title")
    list_filter = ("uploaded_at",)


@admin.register(QuizResponse)
class QuizResponseAdmin(admin.ModelAdmin):
    list_display = ("id", "attempt", "question", "is_correct", "points_earned")
    list_filter = ("is_correct",)
    search_fields = ("attempt__student__email", "question__question_text")


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "lesson", "status", "score", "max_score", "submitted_at", "is_late")
    list_filter = ("status", "is_late", "submitted_at")
    search_fields = ("student__email", "lesson__title")
    readonly_fields = ("submitted_at", "is_late", "attempt_number", "created_at", "updated_at")


@admin.register(ModuleProgress)
class ModuleProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "enrollment", "module", "progress", "completed", "completed_at")
    list_filter = ("completed",)
    search_fields = ("enrollment__student__email", "module__title")
    readonly_fields = ("progress", "completed", "completed_at", "first_accessed", "last_accessed")


@admin.register(FinalCourseAssessment)
class FinalCourseAssessmentAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "title", "passing_score", "max_attempts", "is_active")
    list_filter = ("is_active",)
    search_fields = ("course__title", "title")


class AssessmentAnswerInline(admin.TabularInline):
    model = AssessmentAnswer
    extra = 2


@admin.register(AssessmentQuestion)
class AssessmentQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "assessment", "question_type", "question_text_snippet", "points", "order")
    list_filter = ("question_type", "assessment")
    search_fields = ("question_text",)
    inlines = [AssessmentAnswerInline]

    def question_text_snippet(self, obj):
        return obj.question_text[:50]
    question_text_snippet.short_description = "Question"


@admin.register(AssessmentAnswer)
class AssessmentAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "answer_text", "is_correct", "order")
    list_filter = ("is_correct",)
    search_fields = ("answer_text", "question__question_text")


@admin.register(AssessmentAttempt)
class AssessmentAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "assessment", "score", "passed", "attempt_number", "completed_at")
    list_filter = ("passed", "attempt_number")
    search_fields = ("student__email", "assessment__course__title")


@admin.register(AssessmentResponse)
class AssessmentResponseAdmin(admin.ModelAdmin):
    list_display = ("id", "attempt", "question", "is_correct", "points_earned")
    list_filter = ("is_correct",)
    search_fields = ("attempt__student__email", "question__question_text")
