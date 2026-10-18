from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from room.models import Message, Room


class RoomsViewTests(TestCase):
    def test_rooms_requires_login(self):
        response = self.client.get(reverse('rooms'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])


class RoomViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ada', password='pw')
        self.room = Room.objects.create(name='Work', slug='work')
        self.client.force_login(self.user)

    def test_room_page_lists_history(self):
        for content in ['first', 'second', '<b>third</b>']:
            Message.objects.create(room=self.room, user=self.user, content=content)

        response = self.client.get(reverse('room', args=['work']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'first')
        self.assertContains(response, 'second')
        self.assertContains(response, '&lt;b&gt;third&lt;/b&gt;')
        self.assertNotContains(response, '<b>third</b>')


class WebsocketRoutingTests(TestCase):
    def test_websocket_route_has_no_prefix(self):
        from room.routing import websocket_urlpatterns

        self.assertTrue(any(p.pattern.match('ws/work/') for p in websocket_urlpatterns))


class RoomLayoutTests(TestCase):
    def test_room_page_keeps_chat_ids(self):
        user = User.objects.create_user(username='ada', password='pw')
        Room.objects.create(name='Work', slug='work')
        self.client.force_login(user)

        response = self.client.get(reverse('room', args=['work']))

        for element_id in ['chat-messages', 'chat-message-input', 'chat-message-btn']:
            self.assertContains(response, f'id="{element_id}"')


class RoomPageConfigTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ada', password='pw')
        self.room = Room.objects.create(name='Work', slug='work')
        self.client.force_login(self.user)

    def chat_config(self, response):
        import json
        import re
        match = re.search(r'<script id="chat-config" type="application/json">(.*?)</script>',
                          response.content.decode())
        self.assertIsNotNone(match, 'no chat-config json_script')
        return json.loads(match.group(1))

    def test_channels_mode(self):
        response = self.client.get(reverse('room', args=['work']))

        config = self.chat_config(response)
        self.assertEqual(config['transport'], {'kind': 'channels', 'path': '/ws/work/'})
        self.assertEqual(config['messages_url'], reverse('room-messages', args=['work']))
        self.assertEqual(config['user_id'], self.user.id)
        self.assertContains(response, 'room/chat.js')
        self.assertNotContains(response, 'phoenix-1.8.15.js')
        self.assertNotContains(response, 'new WebSocket')
        self.assertContains(response, 'Realtime: Django Channels')

    def test_columba_mode(self):
        from django.test import override_settings

        from room.tests.test_transports import COLUMBA
        with override_settings(CHAT_TRANSPORT='columba', **COLUMBA):
            response = self.client.get(reverse('room', args=['work']))

        config = self.chat_config(response)
        self.assertEqual(config['transport'], {
            'kind': 'columba',
            'socket_url': COLUMBA['COLUMBA_SOCKET_URL'],
            'topic': f'room:{self.room.id}',
            'token_url': reverse('room-token', args=['work']),
        })
        self.assertContains(response, 'room/vendor/phoenix-1.8.15.js')
        self.assertContains(response, 'Realtime: Columba')
        self.assertNotContains(response, COLUMBA['COLUMBA_API_KEY'])
        self.assertNotContains(response, COLUMBA['COLUMBA_SIGNING_SECRET'])

    def test_history_messages_carry_ids(self):
        message = Message.objects.create(room=self.room, user=self.user, content='hi')

        response = self.client.get(reverse('room', args=['work']))

        self.assertContains(response, f'data-id="{message.id}"')


class SeedRoomsCommandTests(TestCase):
    def test_seeds_fixture_rooms_into_empty_table(self):
        from django.core.management import call_command

        call_command('seed_rooms', verbosity=0)

        self.assertTrue(Room.objects.filter(slug='work').exists())

    def test_leaves_existing_rooms_alone(self):
        from django.core.management import call_command

        Room.objects.create(pk=1, name='Renamed by admin', slug='work')

        call_command('seed_rooms', verbosity=0)

        self.assertEqual(Room.objects.get(pk=1).name, 'Renamed by admin')
        self.assertEqual(Room.objects.count(), 1)

    def test_quiet_at_verbosity_zero(self):
        from io import StringIO

        from django.core.management import call_command

        Room.objects.create(name='Work', slug='work')
        out = StringIO()

        call_command('seed_rooms', verbosity=0, stdout=out)

        self.assertEqual(out.getvalue(), '')
