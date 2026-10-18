import jwt
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from room.models import Room
from room.tests.test_transports import COLUMBA


@override_settings(CHAT_TRANSPORT='columba', **COLUMBA)
class RoomTokenViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ada', password='pw')
        self.room = Room.objects.create(name='Work', slug='work')
        self.url = reverse('room-token', args=['work'])

    def test_anonymous_gets_401_json(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {'error': 'unauthenticated'})

    def test_unknown_room_is_404(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('room-token', args=['nope']))

        self.assertEqual(response.status_code, 404)

    def test_returns_room_scoped_token(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        claims = jwt.decode(response.json()['token'], COLUMBA['COLUMBA_SIGNING_SECRET'], algorithms=['HS256'])
        self.assertEqual(claims['sub'], str(self.user.id))
        self.assertEqual(claims['topics'], [f'room:{self.room.id}'])

    @override_settings(CHAT_TRANSPORT='channels')
    def test_not_available_in_channels_mode(self):
        self.client.force_login(self.user)

        self.assertEqual(self.client.get(self.url).status_code, 404)
