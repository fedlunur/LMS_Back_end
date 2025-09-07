from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import *



@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon", "count", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "count")

    fieldsets = (
        (None, {
            "fields": ("name", "slug", "description", "icon")
        }),
        ("Metadata", {
            "fields": ("count", "created_at"),
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
    list_display = ("title", "category", "level", "price", "instructor", "status", "created_at", "updated_at")
    list_filter = ("category", "level", "status", "is_flagged", "created_at")
    search_fields = ("title", "description", "slug")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("-created_at",)
    autocomplete_fields = ("category", "level", "instructor", "approved_by", "flagged_by")


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



@admin.register(VideoLesson)
class VideoLessonAdmin(admin.ModelAdmin):
    list_display = ("lesson", "youtube_url", "duration")
    search_fields = ("lesson__title",)

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
    list_display = ("lesson", "estimated_read_time")
    search_fields = ("lesson__title",)
    readonly_fields = ("attachments", "external_links")  # JSON fields


@admin.register(LessonResource)
class LessonResourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'lesson', 'type', 'file')
    list_filter = ('type',)
    search_fields = ('title', 'lesson__title')
    
# @admin.register(Enrollment)
# class EnrollmentAdmin(admin.ModelAdmin):
#     list_display = ("student", "course", "progress", "enrolled_at", "completed_at")
#     list_filter = ("course", "progress", "enrolled_at", "completed_at")
#     search_fields = ("student__username", "course__title")
#     autocomplete_fields = ("student", "course")


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
        "student", "course", "progress", "completed", "enrolled_at", "last_accessed", "completed_at"
    )
    list_filter = ("completed", "enrolled_at", "last_accessed")
    search_fields = ("student__email", "course__title")
    date_hierarchy = "enrolled_at"
    readonly_fields = ("progress", "completed", "completed_at", "enrolled_at", "last_accessed")
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