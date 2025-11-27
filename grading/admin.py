from django.contrib import admin
from .models import (
    GradingConfiguration,
    LessonWeight,
    FinalAssessmentWeight,
    StudentLessonGrade,
    StudentFinalAssessmentGrade,
    StudentCourseGrade
)

@admin.register(GradingConfiguration)
class GradingConfigurationAdmin(admin.ModelAdmin):
    list_display = ('course', 'passing_percentage', 'updated_at')
    search_fields = ('course__title',)

@admin.register(LessonWeight)
class LessonWeightAdmin(admin.ModelAdmin):
    list_display = ('lesson', 'weight')
    search_fields = ('lesson__title',)

@admin.register(FinalAssessmentWeight)
class FinalAssessmentWeightAdmin(admin.ModelAdmin):
    list_display = ('assessment', 'weight')

@admin.register(StudentLessonGrade)
class StudentLessonGradeAdmin(admin.ModelAdmin):
    list_display = ('student', 'lesson', 'score_percentage', 'is_override', 'updated_at')
    list_filter = ('is_override', 'updated_at')
    search_fields = ('student__email', 'lesson__title')

@admin.register(StudentFinalAssessmentGrade)
class StudentFinalAssessmentGradeAdmin(admin.ModelAdmin):
    list_display = ('student', 'assessment', 'score_percentage', 'is_override')
    search_fields = ('student__email', 'assessment__title')

@admin.register(StudentCourseGrade)
class StudentCourseGradeAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'final_score_percentage', 'status', 'updated_at')
    list_filter = ('status',)
    search_fields = ('student__email', 'course__title')
