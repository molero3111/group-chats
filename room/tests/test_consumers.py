import json

from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser, User
from django.test import TransactionTestCase

from room.models import Message, Room
from room.payloads import message_payload
from room.routing import websocket_urlpatterns
from room.transports.channels import ChannelsTransport

application = URLRouter(websocket_urlpatterns)


class ChatConsumerTests(TransactionTestCase):
    def setUp(self):
        # The in-memory layer outlives each test; start every test with no groups.
        async_to_sync(get_channel_layer().flush)()
        self.user = User.objects.create_user(username='ada', password='pw')
        self.room = Room.objects.create(name='Work', slug='work')

    def communicator(self, user, slug='work'):
        communicator = WebsocketCommunicator(application, f'/ws/{slug}/')
        communicator.scope['user'] = user
        return communicator

    async def test_anonymous_is_rejected_and_leaves_no_group(self):
        communicator = self.communicator(AnonymousUser())

        connected, _ = await communicator.connect()

        self.assertFalse(connected)
        self.assertFalse(any(get_channel_layer().groups.values()), 'an anonymous socket joined a group')

    async def test_unknown_room_is_rejected(self):
        connected, _ = await self.communicator(self.user, slug='nope').connect()

        self.assertFalse(connected)

    async def test_receives_published_messages(self):
        communicator = self.communicator(self.user)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        message = await sync_to_async(Message.objects.create)(room=self.room, user=self.user, content='hi')
        payload = await sync_to_async(message_payload)(message)

        await sync_to_async(ChannelsTransport().publish)(self.room, 'message.new', payload)

        frame = await communicator.receive_from()
        self.assertEqual(json.loads(frame), {'event': 'message.new', 'payload': payload})
        await communicator.disconnect()

    async def test_client_frames_are_ignored(self):
        sender = self.communicator(self.user)
        listener = self.communicator(self.user)
        await sender.connect()
        await listener.connect()

        await sender.send_to(text_data=json.dumps({'message': 'spoof', 'username': 'bob', 'room': 'work'}))

        self.assertTrue(await listener.receive_nothing(timeout=0.3))
        self.assertTrue(await sender.receive_nothing(timeout=0.1))
        self.assertEqual(await sync_to_async(Message.objects.count)(), 0)
        await sender.disconnect()
        await listener.disconnect()
