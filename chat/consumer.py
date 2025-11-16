
from channels.generic.websocket import AsyncWebsocketConsumer # type: ignore
from asgiref.sync import sync_to_async
from django.apps import apps
import logging
from channels.db import database_sync_to_async # type: ignore
from datetime import datetime, timezone
import json
import jwt
from django.conf import settings

# Create a logger instance
logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.room_number = self.scope['url_route']['kwargs']['room_number']
        self.room_group_name = f'chat_{self.room_number}'

        # Get user_id from the query string (no token required)
        query_params = self.scope.get('query_string', b'').decode('utf-8')
        user_id = None
        for param in query_params.split('&'):
            key, value = param.split('=') if '=' in param else (None, None)
            if key == "user_id":
                user_id = value
                break

        logger.info(f"Received user_id: {user_id}")

        if not user_id:
            logger.error("No user_id found in query string")
            await self.close()
            return

        # Convert to int and fetch user directly (no JWT decoding)
        try:
            user_id_int = int(user_id)
        except ValueError:
            logger.error(f"Invalid user_id format: {user_id}")
            await self.close()
            return
        
        self.user = await self.get_user_from_id(user_id_int)

        if not self.user:
            logger.warning(f"User {user_id} does not exist. Closing connection.")
            await self.close()
            return

        # Fetch and validate the chat room
        try:
            ChatRoom = await database_sync_to_async(apps.get_model)('chat', 'ChatRoom')
            self.room = await database_sync_to_async(ChatRoom.objects.get)(room_number=self.room_number)

            if not await self.is_user_authorized(self.room, self.user):
                logger.warning(f"User {self.user} is not authorized for this room. Closing connection.")
                await self.close()
                return
        except ChatRoom.DoesNotExist:
            logger.error(f"Chat room {self.room_number} does not exist. Closing connection.")
            await self.close()
            return
        except Exception as e:
            logger.error(f"Error fetching chat room: {e}")
            await self.close()
            return

        # Accept the WebSocket connection
        await self.accept()
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.send_chat_history()

    async def get_user_from_id(self, user_id):
        """Fetch user from database without JWT decoding."""
        from user_managment.models import User
        try:
            user = await database_sync_to_async(User.objects.get)(id=user_id)
            return user
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def is_user_authorized(self, room, user):
        """Check if the user is either the seller or buyer for the room."""
        return user in [room.seller, room.buyer]
    
    async def disconnect(self, close_code):
        """Leave room group on disconnect."""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Handle received messages."""
        try:
            # Parse the JSON data
            text_data_json = json.loads(text_data)
            
            # Check if this is a read receipt or a regular message
            message_type = text_data_json.get('type', 'message')
            
            if message_type == 'mark_read':
                # Handle marking messages as read
                message_ids = text_data_json.get('message_ids', [])
                if message_ids:
                    await self.mark_messages_as_read(message_ids)
                    # Send read receipt to other users
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'read_receipt',
                            'message_ids': message_ids,
                            'read_by': self.user.id,
                        }
                    )
                return

            # Extract fields from the JSON payload
            message = text_data_json.get('message', '').strip()
            sender_id = text_data_json.get('sender_id')
            file_id = text_data_json.get('file_id')  # For file messages uploaded via API
            reply_to_id = text_data_json.get('reply_to_id')  # ID of message being replied to

            # Validate required fields - either message or file_id must be present
            if not message and not file_id:
                await self.send(text_data=json.dumps({
                    'error': 'Message or file_id is required'
                }))
                return

            if not sender_id:
                logger.warning("Missing sender_id in received message")
                await self.send(text_data=json.dumps({
                    'error': 'sender_id is required'
                }))
                return

            # Validate sender is authorized - convert both to int for comparison
            try:
                sender_id_int = int(sender_id)
            except (ValueError, TypeError):
                await self.send(text_data=json.dumps({
                    'error': 'Invalid sender_id format'
                }))
                return
            
            if sender_id_int != self.user.id:
                logger.warning(
                    f"Sender ID mismatch - sender_id: {sender_id_int} (type: {type(sender_id_int)}), "
                    f"self.user.id: {self.user.id} (type: {type(self.user.id)}), "
                    f"self.user: {self.user}"
                )
                await self.send(text_data=json.dumps({
                    'error': 'Unauthorized sender',
                    'debug': {
                        'sender_id': sender_id_int,
                        'connected_user_id': self.user.id
                    }
                }))
                return

            # Validate reply_to_id if provided
            reply_to_info = None
            if reply_to_id:
                try:
                    reply_to_id_int = int(reply_to_id)
                    reply_to_info = await self.validate_and_get_reply_to(reply_to_id_int)
                    if not reply_to_info:
                        await self.send(text_data=json.dumps({
                            'error': 'Reply to message not found or not in this room'
                        }))
                        return
                except (ValueError, TypeError):
                    await self.send(text_data=json.dumps({
                        'error': 'Invalid reply_to_id format'
                    }))
                    return

            # If file_id is provided, get the existing message (file was already uploaded via API)
            if file_id:
                try:
                    file_id_int = int(file_id)
                except (ValueError, TypeError):
                    await self.send(text_data=json.dumps({
                        'error': 'Invalid file_id format'
                    }))
                    return
                existing_message = await self.get_message_by_id(file_id_int)
                if existing_message:
                    # Update the existing message with reply_to if provided
                    if reply_to_id:
                        await self.update_message_reply_to(file_id_int, reply_to_id_int)
                    
                    # Broadcast the existing message
                    sender_name = await self.get_sender_name_from_id(sender_id_int)
                    file_info = await self.get_file_info_from_message(existing_message)
                    
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'chat_message',
                            'message': existing_message.get('content', ''),
                            'sender_id': sender_id_int,
                            'sender_name': sender_name,
                            'timestamp': existing_message.get('timestamp'),
                            'message_id': existing_message.get('id'),
                            'file_info': file_info,
                            'is_read': False,  # New messages are unread
                            'reply_to': reply_to_info,
                        }  
                    )
                    return
                else:
                    await self.send(text_data=json.dumps({
                        'error': 'File message not found'
                    }))
                    return

            # Save the text message (no file_id)
            saved_message = await self.save_message(
                sender_id=sender_id_int, 
                message=message,
                reply_to_id=reply_to_id_int if reply_to_id else None,
            )
            timestamp = datetime.now(timezone.utc)
            
            # Get sender info
            sender_name = await self.get_sender_name_from_id(sender_id_int)
            
            # Send message to WebSocket group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'sender_id': sender_id_int,
                    'sender_name': sender_name,
                    'timestamp': timestamp.isoformat(),
                    'message_id': saved_message.get('id') if saved_message else None,
                    'file_info': saved_message.get('file_info'),
                    'is_read': False,  # New messages are unread
                    'reply_to': reply_to_info,
                }  
            )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
            await self.send(text_data=json.dumps({
                'error': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"Unexpected error while processing message: {e}")
            await self.send(text_data=json.dumps({
                'error': 'Failed to process message'
            }))

    async def chat_message(self, event):
        """Send the message to WebSocket."""
        message = event.get('message', '')
        sender_id = event.get('sender_id')
        sender_name = event.get('sender_name', '')
        timestamp_str = event.get('timestamp')
        message_id = event.get('message_id')
        file_info = event.get('file_info')
        is_read = event.get('is_read', False)
        reply_to = event.get('reply_to')
        
        # Parse timestamp if it's a string
        if isinstance(timestamp_str, str):
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except:
                timestamp = datetime.now(timezone.utc)
        else:
            timestamp = timestamp_str or datetime.now(timezone.utc)
        
        # Determine if this message should be marked as read for the current user
        # If the current user is the sender, it's already "read" for them
        # If the current user is the receiver, it's unread until they view it
        current_user_is_sender = sender_id == self.user.id
        
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': message,
            'sender_id': sender_id,
            'sender_name': sender_name,
            'timestamp': timestamp.isoformat(),
            'timestamp_display': time_ago(timestamp),
            'message_id': message_id,
            'file_info': file_info,
            'is_read': is_read if not current_user_is_sender else True,  # Sender's own messages are always "read"
            'reply_to': reply_to,
        }))
    
    async def read_receipt(self, event):
        """Handle read receipts - notify users when messages are read."""
        message_ids = event.get('message_ids', [])
        read_by = event.get('read_by')
        
        # Only send to other users (not the one who read it)
        if read_by != self.user.id:
            await self.send(text_data=json.dumps({
                'type': 'read_receipt',
                'message_ids': message_ids,
                'read_by': read_by,
            }))
        
        

    async def send_chat_history(self):
        """Fetch the last 20 messages and send to WebSocket."""
        messages = await self.get_last_messages(room_number=self.room_number, limit=20)
        now = datetime.now(timezone.utc) 
        chat_history = []
        for msg in messages:
         
            # Wrap access to `msg.room` in `database_sync_to_async`
            room_name = await self.get_room_name(msg)
            buyer=await self.get_buyer_name(msg)
            sender_name=await self.get_sender_name(msg)
            
            # Get file info if exists
            file_info = None
            if msg.file:
                file_info = await self.get_file_info(msg)
            
            # Get reply information if exists
            reply_to_info = None
            if msg.reply_to:
                reply_to_info = await self.get_reply_to_info(msg.reply_to)
            
            # Determine if message is read for current user
            # If current user is sender, it's always "read"
            # Otherwise, check is_read field
            is_read_for_user = True if msg.sender_id == self.user.id else msg.is_read
            
            chat_history.append({
                "sender_id": msg.sender_id,
                "sender_name": sender_name,
                "message": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "timestamp_display": time_ago(msg.timestamp),
                "message_id": msg.id,
                "file_info": file_info,
                "is_read": is_read_for_user,
                "read_at": msg.read_at.isoformat() if msg.read_at else None,
                "reply_to": reply_to_info,
            })
        
        # Get unread count for this room
        unread_count = await self.get_unread_count()

        # Send chat history to WebSocket
        await self.send(text_data=json.dumps({
            "type": "chat_history",
            "messages": chat_history,
            "unread_count": unread_count,
        }))

    @database_sync_to_async
    def get_room_name(self, msg):
        """Fetch the room name synchronously."""
        return msg.room.room_number
    @database_sync_to_async
    def get_buyer_name(self, msg):
        """Fetch the room name synchronously."""
        return msg.room.buyer
    
    @database_sync_to_async
    def get_sender_name(self, msg):
        return msg.sender.get_full_name() or msg.sender.first_name
    
    @database_sync_to_async
    def get_sender_name_from_id(self, sender_id):
        """Get sender name from user ID."""
        from user_managment.models import User
        try:
            user = User.objects.get(id=sender_id)
            return user.get_full_name() or user.first_name
        except User.DoesNotExist:
            return "Unknown User"
    #
    @database_sync_to_async
    def get_message_by_id(self, message_id):
        """Get an existing message by ID within the current room."""
        ChatMessage = apps.get_model('chat', 'ChatMessage')
        ChatRoom = apps.get_model('chat', 'ChatRoom')
        
        try:
            room = ChatRoom.objects.get(room_number=self.room_number)
            msg = ChatMessage.objects.get(id=message_id, room=room)
            return {
                'id': msg.id,
                'content': msg.content,
                'timestamp': msg.timestamp.isoformat(),
                'file': msg.file,
                'file_name': msg.file_name,
                'file_size': msg.file_size,
                'file_type': msg.file_type,
            }
        except ChatMessage.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_file_info_from_message(self, message_data):
        """Get file info from message data."""
        file_obj = message_data.get('file')
        if not file_obj:
            return None
        return {
            'file_url': file_obj.url if file_obj else None,
            'file_name': message_data.get('file_name'),
            'file_size': message_data.get('file_size'),
            'file_type': message_data.get('file_type'),
        }
    
    @database_sync_to_async
    def validate_and_get_reply_to(self, reply_to_id):
        """Validate that reply_to message exists and is in the same room, return reply info."""
        ChatMessage = apps.get_model('chat', 'ChatMessage')
        ChatRoom = apps.get_model('chat', 'ChatRoom')
        
        try:
            room = ChatRoom.objects.get(room_number=self.room_number)
            reply_msg = ChatMessage.objects.select_related('sender').get(
                id=reply_to_id,
                room=room
            )
            return {
                'message_id': reply_msg.id,
                'sender_id': reply_msg.sender_id,
                'sender_name': reply_msg.sender.get_full_name() or reply_msg.sender.first_name,
                'content': reply_msg.content[:100] if reply_msg.content else None,  # Preview of original message
                'file_info': {
                    'file_name': reply_msg.file_name,
                    'file_type': reply_msg.file_type,
                } if reply_msg.file else None,
            }
        except ChatMessage.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_reply_to_info(self, reply_msg):
        """Get reply information from a reply message object."""
        return {
            'message_id': reply_msg.id,
            'sender_id': reply_msg.sender_id,
            'sender_name': reply_msg.sender.get_full_name() or reply_msg.sender.first_name,
            'content': reply_msg.content[:100] if reply_msg.content else None,  # Preview of original message
            'file_info': {
                'file_name': reply_msg.file_name,
                'file_type': reply_msg.file_type,
            } if reply_msg.file else None,
        }
    
    @database_sync_to_async
    def update_message_reply_to(self, message_id, reply_to_id):
        """Update an existing message with reply_to reference."""
        ChatMessage = apps.get_model('chat', 'ChatMessage')
        try:
            msg = ChatMessage.objects.get(id=message_id)
            reply_msg = ChatMessage.objects.get(id=reply_to_id, room=msg.room)
            msg.reply_to = reply_msg
            msg.save()
        except ChatMessage.DoesNotExist:
            pass
    
    @database_sync_to_async
    def save_message(self, sender_id, message, reply_to_id=None):
        """Save a new chat message to the database."""
        ChatMessage = apps.get_model('chat', 'ChatMessage')
        ChatRoom = apps.get_model('chat', 'ChatRoom')

        # Fetch the room
        room = ChatRoom.objects.get(room_number=self.room_number)

        # Get reply_to message if provided
        reply_to_msg = None
        if reply_to_id:
            try:
                reply_to_msg = ChatMessage.objects.get(id=reply_to_id, room=room)
            except ChatMessage.DoesNotExist:
                pass

        # Create the chat message
        msg = ChatMessage.objects.create(
            room=room,
            sender_id=sender_id,
            content=message,
            reply_to=reply_to_msg,
        )
        
        return {
            'id': msg.id,
            'content': msg.content,
            'timestamp': msg.timestamp.isoformat(),
            'file_info': None,
        }
    
    @database_sync_to_async
    def get_file_info(self, msg):
        """Get file information from message."""
        if not msg.file:
            return None
        return {
            'file_url': msg.file.url,
            'file_name': msg.file_name,
            'file_size': msg.file_size,
            'file_type': msg.file_type,
        }
    
    @database_sync_to_async
    def get_other_user(self):
        """Get the other user in the room."""
        if self.room.seller_id == self.user.id:
            return self.room.buyer
        return self.room.seller
    
    @database_sync_to_async
    def mark_messages_as_read(self, message_ids):
        """Mark messages as read."""
        ChatMessage = apps.get_model('chat', 'ChatMessage')
        from django.utils import timezone as tz
        
        # Only mark messages that belong to this room and are not sent by current user
        messages = ChatMessage.objects.filter(
            id__in=message_ids,
            room__room_number=self.room_number,
        ).exclude(sender=self.user)
        
        now = tz.now()
        messages.update(is_read=True, read_at=now)
    
    @database_sync_to_async
    def get_unread_count(self):
        """Get unread message count for current user in this room."""
        ChatMessage = apps.get_model('chat', 'ChatMessage')
        ChatRoom = apps.get_model('chat', 'ChatRoom')
        try:
            room = ChatRoom.objects.get(room_number=self.room_number)
            # Count unread messages sent by the other user
            other_user = room.buyer if room.seller_id == self.user.id else room.seller
            return ChatMessage.objects.filter(
                room=room,
                sender=other_user,
                is_read=False
            ).count()
        except ChatRoom.DoesNotExist:
            return 0

    @database_sync_to_async
    def get_last_messages(self, room_number, limit=20):
        """Retrieve the last `limit` messages."""
        ChatMessage = apps.get_model('chat', 'ChatMessage')
        ChatRoom = apps.get_model('chat', 'ChatRoom')

        room = ChatRoom.objects.get(room_number=room_number)
        # Pre-fetch related fields to avoid additional queries
        return ChatMessage.objects.filter(room=room).select_related(
            'room', 'sender', 'reply_to', 'reply_to__sender'
        ).order_by('-timestamp')[:limit][::-1]
    
    
from datetime import datetime, timezone

def time_ago(timestamp):
    if isinstance(timestamp, str):
        # Convert string timestamp to datetime object
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    now = datetime.now(timezone.utc)
    diff = now - timestamp

    if diff.total_seconds() < 60:
        return "Just now"
    elif diff.total_seconds() < 3600:
        return f"{int(diff.total_seconds() // 60)} minutes ago"
    elif diff.total_seconds() < 86400:
        return f"{int(diff.total_seconds() // 3600)} hours ago"
    else:
        return timestamp.strftime("%b %d, %Y")  # Example: "Feb 6, 2025"
