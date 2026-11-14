"""Rebuild the public demo from scratch (TECHNTING_CMS_DEMO_MODE=1). Run it every 2 hours, see docs/INSTALL.md.

  python manage.py demo_reset           refuses unless demo mode is on
  python manage.py demo_reset --force   also outside demo mode (it replaces the database: never on a real site)

SQLite only: the public demo keeps the default database, and the command refuses on MySQL / MariaDB or PostgreSQL.

  1. build   a child process (`demo_reset --build DIR`) makes a fresh demo in a folder next to VAR_DIR: a new SQLite
             database (migrate, seed_demo, the demo account from TECHNTING_CMS_DEMO_USER / _PASSWORD, setup marked
             complete), its own media folder and a published copy of the site. Nothing live changes if this fails.
  2. database  the SQLite backup API copies the new database into the live one in a single transaction. Workers in
             the middle of a request see the old or the new data, never a mix; renaming a file over a live WAL
             database is not safe. Each request opens its own connection (CONN_MAX_AGE=0), so no worker keeps old data.
  3. media   the folder is swapped with two renames (its contents are moved instead when it is a mount point)
  4. site    changed files are copied over the published site and old ones removed (cms.publish.sync), so the folder
             nginx serves is never empty
  5. sessions are gone with the old database (everyone signs in again); the shared cache is cleared
"""
import io
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

BUILD_TIMEOUT = 480        # seconds; the systemd unit allows 600 for the whole reset
LOCK_STALE = 15 * 60
CARRY = ("redirects.conf", "health.json")       # build results that belong next to the database
FORGET = ("external_links.json",)                # results about content that is gone now


class Command(BaseCommand):
    help = "Rebuild the public demo (database, media and published site) from scratch."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="run even when TECHNTING_CMS_DEMO_MODE is off")
        parser.add_argument("--build", metavar="DIR", help="internal: build the fresh demo in DIR (child process)")

    def handle(self, *args, **o):
        if o["build"]:
            return self.build(Path(o["build"]))
        if not (settings.TECHNTING_CMS_DEMO_MODE or o["force"]):
            raise CommandError("TECHNTING_CMS_DEMO_MODE is off. This command replaces the database and the site; "
                               "use --force only on a demo server.")
        if not (settings.TECHNTING_CMS_DEMO_USER and settings.TECHNTING_CMS_DEMO_PASSWORD):
            raise CommandError("Set TECHNTING_CMS_DEMO_USER and TECHNTING_CMS_DEMO_PASSWORD (the shared demo account).")
        from cms import dbdump
        if dbdump.engine() != "sqlite":
            raise CommandError("demo_reset works only with the SQLite database (TECHNTING_CMS_DB_ENGINE=sqlite, the "
                               "default). A public demo keeps SQLite; this site uses another database, so nothing was changed.")
        var = Path(settings.VAR_DIR)
        lock = var / "demo_reset.lock"
        self.take_lock(lock)
        work = Path(tempfile.mkdtemp(prefix=f".{var.name}-demo-", dir=var.parent))
        started = time.monotonic()
        try:
            self.run_build(work)
            self.swap(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
            lock.unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS(f"Demo reset in {time.monotonic() - started:.1f}s."))

    # ---------------------------------------------------------------- 1. build (child process)
    def run_build(self, work):
        env = {**os.environ, "TECHNTING_CMS_DB_ENGINE": "sqlite",
               "TECHNTING_CMS_VAR_DIR": str(work / "var"), "TECHNTING_CMS_MEDIA_ROOT": str(work / "media"),
               "TECHNTING_CMS_OUTPUT_DIR": str(work / "public"), "TECHNTING_CMS_STATIC_ROOT": str(settings.STATIC_ROOT),
               "TECHNTING_CMS_DEMO_MODE": "1" if settings.TECHNTING_CMS_DEMO_MODE else "0",
               "TECHNTING_CMS_DEMO_USER": settings.TECHNTING_CMS_DEMO_USER,
               "TECHNTING_CMS_DEMO_PASSWORD": settings.TECHNTING_CMS_DEMO_PASSWORD,
               "TECHNTING_CMS_SITE_URL": settings.TECHNTING_CMS_SITE_URL, "TECHNTING_CMS_SITE_NAME": settings.TECHNTING_CMS_SITE_NAME,
               "TECHNTING_CMS_THEME": settings.TECHNTING_CMS_THEME}
        try:
            r = subprocess.run([sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), "demo_reset", "--build", str(work)],
                               cwd=str(settings.BASE_DIR), env=env, capture_output=True, timeout=BUILD_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise CommandError(f"Building the fresh demo took longer than {BUILD_TIMEOUT}s. Nothing was changed.")
        if r.returncode != 0:
            tail = r.stderr.decode("utf-8", "replace").strip()[-1500:]
            raise CommandError(f"Building the fresh demo failed. Nothing was changed.\n{tail}")
        self.stdout.write(r.stdout.decode("utf-8", "replace").strip())

    def build(self, work):
        """Runs inside the child process, whose VAR_DIR, MEDIA_ROOT and OUTPUT_DIR point into the work folder."""
        from django.contrib.auth import get_user_model
        from django.db import connection
        from cms import setup_wizard
        from cms.models import Setting
        from cms.publish import publish_site
        call_command("migrate", interactive=False, verbosity=0)
        call_command("seed_demo", stdout=io.StringIO())
        user = get_user_model()(username=settings.TECHNTING_CMS_DEMO_USER, is_staff=True, is_superuser=True)
        user.set_password(settings.TECHNTING_CMS_DEMO_PASSWORD)
        user.save()   # an administrator: every page can be tried, and cms/demo.py refuses what is unsafe
        Setting.objects.update_or_create(key=setup_wizard.FLAG, defaults={"value": {
            "at": timezone.now().isoformat(), "version": setup_wizard._version(), "by": "demo_reset"}})
        log = publish_site()
        if not log.ok:
            raise CommandError(f"Publishing the fresh demo failed: {log.message}")
        with connection.cursor() as c:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")   # everything in the main file before it is copied
        (work / "database.txt").write_text(str(connection.settings_dict["NAME"]), encoding="utf-8")
        connection.close()
        self.stdout.write(f"Built the fresh demo: {log.message}.")

    # ---------------------------------------------------------------- 2 to 5. swap
    def swap(self, work):
        from django.core.cache import caches
        from django.db import connection
        from cms.publish import sync
        listed = work / "database.txt"
        new_db = Path(listed.read_text(encoding="utf-8").strip()) if listed.is_file() else None
        if not (new_db and new_db.is_file() and work in new_db.parents):
            raise CommandError("The fresh demo has no database. Nothing was changed.")
        src = sqlite3.connect(str(new_db))
        try:
            connection.close()
            connection.ensure_connection()
            src.backup(connection.connection)   # one transaction on the live database
        finally:
            src.close()
            connection.close()
        self.stdout.write("Database replaced; all sessions ended.")
        swap_dir(work / "media", Path(settings.MEDIA_ROOT))
        self.stdout.write("Media folder replaced.")
        var = Path(settings.VAR_DIR)
        for name in CARRY:
            if (work / "var" / name).is_file():
                shutil.copyfile(work / "var" / name, var / (name + ".demo-tmp"))
                os.replace(var / (name + ".demo-tmp"), var / name)
        for name in FORGET:
            (var / name).unlink(missing_ok=True)
        changed, removed = sync(work / "public", Path(settings.TECHNTING_CMS_OUTPUT_DIR))
        self.stdout.write(f"Published site replaced ({changed} files updated, {removed} removed).")
        for alias in settings.CACHES:
            caches[alias].clear()   # rate limits, edit locks, import previews (the Shield counters live in each worker)

    def take_lock(self, lock):
        try:
            if time.time() - lock.stat().st_mtime > LOCK_STALE:
                lock.unlink(missing_ok=True)   # left behind by a reset that was killed
        except FileNotFoundError:
            pass
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise CommandError("Another demo reset is running.")
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)


def swap_dir(new, live):
    """Put the folder new in place of live: two renames when possible, otherwise (a mount point, another file system)
    by emptying live and moving the contents of new into it."""
    new.mkdir(parents=True, exist_ok=True)
    live.parent.mkdir(parents=True, exist_ok=True)
    old = live.with_name(f".{live.name}-old-{secrets.token_hex(4)}")
    try:
        if live.exists():
            os.rename(live, old)
        try:
            os.rename(new, live)
        except OSError:
            if old.exists() and not live.exists():
                os.rename(old, live)
            raise
    except OSError:
        live.mkdir(parents=True, exist_ok=True)
        for child in list(live.iterdir()):
            shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
        for child in list(new.iterdir()):
            shutil.move(str(child), str(live / child.name))
    finally:
        if old.exists():
            shutil.rmtree(old, ignore_errors=True)
