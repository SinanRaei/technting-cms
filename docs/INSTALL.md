# Installing Technting CMS

This guide takes you from an empty server to a published site. Arabic version: [INSTALL-ar.md](INSTALL-ar.md).

Technting CMS has two parts:

- the **dashboard**, a Django application (gunicorn) where editors work, usually on a host such as `cms.example.com`;
- the **public site**, plain static files that the dashboard writes into a folder, served by nginx (or any web server)
  on your main host, such as `example.com`.

The contact form, Technting Forms, the stats beacon and the newsletter on the public site send their requests to the
dashboard (`/api/`, `/f/`, `/newsletter/`), so the web server of the public site forwards those paths.

## Requirements

| | Docker | Linux installer | Manual |
|---|---|---|---|
| System | any host with Docker and the compose plugin | Ubuntu 24.04+ or Debian with Python 3.12+ | any system with Python 3.12+ |
| Memory | 512 MB is enough for a small site | same | same |
| Database | SQLite, nothing to set up; or MySQL / MariaDB or PostgreSQL ([Database](#database)) | same | same |

Get the code as a release archive (`technting-cms-<version>.tar.gz` or `.zip`, check it against `SHA256SUMS`) or as a
Git checkout.

## Database

SQLite is the default: one file in the var folder, nothing to install or set up, and the right choice for a small or
medium site with a handful of editors. Choose MySQL / MariaDB or PostgreSQL for a larger site, many people editing at
once, or when your host gives you a database server (shared hosting, a managed database).

| `TECHNTING_CMS_DB_ENGINE` | Database | Driver |
|---|---|---|
| `sqlite` (default) | SQLite 3 | built into Python |
| `mysql` (also `mariadb`) | MySQL 8.0+ or MariaDB 10.6+ | `requirements-mysql.txt` (mysqlclient) |
| `postgresql` | PostgreSQL 14+ | `requirements-postgresql.txt` (psycopg) |

For `mysql` and `postgresql`, set the connection in `.env` (or the server environment):

```
TECHNTING_CMS_DB_ENGINE=mysql
TECHNTING_CMS_DB_NAME=technting_cms
TECHNTING_CMS_DB_USER=technting_cms
TECHNTING_CMS_DB_PASSWORD=<the password you chose>
TECHNTING_CMS_DB_HOST=127.0.0.1      # default
TECHNTING_CMS_DB_PORT=3306           # default: 3306 for mysql, 5432 for postgresql
```

The dashboard refuses to start when the engine is unknown or a name, user or password is missing. The connection is
never typed into the setup wizard; its summary and Settings, Updates show which database is in use. Keep the password
free of spaces, quotes, backslashes, `$` and `#`: `.env` values are read without quotes.

Create the database and its user yourself before the first start; neither the CMS nor `install.sh` creates database
users or passwords. MySQL / MariaDB (always `utf8mb4`, so Arabic text and emoji are stored correctly):

```sql
CREATE DATABASE technting_cms CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'technting_cms'@'localhost' IDENTIFIED BY '<a long random password>';
GRANT ALL PRIVILEGES ON technting_cms.* TO 'technting_cms'@'localhost';
```

Use the host the CMS connects from instead of `localhost` when the database runs on another machine, and
`TECHNTING_CMS_DB_HOST=localhost` to connect through the local socket. PostgreSQL:

```sql
CREATE USER technting_cms WITH PASSWORD '<a long random password>';
CREATE DATABASE technting_cms OWNER technting_cms ENCODING 'UTF8' TEMPLATE template0;
```

Then install the driver and run the migrations: `install.sh --db mysql` (or `--db postgresql`) does both and writes
the settings to `.env`; by hand, `.venv/bin/pip install -r requirements-mysql.txt`, then `manage.py migrate`. On
Debian and Ubuntu the MySQL driver is compiled, so first install `pkg-config default-libmysqlclient-dev
build-essential python3-dev`. Backups need the client tools too: `mariadb-client` (or the MySQL client) for MySQL and
MariaDB, `postgresql-client` for PostgreSQL, the same major version as the server or newer.

Docker: the image has both drivers and the client tools, so only the settings are needed. To run MariaDB in its own
container next to the CMS, put `TECHNTING_CMS_DB_PASSWORD` and `MARIADB_ROOT_PASSWORD` in `.env` and add the override:

```bash
docker compose -f docker-compose.yml -f deploy/docker/docker-compose.mysql.yml up -d --build
```

The `db` service (`mariadb:11`) creates the database and user from those values on its first start, keeps its data in
the `mariadb` volume, publishes no port and must be healthy before `app` and `scheduler` start. Use the same two `-f`
options for every later `docker compose` command. For a database server outside Docker, set the
`TECHNTING_CMS_DB_*` values in `.env` instead and start the stack as usual. `bash install.sh --docker --db mysql`
asks for the two passwords, writes them to `.env` and uses the override.

Moving an existing site from SQLite to another database: `manage.py dumpdata --natural-foreign --exclude contenttypes
--exclude auth.permission > content.json` with the old settings, then `migrate` and `loaddata content.json` with the
new ones. Backups restore only into the kind of database they were made from. `demo_reset` (the public demo) works with
SQLite only.

## Option 1: Docker

```bash
tar xzf technting-cms-0.4.0.tar.gz && cd technting-cms-0.4.0
bash install.sh --docker
```

`install.sh --docker` checks Docker, writes `.env` (a new secret key, a setup key, the allowed hosts) if there is none,
and runs `docker compose up -d --build`. It prints the setup wizard address, for example
`http://localhost:8000/setup/?token=...`. You can also run `docker compose up -d --build` yourself; without a `.env`
a secret key and a setup key are generated on the first start and kept in the data volume (`/data/var/secret_key`,
`/data/var/setup_token`); `docker compose logs app` shows the wizard address with the key.

What runs:

| Service | What | Port |
|---|---|---|
| `app` | the dashboard (gunicorn); runs the migrations when it starts | inside the stack only |
| `scheduler` | `publish_due` every 5 minutes (scheduled pages, periodic jobs) and `backup --keep 14` once a day after 02:00 | none |
| `web` | nginx: the published site, and the dashboard with its static files | 8080 (site), 8000 (dashboard) |

Volumes: `data` (database, uploads, cache, backups, `site.env`) and `site` (the published site). Back up the `data`
volume, or copy the snapshots from `/data/backups`.

Useful `.env` values for Docker: `TECHNTING_CMS_ALLOWED_HOSTS` (add your dashboard and site host names),
`TECHNTING_CMS_DASHBOARD_PORT` and `TECHNTING_CMS_SITE_PORT` (published ports), `TECHNTING_CMS_SCHEDULE_SECONDS`,
`TECHNTING_CMS_BACKUP_HOUR`, `TECHNTING_CMS_BACKUP_KEEP`, `GUNICORN_CMD_ARGS` (workers and threads). Leave
`TECHNTING_CMS_SITE_NAME`, `_SITE_URL` and `_THEME` out: the wizard sets them, and a value in `.env` would be shown
read-only.

For a public server, put a TLS proxy in front of the two ports. With Caddy, for example:

```
cms.example.com {
  reverse_proxy 127.0.0.1:8000
}
example.com {
  reverse_proxy 127.0.0.1:8080
}
```

Run commands inside the stack with `docker compose exec app python manage.py <command>`, for example
`changepassword <username>`. Logs: `docker compose logs -f app scheduler web`.

## Option 2: the Linux installer

```bash
tar xzf technting-cms-0.4.0.tar.gz && cd technting-cms-0.4.0
sudo bash install.sh --nginx --dashboard-host cms.example.com --site-host example.com
```

What it does, in order (each step is skipped when it is already done):

1. installs the missing packages (`python3-venv`, `git`, `nginx` with `--nginx`, and the database driver's build
   packages and client tools with `--db mysql` or `--db postgresql`) and checks for Python 3.12+;
2. creates the system user `technting` and the folders below;
3. copies the code to `/home/technting/technting-cms` (asks first when code is already there);
4. creates the virtual environment and installs `requirements.txt` (and `requirements-mysql.txt` or
   `requirements-postgresql.txt` with `--db`);
5. writes `.env` (mode 600) with a new secret key, a setup key and, with `--db`, the database connection it read from
   `TECHNTING_CMS_DB_*` or asked for (the password without echo), unless `.env` exists;
6. runs `migrate` and `collectstatic`;
7. installs `technting-cms.service` and the scheduler and backup timers from `deploy/` with your user, folders and port
   (asks before it replaces a unit you changed), enables and starts them;
8. with `--nginx`: writes `/etc/nginx/sites-available/technting-cms.conf` (plain http for both hosts) and the redirects
   watcher;
9. prints the setup wizard address.

Options: `--user`, `--dir`, `--var-dir`, `--output-dir`, `--dashboard-host`, `--site-host`, `--port`, `--db`, `--yes`
(see `bash install.sh --help`). Without `--nginx`, the dashboard listens on `127.0.0.1:18150` only: use
`deploy/cms.example.com.conf` as a starting point for your own nginx site, or open the wizard through an SSH tunnel
(`ssh -L 18150:127.0.0.1:18150 you@server`, then `http://localhost:18150/setup/`).

Add TLS before you share the address, for example `sudo certbot --nginx -d cms.example.com -d example.com`. Until
then, sign-in over plain http to a host name needs `TECHNTING_CMS_HTTPS=0` in `.env` and
`sudo systemctl restart technting-cms`; set it back to 1 once TLS works.

## Option 3: manual install

1. `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (add `-r requirements-mysql.txt` or
   `-r requirements-postgresql.txt` for another database, see [Database](#database))
2. `cp .env.example .env`, then set at least `TECHNTING_CMS_SECRET_KEY` (a long random string),
   `TECHNTING_CMS_ALLOWED_HOSTS`, `TECHNTING_CMS_CSRF_ORIGINS`, `TECHNTING_CMS_ADMIN_URL`, `TECHNTING_CMS_VAR_DIR` and
   `TECHNTING_CMS_OUTPUT_DIR`. `chmod 600 .env`.
3. `.venv/bin/python manage.py migrate` and `.venv/bin/python manage.py collectstatic --noinput`
4. Run gunicorn (`deploy/technting-cms.service` shows the command) and the two timers, and set up nginx as described in
   `deploy/README.md`.

## The setup wizard

Open the dashboard address. Until setup is finished, every dashboard page leads to `/setup/`:

1. **Site**: the site name and the public address.
2. **Languages**: English only, Arabic only, or both with a default language. The default language is served at the
   site root; the other one under `/ar/` or `/en/`.
3. **Administrator**: user name, email and password. The password rules are the dashboard's own: at least 12
   characters, not a common password, not similar to the user name.
4. **Theme**: the installed themes in `themes/`.
5. **Email**: optional SMTP server, port, security (SSL or STARTTLS), user name, password and sender name. *Send test
   email* tries the account before you save it. *Skip this step* leaves email for later (Settings, Email).
6. **Licence key**: paste the free key from the e-mail that brought the download link. The wizard checks it with
   licenses.technting.com for the site address of step 1 and refuses a key that is cancelled, not valid or already
   used on another website (fill in the download form again for a new one). When the licence server cannot be
   reached, the key is kept and checked again later. Settings, Licence changes it afterwards.
7. **Finish**: check the summary, tick *Add demo content* if you want a home page, a privacy page and the header menu,
   and press *Finish setup*.

The wizard then creates the administrator, saves the languages and the email account (the password is encrypted,
exactly like Settings, Email), writes the site name, address and theme to `.env` (or `VAR_DIR/site.env`), signs you in
and publishes the site. `/setup/` answers 404 from then on.

Safety: the wizard only exists while there is no user and setup is not marked complete; every form is CSRF protected;
attempts and test emails are rate limited per address; with `TECHNTING_CMS_SETUP_TOKEN` set, the key is asked once.
Install on a server nobody else can reach yet, or keep the setup key, and finish the wizard right away.

## After setup

- Settings: contact email, leads inbox, two-step verification for all users, header button.
- Users: invite editors, authors and sales users.
- Plugins: turn on Technting Shield (starts in learning mode) and Technting Backup for offsite copies.
- Settings, Updates: press Check for updates. The dashboard asks technting.com for the newest published release
  (`TECHNTING_CMS_UPDATE_FEED`) and installs its zip with Update now. Only the version you run is sent, nothing else.
  To update from your own Git repository instead, set `TECHNTING_CMS_UPDATE_REMOTE` in `.env` to that remote.

## Upgrading

- systemd installs: Settings, Updates (backup, new code, migrations, reload, publish, automatic rollback), or unpack
  the new release and run `sudo bash install.sh` again (it asks before replacing the code; `.env`, `.venv` and data stay).
- Docker: unpack the new release or `git pull`, then `docker compose up -d --build`.
- Read `CHANGELOG.md` before you upgrade.

## Backups and restore

Backups run every night (`backup --keep 14`): a database snapshot, the uploaded media and a manifest with SHA-256 sums.
The snapshot is `technting_cms.sqlite3` with SQLite (SQLite's online backup API) and `database.sql.gz` with MySQL /
MariaDB (`mysqldump --single-transaction --routines`) or PostgreSQL (`pg_dump`); the dump tools get the password from a
temporary option file or the environment, never from the command line. They are listed under Settings, Backups. To
restore on a systemd install:

```bash
sudo systemctl stop technting-cms
sudo -u technting /home/technting/technting-cms/.venv/bin/python /home/technting/technting-cms/manage.py restore_backup <folder> --yes
sudo -u technting /home/technting/technting-cms/.venv/bin/python /home/technting/technting-cms/manage.py publish
sudo systemctl start technting-cms
```

`restore_backup` checks every checksum first. With SQLite it moves the current database file aside; with MySQL /
MariaDB or PostgreSQL it first dumps the current database to `VAR_DIR/database-before-restore-<stamp>/`, then loads
the backup with `mysql` or `psql`. Backups made before 0.3.0 are SQLite backups and still restore.

On Docker: `docker compose stop app scheduler`, then
`docker compose run --rm app manage restore_backup /data/backups/technting-cms/<folder> --yes`,
`docker compose run --rm app manage publish` and `docker compose start app scheduler`.

## Running a public demo

`TECHNTING_CMS_DEMO_MODE=1` turns an installation into a public demo that anyone can try with a shared account. Give
the demo its own server or Docker stack, never your real site: `demo_reset` replaces the database, the uploaded files
and the published site.

What changes in demo mode:

- The login page shows the demo account, and every dashboard page shows a banner (English and Arabic): the demo resets
  every 2 hours, so visitors should not enter real personal data.
- The account is an administrator, so visitors can try pages, collections, media, menus, the CRM, forms, the inbox,
  site settings and find and replace. These actions are refused with a message instead: self-update, backups (making,
  downloading, restoring, offsite), email settings, users (create, invite, change roles, deactivate), the account's
  password and two-step sign-in, social profiles, the security check and Technting Shield, plugin changes, the Technting SEO
  refresh, the external link check and the CRM import.
- No email leaves the server: messages go to the console log, and enquiries still reach the inbox.
- No outbound HTTP: features that call other servers (webhooks, IndexNow, Shield feeds, Cloudflare and reputation
  lookups, Pwned Passwords, Technting SEO, Google Drive, S3) fail quietly. Only the site's own addresses can be reached.
- Uploads: JPEG, PNG, WebP, GIF and PDF up to 5 MB, checked by content and by extension (PDFs with scripts are
  refused), 300 MB in total until the next reset.
- Custom HTML blocks are not offered, are refused on save and are never published. Rich text is cleaned as always.
- The dashboard sends `X-Robots-Tag: noindex, nofollow`, and the published `robots.txt` disallows everything.

Add to `.env`:

```
TECHNTING_CMS_DEMO_MODE=1
TECHNTING_CMS_DEMO_USER=<demo user name>
TECHNTING_CMS_DEMO_PASSWORD=<demo password>
```

The password is public on purpose (the login page shows it), so do not use it anywhere else.

`manage.py demo_reset` builds a fresh demo in a folder next to the var folder (a new database with the demo content,
the demo account and setup marked complete, plus a published copy of the site), then puts it in place: the database is
copied into the live file in one transaction, the media folder is swapped, the published files are updated in place
(nginx never sees an empty folder), every session ends and the cache is cleared. Nothing live changes if the build
fails. The command refuses to run unless demo mode is on (`--force` overrides it; never use it on a real site), and
it works with the default SQLite database only: keep the demo on SQLite.

On a systemd install, reset every 2 hours (on even hours) with the timer; each run may take up to 10 minutes:

```bash
sudo cp deploy/technting-cms-demo-reset.service deploy/technting-cms-demo-reset.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now technting-cms-demo-reset.timer
sudo systemctl start technting-cms-demo-reset.service    # the first demo, now
sudo systemctl disable --now technting-cms-backup.timer  # a demo needs no nightly backups
```

Logs: `journalctl -u technting-cms-demo-reset`.

With Docker, add the demo override:

```bash
docker compose -f docker-compose.yml -f deploy/docker/docker-compose.demo.yml up -d --build
```

It turns demo mode on, limits the dashboard container to 768 MB, and makes the scheduler rebuild the demo when it
starts and then every 2 hours (each run is stopped after 10 minutes) while it keeps publishing scheduled posts. The
dashboard listens on `127.0.0.1:18150` and the site on `127.0.0.1:18151`, for a reverse proxy with HTTPS in front.
Reset by hand with
`docker compose -f docker-compose.yml -f deploy/docker/docker-compose.demo.yml run --rm app manage demo_reset`;
logs: `docker compose logs scheduler`.

## Troubleshooting

| Problem | Fix |
|---|---|
| "CSRF verification failed" or sign-in loops over plain http | use https, or set `TECHNTING_CMS_HTTPS=0` while you test on a network address |
| "Bad Request (400)" | add the host name to `TECHNTING_CMS_ALLOWED_HOSTS` |
| The wizard asks for a setup key | it is `TECHNTING_CMS_SETUP_TOKEN` in `.env` |
| A wizard field is read-only | the value is set in the server environment (systemd or Docker); change it there |
| Forgotten password | `manage.py changepassword <username>` on the server |
| Locked out by Technting Shield | `manage.py shield learning` |
| "TECHNTING_CMS_DB_ENGINE=mysql needs ..." at start | set the missing `TECHNTING_CMS_DB_*` values in `.env` |
| "Error loading MySQLdb module" | install the driver: `pip install -r requirements-mysql.txt` (see [Database](#database)) |
| Backup fails with "mysqldump was not found" or "pg_dump was not found" | install `mariadb-client` or `postgresql-client` |
