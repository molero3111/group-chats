from functools import cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed
from django.dispatch import receiver

from room.transports.base import Transport

COLUMBA_SETTINGS = ('COLUMBA_URL', 'COLUMBA_SOCKET_URL', 'COLUMBA_APP_ID', 'COLUMBA_API_KEY',
                    'COLUMBA_SIGNING_SECRET')


@cache
def get_transport() -> Transport:
    """The transport chosen by settings.CHAT_TRANSPORT, built once per process."""
    if settings.CHAT_TRANSPORT == 'channels':
        from room.transports.channels import ChannelsTransport
        return ChannelsTransport()
    if settings.CHAT_TRANSPORT == 'columba':
        missing = [name for name in COLUMBA_SETTINGS if not getattr(settings, name, '')]
        if missing:
            raise ImproperlyConfigured(f"CHAT_TRANSPORT=columba needs {', '.join(missing)}")
        from room.transports.columba import ColumbaTransport
        return ColumbaTransport()
    raise ImproperlyConfigured(f'Unknown CHAT_TRANSPORT {settings.CHAT_TRANSPORT!r}; use channels or columba')


@receiver(setting_changed)
def _reset_transport(*, setting, **kwargs):
    if setting == 'CHAT_TRANSPORT' or setting in COLUMBA_SETTINGS:
        get_transport.cache_clear()
