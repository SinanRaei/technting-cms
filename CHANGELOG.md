# Changelog

## 0.4.0 (2026-11-13)

A free licence key with every download.

- **Free licence key** (owner decision 2026-11-13): every download from technting.com comes with a free licence
  key. The setup wizard has a required Licence key step, and Settings, Licence shows and changes it. The key is
  checked with licenses.technting.com when it is entered and every 12 hours (sent: the key, a random installation
  id, the site address and the version). One licence covers one website. Without a valid licence the site keeps
  working, administrators see a red warning and Settings, Updates is off; when the licence server cannot be reached,
  the last good check counts for 30 days. The public demo needs no licence. Existing installs add their key under
  Settings, Licence.

## 0.3.1 (2026-11-12)

Updates from the dashboard for every install.

- **Upgrading from 0.3.0**: install 0.3.1 once by hand (unpack it and run `sudo bash install.sh` again, or rebuild
  the Docker containers). 0.3.0 still looks for updates in Git; from 0.3.1 on, Settings, Updates finds every new
  release by itself.
- **Updates from the published releases**: Settings, Updates now checks technting.com for the newest release
  (`TECHNTING_CMS_UPDATE_FEED`) and installs its zip with the same steps as before: full backup, new files, packages
  when `requirements.txt` changed, migrations, reload, publish, and automatic rollback if a step fails. The zip must
  hold exactly the version the feed names, with no links and no paths outside its folder. Files a release drops are
  removed by the next one, and `code-manifest.json` is written for the Shield integrity check. Only the installed
  version is sent to the feed. Git updates stay available with `TECHNTING_CMS_UPDATE_REMOTE`, which now has no default.

## 0.3.0 (2026-11-11)

Public demo mode, and MySQL / MariaDB and PostgreSQL next to SQLite.

- **Open source**: the whole repository is GPL-3.0 (`LICENSE`), the core and every plugin. Nothing is sold and there
  are no licence keys. The plugins once planned as paid are renamed: Technting Backup (was Backup Pro) and Technting
  SEO (was SEO Pro); their folders and ids stay `backup-pro` and `seo-pro`, so existing settings keep working.
- **Demo mode** (`TECHNTING_CMS_DEMO_MODE=1`, `cms/demo.py`): a shared demo account shown on the login page
  (`TECHNTING_CMS_DEMO_USER`, `TECHNTING_CMS_DEMO_PASSWORD`, empty by default) and a banner in the dashboard, in English
  and Arabic. Refused with a message: self-update, backups (making, downloading, restoring, offsite), email settings,
  users and roles, the account's password and two-step sign-in, social profiles, the security check, Technting Shield
  actions, plugin changes, the Technting SEO refresh, the external link check and the CRM import. No email is sent (console
  backend), and urllib refuses outbound HTTP except to the site's own addresses. Custom HTML blocks are hidden, refused
  on save and never published. Uploads: JPEG, PNG, WebP, GIF and PDF up to 5 MB, by content and extension.
  `X-Robots-Tag: noindex` on the dashboard and a `robots.txt` that disallows everything.
- **`manage.py demo_reset`**: builds a fresh demo next to the var folder and swaps it in (database in one SQLite
  transaction, media folder, published site updated in place), ending every session. Runs every 2 hours with
  `deploy/technting-cms-demo-reset.timer` or `deploy/docker/docker-compose.demo.yml`.
- **Uploads, always on**: file names with an executable extension (such as `.php`, `.py`, `.sh`, `.exe`, `.js`,
  `.html`, `.svg`) are refused even when the content is an image, and dots inside a file name become dashes
  (`x.php.png` is stored as `x-php.png`). The content check by file signature is unchanged.
- **MySQL / MariaDB and PostgreSQL**: `TECHNTING_CMS_DB_ENGINE` = `sqlite` (default) | `mysql` (also MariaDB) |
  `postgresql`, with `TECHNTING_CMS_DB_NAME`, `_USER`, `_PASSWORD`, `_HOST` (default 127.0.0.1) and `_PORT`
  (`technting_cms/database.py`). MySQL / MariaDB connect with `utf8mb4`, strict mode and READ COMMITTED. The dashboard
  refuses to start when the engine is unknown or a value is missing. Optional drivers in `requirements-mysql.txt`
  (mysqlclient) and `requirements-postgresql.txt` (psycopg); the Docker image has both plus the client tools.
  `install.sh --db mysql|postgresql` installs the build packages, driver and client tools and writes the connection to
  `.env` (it never creates database users or passwords). `deploy/docker/docker-compose.mysql.yml` runs MariaDB 11 in
  its own container. The setup wizard summary and Settings, Updates show the database in use.
- **Backups per engine** (`cms/dbdump.py`): MySQL / MariaDB are dumped with `mysqldump --single-transaction --routines
  --default-character-set=utf8mb4` and PostgreSQL with `pg_dump` into `database.sql.gz`, checked for the completion
  line; restores load them with `mysql` / `psql` after dumping the current database aside. Passwords go through an
  option file or `PGPASSWORD`, never the command line. The manifest records the engine; older backups are SQLite and
  still restore. Technting Backup uploads whichever database file a backup has, and its monthly restore test reads
  a dump to the end. `demo_reset` stays SQLite only and says so on other databases.
- The CMS database connection is closed after every request (`CONN_MAX_AGE=0`, now explicit).
- Text: em and en dashes removed from the interface, emails and comments ("-" for empty values, "to" for ranges).
- Documentation: "Running a public demo" and "Database" in `docs/INSTALL.md` and `docs/INSTALL-ar.md`.

## 0.2.0 (2026-11-03)

Easy installation.

- **Setup wizard**: on a new installation every dashboard address opens `/setup/`, which asks for the site name and
  address, the languages (English, Arabic or both, and the default), the first administrator, the theme, an optional
  SMTP account (with a test email) and optional demo content. It then signs the administrator in and publishes the
  site once; afterwards `/setup/` no longer exists. English and Arabic interface, CSRF protection, rate limits, and an
  optional setup key (`TECHNTING_CMS_SETUP_TOKEN`).
- **Docker**: `Dockerfile` (non-root user, gunicorn, static files collected at build time, health check) and
  `docker-compose.yml` with the dashboard, a scheduler (scheduled publishing every 5 minutes, a daily backup) and an
  nginx container that serves the published site and the dashboard. A secret key is generated on the first start.
- **One-command installer**: `install.sh` for Ubuntu and Debian: system user, virtual environment, `.env` with a new
  secret key, migrations, static files, the systemd units and timers from `deploy/`, optionally an nginx site
  (`--nginx`), or the Docker stack (`--docker`). Safe to run again.
- **Versioning and releases**: the version lives in `technting_cms/__init__.py`; `tools/make_release.py` builds
  `technting-cms-<version>.zip` and `.tar.gz` with `SHA256SUMS` from a Git commit.
- New settings: `TECHNTING_CMS_HTTPS` (secure cookies, default on), `TECHNTING_CMS_SETUP_TOKEN`,
  `TECHNTING_CMS_DEMO_MODE`, `TECHNTING_CMS_STATIC_ROOT`; the wizard writes `VAR_DIR/site.env` when `.env` cannot be
  written.
- Documentation: a new README install guide, `docs/INSTALL.md` and `docs/INSTALL-ar.md`.
- Cleanup: leftover sample data and wording from the original codebase removed (neutral example domains, phone
  numbers and places in the test data), "Lab" renamed to "Area" in the dashboard, CRM and forms, generic service codes
  (1 to 3 letters plus a number, such as W1), browser storage keys renamed to `tcms-*`.

## 0.1.0 (2026-10-29)

- Initial import.
