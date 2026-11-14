# Technting CMS

Made and maintained by **Technting** ([technting.com](https://technting.com/products/cms/)).

> **You need a free licence key to install it.** Get it at
> [technting.com/products/cms/#download](https://technting.com/products/cms/#download): give your name, e-mail and
> phone, and the key comes by e-mail with the download link. The setup wizard asks for it (one licence per website).
> Try it first in the live demo: [cms.technting.com](https://cms.technting.com/).

A bilingual (English / Arabic) website CMS built on Django. Editors work in a dashboard; the public site is published as
static files, so it is fast and has almost nothing to attack. It includes a small CRM, multi-step forms, scheduled
publishing, backups and a security plugin.

- **Content**: pages built from blocks, collections (blog posts, services, team, ...), media library with WebP variants,
  menus, redirects, find and replace, translations overview, revisions, scheduled publish / unpublish.
- **Publishing**: the theme (Jinja2) is rendered into plain files: HTML, sitemap, RSS, search index, `llms.txt`,
  robots.txt. Only changed files are written.
- **Technting CRM**: organisations, contacts, deals pipeline, tasks, website enquiries, newsletter, prospect lists.
- **Technting Forms**: multi-step forms with scores, rules, results pages, personal links and CRM capture.
- **Plugins**: Technting Shield for CMS (firewall, lockouts, threat lists, file and certificate checks), Technting Backup
  (encrypted offsite copies to R2 / B2 / S3 / Google Drive), Technting SEO (Search Console, Bing, PageSpeed),
  site stats, Google Analytics, IndexNow, site verification, webhooks, announcement bar, newsletter.
- **Dashboard roles**: administrator, editor, author (writes posts for review), sales (CRM, inbox, stats).
- **Theme**: `themes/technting`, a neutral starter theme. Copy it to make your own.
- **Database**: SQLite by default (nothing to set up), or MySQL / MariaDB or PostgreSQL for larger sites
  (`TECHNTING_CMS_DB_ENGINE`, see "Database" in [docs/INSTALL.md](docs/INSTALL.md)).

## Licence

Copyright (C) 2026 Technting (technting.com). Technting CMS is free and open source software under the GNU General
Public License, version 3 ([LICENSE](LICENSE)).
That covers everything in this repository: the core, Technting CRM, Technting Forms and every plugin in `plugins/`,
Technting Shield for CMS, Technting Backup and Technting SEO included. There are no paid tiers.

Every download from technting.com comes with a free licence key, e-mailed with the download link. The setup wizard
asks for it and checks it with licenses.technting.com, and the dashboard checks it again twice a day. Only the key, a
random id of the installation, the site address and the version are sent. One licence covers one website. Without a
valid licence the site keeps working; the dashboard shows a warning and Settings, Updates is off. If the licence
server cannot be reached, the last good check counts for 30 days.

The bundled fonts keep their own licence (SIL Open Font License, next to each font). The Technting name and logo
identify the project and are not licensed for use as your own brand: a fork or a site you build may use the code
freely, but should carry its own name and logo.

## Install

Pick one of three ways. All of them end in the same place: open the dashboard and the **setup wizard** walks you
through the rest. Step-by-step guides: [docs/INSTALL.md](docs/INSTALL.md) (English) and
[docs/INSTALL-ar.md](docs/INSTALL-ar.md) (العربية).

### 1. Docker (quickest)

Needs Docker with the compose plugin.

```bash
cd technting-cms-0.4.0        # an unpacked release, or a Git checkout
bash install.sh --docker         # or: docker compose up -d --build
```

Open <http://localhost:8000/>: the setup wizard starts. The published site is on <http://localhost:8080/>.
`install.sh --docker` writes a `.env` with a secret key and a setup key and prints the wizard address. With plain
`docker compose up`, no `.env` is needed: a secret key is generated on the first start and kept in the data volume.

Three containers run: `app` (the dashboard), `scheduler` (scheduled publishing every 5 minutes and a daily backup)
and `web` (nginx: the published site on 8080, the dashboard on 8000). For a public server, put your TLS proxy in front
of both ports and add the dashboard host name to `TECHNTING_CMS_ALLOWED_HOSTS` in `.env`.

### 2. One command on Ubuntu or Debian

Needs Python 3.12 or newer (Ubuntu 24.04 has it) and root.

```bash
cd technting-cms-0.4.0
sudo bash install.sh --nginx --dashboard-host cms.example.com --site-host example.com
```

The installer creates the system user `technting`, a virtual environment, `.env` with a new secret key, runs the
migrations and `collectstatic`, installs the systemd service and timers from `deploy/`, and (with `--nginx`) an nginx
site for both host names. It is safe to run again and asks before it replaces anything. At the end it prints the
setup wizard address. Add TLS (for example `certbot --nginx`) before you share it. `bash install.sh --help` lists the
options (user, folders, port).

### 3. Manual install

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # set the secret key, hosts and folders; see the comments in the file
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/gunicorn technting_cms.wsgi:application --bind 127.0.0.1:18150
```

Then follow `deploy/README.md` for systemd and nginx, and open the dashboard: the setup wizard starts.

## The setup wizard

On a new installation every dashboard address opens `/setup/` until it is finished. Six short steps:

1. **Site**: name and public address (for example `https://example.com`).
2. **Languages**: English, Arabic or both, and the default language (served at the site root; the other gets `/ar/` or `/en/`).
3. **Administrator**: user name, email and a password (at least 12 characters, checked like every dashboard password).
4. **Theme**: one of the themes in `themes/`.
5. **Email** (optional): an SMTP account for enquiry copies and invitations, with a *Send test email* button. Skip it
   and set it later under Settings, Email.
6. **Licence key**: the free key from the download e-mail (see Licence above). Change it later under Settings, Licence.
7. **Finish**: optionally add demo content (a home page, a privacy page and the header menu), then the administrator
   is signed in and the site is published.

The interface switches between English and Arabic at the top. When `.env` sets `TECHNTING_CMS_SETUP_TOKEN` (the
installer does), the wizard asks for that key once. After the finish `/setup/` answers 404. Existing installations
that already have users never see the wizard.

## Upgrading

- **Built-in updater** (systemd installs): Settings, Updates checks technting.com for the newest published release,
  downloads its zip over HTTPS, takes a full backup, installs the new code, runs the migrations, reloads gunicorn and
  publishes, and rolls back by itself if a step fails. To update from your own Git repository instead, set
  `TECHNTING_CMS_UPDATE_REMOTE` in `.env` (see `docs/INSTALL.md`).
- **Docker**: unpack the new release (or `git pull`) and run `docker compose up -d --build`. Migrations run when the
  `app` container starts; your data stays in the volumes. The built-in updater does not apply to containers.
- **Manual**: replace the code, then `pip install -r requirements.txt`, `manage.py migrate`,
  `manage.py collectstatic --noinput` and restart gunicorn.

## Backups

`manage.py backup --keep 14` writes a consistent database snapshot (the SQLite file, or a `mysqldump` / `pg_dump`
of MySQL, MariaDB or PostgreSQL), the uploaded media and a manifest with SHA-256 sums to `backups/technting-cms/technting-cms-<date>/` next to the var folder. The systemd timer and the Docker scheduler
run it every night; Settings, Backups lists and downloads them. Restore with
`manage.py restore_backup <folder> --yes`, then `manage.py publish`. Turn on Technting Backup to copy encrypted
backups off the server.

## Where things live

| What | systemd install (defaults) | Docker |
|---|---|---|
| Code and `.venv` | `/home/technting/technting-cms` | inside the image (`/app`) |
| Settings | `/home/technting/technting-cms/.env` (mode 600) | `.env` next to `docker-compose.yml`, `site.env` in the data volume |
| Database, uploads, cache | `/home/technting/technting-cms-var` | volume `data`, `/data/var` |
| Backups | `/home/technting/backups/technting-cms` | volume `data`, `/data/backups` |
| Published site | `/home/technting/htdocs/public` | volume `site`, `/srv/site` |
| Logs | `journalctl -u technting-cms` | `docker compose logs app` |

## Configuration

Deployment settings come from environment variables (`TECHNTING_CMS_*`, see `.env.example`): secret key, allowed
hosts, dashboard URL, var and output folders, database (`TECHNTING_CMS_DB_*`), time zone, SMTP, update remote, setup
key, demo mode. The setup wizard
writes the site name, site URL and theme into `.env` (or into `site.env` in the var folder when `.env` cannot be
written); values set in the real environment win and show read-only in the wizard. Everything else (email, leads
inbox, social profiles, plugins, backups) is set in the dashboard.

`TECHNTING_CMS_DEMO_MODE=1` turns a server into a public demo: a shared account shown on the login page, uploads limited
to images and PDF, no email, no outbound connections, no self-update, user or plugin changes, and `manage.py demo_reset`
to rebuild everything every 2 hours. See "Running a public demo" in [docs/INSTALL.md](docs/INSTALL.md).

## For developers

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
export TECHNTING_CMS_DEBUG=1 TECHNTING_CMS_VAR_DIR=./var            # PowerShell: $env:TECHNTING_CMS_DEBUG="1"
python manage.py migrate
python manage.py runserver          # http://127.0.0.1:8000/ opens the setup wizard
python manage.py test               # the whole suite
python -m http.server 8080 --directory var/public    # look at the published site
```

`python manage.py seed_demo` adds the demo content without the wizard, `python manage.py createsuperuser` creates an
administrator (which also skips the wizard).

Releases: set `__version__` in `technting_cms/__init__.py`, add a `CHANGELOG.md` entry, commit, then
`python tools/make_release.py` builds `dist/technting-cms-<version>.zip`, `.tar.gz` and `SHA256SUMS` from the commit
(tests and `tools/` are left out).

| Folder | What |
|---|---|
| `technting_cms/` | Django project (settings, urls, wsgi, version) |
| `cms/` | dashboard, pages, media, publishing, backups, updater, setup wizard, plugins loader |
| `crm/` | Technting CRM |
| `formbuilder/` | Technting Forms |
| `shield/` | Technting Shield (security) |
| `plugins/` | optional plugins (each folder has `plugin.json` and `plugin.py`) |
| `themes/technting/` | starter theme |
| `deploy/` | systemd units, nginx example, Docker helper files |
| `docs/` | install guides |
| `tools/` | release packaging |
