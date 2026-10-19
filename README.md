# group-chats

A room-based chat app: sign up, pick a room and talk in real time with everyone in it.
Live at [https://group-chats.emmanuelcodinghub.com](https://group-chats.emmanuelcodinghub.com).

## Features

- Email sign-up and login.
- Chat rooms with persistent history.
- Real-time messaging over WebSockets.

## Technologies

- **Python 3.14 / Django 6.1**: the web framework.
- **Channels + Daphne**: WebSocket handling and the ASGI server.
- **PostgreSQL 18**: users, rooms and messages.
- **Redis 8**: the Channels layer and the cache.
- **WhiteNoise**: static files.
- **Bootstrap 5.3**: styling.

## Run it locally with Docker

1. Clone the repository:

       git clone https://github.com/molero3111/group-chats.git
       cd group-chats

2. Create `.env` from `.env.example` and replace every `change-me` value.

3. Start the stack:

       docker compose -p group-chats-dev -f docker-compose-development.yml up --build

   The app is at [http://localhost:8000](http://localhost:8000), with the rooms from `fixtures/` loaded.

## Realtime transports

`CHAT_TRANSPORT` picks how new messages reach the other people in a room. The UI and models are the same in both
modes. Browsers only receive; a message is always sent with an authenticated `POST /rooms/<slug>/messages/`.
Django saves it, then publishes it through the transport.

| Mode | How it works | Server |
|---|---|---|
| `channels` (default) | Django Channels: the browser opens `/ws/<slug>/`; messages fan out through the Redis channel layer. | Daphne (ASGI) |
| `columba` | [Columba](https://staging-columba.emmanuelcodinghub.com/docs), a hosted fan-out service: Django publishes to `POST /api/v1/publish`, and the browser joins `topic:room:<room id>` with the Phoenix JS client and a short-lived token from `GET /rooms/<slug>/token/`. | gunicorn (WSGI); no Redis channel layer needed |

Columba stores nothing, so Django stays the source of truth for history. After every connect or reconnect, the page
catches up with `GET /rooms/<slug>/messages/?after=<last id>`, and drops duplicates by message id.

Columba settings (from the Columba dashboard; keep them out of the repo):

| Key | Example |
|---|---|
| `COLUMBA_URL` | `https://staging-columba.emmanuelcodinghub.com` (server-side publish; inside Docker on the infra network, `http://columba:4000`) |
| `COLUMBA_SOCKET_URL` | `wss://staging-columba.emmanuelcodinghub.com/socket` (what the browser connects to) |
| `COLUMBA_APP_ID`, `COLUMBA_API_KEY`, `COLUMBA_SIGNING_SECRET` | shown once when the app is created |

For a local Columba on the shared infra platform, use `http://columba.localhost` and `ws://columba.localhost/socket`.
If `CHAT_TRANSPORT=columba` and any of these is missing, the app refuses to start and names the missing keys.

## Run the tests

The test settings use in-memory SQLite and an in-memory channel layer, so no services are needed:

    uv venv -p 3.14 .venv
    uv pip install -p .venv/bin/python -r requirements-dev.txt
    .venv/bin/python manage.py test --settings=groupchats.settings_test

CI runs the same command on every push and pull request.

## Deploying

`start.sh` runs migrations, optionally loads fixtures (`--load-fixtures`), collects static files and starts Daphne
(or gunicorn when `CHAT_TRANSPORT=columba`, or `runserver` with `--environment=local`). Kubernetes manifests are in
`kubernetes/`, and an nginx reverse-proxy example is in `nginx/nginx.conf.example`. Both expect the app at the root
of its own host.

### Homelab (https://group-chats.emmanuelcodinghub.com)

The public instance runs in Columba mode on the homelab, behind a Cloudflare tunnel to `127.0.0.1:8086`.

- **Flow:** merging into `staging` runs `.github/workflows/deploy-homelab.yml`. It runs CI on that commit, pushes
  `ghcr.io/molero3111/group-chats:<sha>`, then joins the tailnet and calls the host's `homelab-deploy` over ssh with
  `group-chats <sha>`. The host migrates with the new image while the old one serves, swaps, waits for `/healthz`
  and reverts to the previous image if the gate fails. The job's exit code says which of those happened.
- **On the host** (owned by the homelab, not this repo): `/srv/apps/group-chats/compose.yml` is a copy of
  `deploy/homelab/compose.yml`; `/srv/apps/group-chats/.env` (mode 0600) holds the settings; Postgres data lives on
  an 800 MB capped volume at `/srv/volumes/group-chats-db/data`.
- **Settings the host's `.env` needs** beyond `.env.example`'s local values: `CHAT_TRANSPORT=columba` with the
  `COLUMBA_*` keys, `DEBUG=False`, `ALLOWED_HOSTS` including `127.0.0.1` (the container healthcheck),
  `CLIENT_IP_HEADER=HTTP_CF_CONNECTING_IP`, `USE_X_FORWARDED_PROTO=True` and `SECURE_COOKIES=True`. The limits
  `LOGIN_RATE`, `SIGNUP_RATE`, `MESSAGE_RATE` and `MAX_USERS` default to 10/300, 5/3600, 30/60 and 500.
- **Rollback:** `gh workflow run deploy-homelab.yml --ref staging -f sha=<full sha>` redeploys an image that is on
  `staging`, passed CI and still exists. It never rolls the schema back.
- **Migrations must be expand/contract.** A failed health gate puts the previous image back on the new schema, so
  every release must leave the schema usable by the release before it: add columns and tables first, and drop
  them only in a later release once nothing reads them.
- Realtime depends on Columba staging being up. Sending and history keep working without it; open pages catch up
  once it is back.
