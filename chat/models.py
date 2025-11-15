from django.db import models
from user_managment.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey


import uuid


class ChatRoom(models.Model):
    room_number = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    product_id = models.CharField(max_length=100)  # Reference to your Product model
    seller = models.ForeignKey(User, related_name='seller_rooms', on_delete=models.CASCADE)
    buyer = models.ForeignKey(User, related_name='buyer_rooms', on_delete=models.CASCADE)
    contenttype = models.ForeignKey(ContentType, on_delete=models.CASCADE,blank=True,null=True)
    objectid = models.PositiveIntegerField()
    item = GenericForeignKey('contenttype', 'objectid')
    created = models.DateTimeField(auto_now_add=True)

class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, related_name='messages', on_delete=models.CASCADE)
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    # NEW FIELDS 
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
      