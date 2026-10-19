from unittest import mock

import jwt
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from room.models import Message, Room
from room.payloads import message_payload
from room.tests.test_transports import COLUMBA


@override_settings(MESSAGE_RATE='2/60')
class MessageRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ada = User.objects.create_user(username='ada', password='pw')
        self.bob = User.objects.create_user(username='bob', password='pw')
        Room.objects.create(name='Work', slug='work')
        self.url = reverse('room-messages', args=['work'])
        self.transport = mock.Mock()
        patcher = mock.patch('room.views.get_transport', return_value=self.transport)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, user):
        self.client.force_login(user)
        return self.client.post(self.url, {'content': 'hi'})

    def test_rate_limited_after_limit(self):
        self.send(self.ada)
        self.send(self.ada)

        response = self.send(self.ada)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {'error': 'rate_limited'})
        self.assertEqual(Message.objects.count(), 2)

    def test_limit_is_per_user(self):
        self.send(self.ada)
        self.send(self.ada)

        self.assertEqual(self.send(self.bob).status_code, 201)

    def test_rate_limited_message_is_not_published(self):
        self.send(self.ada)
        self.send(self.ada)

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.send(self.ada)

        self.assertEqual(callbacks, [])
        self.assertEqual(self.transport.publish.call_count, 0)


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


class RoomMessagesPostTests(TestCase):
    def setUp(self):
        self.ada = User.objects.create_user(username='ada', password='pw')
        self.bob = User.objects.create_user(username='bob', password='pw')
        self.room = Room.objects.create(name='Work', slug='work')
        self.url = reverse('room-messages', args=['work'])
        self.transport = mock.Mock()
        patcher = mock.patch('room.views.get_transport', return_value=self.transport)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_author_is_the_logged_in_user_not_the_body(self):
        self.client.force_login(self.ada)

        response = self.client.post(self.url, {'content': 'hi', 'username': 'bob', 'user': self.bob.id,
                                               'room': 'other'})

        self.assertEqual(response.status_code, 201)
        message = Message.objects.get()
        self.assertEqual(message.user, self.ada)
        self.assertEqual(message.room, self.room)
        self.assertEqual(response.json(), message_payload(message))

    def test_accepts_json_body(self):
        self.client.force_login(self.ada)

        response = self.client.post(self.url, {'content': 'from json'}, content_type='application/json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Message.objects.get().content, 'from json')

    def test_missing_csrf_is_403(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.ada)

        response = client.post(self.url, {'content': 'hi'})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Message.objects.exists())

    def test_anonymous_is_401(self):
        response = self.client.post(self.url, {'content': 'hi'})

        self.assertEqual(response.status_code, 401)
        self.assertFalse(Message.objects.exists())

    def test_unknown_room_is_404(self):
        self.client.force_login(self.ada)

        response = self.client.post(reverse('room-messages', args=['nope']), {'content': 'hi'})

        self.assertEqual(response.status_code, 404)

    def test_empty_and_too_long_are_400(self):
        self.client.force_login(self.ada)
        cases = {'': 'empty', '   \n ': 'empty', 'x' * 4001: 'too_long'}
        for content, error in cases.items():
            with self.subTest(error=error, length=len(content)):
                response = self.client.post(self.url, {'content': content})

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {'error': error})
        self.assertFalse(Message.objects.exists())

    def test_nul_character_is_400(self):
        # PostgreSQL text columns reject NUL bytes; this must not become a 500.
        self.client.force_login(self.ada)

        response = self.client.post(self.url, {'content': 'a\x00b'}, content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'error': 'invalid_body'})
        self.assertFalse(Message.objects.exists())

    def test_publish_failure_still_returns_201(self):
        self.client.force_login(self.ada)
        self.transport.publish.side_effect = RuntimeError('transport broke')

        # assertLogs must be outermost: captured callbacks only run when the inner context exits.
        with self.assertLogs(level='ERROR'), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {'content': 'hi'})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Message.objects.count(), 1)

    def test_4000_characters_is_accepted(self):
        self.client.force_login(self.ada)

        self.assertEqual(self.client.post(self.url, {'content': 'x' * 4000}).status_code, 201)

    def test_publishes_once_after_commit(self):
        self.client.force_login(self.ada)

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            response = self.client.post(self.url, {'content': 'hi'})
            self.transport.publish.assert_not_called()
        for callback in callbacks:
            callback()

        self.transport.publish.assert_called_once_with(self.room, 'message.new', response.json())


class RoomMessagesCatchUpTests(TestCase):
    def setUp(self):
        self.ada = User.objects.create_user(username='ada', password='pw')
        self.room = Room.objects.create(name='Work', slug='work')
        self.other = Room.objects.create(name='Art', slug='art')
        self.url = reverse('room-messages', args=['work'])
        self.client.force_login(self.ada)

    def test_returns_newer_messages_in_order(self):
        old = Message.objects.create(room=self.room, user=self.ada, content='old')
        new = [Message.objects.create(room=self.room, user=self.ada, content=f'new {i}') for i in range(3)]
        Message.objects.create(room=self.other, user=self.ada, content='elsewhere')

        response = self.client.get(self.url, {'after': old.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'messages': [message_payload(m) for m in new]})

    def test_capped_at_100(self):
        Message.objects.bulk_create(Message(room=self.room, user=self.ada, content=str(i)) for i in range(105))

        messages = self.client.get(self.url, {'after': 0}).json()['messages']

        self.assertEqual(len(messages), 100)
        self.assertEqual(messages[0]['content'], '0')

    def test_hostile_content_is_returned_verbatim_as_json(self):
        hostile = '<img src=x onerror=alert(1)>'
        Message.objects.create(room=self.room, user=self.ada, content=hostile)

        response = self.client.get(self.url, {'after': 0})

        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json()['messages'][0]['content'], hostile)

    def test_non_integer_after_is_400(self):
        self.assertEqual(self.client.get(self.url, {'after': 'abc'}).status_code, 400)

    def test_anonymous_is_401(self):
        self.client.logout()

        self.assertEqual(self.client.get(self.url, {'after': 0}).status_code, 401)


class RoomPageTests(TestCase):
    def test_unknown_room_page_is_404(self):
        self.client.force_login(User.objects.create_user(username='ada', password='pw'))

        self.assertEqual(self.client.get(reverse('room', args=['nope'])).status_code, 404)
