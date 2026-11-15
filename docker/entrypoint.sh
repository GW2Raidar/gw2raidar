#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
  # Named volumes created by earlier (root) containers may be root-owned.
  chown -R app:app /data/uploads /data/reports
  exec env HOME=/app setpriv --reuid=app --regid=app --init-groups "$0" "$@"
fi

cd /app
case "$1" in
  web)
    python manage.py migrate --noinput
    exec gunicorn -c /app/docker/gunicorn.conf.py gw2raidar.wsgi:application
    ;;
  worker)
    # process_uploads holds a lock row in the database; a worker killed mid-run (e.g. by a
    # redeploy) would leave it behind and block all future runs, so clear it on start.
    python manage.py shell -c "from raidar.models import Variable; Variable.objects.filter(key='process_uploads_pid').delete()"
    # process_uploads is a one-shot batch job (meant for cron): run it in a loop
    while true; do
      python manage.py process_uploads || echo "process_uploads failed, retrying"
      sleep "${WORKER_INTERVAL:-30}"
    done
    ;;
  *) exec "$@" ;;
esac
