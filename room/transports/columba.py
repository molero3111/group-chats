import logging
import time

import jwt
import requests
from django.conf import settings
from django.urls import reverse

from room.payloads import room_topic

logger = logging.getLogger('room.transports')

PUBLISH_TIMEOUT = 2
TOKEN_LIFETIME = 600  # The token travels in the socket URL, so keep it short; Columba caps it at 24 h.


def mint_token(user, room, now: int | None = None) -> str:
    """A Columba client token allowing `user` to receive events for `room` only."""
    issued_at = int(time.time()) if now is None else now
    claims = {
        'app': settings.COLUMBA_APP_ID,
        'sub': str(user.id),
        'topics': [room_topic(room)],
        'iat': issued_at,
        'exp': issued_at + TOKEN_LIFETIME,
    }
    return jwt.encode(claims, settings.COLUMBA_SIGNING_SECRET, algorithm='HS256')


class ColumbaTransport:
    def publish(self, room, event, payload):
        # The message is already saved; on failure, open tabs fetch it on their next HTTP sync.
        body = {'topics': [room_topic(room)], 'event': event, 'payload': payload, 'id': str(payload['id'])}
        try:
            response = requests.post(
                f'{settings.COLUMBA_URL}/api/v1/publish',
                json=body,
                headers={'Authorization': f'Bearer {settings.COLUMBA_API_KEY}'},
                timeout=PUBLISH_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning('Columba publish failed for %s: %s', body['topics'][0], type(exc).__name__)
            return
        if response.status_code != 202:
            logger.warning('Columba publish for %s answered %s (%s)',
                           body['topics'][0], response.status_code, _error_code(response))

    def client_config(self, request, room):
        return {
            'kind': 'columba',
            'socket_url': settings.COLUMBA_SOCKET_URL,
            'topic': room_topic(room),
            'token_url': reverse('room-token', args=[room.slug]),
        }


def _error_code(response) -> str:
    try:
        return response.json()['error']['code']
    except (ValueError, KeyError, TypeError):
        return 'no error code'
