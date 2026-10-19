import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'groupchats.settings')

from django.core.asgi import get_asgi_application  # noqa: E402

# Initialise Django (apps, settings) before importing anything that touches models.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from room import routing  # noqa: E402

# Creates the ProtocolTypeRouter with its mapping
application = ProtocolTypeRouter({'websocket': AllowedHostsOriginValidator(
    AuthMiddlewareStack(
        URLRouter(
            routing.websocket_urlpatterns
        )
    )
), 'http': django_asgi_app})
