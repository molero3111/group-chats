from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from room.payloads import room_group


class ChannelsTransport:
    def publish(self, room, event, payload):
        async_to_sync(get_channel_layer().group_send)(
            room_group(room), {'type': 'chat.message', 'event': event, 'payload': payload}
        )

    def client_config(self, request, room):
        return {'kind': 'channels', 'path': f'/ws/{room.slug}/'}
