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
