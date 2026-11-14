#!/bin/sh
# Start nginx and reload it when the dashboard rewrites its redirects file (the Docker version of
# technting-cms-redirects.path).
set -eu

REDIRECTS=/data/var/redirects.conf
sum() { [ -f "$REDIRECTS" ] && md5sum "$REDIRECTS" | cut -d' ' -f1 || echo none; }

nginx -g 'daemon off;' &
pid=$!
trap 'kill -TERM "$pid" 2>/dev/null; wait "$pid"; exit 0' TERM INT

last="$(sum)"
while kill -0 "$pid" 2>/dev/null; do
  sleep 20 &
  wait $! || true
  now="$(sum)"
  if [ "$now" != "$last" ]; then
    if nginx -t -q; then
      nginx -s reload && echo "web: redirects changed, nginx reloaded"
    else
      echo "web: redirects.conf did not pass nginx -t, keeping the running configuration"
    fi
    last="$now"
  fi
done
wait "$pid"
