from django.http import JsonResponse
from courses.models import *
from user_managment.models import User
def get_counts(request):
 
    result = {
        "enabledUserCount": User.objects.filter(is_active=True).count(),
        "disabledUserCount": User.objects.filter(is_active=False).count(),
        "totalCourse": Course.objects.count(),
        "totalPublishedCourse": Course.objects.filter(status='published').count(),
        "total Lessons": Lesson.objects.filter().count(),
         
     
    }
    
    return JsonResponse(result)