from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.ratelimit import allow, parse_rate

PASSWORD = 'a-Long-test-passw0rd'


class RateLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_allows_up_to_count_then_blocks(self):
        results = [allow('t', 'a', '3/60') for _ in range(4)]

        self.assertEqual(results, [True, True, True, False])

    def test_identities_are_independent(self):
        for _ in range(3):
            allow('t', 'a', '3/60')

        self.assertFalse(allow('t', 'a', '3/60'))
        self.assertTrue(allow('t', 'b', '3/60'))

    def test_window_expires(self):
        for _ in range(4):
            allow('t', 'a', '3/60')

        cache.delete('rl:t:a')  # what the cache does when the window's timeout passes

        self.assertTrue(allow('t', 'a', '3/60'))

    def test_scopes_are_independent(self):
        for _ in range(3):
            allow('login', 'a', '3/60')

        self.assertTrue(allow('signup', 'a', '3/60'))

    def test_cache_error_fails_open(self):
        with patch('core.ratelimit.cache.incr', side_effect=ConnectionError('redis down')):
            with self.assertLogs('core.ratelimit', 'WARNING') as logs:
                self.assertTrue(allow('login', '203.0.113.7', '1/60'))

        self.assertIn('login', logs.output[0])
        self.assertNotIn('203.0.113.7', logs.output[0])

    def test_parse_rate(self):
        self.assertEqual(parse_rate('10/300'), (10, 300))

    def test_parse_rate_rejects_garbage(self):
        for value in ['abc', '0/60', '5/0', '5', '-1/60']:
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                parse_rate(value)


@override_settings(CLIENT_IP_HEADER='HTTP_CF_CONNECTING_IP', LOGIN_RATE='2/300')
class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user(username='ada', email='ada@example.com', password=PASSWORD)

    def post(self, password, ip='203.0.113.7'):
        return self.client.post(reverse('login'), {'username': 'ada@example.com', 'password': password},
                                HTTP_CF_CONNECTING_IP=ip)

    def test_login_throttled_after_limit(self):
        self.post('wrong')
        self.post('wrong')

        response = self.post(PASSWORD)

        self.assertEqual(response.status_code, 429)
        self.assertContains(response, 'Too many attempts', status_code=429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_other_ip_still_logs_in(self):
        self.post('wrong')
        self.post('wrong')

        response = self.post(PASSWORD, ip='198.51.100.9')

        self.assertRedirects(response, reverse('rooms'), fetch_redirect_response=False)

    def test_get_is_not_counted(self):
        for _ in range(3):
            self.client.get(reverse('login'), HTTP_CF_CONNECTING_IP='203.0.113.7')

        response = self.post(PASSWORD)

        self.assertEqual(response.status_code, 302)


@override_settings(CLIENT_IP_HEADER='HTTP_CF_CONNECTING_IP', SIGNUP_RATE='1/3600', MAX_USERS=0)
class SignupLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def post(self, email, ip='203.0.113.7'):
        return self.client.post(reverse('signup'), {'email': email, 'password1': PASSWORD, 'password2': PASSWORD},
                                HTTP_CF_CONNECTING_IP=ip)

    def test_signup_throttled_after_limit(self):
        self.post('ada@example.com')
        self.client.logout()

        response = self.post('bob@example.com')

        self.assertEqual(response.status_code, 429)
        self.assertContains(response, 'Too many attempts', status_code=429)
        self.assertFalse(User.objects.filter(email='bob@example.com').exists())

    @override_settings(MAX_USERS=1)
    def test_signup_closed_at_max_users(self):
        User.objects.create_user(username='ada', password=PASSWORD)

        page = self.client.get(reverse('signup'))
        response = self.post('bob@example.com')

        self.assertContains(page, 'Sign-ups are closed.', status_code=403)
        self.assertContains(response, 'Sign-ups are closed.', status_code=403)
        self.assertEqual(User.objects.count(), 1)

    def test_max_users_zero_is_unlimited(self):
        User.objects.bulk_create([User(username=f'u{i}') for i in range(5)])

        response = self.post('ada@example.com')

        self.assertEqual(response.status_code, 302)
