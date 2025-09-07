# views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Level,Category

@api_view(["GET"])
@permission_classes([AllowAny])
def constants_view(request): 
    categories = Category.objects.all().values()  # retrieves all fields
    levels = Level.objects.all().values("id", "name")
    return Response({
        "categories": list(categories),
        "levels": list(levels),
        
    })
