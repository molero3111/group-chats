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

       git clone https://github.com/molero3111/chat_in_django.git
       cd chat_in_django

2. Create `.env` from `.env.example` and replace every `change-me` value.

3. Start the stack:

       docker compose -p group-chats-dev -f docker-compose-development.yml up --build

   The app is at [http://localhost:8000](http://localhost:8000), with the rooms from `fixtures/` loaded.

## Run the tests

The test settings use in-memory SQLite and an in-memory channel layer, so no services are needed:

    uv venv -p 3.14 .venv
    uv pip install -p .venv/bin/python -r requirements-dev.txt
    .venv/bin/python manage.py test --settings=groupchats.settings_test

CI runs the same command on every push and pull request.

## Deploying

`start.sh` runs migrations, optionally loads fixtures (`--load-fixtures`), collects static files and starts Daphne
(or `runserver` with `--environment=local`). Kubernetes manifests are in `kubernetes/`, and an nginx reverse-proxy
example is in `nginx/nginx.conf.example`. Both expect the app at the root of its own host.
