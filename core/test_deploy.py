import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parent.parent


class ProductionSettingsTests(SimpleTestCase):
    def test_settings_load_without_env_file(self):
        # Kubernetes supplies config only through the environment; there is no .env in the image.
        env = {**os.environ, 'ENV_FILE': '/nonexistent/.env', 'SECRET_KEY': 'x',
               'POSTGRES_PASSWORD': 'x', 'REDIS_PASSWORD': 'x', 'DJANGO_SETTINGS_MODULE': 'groupchats.settings'}
        result = subprocess.run([sys.executable, '-c', 'import django; django.setup()'],
                                cwd=ROOT, env=env, capture_output=True, text=True)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_columba_without_credentials_fails_at_startup(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('COLUMBA_')}
        env.update({'ENV_FILE': '/nonexistent/.env', 'SECRET_KEY': 'x', 'POSTGRES_PASSWORD': 'x',
                    'REDIS_PASSWORD': 'x', 'DJANGO_SETTINGS_MODULE': 'groupchats.settings',
                    'CHAT_TRANSPORT': 'columba'})
        result = subprocess.run([sys.executable, '-c', 'import django; django.setup()'],
                                cwd=ROOT, env=env, capture_output=True, text=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ImproperlyConfigured', result.stderr)
        self.assertIn('COLUMBA_API_KEY', result.stderr)

    def test_docker_build_context_excludes_local_secrets(self):
        ignored = (ROOT / '.dockerignore').read_text().split()

        for entry in ['.env', '.venv/', '.git', '.claude/']:
            self.assertIn(entry, ignored)


class TransportConfigTests(SimpleTestCase):
    def test_settings_example_lists_columba_keys(self):
        lines = dict(line.split('=', 1) for line in (ROOT / '.env.example').read_text().splitlines()
                     if '=' in line and not line.startswith('#'))

        self.assertEqual(lines.get('CHAT_TRANSPORT'), 'channels')
        for key in ['COLUMBA_URL', 'COLUMBA_SOCKET_URL', 'COLUMBA_APP_ID', 'COLUMBA_API_KEY', 'COLUMBA_SIGNING_SECRET']:
            self.assertIn(key, lines)
            self.assertEqual(lines[key], '', f'{key} must be empty in the example')

    def run_start(self, *args, transport):
        import tempfile
        with tempfile.TemporaryDirectory() as bin_dir:
            for name in ['python', 'daphne', 'gunicorn']:
                stub = Path(bin_dir) / name
                stub.write_text(f'#!/bin/sh\necho "{name} $*"\n')
                stub.chmod(0o755)
            env = {'PATH': f'{bin_dir}:/usr/bin:/bin', 'CHAT_TRANSPORT': transport}
            return subprocess.run([str(ROOT / 'start.sh'), *args], cwd=ROOT, env=env,
                                  capture_output=True, text=True)

    def test_start_serves_columba_with_gunicorn(self):
        result = self.run_start(transport='columba')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('gunicorn groupchats.wsgi:application', result.stdout)

    def test_start_serves_channels_with_daphne(self):
        result = self.run_start(transport='channels')

        self.assertIn('daphne groupchats.asgi:application', result.stdout)

    def test_start_local_uses_runserver_in_both_modes(self):
        for transport in ['channels', 'columba']:
            with self.subTest(transport):
                result = self.run_start('--environment=local', transport=transport)

                self.assertIn('python manage.py runserver', result.stdout)


class DatabaseDefaultsTests(SimpleTestCase):
    def test_database_defaults_use_group_chats_names(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('POSTGRES_')}
        env.update({'ENV_FILE': '/nonexistent/.env', 'SECRET_KEY': 'x', 'POSTGRES_PASSWORD': 'x',
                    'REDIS_PASSWORD': 'x', 'DJANGO_SETTINGS_MODULE': 'groupchats.settings'})
        code = "from django.conf import settings as s; d = s.DATABASES['default']; print(d['NAME'], d['USER'])"
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True, text=True)

        self.assertEqual(result.stdout.split(), ['group_chats', 'group_chats'], result.stderr)


@skipUnless(shutil.which('git'), 'needs git, which the app image does not have')
class RepositoryHygieneTests(SimpleTestCase):
    def test_nginx_ssl_and_venv_are_gitignored(self):
        result = subprocess.run(['git', 'check-ignore', '--no-index', '-q', 'nginx/ssl/server.key'], cwd=ROOT)
        self.assertEqual(result.returncode, 0, 'nginx/ssl/ is not ignored')
        rules = (ROOT / '.gitignore').read_text().splitlines()
        self.assertIn('.venv/', rules)


class KubernetesManifestTests(SimpleTestCase):
    def test_ingress_serves_from_root(self):
        ingress = (ROOT / 'kubernetes/django/ingress.yml.example').read_text()

        self.assertIn('- path: /\n', ingress)

    def test_database_container_creates_the_app_database(self):
        db = (ROOT / 'kubernetes/db/deployment.yml').read_text()

        self.assertIn('name: POSTGRES_DB', db)
        self.assertIn('name: POSTGRES_USER', db)
