# group-chats: Modernize, Rename, Serve From Root, Restyle — Implementation Plan (PR 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the chat demo up to the current Python/Django stack, rename it to `group-chats`, serve it from `/` on its own subdomain, give it a real test suite with CI, and restyle the UI on Bootstrap 5.3, without changing chat behaviour.

**Architecture:** Same apps (`core`, `room`), same models, same Channels consumer. The Django project package becomes `groupchats`, `URL_PREFIX`/`FORCE_SCRIPT_NAME` go away, WhiteNoise serves static files, and a sqlite/in-memory test settings module lets `manage.py test` run without services, locally and in GitHub Actions. PR 2 (`2026-10-18-pluggable-transport.md`) builds on this branch.

**Tech Stack:** Python 3.14, Django 6.1.2, channels 4.3.2, channels-redis 4.3.0, daphne 4.2.3, gunicorn 26.2.0, whitenoise 6.12.0, psycopg 3.3.6 (binary), django-redis 7.0.0, redis 8.1.0, python-decouple 3.8, Bootstrap 5.3.8.

**Spec:** Emmanuel's decisions of 2026-10-18, recorded in `~/.claude/scratch/chat_in_django/scratchpad.md` § "Decisions". Repo facts with line numbers: same file, § "Repo map".

## Global Constraints

- Name: `group-chats` for the subdomain (`group-chats.emmanuelcodinghub.com`), page titles, Docker image, compose project/networks and k8s resources. Python package: `groupchats`.
- Served from `/`. No `URL_PREFIX`, no `FORCE_SCRIPT_NAME`, websocket path `ws/<room>/`.
- "Latest everything": versions exactly as in Tech Stack, pinned with `==` in `requirements.txt`; dev/test-only deps in `requirements-dev.txt`.
- Verify command (also run by CI): `python manage.py test --settings=groupchats.settings_test`.
- No secret values in the repo. `.env.example` lists key names with placeholder values only; drop the hard-coded secret fallbacks in settings (`SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`), except `settings_test.py`, which may hard-code a test-only `SECRET_KEY`.
- No behaviour change to chat sending/receiving in this PR. Transport, XSS and spoofing fixes are PR 2.
- The GitHub repo rename (`chat_in_django` → `group-chats`) happens after both PRs merge, with Emmanuel's go-ahead. It is not part of any task here.

## Review Focus

1. Login/logout/signup redirects after the prefix removal: every `LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL` and every hard-coded relative redirect in `core/views.py` must resolve from `/`. Tested in Task 2.
2. The websocket still connects at `ws://host/ws/<slug>/` from the restyled room page. Tested in Task 2 (routing) and checked in QA.
3. Static files under daphne with `DEBUG=False`: admin CSS and the Bootstrap page must load with no 404. Tested in Task 3 (manifest storage + `collectstatic`).
4. Startup in Docker with a fresh database: no `makemigrations` at boot, migrations committed, fixtures loaded once. Checked in Task 4.
5. Logout is POST-only in modern Django: the restyled navbar must logout via a POST form with CSRF. Tested in Task 5.

---

### Task 1: Pinned modern dependencies, test settings, CI

**Files:**
- Modify: `requirements.txt` (replace wholesale: only direct deps, pinned)
- Create: `requirements-dev.txt` (`-r requirements.txt`, nothing else needed yet; PR 2 adds `responses`)
- Create: `djangochat/settings_test.py` (renamed in Task 2)
- Modify: `djangochat/settings.py`, `djangochat/asgi.py`
- Create: `.github/workflows/ci.yml`
- Test: `core/tests.py`, `room/tests.py` (replace the stubs)

**Interfaces:**
- Produces: the verify command; `settings_test` that first does `os.environ.setdefault(...)` for every key production settings require (`SECRET_KEY` test-only value, `POSTGRES_*`, `REDIS_*` dummies) and then `from .settings import *`, overriding sqlite `:memory:`, `CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}`, locmem `CACHES` for both `default` and `system`, `PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]`, `STORAGES` staticfiles = `django.contrib.staticfiles.storage.StaticFilesStorage`.

- [ ] **Step 1: Create `.venv` with `uv venv -p 3.14 .venv` and install the pinned deps** (`uv pip install -r requirements-dev.txt`). `requirements.txt` holds exactly: Django, channels, channels-redis, daphne, gunicorn, whitenoise, psycopg[binary], django-redis, redis, python-decouple, at the Tech Stack versions. Drop psycopg2-binary, Twisted, autobahn and the other transitive pins.
- [ ] **Step 2: Write the smoke tests** in `core/tests.py`: `test_frontpage_redirects_anonymous_to_login` (GET `/` → 302 to the login URL), `test_signup_creates_user_and_logs_in` (POST valid form → user exists, follow → rooms page 200), `test_login_with_email` (custom backend accepts email). In `room/tests.py`: `test_rooms_requires_login`, `test_room_page_lists_history` (create Room + 3 Messages, GET room page → 200, all 3 contents present, autoescaped `<b>` appears as `&lt;b&gt;`).
- [ ] **Step 3: Run the verify command, expect failures** from the old stack or missing settings module.
- [ ] **Step 4: Fix settings for Django 6.1.** Engine `django.db.backends.postgresql` (the app uses no GIS; drop `GDAL` from the Dockerfile in Task 4). Remove the hard-coded secret fallbacks. In `asgi.py`, set `DJANGO_SETTINGS_MODULE` before `django.setup()`. Fix whatever deprecations the test run reports.
- [ ] **Step 5: Run the verify command.** Expected: all tests PASS, no warnings under `python -W error::DeprecationWarning`.
- [ ] **Step 6: Write `.github/workflows/ci.yml`** (job `test`, on `push` and `pull_request`): `actions/checkout`, `actions/setup-python` with 3.14, `pip install -r requirements-dev.txt`, then `python manage.py makemigrations --check --dry-run --settings=groupchats.settings_test` and the verify command. (Use `djangochat.settings_test` until Task 2 renames it.)
- [ ] **Step 7: Commit** via `commit-preferences`.

### Task 2: Rename package to `groupchats`, serve from `/`

**Files:**
- Rename: `djangochat/` → `groupchats/` (`git mv`)
- Modify: `manage.py`, `groupchats/{settings,settings_test,asgi,wsgi,urls}.py`, `room/routing.py:7`, `room/views.py:7,27-31`, `room/templates/room.html:39-42`, `core/views.py` (relative redirects), `.env.example`, `kubernetes/django/config-map.yml.example`
- Test: `room/tests.py`, `core/tests.py`

**Interfaces:**
- Consumes: Task 1 settings modules.
- Produces: `DJANGO_SETTINGS_MODULE=groupchats.settings`; websocket route `ws/<str:room_name>/`; no `url_prefix` template variable anywhere.

- [ ] **Step 1: Write the failing tests:** `test_websocket_route_has_no_prefix` (resolve `ws/work/` against `room.routing.websocket_urlpatterns`, assert a match), `test_login_redirect_is_root_relative` (`settings.LOGIN_URL == "/login/"`, `LOGIN_REDIRECT_URL == "/rooms/"`, `LOGOUT_REDIRECT_URL == "/"`), and `test_frontpage_redirects_authenticated_to_rooms` (Location == `/rooms/`).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: `git mv djangochat groupchats`; replace every `djangochat` reference** (`grep -rn djangochat` must return only the plan docs). Delete `URL_PREFIX`, `URL_PREFIX_FORWARD_SLASH` and `FORCE_SCRIPT_NAME` from settings and all users. Redirects in `core/views.py` use `redirect("rooms")` / `redirect("login")`, not relative strings. `room.html` builds the ws URL as `` `${proto}://${location.host}/ws/${roomName}/` ``. Remove `URL_PREFIX` from `.env.example` and the config map. Set `.env.example` `DJANGO_SETTINGS_MODULE=groupchats.settings`, `ALLOWED_HOSTS=localhost group-chats.emmanuelcodinghub.com` and `CSRF_TRUSTED_ORIGINS=http://localhost:8000 https://group-chats.emmanuelcodinghub.com`.
- [ ] **Step 4: Run the verify command.** Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 3: WhiteNoise static serving

**Files:**
- Modify: `groupchats/settings.py` (MIDDLEWARE, `STORAGES`)
- Test: `core/tests.py`

- [ ] **Step 1: Write the failing test** `test_whitenoise_installed`: `"whitenoise.middleware.WhiteNoiseMiddleware"` is directly after `"django.middleware.security.SecurityMiddleware"` in `settings.MIDDLEWARE` (inherited by `settings_test`), and `groupchats.settings.STORAGES["staticfiles"]["BACKEND"] == "whitenoise.storage.CompressedManifestStaticFilesStorage"` (the production module object, importable because `settings_test` set the env defaults).
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement. Step 4: Run** the verify command, then `SECRET_KEY=x POSTGRES_PASSWORD=x REDIS_PASSWORD=x python manage.py collectstatic --noinput --settings=groupchats.settings`. Expected: exits 0 and writes `staticfiles/staticfiles.json`.
- [ ] **Step 5: Commit.**

### Task 4: Deployment artefacts renamed and modernized

**Files:**
- Modify: `Dockerfile`, `Dockerfile-kubernetes` (base `python:3.14-slim`, no GDAL; `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`)
- Modify: `docker-compose-development.yml` (service/network names `group-chats…`, DB image `postgres:18-alpine`, redis `redis:8-alpine`)
- Delete: `docker-compose-staging.yml` (only `deploy.sh` used it; the deploy paths that remain are the dev compose and k8s)
- Modify: `start_chat_app.sh` → rename to `start.sh` (no `makemigrations`; `migrate`, `loaddata` only when `rooms` table is empty via a `--load-fixtures` flag, `collectstatic`, then `runserver` for local, else `daphne groupchats.asgi:application`)
- Modify: `kubernetes/**` (names, image `molero3111/group-chats`, ingress host `group-chats.emmanuelcodinghub.com`, path `/`)
- Modify: `nginx/nginx.conf.example` (`server_name group-chats.emmanuelcodinghub.com`; `location /` and `location /ws/` proxying to `web:8000` with no prefix stripping)
- Delete: `deploy.sh` (the ssh/VPS deploy flow is retired). Remove `VPS_USERNAME`, `VPS_IP`, `VPS_PROJECT_PATH`, `CONTAINER_NAME` and `DOCKER_COMPOSE_FILE` from `.env.example`, and remove every README mention of deploy.sh or the VPS. `grep -rnE 'VPS_|CONTAINER_NAME|DOCKER_COMPOSE_FILE|deploy\.sh'` must return only the plan docs.
- Modify: `README.md` (name, subdomain, the new run/test commands, the env keys)

**Interfaces:**
- Produces: `start.sh [--environment=local] [--load-fixtures]`, used by PR 2 to choose the server per transport.

- [ ] **Step 1: Verify migrations are committed:** `python manage.py makemigrations --check --dry-run --settings=groupchats.settings_test` → "No changes detected". If not, generate them and commit as part of this task.
- [ ] **Step 2: Apply the file changes above.**
- [ ] **Step 3: Build and boot:** `docker compose -p group-chats-dev -f docker-compose-development.yml up --build -d`, then `curl -sI http://localhost:8000/login/` → `200`, `curl -sI http://localhost:8000/static/admin/css/base.css` → `200`. Tear down with `down -v`.
- [ ] **Step 4: Commit.**

Note for the PR body: the DB image changes from `postgis/postgis:13-3.1` to `postgres:18-alpine`, and the compose project name changes. Existing staging data is **not** migrated (new volume). It's a demo, so this is intended, but the PR must say so.

### Task 5: Bootstrap 5.3 restyle

**Files:**
- Modify: `core/templates/base.html`, `core/templates/{frontpage,login,signup}.html`, `room/templates/{rooms,room}.html`
- Create: `core/static/core/app.css` (small: chat layout, bubbles, sticky composer)
- Test: `core/tests.py`, `room/tests.py`

**Design:** Bootstrap 5.3.8 from jsDelivr with SRI hashes, no jQuery or Popper (use the bundle). `data-bs-theme` follows `prefers-color-scheme` via a small inline script. Navbar: brand "group-chats", rooms link, username, and a logout `<form method="post">` with `{% csrf_token %}`. Rooms page: card grid of rooms. Room page: header with the room name, a scrollable message list (own messages right-aligned, others left, username + time in small muted text), and a composer pinned to the bottom. Mobile-first: it must work at 360 px width. Keep the existing element ids that the inline ws script uses (`chat-messages`, `chat-message-input`, `chat-message-submit`), so chat keeps working until PR 2 replaces the script.

- [ ] **Step 1: Write the failing tests:** `test_base_uses_bootstrap_5` (GET login page contains `bootstrap@5.3.8` and `integrity="sha384-`), `test_logout_is_post_form` (rooms page HTML contains a `<form` posting to `reverse("logout")` with `csrfmiddlewaretoken`), `test_room_page_keeps_chat_ids` (the three ids present).
- [ ] **Step 2: Run, expect FAIL. Step 3: Implement the templates and CSS. Step 4: Run the verify command → PASS.**
- [ ] **Step 5: Visual check:** `python manage.py runserver` with a local `.env` and `docker compose` DB/Redis up. Screenshot the login, rooms and room pages at 360 px and 1280 px in light and dark. Two browser tabs exchange a message in real time.
- [ ] **Step 6: Commit.**
