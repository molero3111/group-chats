from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # Fail at startup, not on every login, when a rate limit is malformed: /healthz never
        # reads them, so a bad value would otherwise pass the deploy's health gate.
        from core.ratelimit import parse_rate
        for name in ['LOGIN_RATE', 'SIGNUP_RATE', 'MESSAGE_RATE']:
            try:
                parse_rate(getattr(settings, name))
            except ImproperlyConfigured as exc:
                raise ImproperlyConfigured(f'{name}: {exc}') from None
