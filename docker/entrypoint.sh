#!/bin/sh
set -e
cd /app
until python -c "import socket,os; socket.create_connection((os.environ.get('POSTGRES_HOST','db'), int(os.environ.get('POSTGRES_PORT','5432'))), 2)" 2>/dev/null; do echo "waiting for db"; sleep 1; done
case "$1" in
  web)
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
    cp /app/docker/wsgi_docker.py /app/gw2raidar/wsgi_docker.py
    exec gunicorn gw2raidar.wsgi_docker:application --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile -
    ;;
  worker)
    # process_uploads is a one-shot batch job (meant for cron): run it in a loop
    while true; do
      python manage.py process_uploads || echo "process_uploads failed, retrying"
      sleep "${WORKER_INTERVAL:-30}"
    done
    ;;
  *) exec "$@" ;;
esac
