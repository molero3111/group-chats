from django.apps import AppConfig


class RoomConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'room'

    def ready(self):
        # Fail at startup, not on the first message, when the transport is misconfigured.
        from room.transports import get_transport
        get_transport()
