import logging

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


def parse_rate(value):
    """'10/300' -> (10, 300): at most 10 hits per 300 seconds."""
    try:
        count, seconds = (int(part) for part in value.split('/'))
    except ValueError:
        raise ImproperlyConfigured(f'Rate {value!r} must look like <count>/<seconds>') from None
    if count < 1 or seconds < 1:
        raise ImproperlyConfigured(f'Rate {value!r} needs a positive count and window')
    return count, seconds


def allow(scope, ident, rate):
    """Count one hit for ident in a fixed window; False once the window's count is used up.

    Fails open: if the cache is unreachable the request is allowed and a warning is logged,
    so a Redis outage never locks people out of logging in or sending.
    """
    count, seconds = parse_rate(rate)
    key = f'rl:{scope}:{ident}'
    try:
        cache.add(key, 0, timeout=seconds)  # starts the window; a no-op while it is open
        return cache.incr(key) <= count
    except Exception as exc:
        logger.warning('Rate limit %s skipped, cache unavailable: %s', scope, type(exc).__name__)
        return True
