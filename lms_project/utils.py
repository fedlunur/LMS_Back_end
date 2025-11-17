import importlib
from django.apps import apps
from django.db.models.base import ModelBase

from chat.models import ChatMessage, ChatRoom
from user_managment.models import *

# Import courses models module directly to avoid import timing issues
import courses.models as courses_models
from grading.models import *

##
# left URl pattern and right Excat model name should map with URL's 
# Use getattr to access models dynamically to avoid import timing issues
def get_model_mapping():
    """Get model mapping - lazy initialization to avoid import timing issues"""
    return {
        # User managment
        'user': User,
        'role': Role,
        "category": courses_models.Category,
        "level": courses_models.Level,
        "course": courses_models.Course,
        "module": courses_models.Module,
        "lesson": courses_models.Lesson,
        "enrollment": courses_models.Enrollment,
        "videolesson": courses_models.VideoLesson,
        'articlelesson': courses_models.ArticleLesson,
        'assignmentlesson': courses_models.AssignmentLesson,
        'lessonresource': courses_models.LessonResource,
        # Newly added
        "certificate": courses_models.Certificate,
        "coursebadge": courses_models.CourseBadge,
        'quizlesson': courses_models.QuizLesson,
        "courseqa": courses_models.CourseQA,
        "courseresource": courses_models.CourseResource,
        "courseannouncement": courses_models.CourseAnnouncement,
        "checkpointquizresponse": courses_models.CheckpointQuizResponse,
        "videocheckpointquiz": courses_models.VideoCheckpointQuiz,
        "videocheckpointresponse": courses_models.VideoCheckpointResponse,
        "courserating": courses_models.CourseRating,
        "conversation": courses_models.Conversation,
        "message": courses_models.Message,
        "course_overview": courses_models.CourseOverview,
        "course_faq": courses_models.CourseFAQ,
        "lessonattachment": courses_models.LessonAttachment,
        "quizquestion": courses_models.QuizQuestion,
        "quizanswer": courses_models.QuizAnswer,
        "quizattempt": courses_models.QuizAttempt,
        "quizresponse": courses_models.QuizResponse,
        "quizconfiguration": courses_models.QuizConfiguration,
        "assignmentsubmission": courses_models.AssignmentSubmission,
        "moduleprogress": courses_models.ModuleProgress,
        "lessonprogress": courses_models.LessonProgress,
        "finalcourseassessment": courses_models.FinalCourseAssessment,
        "assessmentquestion": courses_models.AssessmentQuestion,
        "assessmentanswer": courses_models.AssessmentAnswer,
        "assessmentattempt": courses_models.AssessmentAttempt,
        "assessmentresponse": courses_models.AssessmentResponse,
        "event": courses_models.Event,
        "eventtype": courses_models.EventType,
        "notification": courses_models.Notification,

        #  Chat 
  
    
    }

# Initialize model_mapping
model_mapping = get_model_mapping()
# for any model exclude fileds 
donot_include_fields = {

   'user': ['removed','created','updated','enabled','password','user_permissions','groups','is_superuser','last_login','is_staff','date_joined'],
   'role': ['removed','created','updated','enabled'],
   "course": ["approved_by", "flagged_by"],

   
}
#return Json instead of Id for foreign keys 
genericlist_filds_nested_model = {
   
    'user':['id','phone','first_name','middle_name',],
    'role':['id','name'],
    # 'course':['id','title','instructor']
    
   
   
}


