# Deploying Technting CMS

The quickest way is the installer in the repository root: `sudo bash install.sh --nginx` on Ubuntu or Debian (systemd,
the units below, an nginx site, a new `.env`), or `bash install.sh --docker` for the Docker stack. It ends by printing the
setup wizard address. Full guide: `docs/INSTALL.md`. This page describes what the installer sets up, for a manual
install or a custom layout.

The files in this folder assume a Linux server with nginx and systemd, a site user `technting`, the dashboard on
`cms.example.com` and the public site on `example.com`. Replace the user, paths and domains with your own.

| Path | Purpose |
|---|---|
| `/home/technting/technting-cms` | code + `.venv` + `.env` (mode 600) |
| `/home/technting/technting-cms-var` | SQLite database (the default), uploads (`media/`), admin static files, publish manifest, `redirects.conf` |
| `/home/technting/htdocs/example.com/public` | the public site Technting CMS writes (`TECHNTING_CMS_OUTPUT_DIR`) |

Services: `technting-cms.service` (gunicorn on 127.0.0.1:18150), `technting-cms-scheduler.timer` (publishes scheduled pages
and runs periodic jobs every 5 minutes), `technting-cms-backup.timer` (nightly backup).
nginx: `cms.example.com.conf` for the dashboard host. The public site is plain static files served by your own vhost.
Docker: `docker/` holds the container entrypoint (gunicorn, the scheduler loop, a secret key on the first start), the
health check, the nginx configuration of the `web` container and its start script (used by the root `Dockerfile` and
`docker-compose.yml`), and two overrides: `docker-compose.mysql.yml` (MariaDB in its own container) and
`docker-compose.demo.yml` (public demo).

Database: SQLite in the var folder unless `TECHNTING_CMS_DB_ENGINE` is `mysql` (MySQL, MariaDB) or `postgresql`, with
`TECHNTING_CMS_DB_NAME`, `_USER`, `_PASSWORD`, `_HOST` and `_PORT` in `.env`. Create the database (`utf8mb4` for
MySQL / MariaDB) and its user first, install `requirements-mysql.txt` or `requirements-postgresql.txt` and the client
tools for backups (`mariadb-client` or `postgresql-client`); `install.sh --db mysql|postgresql` does the installing.
See `docs/INSTALL.md`, "Database".

## First install (what install.sh does)

1. Copy the code to `/home/technting/technting-cms`, create the virtual environment and install:
   `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (plus `-r requirements-mysql.txt` or
   `-r requirements-postgresql.txt` for MySQL / MariaDB or PostgreSQL).
2. Copy `.env.example` to `.env` (mode 600) and fill it in (secret key, hosts, site URL, output folder, var folder).
3. `.venv/bin/python manage.py migrate`, `.venv/bin/python manage.py collectstatic --noinput`. Then open the
   dashboard: the setup wizard creates the administrator (or run `manage.py createsuperuser`, which skips the wizard).
4. Copy the unit files to `/etc/systemd/system/`, then `sudo systemctl daemon-reload` and enable
   `technting-cms.service`, `technting-cms-scheduler.timer`, `technting-cms-backup.timer` and (optional)
   `technting-cms-redirects.path`.
5. Install the nginx file with your certificate paths and reload nginx.

Update the code: upload a new tree, then `.venv/bin/pip install -r requirements.txt`, `python manage.py migrate`,
`python manage.py collectstatic --noinput`, `sudo systemctl restart technting-cms`.

Create or reset an editor's password (run it yourself so nobody else sees it):
`sudo -u technting /home/technting/technting-cms/.venv/bin/python /home/technting/technting-cms/manage.py changepassword <username>`

## Forms, email and redirects
- Contact form: let nginx on the public site send `/api/contact` to Technting CMS (Host = the dashboard host). Enquiries are
  stored in the dashboard Inbox.
- Email copies: `sudo bash /home/technting/technting-cms/deploy/setup_gmail_smtp.sh` (asks for the Gmail address and app
  password, tests the login, writes TECHNTING_CMS_SMTP_* into .env, restarts Technting CMS). Any SMTP server works; you can
  also set it in the dashboard under Settings → Email.
- Redirects: the dashboard writes `/home/technting/technting-cms-var/redirects.conf`; include it in the public site vhost.
  `technting-cms-redirects.path` tests and reloads nginx when it changes.
- Blog: page key `blog` (created as a draft by `manage.py create_blog_page`); posts are the `post` collection at
  /blog/<key>/; the RSS feed is generated only while the blog page is published.

## Backups
`technting-cms-backup.timer` runs `manage.py backup --keep 14` every night at about 02:30 server time. Snapshots go to
`/home/technting/backups/technting-cms/technting-cms-YYYYmmdd-HHMMSS/` (the database: `technting_cms.sqlite3` via
SQLite's backup API, or `database.sql.gz` from `mysqldump --single-transaction` / `pg_dump` with MySQL, MariaDB or
PostgreSQL; media.tar.gz; manifest.json with SHA-256). Offsite copies (Technting Backup) carry the same files.
Restore: `sudo systemctl stop technting-cms`, then
`sudo -u technting .venv/bin/python manage.py restore_backup <folder> --yes`, then `manage.py publish` and
`sudo systemctl start technting-cms`. The previous database and media are kept with the suffix `before-restore-<stamp>`
(MySQL / MariaDB and PostgreSQL: a dump in `technting-cms-var/database-before-restore-<stamp>/`).
Backups live on the same server: turn on Technting Backup or copy them off the server regularly.

## Technting Shield (security plugin)

Code lives in `shield/` (an app; the plugin folder `plugins/technting-shield` only switches it on). After `migrate`, an
administrator turns it on in Plugins; it starts in learning mode (logs, blocks nothing). Its jobs run inside
`publish_due` (threat lists daily, Tor every 6 h, packages daily, files hourly, certificates twice a day).

File check: after Settings → Updates installs a version, Technting Shield compares the code with that exact commit
(from the updater's copy of the repository), so updates need nothing extra. After a manual upload instead, run
`python manage.py shield accept-files` on the server (or upload a `code-manifest.json` made with
`python manage.py shield manifest` in the Git checkout); otherwise the upload shows as changed files.

Locked out? `python manage.py shield learning` (stop blocking) or `python manage.py shield unblock <address>`.
`python manage.py shield status` shows the lists and blocks; `shield run [feeds|osv|integrity|ct]` runs a job now.

## Updates (Settings → Updates)

By default the updater installs the published releases: the feed on technting.com (`TECHNTING_CMS_UPDATE_FEED`) names
the newest version and gives a five-minute HTTPS link to its zip, which must hold exactly that version. With
`TECHNTING_CMS_UPDATE_REMOTE` set in `.env` (or once `technting-cms-src.git` exists next to the code), it updates from
Git main instead: a bare clone read with a read-only deploy key under the ssh alias `github-technting-cms`. The updater restarts
gunicorn through systemd, so it does not apply to Docker (rebuild the containers instead).
