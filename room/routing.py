from django.urls import path

from djangochat.settings import URL_PREFIX
from room.consumers import ChatConsumer

websocket_urlpatterns = [
    path(f'{URL_PREFIX}/ws/<str:room_name>/', ChatConsumer.as_asgi())
]
