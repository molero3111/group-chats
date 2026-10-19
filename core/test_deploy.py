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

        for entry in ['.env*', '.venv/', '.git', '.claude/']:
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


try:
    import yaml
except ImportError:  # requirements-dev.txt only; the app image does not ship it
    yaml = None

PG_IMAGE = 'postgres:18-alpine@sha256:'
REDIS_IMAGE = 'redis:8-alpine@sha256:'


@skipUnless(yaml, 'needs PyYAML from requirements-dev.txt')
class HomelabComposeTests(SimpleTestCase):
    def setUp(self):
        self.compose = yaml.safe_load((ROOT / 'deploy/homelab/compose.yml').read_text())
        self.services = self.compose['services']

    def test_only_web_publishes_a_port_on_loopback(self):
        self.assertEqual(self.services['web']['ports'], ['127.0.0.1:8086:8000'])
        for name in ['db', 'redis']:
            self.assertNotIn('ports', self.services[name])

    def test_images_are_pinned(self):
        self.assertTrue(self.services['db']['image'].startswith(PG_IMAGE))
        self.assertTrue(self.services['redis']['image'].startswith(REDIS_IMAGE))
        self.assertEqual(self.services['web']['image'],
                         'ghcr.io/molero3111/group-chats:${IMAGE_TAG:?IMAGE_TAG is required}')

    def test_db_volume_binds_capped_dir_at_pg18_path(self):
        self.assertEqual(self.services['db']['volumes'], ['group_chats_db:/var/lib/postgresql'])
        self.assertEqual(self.compose['volumes']['group_chats_db'], {
            'driver': 'local',
            'driver_opts': {'type': 'none', 'o': 'bind', 'device': '/srv/volumes/group-chats-db/data'},
        })

    def test_db_gets_no_app_env_file(self):
        self.assertNotIn('env_file', self.services['db'])
        self.assertEqual(set(self.services['db']['environment']),
                         {'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD'})

    def test_web_waits_for_healthy_db_and_redis(self):
        self.assertEqual(self.services['web']['depends_on'], {
            'db': {'condition': 'service_healthy'},
            'redis': {'condition': 'service_healthy'},
        })

    def test_web_healthcheck_hits_healthz(self):
        self.assertIn('http://127.0.0.1:8000/healthz', ' '.join(self.services['web']['healthcheck']['test']))

    def test_every_service_has_healthcheck_and_mem_limit(self):
        for name, service in self.services.items():
            with self.subTest(name):
                self.assertIn('healthcheck', service)
                self.assertIn('mem_limit', service)
                self.assertEqual(service['restart'], 'unless-stopped')

    def test_redis_is_a_passworded_memory_only_cache(self):
        command = self.services['redis']['command']

        for part in ['--requirepass', '--save ""', '--appendonly no', '--maxmemory 64mb', 'allkeys-lru']:
            self.assertIn(part, command)


def load_workflow(name):
    workflow = yaml.safe_load((ROOT / '.github/workflows' / name).read_text())
    # YAML 1.1 reads the bare key `on` as True.
    workflow['on'] = workflow.pop(True, workflow.get('on'))
    return workflow


@skipUnless(yaml, 'needs PyYAML from requirements-dev.txt')
class DeployWorkflowTests(SimpleTestCase):
    def setUp(self):
        self.workflow = load_workflow('deploy-homelab.yml')
        self.jobs = self.workflow['jobs']

    def test_triggers_are_staging_push_and_dispatch(self):
        self.assertEqual(self.workflow['on']['push'], {'branches': ['staging']})
        self.assertIn('sha', self.workflow['on']['workflow_dispatch']['inputs'])

    def test_one_deploy_at_a_time(self):
        self.assertEqual(self.workflow['concurrency'],
                         {'group': 'deploy-homelab-group-chats', 'cancel-in-progress': False})

    def test_deploy_job_uses_homelab_environment_and_read_only_packages(self):
        deploy = self.jobs['deploy']

        self.assertEqual(deploy['environment'], 'homelab')
        self.assertEqual(deploy['permissions'], {'contents': 'read', 'packages': 'read'})

    def test_deploy_targets_group_chats_app_key(self):
        script = next(step['run'] for step in self.jobs['deploy']['steps'] if step.get('name') == 'Deploy via SSH')

        self.assertIn('deploy@100.77.124.5 "group-chats $DEPLOY_SHA"', script)
        self.assertIn('StrictHostKeyChecking=yes', script)
        self.assertIn("printf '%s' \"$GHCR_TOKEN\" |", script)

    def test_ci_runs_before_build(self):
        self.assertEqual(self.jobs['ci']['uses'], './.github/workflows/ci.yml')
        self.assertIn('ci', self.jobs['build']['needs'])
        self.assertIn('build', self.jobs['deploy']['needs'])

    def test_build_is_amd64_and_sha_tagged(self):
        build = next(step['with'] for step in self.jobs['build']['steps']
                     if step.get('uses', '').startswith('docker/build-push-action@'))

        self.assertEqual(build['platforms'], 'linux/amd64')
        self.assertEqual(build['tags'], '${{ env.IMAGE_NAME }}:${{ needs.resolve.outputs.sha }}')
        self.assertEqual(self.workflow['env']['IMAGE_NAME'], 'ghcr.io/molero3111/group-chats')

    def test_rollback_guard_checks_this_repos_ci_job(self):
        script = (ROOT / '.github/scripts/resolve-deploy-sha.sh').read_text()

        self.assertIn('test("(^|/ )test$")', script)

    def test_ci_is_callable_and_skips_staging_push(self):
        ci = load_workflow('ci.yml')

        self.assertIn('workflow_call', ci['on'])
        self.assertEqual(ci['on']['push'], {'branches-ignore': ['staging']})
