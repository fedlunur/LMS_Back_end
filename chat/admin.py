from django.contrib import admin
from .models import ChatRoom, ChatMessage
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User

# Registering ChatRoom model
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('room_number', 'product_id', 'seller', 'buyer', 'created')
    search_fields = ('room_number', 'product_id', 'seller__username', 'buyer__username')
    list_filter = ('created', 'seller', 'buyer')

    # Displaying the related ContentType and objectid fields
    def content_item(self, obj):
        return f"{obj.contenttype} - {obj.objectid}"

    content_item.short_description = 'Item'

    fieldsets = (
        (None, {
            'fields': ('room_number', 'product_id', 'seller', 'buyer', 'contenttype', 'objectid')
        }),
        ('Timestamps', {
            'fields': ('created',)
        }),
    )

    readonly_fields = ('room_number', 'created')  # Set fields as read-only that shouldn't be edited

admin.site.register(ChatRoom, ChatRoomAdmin)


# Registering ChatMessage model
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'sender', 'timestamp', 'content_preview')
    search_fields = ('room__room_number', 'sender__username', 'content')
    list_filter = ('timestamp', 'sender')

    def content_preview(self, obj):
        return obj.content[:50]  # Shows the first 50 characters of the content

    content_preview.short_description = 'Content Preview'

    fieldsets = (
        (None, {
            'fields': ('room', 'sender', 'content', 'file','is_read', 'read_at', 'reply_to')
        }),
        ('Timestamp', {
            'fields': ('timestamp',)
        }),
    )

    readonly_fields = ('timestamp',)  # Make the timestamp field read-only

admin.site.register(ChatMessage, ChatMessageAdmin)
