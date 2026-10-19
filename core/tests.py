from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import OperationalError
from django.test import TestCase, override_settings
from django.urls import reverse

PASSWORD = 'a-Long-test-passw0rd'


class FrontpageTests(TestCase):
    def test_frontpage_redirects_anonymous_to_login(self):
        response = self.client.get(reverse('frontpage'))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].endswith('login/'))


class SignupTests(TestCase):
    def test_signup_creates_user_and_logs_in(self):
        response = self.client.post(reverse('signup'), {
            'email': 'ada@example.com',
            'password1': PASSWORD,
            'password2': PASSWORD,
        }, follow=True)

        self.assertTrue(User.objects.filter(email='ada@example.com', username='ada').exists())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['user'].is_authenticated)


class LoginTests(TestCase):
    def test_login_with_email(self):
        User.objects.create_user(username='ada', email='ada@example.com', password=PASSWORD)

        self.assertTrue(self.client.login(username='ada@example.com', password=PASSWORD))


class RootPathTests(TestCase):
    def test_login_redirect_is_root_relative(self):
        from django.conf import settings

        self.assertEqual(settings.LOGIN_URL, '/login/')
        self.assertEqual(settings.LOGIN_REDIRECT_URL, '/rooms/')
        self.assertEqual(settings.LOGOUT_REDIRECT_URL, '/')

    def test_frontpage_redirects_authenticated_to_rooms(self):
        self.client.force_login(User.objects.create_user(username='ada', password=PASSWORD))

        response = self.client.get('/')

        self.assertRedirects(response, '/rooms/', fetch_redirect_response=False)


class StaticFilesTests(TestCase):
    def test_whitenoise_installed(self):
        from django.conf import settings

        from groupchats import settings as production

        security = settings.MIDDLEWARE.index('django.middleware.security.SecurityMiddleware')
        self.assertEqual(settings.MIDDLEWARE[security + 1], 'whitenoise.middleware.WhiteNoiseMiddleware')
        self.assertEqual(
            production.STORAGES['staticfiles']['BACKEND'],
            'whitenoise.storage.CompressedManifestStaticFilesStorage',
        )


class LayoutTests(TestCase):
    def test_base_uses_bootstrap_5(self):
        response = self.client.get(reverse('login'))

        self.assertContains(response, 'bootstrap@5.3.8')
        self.assertContains(response, 'integrity="sha384-')
        self.assertNotContains(response, 'jquery')

    def test_logout_is_post_form(self):
        self.client.force_login(User.objects.create_user(username='ada', password=PASSWORD))

        response = self.client.get(reverse('rooms'))

        self.assertContains(response, f'<form method="post" action="{reverse("logout")}"')
        self.assertContains(response, 'csrfmiddlewaretoken')


class HealthzTests(TestCase):
    def test_ok_without_login(self):
        response = self.client.get('/healthz')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_database_down_is_503(self):
        with patch('core.views.connection.cursor', side_effect=OperationalError('down')):
            response = self.client.get('/healthz')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable'})

    @override_settings(SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'), ALLOWED_HOSTS=['127.0.0.1'])
    def test_plain_http_from_the_container_healthcheck(self):
        response = self.client.get('/healthz', HTTP_HOST='127.0.0.1')

        self.assertEqual(response.status_code, 200)
