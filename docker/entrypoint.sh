#!/bin/sh
set -e
cd /app
until nc -z "${POSTGRES_HOST:-db}" "${POSTGRES_PORT:-5432}"; do echo "waiting for db"; sleep 1; done
case "$1" in
  web)
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
    cp /app/docker/wsgi_docker.py /app/gw2raidar/wsgi_docker.py
    exec gunicorn gw2raidar.wsgi_docker:application --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 120
    ;;
  worker)
    exec python manage.py process_uploads
    ;;
  *) exec "$@" ;;
esac
