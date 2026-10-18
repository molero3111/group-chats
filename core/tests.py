from django.contrib.auth.models import User
from django.test import TestCase
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
