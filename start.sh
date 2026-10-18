#!/bin/bash
# Usage: ./start.sh [--environment=local] [--load-fixtures]
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

# Fixtures carry primary keys, so loading them again updates the same rows.
if [ "$load_fixtures" = true ]; then
    python manage.py loaddata fixtures/*
fi

python manage.py collectstatic --no-input

if [ "$environment" = "local" ]; then
    exec python manage.py runserver 0.0.0.0:8000
else
    exec daphne groupchats.asgi:application -b 0.0.0.0 -p 8000
fi
