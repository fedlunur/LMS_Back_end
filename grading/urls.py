from django.urls import path
from .views import (
    TeacherGradingTableView,
    UpdateStudentGradeView,
    StudentGradingReportView
)

urlpatterns = [
    path('teacher/course/<int:course_id>/table/', TeacherGradingTableView.as_view(), name='teacher_grading_table'),
    path('teacher/grade/update/', UpdateStudentGradeView.as_view(), name='update_student_grade'),
    path('student/course/<int:course_id>/report/', StudentGradingReportView.as_view(), name='student_grading_report'),
]

