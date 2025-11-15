
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

        # Fetch user directly (no JWT decoding)
        self.user = await self.get_user_from_id(user_id)

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
            # Debugging: Print the raw text_data
            print(f"📥 Raw text_data: {text_data}")

            # Parse the JSON data
            text_data_json = json.loads(text_data)

            # Extract fields from the JSON payload
            message = text_data_json.get('message', '').strip()
            sender_id = text_data_json.get('sender_id')

            # Debugging: Print extracted fields
            print(f"📤 Extracted fields: message={message}, sender_id={sender_id}")

            # Validate required fields
            if not sender_id:
                logger.warning("Missing required fields in received message")
                return  # Reject message if required fields are missing

            # Save the message
            await self.save_message(sender_id=sender_id, message=message)
            timestamp = datetime.now(timezone.utc)
            
          
            # Send message to WebSocket group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'sender_id': sender_id,
                    'timestamp': time_ago(timestamp),  
                 
                }  
            )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while processing message: {e}")

    async def chat_message(self, event):
        """Send the message to WebSocket."""
        message = event.get('message', '')
        sender_id = event.get('sender_id')
        timestamp = datetime.now(timezone.utc)
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'sender_id': sender_id,
            'timestamp': time_ago(timestamp),  
           
           
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
                "buyer": buyer.id,
                "buyer_name":buyer.first_name,
                "sender_name":sender_name,
                "room": str(room_name),  # Use the fetched room name
                "message": msg.content,
                "timestamp":time_ago(msg.timestamp),
              
            })

        # Send chat history to WebSocket
        await self.send(text_data=json.dumps({
            "chat_history": chat_history
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
        return msg.sender.first_name
    #
    @database_sync_to_async
    def save_message(self, sender_id, message):
        """Save a new chat message to the database."""
        logger.info("Saving the chat message to the database")
        ChatMessage = apps.get_model('chat', 'ChatMessage')
        ChatRoom = apps.get_model('chat', 'ChatRoom')

        # Fetch the room
        room = ChatRoom.objects.get(room_number=self.room_number)
        logger.info("Ready to create chat message")

        # Create the chat message
        ChatMessage.objects.create(
            room=room,
            sender_id=sender_id,
            content=message,
        )
        logger.info("Chat message successfully created")

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
