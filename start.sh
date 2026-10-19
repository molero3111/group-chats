#!/bin/bash
# Usage: ./start.sh [--environment=local] [--load-fixtures]
# Serves with Daphne (CHAT_TRANSPORT=channels) or gunicorn (CHAT_TRANSPORT=columba).
set -euo pipefail

environment="production"
load_fixtures=false
for arg in "$@"
do
    case $arg in
        --environment=*)
            environment="${arg#*=}"
            ;;
        --load-fixtures)
            load_fixtures=true
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 2
            ;;
    esac
done

python manage.py migrate --no-input

# Seed the default rooms on a fresh database only, so admin edits survive restarts.
if [ "$load_fixtures" = true ]; then
    python manage.py seed_rooms
fi

python manage.py collectstatic --no-input

if [ "$environment" = "local" ]; then
    exec python manage.py runserver 0.0.0.0:8000
elif [ "${CHAT_TRANSPORT:-channels}" = "columba" ]; then
    # Columba carries the websockets, so plain WSGI is enough.
    exec gunicorn groupchats.wsgi:application -b 0.0.0.0:8000 -w "${WEB_CONCURRENCY:-3}"
else
    exec daphne groupchats.asgi:application -b 0.0.0.0 -p 8000
fi
