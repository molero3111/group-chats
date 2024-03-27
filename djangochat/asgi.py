import django

django.setup()

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangochat.settings')

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application
from room import routing

# Creates the ProtocolTypeRouter with its mapping
application = ProtocolTypeRouter({'websocket': AllowedHostsOriginValidator(
    AuthMiddlewareStack(
        URLRouter(
            routing.websocket_urlpatterns
        )
    )
), 'http': get_asgi_application()})
