import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from room.payloads import room_group

logger = logging.getLogger('room.transports')


class ChannelsTransport:
    def publish(self, room, event, payload):
        # The message is already saved; on failure, receivers catch up over HTTP.
        group = room_group(room)
        try:
            async_to_sync(get_channel_layer().group_send)(
                group, {'type': 'chat.message', 'event': event, 'payload': payload}
            )
        except Exception as exc:  # any channel-layer backend error (Redis down, timeout, ...)
            logger.warning('Channels publish failed for %s: %s', group, type(exc).__name__)

    def client_config(self, request, room):
        return {'kind': 'channels', 'path': f'/ws/{room.slug}/'}
