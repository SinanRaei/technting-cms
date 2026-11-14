#!/usr/bin/env bash
# Technting CMS installer for a plain Ubuntu or Debian server.
#
#   sudo bash install.sh                 install with systemd (gunicorn, scheduler and backup timers)
#   sudo bash install.sh --nginx         ...and an nginx site for the dashboard and the public site (plain http; add TLS after)
#   bash install.sh --docker             build and start the Docker compose stack instead
#
# Run it from an unpacked release or a Git checkout. Safe to run again: existing users, the virtual environment and
# .env are kept, and nothing is overwritten without asking. Options (or the same names as environment variables):
#
#   --user NAME            system user                 (TECHNTING_USER, default technting)
#   --dir PATH             code folder                 (TECHNTING_DIR, default /home/USER/technting-cms)
#   --var-dir PATH         database, uploads, cache    (TECHNTING_VAR_DIR, default /home/USER/technting-cms-var)
#   --output-dir PATH      the published site          (TECHNTING_OUTPUT_DIR, default /home/USER/htdocs/public)
#   --dashboard-host HOST  e.g. cms.example.com        (TECHNTING_DASHBOARD_HOST, default the server's address)
#   --site-host HOST       e.g. example.com            (TECHNTING_SITE_HOST, only used with --nginx)
#   --port PORT            gunicorn port on 127.0.0.1  (TECHNTING_PORT, default 18150)
#   --db ENGINE            sqlite, mysql (MySQL and MariaDB) or postgresql  (TECHNTING_CMS_DB_ENGINE, default sqlite)
#   --yes                  answer yes to every question
#
# With --db mysql or postgresql, create the database and its user first (docs/INSTALL.md, "Database"): this script
# installs the driver and client tools and writes the connection to .env, but never creates database users or
# passwords. It reads TECHNTING_CMS_DB_NAME, _USER, _PASSWORD, _HOST (127.0.0.1) and _PORT from the environment or
# asks for them; the password is read without echo. With --docker --db mysql and no TECHNTING_CMS_DB_HOST, MariaDB
# runs in its own container (deploy/docker/docker-compose.mysql.yml) and MARIADB_ROOT_PASSWORD is asked for too.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="${TECHNTING_USER:-technting}"
APP_DIR="${TECHNTING_DIR:-}"
VAR_DIR="${TECHNTING_VAR_DIR:-}"
OUTPUT_DIR="${TECHNTING_OUTPUT_DIR:-}"
DASHBOARD_HOST="${TECHNTING_DASHBOARD_HOST:-}"
SITE_HOST="${TECHNTING_SITE_HOST:-}"
PORT="${TECHNTING_PORT:-18150}"
DB_ENGINE="${TECHNTING_CMS_DB_ENGINE:-sqlite}"
MODE="systemd"
WITH_NGINX=0
ASSUME_YES=0

say()  { printf '\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33mWarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }

ask() {   # ask "Question?" -> 0 for yes
  if [ "$ASSUME_YES" = 1 ]; then return 0; fi
  if [ ! -t 0 ]; then warn "$1 (no terminal, answering no; use --yes)"; return 1; fi
  local reply
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]
}

usage() { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --docker) MODE="docker" ;;
    --nginx) WITH_NGINX=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --user) APP_USER="$2"; shift ;;
    --dir) APP_DIR="$2"; shift ;;
    --var-dir) VAR_DIR="$2"; shift ;;
    --output-dir) OUTPUT_DIR="$2"; shift ;;
    --dashboard-host) DASHBOARD_HOST="$2"; shift ;;
    --site-host) SITE_HOST="$2"; shift ;;
    --port) PORT="$2"; shift ;;
    --db) DB_ENGINE="$2"; shift ;;
    -h|--help) usage ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
  shift
done

DB_ENGINE="$(printf '%s' "$DB_ENGINE" | tr '[:upper:]' '[:lower:]')"
case "$DB_ENGINE" in
  ""|sqlite|sqlite3) DB_ENGINE=sqlite ;;
  mysql|mariadb) DB_ENGINE=mysql ;;
  postgresql|postgres) DB_ENGINE=postgresql ;;
  *) die "Unknown database engine: $DB_ENGINE (use sqlite, mysql or postgresql)" ;;
esac

# ---------------------------------------------------------------- database connection (mysql / postgresql)
DB_NAME="${TECHNTING_CMS_DB_NAME:-}"
DB_USER="${TECHNTING_CMS_DB_USER:-}"
DB_PASSWORD="${TECHNTING_CMS_DB_PASSWORD:-}"
DB_HOST="${TECHNTING_CMS_DB_HOST:-}"
DB_PORT="${TECHNTING_CMS_DB_PORT:-}"
DB_ROOT_PASSWORD="${MARIADB_ROOT_PASSWORD:-}"

ask_value() {   # ask_value VAR "Prompt" [default] [secret]: keeps a value that is already set
  local var="$1" prompt="$2" default="${3:-}" secret="${4:-}" reply=""
  [ -n "${!var}" ] && return 0
  if [ ! -t 0 ]; then
    [ -n "$default" ] && { printf -v "$var" '%s' "$default"; return 0; }
    die "$prompt is needed: set it in the environment (no terminal to ask)."
  fi
  if [ -n "$secret" ]; then
    read -r -s -p "$prompt: " reply; echo
  else
    read -r -p "$prompt${default:+ [$default]}: " reply
  fi
  printf -v "$var" '%s' "${reply:-$default}"
  [ -n "${!var}" ] || die "$prompt is needed."
}

check_password() {   # .env files keep values unquoted, so a few characters cannot be used
  if printf '%s' "$1" | grep -q '[[:space:]"'"'"'`$\#]'; then
    die "$2 contains a space, quote, backslash, \$, \` or #. Choose one with letters, digits and other symbols."
  fi
}

collect_db_settings() {   # collect_db_settings docker|server
  [ "$DB_ENGINE" = sqlite ] && return 0
  local default_port=3306
  [ "$DB_ENGINE" = postgresql ] && default_port=5432
  if [ "$1" = docker ] && [ "$DB_ENGINE" = mysql ] && [ -z "$DB_HOST" ]; then
    say "MariaDB container (deploy/docker/docker-compose.mysql.yml)"
    ask_value DB_NAME "Database name" technting_cms
    ask_value DB_USER "Database user" technting_cms
    ask_value DB_PASSWORD "Password for the database user (choose one)" "" secret
    ask_value DB_ROOT_PASSWORD "MariaDB root password (choose one)" "" secret
    check_password "$DB_ROOT_PASSWORD" "The MariaDB root password"
  else
    if [ "$1" = docker ] && [ -z "$DB_HOST" ]; then
      die "With --docker --db postgresql, set TECHNTING_CMS_DB_HOST to your PostgreSQL server."
    fi
    say "Database connection ($DB_ENGINE). The database and its user must exist already (docs/INSTALL.md)"
    ask_value DB_HOST "Database host" 127.0.0.1
    ask_value DB_PORT "Database port" "$default_port"
    ask_value DB_NAME "Database name" technting_cms
    ask_value DB_USER "Database user" technting_cms
    ask_value DB_PASSWORD "Password of that user" "" secret
  fi
  check_password "$DB_PASSWORD" "The database password"
}

db_env_lines() {   # the TECHNTING_CMS_DB_* lines for .env (the password goes only into the file)
  echo "# Database (docs/INSTALL.md, \"Database\")"
  echo "TECHNTING_CMS_DB_ENGINE=$DB_ENGINE"
  [ "$DB_ENGINE" = sqlite ] && return 0
  echo "TECHNTING_CMS_DB_NAME=$DB_NAME"
  echo "TECHNTING_CMS_DB_USER=$DB_USER"
  echo "TECHNTING_CMS_DB_PASSWORD=$DB_PASSWORD"
  if [ -n "$DB_HOST" ]; then echo "TECHNTING_CMS_DB_HOST=$DB_HOST"; fi
  if [ -n "$DB_PORT" ]; then echo "TECHNTING_CMS_DB_PORT=$DB_PORT"; fi
  if [ -n "$DB_ROOT_PASSWORD" ]; then echo "MARIADB_ROOT_PASSWORD=$DB_ROOT_PASSWORD"; fi
}

add_db_settings() {   # add_db_settings FILE docker|server: an .env from an earlier install has no database lines
  local file="$1"
  [ "$DB_ENGINE" = sqlite ] && return 0
  if grep -q '^TECHNTING_CMS_DB_ENGINE=' "$file"; then
    grep -q "^TECHNTING_CMS_DB_ENGINE=$DB_ENGINE\$" "$file" \
      || warn "$file sets another TECHNTING_CMS_DB_ENGINE; it is kept. Edit the file to change databases."
    return 0
  fi
  ask "Add the $DB_ENGINE connection to $file?" || die "Add the TECHNTING_CMS_DB_* settings to $file yourself, then run this again."
  collect_db_settings "$2"
  ( umask 077; db_env_lines >> "$file" )
  echo "  added the database settings"
}

random_key() { python3 -c 'import secrets; print(secrets.token_urlsafe(50))' 2>/dev/null || head -c 48 /dev/urandom | base64 | tr -d '\n/+='; }
random_token() { python3 -c 'import secrets; print(secrets.token_urlsafe(18))' 2>/dev/null || head -c 18 /dev/urandom | base64 | tr -d '\n/+='; }
server_address() { hostname -I 2>/dev/null | awk '{print $1}' || true; }

# ---------------------------------------------------------------- Docker
if [ "$MODE" = "docker" ]; then
  command -v docker >/dev/null || die "Docker is not installed. See https://docs.docker.com/engine/install/"
  docker compose version >/dev/null 2>&1 || die "The Docker compose plugin is missing (docker compose version failed)."
  cd "$SRC_DIR"
  [ -f docker-compose.yml ] || die "Run this from the Technting CMS folder (docker-compose.yml not found)."
  host="${DASHBOARD_HOST:-localhost}"
  compose=(docker compose)
  if [ "$DB_ENGINE" = mysql ] && [ -z "$DB_HOST" ] && ! grep -qs '^TECHNTING_CMS_DB_HOST=' .env; then
    compose+=(-f docker-compose.yml -f deploy/docker/docker-compose.mysql.yml)
  fi
  if [ ! -f .env ]; then
    collect_db_settings docker
    say "Writing .env for Docker"
    umask 077
    cat > .env <<EOF
# Technting CMS (Docker). Leave TECHNTING_CMS_SITE_NAME, _SITE_URL and _THEME out so the setup wizard can set them.
TECHNTING_CMS_SECRET_KEY=$(random_key)
TECHNTING_CMS_ALLOWED_HOSTS=${host},localhost,127.0.0.1
TECHNTING_CMS_SETUP_TOKEN=$(random_token)
# Set to 0 only while you test over plain http on a network address (not needed for http://localhost)
TECHNTING_CMS_HTTPS=1
# TECHNTING_CMS_DASHBOARD_PORT=8000
# TECHNTING_CMS_SITE_PORT=8080
$(db_env_lines)
EOF
  else
    say "Keeping the existing .env"
    add_db_settings .env docker
  fi
  say "Building and starting the containers"
  "${compose[@]}" up -d --build
  token="$(grep -E '^TECHNTING_CMS_SETUP_TOKEN=' .env | tail -n1 | cut -d= -f2- || true)"
  port="$(grep -E '^TECHNTING_CMS_DASHBOARD_PORT=' .env | tail -n1 | cut -d= -f2- || true)"
  echo
  say "Technting CMS is starting. Next step: open the setup wizard"
  echo "    http://${host}:${port:-8000}/setup/${token:+?token=$token}"
  echo "  The published site will be on port ${TECHNTING_CMS_SITE_PORT:-8080}. Logs: ${compose[*]} logs -f app"
  exit 0
fi

# ---------------------------------------------------------------- systemd install
[ "$(id -u)" -eq 0 ] || die "Run as root (sudo bash install.sh), or use --docker."
[ -f /etc/debian_version ] || warn "This installer is written for Ubuntu and Debian; other systems may need changes."
command -v systemctl >/dev/null || die "systemd is required (or use --docker)."
[ -f "$SRC_DIR/manage.py" ] && [ -f "$SRC_DIR/requirements.txt" ] || die "Run this from the Technting CMS folder."

HOME_DIR="/home/$APP_USER"
APP_DIR="${APP_DIR:-$HOME_DIR/technting-cms}"
VAR_DIR="${VAR_DIR:-$HOME_DIR/technting-cms-var}"
OUTPUT_DIR="${OUTPUT_DIR:-$HOME_DIR/htdocs/public}"
DASHBOARD_HOST="${DASHBOARD_HOST:-$(server_address)}"
DASHBOARD_HOST="${DASHBOARD_HOST:-localhost}"

say "Packages"
missing=()
for pkg in python3 python3-venv python3-pip git; do
  dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if [ "$WITH_NGINX" = 1 ]; then dpkg -s nginx >/dev/null 2>&1 || missing+=(nginx); fi
# the MySQL / MariaDB driver (mysqlclient) is compiled; the client tools make and restore the backups
case "$DB_ENGINE" in
  mysql) db_pkgs=(pkg-config default-libmysqlclient-dev build-essential mariadb-client) ;;
  postgresql) db_pkgs=(postgresql-client) ;;
  *) db_pkgs=() ;;
esac
for pkg in "${db_pkgs[@]}"; do
  dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "  installing: ${missing[*]}"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
fi

PYTHON="${PYTHON:-}"
for candidate in "$PYTHON" python3.13 python3.12 python3; do
  [ -n "$candidate" ] && command -v "$candidate" >/dev/null || continue
  if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then PYTHON="$(command -v "$candidate")"; break; fi
done
[ -n "$PYTHON" ] && "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
  || die "Python 3.12 or newer is required ($(python3 --version 2>&1)). Ubuntu 24.04 has it; on older systems use --docker."
echo "  Python: $("$PYTHON" --version)"
ver="$("$PYTHON" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
if ! "$PYTHON" -m venv --help >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "python${ver}-venv"
fi
if [ "$DB_ENGINE" = mysql ] && ! dpkg -s "python${ver}-dev" >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "python${ver}-dev"   # headers for building mysqlclient
fi

say "System user $APP_USER"
if id "$APP_USER" >/dev/null 2>&1; then
  echo "  exists"
else
  useradd --system --create-home --home-dir "$HOME_DIR" --shell /usr/sbin/nologin "$APP_USER"
  echo "  created"
fi
install -d -o "$APP_USER" -g "$APP_USER" -m 755 "$HOME_DIR" "$APP_DIR" "$VAR_DIR" "$OUTPUT_DIR" "$HOME_DIR/backups"

say "Code in $APP_DIR"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
  if [ -f "$APP_DIR/manage.py" ] && ! ask "Replace the code in $APP_DIR with this copy? (.env, .venv and your data are kept)"; then
    echo "  keeping the code that is there"
  else
    tar -C "$SRC_DIR" --exclude=./.git --exclude=./.venv --exclude=./.env --exclude=./var -cf - . | tar -C "$APP_DIR" -xf -
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"
    echo "  copied"
  fi
else
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

as_app() { runuser -u "$APP_USER" -- "$@"; }

say "Virtual environment"
[ -x "$APP_DIR/.venv/bin/python" ] || as_app "$PYTHON" -m venv "$APP_DIR/.venv"
as_app "$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
as_app "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
case "$DB_ENGINE" in
  mysql) as_app "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements-mysql.txt" ;;
  postgresql) as_app "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements-postgresql.txt" ;;
esac

say "Settings ($APP_DIR/.env)"
ENV_FILE="$APP_DIR/.env"
if [ -f "$ENV_FILE" ]; then
  echo "  keeping the existing .env"
  add_db_settings "$ENV_FILE" server
else
  collect_db_settings server
  umask 077
  cat > "$ENV_FILE" <<EOF
# Technting CMS settings, written by install.sh. The setup wizard adds the site name, site URL and theme.
TECHNTING_CMS_DEBUG=0
TECHNTING_CMS_SECRET_KEY=$(random_key)
TECHNTING_CMS_ALLOWED_HOSTS=${DASHBOARD_HOST},localhost,127.0.0.1
TECHNTING_CMS_CSRF_ORIGINS=https://${DASHBOARD_HOST}
TECHNTING_CMS_ADMIN_URL=https://${DASHBOARD_HOST}
TECHNTING_CMS_VAR_DIR=${VAR_DIR}
TECHNTING_CMS_OUTPUT_DIR=${OUTPUT_DIR}
TECHNTING_CMS_TIME_ZONE=UTC
# Asked once by the setup wizard; delete this line after setup if you like
TECHNTING_CMS_SETUP_TOKEN=$(random_token)
# TECHNTING_CMS_UPDATE_REMOTE=   update from this Git remote instead of the published releases (see docs/INSTALL.md)
$(db_env_lines)
EOF
  umask 022
  echo "  written with a new secret key"
fi
chown "$APP_USER:$APP_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

say "Database and static files"
(cd "$APP_DIR" && as_app .venv/bin/python manage.py migrate --noinput)
(cd "$APP_DIR" && as_app .venv/bin/python manage.py collectstatic --noinput >/dev/null)

say "systemd units"
units=(technting-cms.service technting-cms-scheduler.service technting-cms-scheduler.timer
       technting-cms-backup.service technting-cms-backup.timer)
if [ "$WITH_NGINX" = 1 ]; then units+=(technting-cms-redirects.service technting-cms-redirects.path); fi
changed=0
for unit in "${units[@]}"; do
  tmp="$(mktemp)"
  sed -e "s#/home/technting/technting-cms-var#${VAR_DIR}#g" \
      -e "s#/home/technting/technting-cms#${APP_DIR}#g" \
      -e "s#^User=technting#User=${APP_USER}#" -e "s#^Group=technting#Group=${APP_USER}#" \
      -e "s#127.0.0.1:18150#127.0.0.1:${PORT}#" \
      -e "s#(cms.example.com)#(${DASHBOARD_HOST})#" "$APP_DIR/deploy/$unit" > "$tmp"
  target="/etc/systemd/system/$unit"
  if [ -f "$target" ] && cmp -s "$tmp" "$target"; then
    rm -f "$tmp"; continue
  fi
  if [ -f "$target" ] && ! ask "Replace the changed $target?"; then
    rm -f "$tmp"; echo "  kept $unit"; continue
  fi
  install -m 644 "$tmp" "$target"; rm -f "$tmp"; changed=1; echo "  installed $unit"
done
[ "$changed" = 1 ] && systemctl daemon-reload
systemctl enable --now technting-cms.service technting-cms-scheduler.timer technting-cms-backup.timer >/dev/null
[ "$WITH_NGINX" = 1 ] && systemctl enable --now technting-cms-redirects.path >/dev/null
systemctl restart technting-cms.service

if [ "$WITH_NGINX" = 1 ]; then
  say "nginx"
  SITE_HOST="${SITE_HOST:-_}"
  conf=/etc/nginx/sites-available/technting-cms.conf
  tmp="$(mktemp)"
  cat > "$tmp" <<EOF
# Written by Technting CMS install.sh. Plain http: add TLS (for example with certbot --nginx) before going live.
server {
  listen 80;
  server_name ${DASHBOARD_HOST};
  client_max_body_size 100m;
  add_header X-Robots-Tag "noindex, nofollow" always;
  location /static/ { alias ${VAR_DIR}/static/; expires 7d; }
  location / {
    proxy_pass http://127.0.0.1:${PORT};
    proxy_set_header Host \$host;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_read_timeout 90s;
  }
}
server {
  listen 80;
  server_name ${SITE_HOST};
  root ${OUTPUT_DIR};
  index index.html;
  include ${VAR_DIR}/redirects*.conf;
  location ~ ^/(api|f|newsletter)/ {
    proxy_pass http://127.0.0.1:${PORT};
    proxy_set_header Host ${DASHBOARD_HOST};
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_set_header X-Real-IP \$remote_addr;
  }
  location / { try_files \$uri \$uri/ =404; }
  error_page 404 /404.html;
}
EOF
  if [ -f "$conf" ] && ! cmp -s "$tmp" "$conf" && ! ask "Replace the changed $conf?"; then
    rm -f "$tmp"; echo "  kept $conf"
  else
    install -m 644 "$tmp" "$conf"; rm -f "$tmp"
    ln -sf "$conf" /etc/nginx/sites-enabled/technting-cms.conf
    nginx -t -q && systemctl reload nginx
    echo "  $conf"
  fi
  # nginx reads the published site, the static files and redirects.conf through the app user's group
  id -nG www-data 2>/dev/null | grep -qw "$APP_USER" || usermod -aG "$APP_USER" www-data
  chmod 750 "$HOME_DIR" "$VAR_DIR"
  systemctl restart nginx
fi

token="$(grep -E '^TECHNTING_CMS_SETUP_TOKEN=' "$ENV_FILE" | tail -n1 | cut -d= -f2- || true)"
echo
say "Technting CMS is installed and running (systemctl status technting-cms)"
echo "Next step: open the setup wizard."
if [ "$WITH_NGINX" = 1 ]; then
  echo "    http://${DASHBOARD_HOST}/setup/${token:+?token=$token}"
  echo "  Add TLS before you share the address, for example: certbot --nginx -d ${DASHBOARD_HOST}"
  echo "  Until TLS is on, set TECHNTING_CMS_HTTPS=0 in $ENV_FILE and run: systemctl restart technting-cms"
else
  echo "  The dashboard listens on 127.0.0.1:${PORT}. Put nginx in front (sudo bash install.sh --nginx, or see deploy/README.md),"
  echo "  or open it now through an SSH tunnel from your computer:"
  echo "    ssh -L ${PORT}:127.0.0.1:${PORT} <you>@<this server>"
  echo "    http://localhost:${PORT}/setup/${token:+?token=$token}"
fi
