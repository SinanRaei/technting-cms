#!/bin/sh
# Technting CMS container entrypoint.
#
#   web         migrate, then run the dashboard with gunicorn on :8000 (default)
#   scheduler   publish_due every TECHNTING_CMS_SCHEDULE_SECONDS (300), backup once a day after TECHNTING_CMS_BACKUP_HOUR (2)
#   manage ...  any manage.py command, e.g. "docker compose run --rm app manage createsuperuser"
#
# A secret key and a setup key are generated on the first start and kept in the data volume when not set in the environment.
set -eu

VAR_DIR="${TECHNTING_CMS_VAR_DIR:-/data/var}"
mkdir -p "$VAR_DIR"

case "${TECHNTING_CMS_SECRET_KEY:-}" in
  ""|change-me*)
    if [ ! -s "$VAR_DIR/secret_key" ]; then
      umask 077
      python -c "import secrets; print(secrets.token_urlsafe(50))" > "$VAR_DIR/secret_key"
      echo "Technting CMS: generated a new secret key in $VAR_DIR/secret_key"
    fi
    TECHNTING_CMS_SECRET_KEY="$(cat "$VAR_DIR/secret_key")"
    export TECHNTING_CMS_SECRET_KEY
    ;;
esac

# The setup wizard needs this key until it is finished, so nobody else can claim a fresh install first.
if [ -z "${TECHNTING_CMS_SETUP_TOKEN:-}" ]; then
  if [ ! -s "$VAR_DIR/setup_token" ]; then
    umask 077
    python -c "import secrets; print(secrets.token_urlsafe(24))" > "$VAR_DIR/setup_token"
  fi
  TECHNTING_CMS_SETUP_TOKEN="$(cat "$VAR_DIR/setup_token")"
  export TECHNTING_CMS_SETUP_TOKEN
fi

cmd="${1:-web}"
[ "$#" -gt 0 ] && shift

case "$cmd" in
  web)
    python manage.py migrate --noinput
    if [ -n "${TECHNTING_CMS_SETUP_TOKEN:-}" ]; then
      echo "Technting CMS: open /setup/?token=$TECHNTING_CMS_SETUP_TOKEN on the dashboard to finish the installation (until it is finished)."
    fi
    exec gunicorn technting_cms.wsgi:application --bind 0.0.0.0:8000 "$@"
    ;;
  scheduler)
    every="${TECHNTING_CMS_SCHEDULE_SECONDS:-300}"
    hour="${TECHNTING_CMS_BACKUP_HOUR:-2}"
    stamp="$VAR_DIR/.last-backup"
    sleep 30   # let the web service run the migrations first
    while :; do
      python manage.py publish_due || echo "scheduler: publish_due failed"
      today="$(date +%F)"
      if [ "$(date +%H)" -ge "$hour" ] && [ "$(cat "$stamp" 2>/dev/null || true)" != "$today" ]; then
        if python manage.py backup --keep "${TECHNTING_CMS_BACKUP_KEEP:-14}"; then
          echo "$today" > "$stamp"
        else
          echo "scheduler: backup failed"
        fi
      fi
      sleep "$every"
    done
    ;;
  manage)
    exec python manage.py "$@"
    ;;
  *)
    exec "$cmd" "$@"
    ;;
esac
