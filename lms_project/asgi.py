import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter # type: ignore
from channels.auth import AuthMiddlewareStack # type: ignore
from chat.routing import *  # Import your routing file
from django.urls import path
print("asgi configurations !!!!  ")
# Use the actual settings module for this project
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms_project.settings')


application = ProtocolTypeRouter({
    "http": get_asgi_application(),  # Handle HTTP requests
    "websocket": AuthMiddlewareStack(  # Handle WebSocket connections with authentication
        URLRouter(websocket_urlpatterns)  # Use the routing from chat.routing
    ),
})