from django.conf import settings


def client_ip(request):
    """The client's address, from the trusted proxy header when one is configured.

    X-Forwarded-For is never read: its leftmost entry is whatever the client sent.
    Behind Cloudflare, CF-Connecting-IP (META 'HTTP_CF_CONNECTING_IP') is set by Cloudflare itself.
    """
    header = settings.CLIENT_IP_HEADER
    if header and request.META.get(header):
        return request.META[header]
    return request.META.get('REMOTE_ADDR', '')
