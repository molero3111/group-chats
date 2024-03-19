import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import User

from room.models import Room, Message


# TODO: fix websocket connection on docker, check nginx file and docker compose file
class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_name = None
        self.room_group_name = None

    async def connect(self):
        # Check if the user is authenticated
        print('test user: ', self.scope["user"], self.scope["user"].is_authenticated)
        if not self.scope["user"].is_authenticated:
            # Unauthenticated, close the connection
            print('user is not authenticated')
            await self.close()
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f"chat_{self.room_name}"
        print('test user: ', self.room_name, self.room_group_name)
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        print('added layer')
        await self.accept()
        print('accepted connection')

    async def disconnect(self, code):
        print('disconnecting user')
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data=None, bytes_data=None):
        data = json.loads(text_data)
        message = data['message']
        username = data['username']
        room = data['room']

        await self.save_message(username, room, message)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'username': username,
                'room': room
            }
        )

    async def chat_message(self, event):
        message = event['message']
        username = event['username']
        room = event['room']

        await self.send(text_data=json.dumps({
            'message': message,
            'username': username,
            'room': room
        }))

    @database_sync_to_async
    def save_message(self, username, room, message):
        try:
            user = User.objects.get(username=username)
            room_obj = Room.objects.get(slug=room)
            Message.objects.create(user=user, room=room_obj, content=message)
        except (User.DoesNotExist, Room.DoesNotExist) as e:
            # Here you can handle the exception, for example, logging it.
            pass
