from django.urls import path

from djangochat.settings import URL_PREFIX_FORWARD_SLASH
from room.consumers import ChatConsumer

websocket_urlpatterns = [
    path(f'ws/<str:room_name>/', ChatConsumer.as_asgi())
]
