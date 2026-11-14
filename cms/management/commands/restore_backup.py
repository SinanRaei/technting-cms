"""Restore a Technting CMS backup made by `manage.py backup`.

  python manage.py restore_backup /home/technting/backups/technting-cms/technting-cms-YYYYmmdd-HHMMSS --yes

Stop the service first (sudo systemctl stop technting-cms). The current database and media are moved aside
(…-before-restore-<stamp>) so the restore itself can be undone. With MySQL / MariaDB or PostgreSQL the current
database is first dumped to VAR_DIR/database-before-restore-<stamp>.sql.gz, then the backup's dump is loaded with
mysql or psql (cms/dbdump.py). A backup is restored into the same kind of database it was made from.
Run `manage.py publish` afterwards.
"""
import hashlib
import json
import shutil
import tarfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from cms import dbdump
from .backup import archives


class Command(BaseCommand):
    help = "Restore the database and media from a backup folder."

    def add_arguments(self, parser):
        parser.add_argument("folder")
        parser.add_argument("--yes", action="store_true", help="Confirm that you want to replace the current data")

    def handle(self, *args, **opts):
        src = Path(opts["folder"])
        manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
        listed = archives(manifest)
        if [k for _, k in listed][:2] != ["database", "media"]:
            raise CommandError("The manifest does not list the database and media; the backup is damaged.")
        for name, key in listed:
            digest = hashlib.sha256((src / name).read_bytes()).hexdigest()
            if digest != manifest[key]["sha256"]:
                raise CommandError(f"{name} does not match its checksum; the backup is damaged.")
        made_from, engine = dbdump.manifest_engine(manifest), dbdump.engine()
        if made_from != engine:
            raise CommandError(f"This backup holds a {made_from} database and this site uses {engine}. Restore it on a "
                               f"site with TECHNTING_CMS_DB_ENGINE={made_from}, or move the content with dumpdata / loaddata.")
        if not opts["yes"]:
            raise CommandError("Add --yes to replace the current database and media.")
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        media = Path(settings.MEDIA_ROOT)
        db_file = src / dbdump.manifest_file(manifest)
        try:
            if engine == "sqlite":
                db = Path(settings.DATABASES["default"]["NAME"])
                for p in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm")):
                    if p.exists():
                        p.rename(p.with_name(p.name + f".before-restore-{stamp}"))
            else:
                dbdump.check_dump(db_file, engine)
                aside = Path(settings.VAR_DIR) / f"database-before-restore-{stamp}"
                aside.mkdir()
                dbdump.dump(aside)
                self.stdout.write(f"Current database saved to {aside / dbdump.DUMP_FILE}.")
        except dbdump.DumpError as exc:
            raise CommandError(f"{exc}. Nothing was changed.") from None
        if engine == "sqlite":
            shutil.copyfile(db_file, db)
        else:
            try:
                dbdump.load(db_file)
            except dbdump.DumpError as exc:
                raise CommandError(f"Loading the database failed: {exc}. The media folder was not changed; "
                                   f"the database from before is in {aside}.") from None
        if media.exists():
            media.rename(media.with_name(media.name + f"-before-restore-{stamp}"))
        media.mkdir(parents=True)
        with tarfile.open(src / "media.tar.gz", "r:gz") as tar:
            tar.extractall(media, filter="data")
        self.stdout.write(self.style.SUCCESS(f"Restored {src.name}. Previous data kept with suffix before-restore-{stamp}. Now run: manage.py publish"))
