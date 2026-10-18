import json
from unittest import mock

import jwt
import requests
import responses
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from room.models import Message, Room
from room.payloads import message_payload, room_group, room_topic
from room.transports import get_transport
from room.transports.channels import ChannelsTransport
from room.transports.columba import ColumbaTransport, mint_token

COLUMBA = {
    'COLUMBA_URL': 'https://columba.test',
    'COLUMBA_SOCKET_URL': 'wss://columba.test/socket',
    'COLUMBA_APP_ID': '0b6f1a52-6a43-4c3a-9a7a-3f1d6f0f9c11',
    'COLUMBA_API_KEY': 'ck_live_test',
    'COLUMBA_SIGNING_SECRET': 'test-signing-secret',
}
PUBLISH_URL = 'https://columba.test/api/v1/publish'


class PayloadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ada', password='pw')
        self.room = Room.objects.create(name='Work', slug='work')
        self.message = Message.objects.create(room=self.room, user=self.user, content='hello')

    def test_message_payload_shape(self):
        payload = message_payload(self.message)

        self.assertEqual(set(payload), {'id', 'room', 'user', 'content', 'created_at'})
        self.assertEqual(payload['id'], self.message.id)
        self.assertEqual(payload['room'], 'work')
        self.assertEqual(payload['user'], {'id': self.user.id, 'username': 'ada'})
        self.assertEqual(payload['content'], 'hello')
        self.assertTrue(payload['created_at'].endswith(('Z', '+00:00')))

    def test_topic_and_group_use_room_id(self):
        self.assertEqual(room_topic(self.room), f'room:{self.room.id}')
        self.assertEqual(room_group(self.room), f'chat_{self.room.id}')


@override_settings(CHAT_TRANSPORT='columba', **COLUMBA)
class ColumbaTransportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ada', password='pw')
        self.room = Room.objects.create(name='Work', slug='work')
        self.message = Message.objects.create(room=self.room, user=self.user, content='hello')
        self.payload = message_payload(self.message)

    @responses.activate
    def test_columba_publish_request(self):
        responses.post(PUBLISH_URL, status=202, json={'accepted': True, 'id': str(self.message.id), 'topics': 1})

        with mock.patch('room.transports.columba.requests.post', wraps=requests.post) as post:
            ColumbaTransport().publish(self.room, 'message.new', self.payload)

        self.assertEqual(post.call_args.kwargs['timeout'], 2)
        sent = responses.calls[0].request
        self.assertEqual(sent.url, PUBLISH_URL)
        self.assertEqual(sent.headers['Authorization'], 'Bearer ck_live_test')
        self.assertEqual(sent.headers['Content-Type'], 'application/json')
        self.assertEqual(json.loads(sent.body), {
            'topics': [f'room:{self.room.id}'],
            'event': 'message.new',
            'payload': self.payload,
            'id': str(self.message.id),
        })

    @responses.activate
    def test_columba_publish_failures_are_logged_not_raised(self):
        failures = {
            '429': {'status': 429, 'json': {'error': {'code': 'rate_limited', 'retry_after': 3}}},
            '503': {'status': 503, 'body': 'unavailable'},
            'timeout': {'body': requests.Timeout('slow')},
            'connection': {'body': requests.ConnectionError('down')},
        }
        for name, kwargs in failures.items():
            with self.subTest(name):
                responses.reset()
                responses.post(PUBLISH_URL, **kwargs)

                with self.assertLogs('room.transports', 'WARNING') as logs:
                    ColumbaTransport().publish(self.room, 'message.new', self.payload)

                output = '\n'.join(logs.output)
                self.assertNotIn('ck_live_test', output)
                self.assertNotIn('hello', output)
                if name == '429':
                    self.assertIn('rate_limited', output)

    def test_mint_token_claims(self):
        token = mint_token(self.user, self.room, now=1_800_000_000)

        claims = jwt.decode(token, 'test-signing-secret', algorithms=['HS256'],
                            options={'verify_exp': False, 'verify_iat': False})
        self.assertEqual(jwt.get_unverified_header(token)['alg'], 'HS256')
        self.assertEqual(claims['app'], COLUMBA['COLUMBA_APP_ID'])
        self.assertEqual(claims['sub'], str(self.user.id))
        self.assertEqual(claims['topics'], [f'room:{self.room.id}'])
        self.assertEqual(claims['iat'], 1_800_000_000)
        self.assertEqual(claims['exp'] - claims['iat'], 600)


class ChannelsTransportTests(TestCase):
    def test_channels_publish_group_send(self):
        user = User.objects.create_user(username='ada', password='pw')
        room = Room.objects.create(name='Work', slug='work')
        payload = message_payload(Message.objects.create(room=room, user=user, content='hello'))
        layer = get_channel_layer()
        channel = async_to_sync(layer.new_channel)()
        async_to_sync(layer.group_add)(room_group(room), channel)

        ChannelsTransport().publish(room, 'message.new', payload)

        received = async_to_sync(layer.receive)(channel)
        self.assertEqual(received, {'type': 'chat.message', 'event': 'message.new', 'payload': payload})


class GetTransportTests(TestCase):
    def setUp(self):
        get_transport.cache_clear()
        self.addCleanup(get_transport.cache_clear)

    def test_default_is_channels(self):
        self.assertIsInstance(get_transport(), ChannelsTransport)

    @override_settings(CHAT_TRANSPORT='columba', **COLUMBA)
    def test_columba_selected(self):
        self.assertIsInstance(get_transport(), ColumbaTransport)

    @override_settings(CHAT_TRANSPORT='columba', **{**COLUMBA, 'COLUMBA_API_KEY': ''})
    def test_columba_misconfigured_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            get_transport()

    @override_settings(CHAT_TRANSPORT='carrier-pigeon')
    def test_unknown_transport_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            get_transport()
