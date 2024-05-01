from django.urls import path

from djangochat.settings import URL_PREFIX_FORWARD_SLASH
from room.consumers import ChatConsumer

websocket_urlpatterns = [
    path(f'{URL_PREFIX_FORWARD_SLASH}ws/<str:room_name>/', ChatConsumer.as_asgi())
]
