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
    content = models.TextField(blank=True)  # Allow empty for file-only messages
    timestamp = models.DateTimeField(auto_now_add=True)

    # NEW FIELDS 
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # File upload support
    file = models.FileField(upload_to='chat_files/%Y/%m/%d/', null=True, blank=True)
    file_name = models.CharField(max_length=255, null=True, blank=True)
    file_size = models.IntegerField(null=True, blank=True)  # Size in bytes
    file_type = models.CharField(max_length=100, null=True, blank=True)  # MIME type
    
    # Reply to message support (like Telegram)
    reply_to = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='replies',
        help_text='The message this is replying to'
    )
    
    class Meta:
        ordering = ['timestamp']
      