
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

            # Extract fields from the JSON payload
            message = text_data_json.get('message', '').strip()
            sender_id = text_data_json.get('sender_id')

            # Validate required fields
            if not message:
                await self.send(text_data=json.dumps({
                    'error': 'Message cannot be empty'
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

            # Save the message
            saved_message = await self.save_message(sender_id=sender_id_int, message=message)
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
        
        # Parse timestamp if it's a string
        if isinstance(timestamp_str, str):
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except:
                timestamp = datetime.now(timezone.utc)
        else:
            timestamp = timestamp_str or datetime.now(timezone.utc)
        
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': message,
            'sender_id': sender_id,
            'sender_name': sender_name,
            'timestamp': timestamp.isoformat(),
            'timestamp_display': time_ago(timestamp),
            'message_id': message_id,
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
            chat_history.append({
                "sender_id": msg.sender_id,
                "sender_name": sender_name,
                "message": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "timestamp_display": time_ago(msg.timestamp),
                "message_id": msg.id,
            })

        # Send chat history to WebSocket
        await self.send(text_data=json.dumps({
            "type": "chat_history",
            "messages": chat_history
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
    def save_message(self, sender_id, message):
        """Save a new chat message to the database."""
        ChatMessage = apps.get_model('chat', 'ChatMessage')
        ChatRoom = apps.get_model('chat', 'ChatRoom')

        # Fetch the room
        room = ChatRoom.objects.get(room_number=self.room_number)

        # Create the chat message
        msg = ChatMessage.objects.create(
            room=room,
            sender_id=sender_id,
            content=message,
        )
        return {
            'id': msg.id,
            'content': msg.content,
            'timestamp': msg.timestamp.isoformat(),
        }

    @database_sync_to_async
    def get_last_messages(self, room_number, limit=20):
        """Retrieve the last `limit` messages."""
        ChatMessage = apps.get_model('chat', 'ChatMessage')
        ChatRoom = apps.get_model('chat', 'ChatRoom')

        room = ChatRoom.objects.get(room_number=room_number)
        # Pre-fetch related `room` field to avoid additional queries
        return ChatMessage.objects.filter(room=room).select_related('room').order_by('-timestamp')[:limit][::-1]
    
    
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
