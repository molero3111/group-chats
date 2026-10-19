import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from room.models import Room
from room.payloads import room_group


class ChatConsumer(AsyncWebsocketConsumer):
    """Receive-only: delivers room events to signed-in members. Sending is POST /rooms/<slug>/messages/."""

    group_name = None

    async def connect(self):
        if not self.scope['user'].is_authenticated:
            await self.close()
            return
        room = await self.get_room(self.scope['url_route']['kwargs']['room_name'])
        if room is None:
            await self.close()
            return
        self.group_name = room_group(room)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """Clients never send over the socket; anything they send is dropped."""

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({'event': event['event'], 'payload': event['payload']}))

    @database_sync_to_async
    def get_room(self, slug):
        return Room.objects.filter(slug=slug).first()
