import os
import subprocess
import sys
from pathlib import Path

from django.test import RequestFactory, SimpleTestCase, override_settings

from core.net import client_ip

ROOT = Path(__file__).resolve().parent.parent


class ClientIpTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(CLIENT_IP_HEADER='HTTP_CF_CONNECTING_IP')
    def test_uses_configured_header(self):
        request = self.factory.get('/', HTTP_CF_CONNECTING_IP='203.0.113.7', REMOTE_ADDR='172.18.0.1')

        self.assertEqual(client_ip(request), '203.0.113.7')

    @override_settings(CLIENT_IP_HEADER='')
    def test_ignores_x_forwarded_for(self):
        request = self.factory.get('/', HTTP_X_FORWARDED_FOR='1.2.3.4', REMOTE_ADDR='172.18.0.1')

        self.assertEqual(client_ip(request), '172.18.0.1')

    @override_settings(CLIENT_IP_HEADER='HTTP_CF_CONNECTING_IP')
    def test_falls_back_to_remote_addr_when_header_missing(self):
        request = self.factory.get('/', REMOTE_ADDR='172.18.0.1')

        self.assertEqual(client_ip(request), '172.18.0.1')


class ProxySettingsTests(SimpleTestCase):
    def load_settings(self, **extra):
        env = {k: v for k, v in os.environ.items()
               if k not in ('USE_X_FORWARDED_PROTO', 'SECURE_COOKIES')}
        env.update({'ENV_FILE': '/nonexistent/.env', 'SECRET_KEY': 'x', 'POSTGRES_PASSWORD': 'x',
                    'REDIS_PASSWORD': 'x', 'DJANGO_SETTINGS_MODULE': 'groupchats.settings', **extra})
        code = ('import django; django.setup(); from django.conf import settings as s; '
                'print(s.SECURE_PROXY_SSL_HEADER, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE)')
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_proxy_flags_off_by_default(self):
        self.assertEqual(self.load_settings(), 'None False False')

    def test_proxy_flags_on(self):
        self.assertEqual(self.load_settings(USE_X_FORWARDED_PROTO='True', SECURE_COOKIES='True'),
                         "('HTTP_X_FORWARDED_PROTO', 'https') True True")
