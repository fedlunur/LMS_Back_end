import importlib
from django.apps import apps
from django.db.models.base import ModelBase

from user_managment.models import *

from courses.models import *
from grading.models import *

##
# left URl pattern and right Excat model name should map with URL's 
model_mapping = {
           # Products /all catagories 
     
          # User managment
        'user':User,
        'role': Role,
        "category": Category,
        "level": Level,
        "course": Course,
        "module": Module,
        "lesson": Lesson,
        "enrollment": Enrollment,
        "videolesson":   VideoLesson,
        'articlelesson':ArticleLesson,
        'assignmentlesson':AssignmentLesson,
        'lessonresource':LessonResource,
           # Newly added
        "certificate": Certificate,
        "coursebadge": CourseBadge,
        'quizlesson':QuizLesson,
        "courseqa": CourseQA,
        "courseresource": CourseResource,
        "courseannouncement": CourseAnnouncement,
        "checkpointquizresponse": CheckpointQuizResponse,
        "videocheckpointquiz": VideoCheckpointQuiz,
        "videocheckpointresponse": VideoCheckpointResponse,
        "courserating": CourseRating,
        "conversation": Conversation,
        "message": Message,

        #--------------------------
        # others
        #--------------------------
        "faq": FAQ,

    }
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


