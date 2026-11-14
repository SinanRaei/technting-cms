"""Back up the Technting CMS database and uploaded media.

  python manage.py backup [--dest DIR] [--keep 14]

Writes DEST/technting-cms-YYYYmmdd-HHMMSS/ with:
  technting_cms.sqlite3   SQLite: consistent snapshot via SQLite's online backup API (safe while the site runs)
  database.sql.gz         MySQL / MariaDB or PostgreSQL: mysqldump / pg_dump in one transaction (cms/dbdump.py)
  media.tar.gz     uploaded files (images, videos, PDFs and their WebP variants)
  manifest.json    sizes, counts and SHA-256 of every file
and deletes snapshots older than the newest KEEP.
"""
import hashlib
import json
import shutil
import tarfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from cms import dbdump

# (file name, manifest key) of every archive a backup can hold; the database is one of the two names, by engine.
# Readers use archives() so a later archive can be added without breaking older backups.
ARCHIVES = ((dbdump.SQLITE_FILE, "database"), (dbdump.DUMP_FILE, "database"), ("media.tar.gz", "media"))


def archives(manifest):
    """The (file, key) pairs this backup's manifest lists, older backups included."""
    db_file = dbdump.manifest_file(manifest)
    return [(name, key) for name, key in ARCHIVES if key in manifest and (key != "database" or name == db_file)]


def tar_folder(root, out):
    """Write every file under root into out (gzip). Returns the number of files."""
    files = 0
    with tarfile.open(out, "w:gz") as tar:
        if root.exists():
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    tar.add(f, arcname=f.relative_to(root).as_posix())
                    files += 1
    return files


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Command(BaseCommand):
    help = "Snapshot the database and media into a dated backup folder and prune old ones."

    def add_arguments(self, parser):
        parser.add_argument("--dest", default=str(Path(settings.VAR_DIR).parent / "backups" / "technting-cms"))
        parser.add_argument("--keep", type=int, default=14)

    def handle(self, *args, **opts):
        from cms.models import Setting
        from cms.plugins import do_action
        try:
            self.backup(opts)
        except (Exception, SystemExit) as exc:  # remembered for the Backups page and alerts, then re-raised
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
            Setting.objects.update_or_create(key="backup_failed", defaults={"value": {"at": timezone.now().isoformat(), "error": error}})
            do_action("backup_failed", error=error)
            raise

    def backup(self, opts):
        dest_root = Path(opts["dest"])
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        out = dest_root / f"technting-cms-{stamp}"
        out.mkdir(parents=True, exist_ok=False)
        out.chmod(0o700)

        from cms.models import Entry, Page
        counts = {"pages": Page.objects.count(), "entries": Entry.objects.count()}  # checked by the restore test
        try:
            database = dbdump.dump(out)
        except dbdump.DumpError as exc:
            raise SystemExit(str(exc)) from None
        db_out = out / database["file"]

        media_out = out / "media.tar.gz"
        files = tar_folder(Path(settings.MEDIA_ROOT), media_out)

        manifest = {"created": timezone.now().isoformat(),
                    "database": {**database, **counts, "bytes": db_out.stat().st_size, "sha256": sha256(db_out)},
                    "media": {"files": files, "bytes": media_out.stat().st_size, "sha256": sha256(media_out)}}
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

        snapshots = sorted(p for p in dest_root.glob("technting-cms-*") if p.is_dir())
        removed = 0
        for old in snapshots[:-opts["keep"]] if opts["keep"] > 0 else []:
            shutil.rmtree(old)
            removed += 1
        self.stdout.write(self.style.SUCCESS(
            f"Backup {out.name}: {database['engine']} database {manifest['database']['bytes']} bytes, {files} media files; removed {removed} old snapshot(s)."))
