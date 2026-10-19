# Homelab Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make group-chats deployable as a public app at https://group-chats.emmanuelcodinghub.com on the homelab, in Columba mode: deploy files, a health endpoint, settings for running behind Cloudflare, and the minimum abuse limits a public sign-up app needs.

**Architecture:**
- **Request flow:** Cloudflare tunnel → `127.0.0.1:8086` → the `web` container on :8000, served by gunicorn because `CHAT_TRANSPORT=columba`. Postgres and Redis sit on a private compose network.
- **Deploys:** a push to `staging` runs CI as a reusable workflow, builds `ghcr.io/molero3111/group-chats:<sha>`, then SSHes over Tailscale to the host's `homelab-deploy` forced command. That command migrates, swaps, health-gates and auto-reverts.
- **Rate limits:** fixed-window counters in the Django cache (Redis), keyed by the Cloudflare client IP or the user id.

**Tech Stack:** Django 6.1, gunicorn, docker compose, GitHub Actions, GHCR, Tailscale.

**Spec:** the "homelab setup" peer session's request of 2026-10-18, plus Emmanuel's answers, all recorded in `~/.claude/scratch/chat_in_django/scratchpad.md` § "Columba homelab deploy reference". Working reference: `~/Documents/projects/erlang/columba/.github/workflows/deploy-homelab.yml`, `deploy/homelab/compose.yml` and `deploy/homelab/DEPLOY-CONTRACT.md`.

## Global Constraints

- **App key and host:**
  - The app key on the host is `group-chats`, so the deploy call is `"group-chats <40-char sha>"`.
  - The host is `deploy@100.77.124.5`.
  - The image is `ghcr.io/molero3111/group-chats:<sha>`, linux/amd64, tagged with the sha only.
- **Ports:** web publishes only `127.0.0.1:8086:8000`. db and redis publish no ports.
- **db service:**
  - Image: `postgres:18-alpine@sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873`.
  - Volume: a bind to `/srv/volumes/group-chats-db/data`, mounted at `/var/lib/postgresql` (PG18 keeps PGDATA at `/var/lib/postgresql/18/docker`).
- **redis service:**
  - Image: `redis:8-alpine@sha256:3811787313eba226a2ef38658c6ccb91cd5e110edc89c37767de373120a0e5a0`.
  - Command: `redis-server --requirepass ${REDIS_PASSWORD} --save "" --appendonly no --maxmemory 64mb --maxmemory-policy allkeys-lru`, with mem_limit 128m.
- **Secrets:** none in the repo. COLUMBA_APP_ID, COLUMBA_API_KEY and COLUMBA_SIGNING_SECRET are set by Emmanuel on the server.
- **New env keys** have safe local defaults: proxy trust and secure cookies are off, `CLIENT_IP_HEADER` is empty. The homelab .env turns them on.
- **Limits** (Emmanuel's choice) are env-configurable, in `<count>/<seconds>` form:
  - `LOGIN_RATE=10/300` per IP
  - `SIGNUP_RATE=5/3600` per IP
  - `MESSAGE_RATE=30/60` per user
  - `MAX_USERS=500`, where 0 means unlimited
- **No Turnstile.** Room creation stays admin-only, so it has no cap.
- **Migrations are expand/contract:** the previous image must run on the new schema. This plan adds no migration.

## Review Focus

1. **Redis unavailable:** login, sign-up and sending must still work. Rate limits fail open with a logged warning, never a 500.
2. **Spoofed client IP:** `X-Forwarded-For` is never read. Only the configured `CLIENT_IP_HEADER` is read, falling back to `REMOTE_ADDR` when the header is absent.
3. **/healthz:**
  - It is reachable without login, over plain HTTP, with Host `127.0.0.1`, while `SECURE_PROXY_SSL_HEADER` is on.
  - It returns 503 rather than 500 when the database is down.
4. **Deploy `if` logic:** a redeploy dispatch, where ci and build are skipped, still deploys. A failed CI never deploys.
5. **First sign-up when the user cap is reached:** the page says sign-ups are closed, and no user row is created.

---

### Task 1: Client IP and proxy settings

**Files:**
- Create: `core/net.py`
- Modify: `groupchats/settings.py` (after `CSRF_TRUSTED_ORIGINS`) and `.env.example`
- Test: `core/test_net.py`

**Interfaces:**
- Produces:
  - `client_ip(request) -> str`, which reads `request.META[settings.CLIENT_IP_HEADER]` when that setting is non-empty and the header is present, else `REMOTE_ADDR`.
  - These settings:
    - `CLIENT_IP_HEADER` (str, default `''`)
    - `USE_X_FORWARDED_PROTO` (bool, default False), which sets `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` when True
    - `SECURE_COOKIES` (bool, default False), which sets `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE`

- [ ] **Step 1: Write the failing tests** in `core/test_net.py`, using `RequestFactory` and `override_settings`:
  - `test_uses_configured_header` sets `CLIENT_IP_HEADER='HTTP_CF_CONNECTING_IP'` and passes META `HTTP_CF_CONNECTING_IP='203.0.113.7'` plus `REMOTE_ADDR='172.18.0.1'`. It expects `'203.0.113.7'`.
  - `test_ignores_x_forwarded_for` leaves the header unset and passes `HTTP_X_FORWARDED_FOR='1.2.3.4'`. It expects `REMOTE_ADDR`.
  - `test_falls_back_to_remote_addr_when_header_missing` expects `REMOTE_ADDR`.
  - `test_proxy_flags_off_by_default` and `test_proxy_flags_on` run in a subprocess, like `core/test_deploy.py:ProductionSettingsTests`:
    - With the env flags unset, `SECURE_PROXY_SSL_HEADER` is None and both cookie flags are False.
    - With `USE_X_FORWARDED_PROTO=True` and `SECURE_COOKIES=True`, they become the tuple and True.
- [ ] **Step 2: Run them.** `.venv/bin/python manage.py test core.test_net --settings=groupchats.settings_test`. Expected: FAIL with ImportError on `core.net`.
- [ ] **Step 3: Implement** `core/net.py` and the settings. Add `CLIENT_IP_HEADER=`, `USE_X_FORWARDED_PROTO=False` and `SECURE_COOKIES=False` to `.env.example`, each with a one-line comment.
- [ ] **Step 4: Run them again.** Expected: PASS. Then run the full suite: PASS.
- [ ] **Step 5: Commit** `feat(core): read the client ip and https scheme from a trusted proxy`

### Task 2: /healthz

**Files:**
- Modify: `core/views.py` and `core/urls.py` (`path('healthz', HealthzView.as_view(), name='healthz')`)
- Test: `core/tests.py`, class `HealthzTests`

**Interfaces:**
- Produces: `GET /healthz`, which returns 200 `{"status": "ok"}` when `connection.cursor().execute('SELECT 1')` succeeds, and 503 `{"status": "unavailable"}` on `django.db.Error`. It needs no login.

- [ ] **Step 1: Write the failing tests:**
  - `test_ok_without_login` expects 200 and the JSON body.
  - `test_database_down_is_503` patches `core.views.connection.cursor` to raise `OperationalError` and expects 503 with `{"status": "unavailable"}`.
  - `test_plain_http_behind_proxy_header` uses `override_settings(SECURE_PROXY_SSL_HEADER=(...))` with no forwarded header and expects 200, not a redirect.
- [ ] **Step 2: Run them.** Expected: FAIL with 404.
- [ ] **Step 3: Implement `HealthzView`.**
- [ ] **Step 4: Run them again.** Expected: PASS, and the suite passes.
- [ ] **Step 5: Commit** `feat(core): add a healthz endpoint that checks the database`

### Task 3: Rate limits for login and sign-up, and the user cap

**Files:**
- Create: `core/ratelimit.py`
- Modify: `core/views.py` (adds `ThrottledLoginView(LoginView)` and changes `SignupView`), `core/urls.py`, `groupchats/settings.py` and `.env.example`
- Test: `core/test_ratelimit.py`, plus `core/tests.py` classes `LoginThrottleTests` and `SignupLimitTests`

**Interfaces:**
- Produces:
  - `parse_rate(value: str) -> tuple[int, int]`, which turns `'10/300'` into `(10, 300)` and raises `ImproperlyConfigured` on bad input.
  - `allow(scope: str, ident: str, rate: str) -> bool`, a fixed window. It does `cache.add(key, 0, timeout=seconds)`, then `cache.incr(key) <= count`. The key is `rl:<scope>:<ident>`. Any cache exception logs a warning that names the scope only, and returns True.
  - These settings: `LOGIN_RATE`, `SIGNUP_RATE`, `MESSAGE_RATE` and `MAX_USERS`, with the defaults from Global Constraints.

- [ ] **Step 1: Write the failing tests:**
  - **Rate helper:**
    - `test_allows_up_to_count_then_blocks`: with `'3/60'`, three calls are True and the fourth is False.
    - `test_identities_are_independent`.
    - `test_window_expires`: patch `cache.add` and `cache.incr`, or use a tiny window plus `cache.delete` of the key.
    - `test_cache_error_fails_open`: patch `cache.incr` to raise `ConnectionError`. It returns True, and `assertLogs('core.ratelimit', 'WARNING')` holds.
    - `test_parse_rate_rejects_garbage` covers `'abc'`, `'0/60'` and `'5/0'`.
  - **Login:** `test_login_throttled_after_limit` sets `LOGIN_RATE='2/300'`. The third POST from the same `CLIENT_IP_HEADER` value gets 429, the error is shown, and no session is created even with a correct password. A POST from another IP still logs in.
  - **Sign-up:**
    - `test_signup_throttled_after_limit` gets 429 and creates no user.
    - `test_signup_closed_at_max_users` sets `MAX_USERS=1` with one existing user. GET and POST both return 403 with the copy "Sign-ups are closed.", and the user count is unchanged.
    - `test_max_users_zero_is_unlimited`.
- [ ] **Step 2: Run them.** Expected: FAIL with ImportError, and the views tests FAIL.
- [ ] **Step 3: Implement the views.**
  - Both views count only POSTs.
  - A throttled form gets `form.add_error(None, 'Too many attempts. Try again in a few minutes.')` and renders with status 429.
  - The login URL uses `ThrottledLoginView.as_view(template_name='login.html')`.
- [ ] **Step 4: Run them again.** Expected: PASS, and the suite passes.
- [ ] **Step 5: Commit** `feat(core): throttle login and sign-up per ip and cap total sign-ups`

### Task 4: Per-user message rate limit

**Files:**
- Modify: `room/views.py` (`RoomMessagesView.post`, checked after the auth and room lookup and before validation) and `room/static/room/chat.js` (the submit handler)
- Test: `room/tests/test_api.py`, class `MessageRateLimitTests`

**Interfaces:**
- Consumes: Task 3's `allow('message', str(user.id), settings.MESSAGE_RATE)`.
- Produces: a 429 response `{"error": "rate_limited"}`. The client shows "You're sending messages too fast. Wait a moment and try again."

- [ ] **Step 1: Write the failing tests:**
  - `test_rate_limited_after_limit` sets `MESSAGE_RATE='2/60'`. The third POST gets 429 and only 2 rows exist.
  - `test_limit_is_per_user`: a second user can still send.
  - `test_rate_limited_message_is_not_published`: under `captureOnCommitCallbacks`, the 429 queues no callback.
- [ ] **Step 2: Run them.** Expected: FAIL, because the third POST gets 201.
- [ ] **Step 3: Implement the view check and the 429 branch in chat.js.**
- [ ] **Step 4: Run them again.** Expected: PASS, and the suite passes.
- [ ] **Step 5: Commit** `feat(room): rate limit sending per user`

### Task 5: Homelab compose and the image build context

**Files:**
- Create: `deploy/homelab/compose.yml`
- Modify: `.dockerignore` (replace `.env` with `.env*`) and `requirements-dev.txt` (add `PyYAML`, pinned to the latest release)
- Test: `core/test_deploy.py`, class `HomelabComposeTests`, plus an update to `test_docker_build_context_excludes_local_secrets`

**Interfaces:**
- Produces: the file the host installs at `/srv/apps/group-chats/compose.yml`. Top-level `name: group-chats`, and services `web`, `db` and `redis` on network `group_chats`.
  - **web:**
    - image `ghcr.io/molero3111/group-chats:${IMAGE_TAG:?IMAGE_TAG is required}`
    - `command: ["./start.sh", "--load-fixtures"]`, `env_file: .env`, ports `["127.0.0.1:8086:8000"]`
    - depends_on db and redis with `condition: service_healthy`
    - healthcheck `["CMD", "python", "-c", "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status != 200)"]`, interval 10s, timeout 5s, retries 6, start_period 60s
    - mem_limit and memswap_limit 512m, cpus "1.0", pids_limit 512
  - **db:**
    - only `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD`, as `${VAR:?VAR is required}`, with no env_file
    - pg_isready healthcheck at 5s, 3s, 12 retries and start_period 20s
    - mem 256m, cpus "0.5", pids 200
    - volume `group_chats_db:/var/lib/postgresql`
  - **redis:**
    - the command from Global Constraints
    - healthcheck `["CMD-SHELL", "redis-cli -a \"$$REDIS_PASSWORD\" --no-auth-warning ping | grep -q PONG"]`, with `environment: REDIS_PASSWORD: ${REDIS_PASSWORD:?REDIS_PASSWORD is required}`
    - mem 128m, cpus "0.5"
  - **All services:** `restart: unless-stopped`, logging json-file with max-size 10m and max-file "3".
  - **Volume:** `group_chats_db`, a bind to the capped directory.

- [ ] **Step 1: Write the failing tests.** They load the YAML with `yaml.safe_load`.
  - `test_only_web_publishes_a_port_on_loopback`
  - `test_images_are_pinned`: db and redis contain `@sha256:`, and web uses `${IMAGE_TAG:?`.
  - `test_db_volume_binds_capped_dir_at_pg18_path`
  - `test_db_gets_no_app_env_file`
  - `test_web_waits_for_healthy_db_and_redis`
  - `test_every_service_has_healthcheck_and_mem_limit`
  - `.dockerignore` contains `.env*`
- [ ] **Step 2: Run them.** Expected: FAIL, file not found.
- [ ] **Step 3: Write the compose file and the `.dockerignore` change.** Validate them with `IMAGE_TAG=x POSTGRES_DB=a POSTGRES_USER=a POSTGRES_PASSWORD=a REDIS_PASSWORD=a docker compose -f deploy/homelab/compose.yml config -q`, using a throwaway empty `.env` in a temp dir copy. Expected: exit 0.
- [ ] **Step 4: Run them again.** Expected: PASS, and the suite passes.
- [ ] **Step 5: Commit** `feat(deploy): add the homelab compose stack`

### Task 6: Deploy workflow

**Files:**
- Create: `.github/workflows/deploy-homelab.yml` and `.github/scripts/resolve-deploy-sha.sh` (ported from Columba's; the CI check name regex is `(^|/ )test$`)
- Modify: `.github/workflows/ci.yml` (add `workflow_call:`; change push to `branches-ignore: [staging]`)
- Test: `core/test_deploy.py`, class `DeployWorkflowTests`

**Interfaces:**
- Produces:
  - Triggers: push to `staging`, and `workflow_dispatch` with input `sha`.
  - Jobs: `resolve` → `ci` (`uses: ./.github/workflows/ci.yml`) → `build` → `deploy`, the same structure and `if` expressions as Columba's (scratchpad reference).
  - Concurrency group `deploy-homelab-group-chats`, `cancel-in-progress: false`.
  - The deploy job has `environment: homelab`, `permissions: {contents: read, packages: read}`, tailscale/github-action@v3 with `TS_OAUTH_*` and `tags: tag:ci`, and the ssh call `"group-chats $DEPLOY_SHA"`. Its exit-code case covers 0, 2, 3, 4, 5, 6, 7 and 255, writes to the step summary, and runs `exit "$rc"`.

- [ ] **Step 1: Write the failing tests** with `yaml.safe_load`. PyYAML parses the `on` key as `True`; handle both.
  - `test_triggers_are_staging_push_and_dispatch`
  - `test_deploy_job_uses_homelab_environment_and_read_only_packages`
  - `test_deploy_targets_group_chats_app_key`: the run script contains `"group-chats $DEPLOY_SHA"` and `StrictHostKeyChecking=yes`.
  - `test_ci_runs_before_build`
  - `test_ci_is_callable_and_skips_staging_push`
  - `test_build_is_amd64_and_sha_tagged`
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Write the workflow and the script.** Make the script executable (`git update-index --chmod=+x`). Run `actionlint` through `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`. Expected: no errors.
- [ ] **Step 4: Run them again.** Expected: PASS, and the suite passes.
- [ ] **Step 5: Commit** `ci(deploy): build and deploy staging to the homelab`

### Task 7: Docs

**Files:**
- Modify: `README.md` (new "Homelab deploy" section)

- [ ] **Step 1: Write the section.** It covers:
  - the flow, from staging push to CI, build, ssh and gate
  - the server-side files and who owns them
  - the env keys, by name, with the values the homelab .env needs: `CLIENT_IP_HEADER=HTTP_CF_CONNECTING_IP`, `USE_X_FORWARDED_PROTO=True`, `SECURE_COOKIES=True` and the limits
  - rollback with `gh workflow run deploy-homelab.yml --ref staging -f sha=<sha>`
  - the expand/contract migration rule
  - the dependency on Columba staging's uptime
- [ ] **Step 2: Commit** `docs(readme): document the homelab deploy`
