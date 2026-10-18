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
