"""Technting Backup from the command line (the same work the 5-minute timer and the Backups page do).

  python manage.py offsite_backup --status
  python manage.py offsite_backup --upload            copy the newest local backup offsite now
  python manage.py offsite_backup --verify            compare every copy in the bucket with its index
  python manage.py offsite_backup --prune             delete copies outside the retention plan now
  python manage.py offsite_backup --restore-test      download, decrypt and open the newest copy in a throwaway folder
  python manage.py offsite_backup --fetch [NAME] --dest DIR
        download and decrypt a copy into DIR; then `manage.py restore_backup DIR --yes` puts it back
"""
from django.core.management.base import BaseCommand, CommandError

from cms import offsite


class Command(BaseCommand):
    help = "Upload, check, test-restore or download encrypted offsite backups."

    def add_arguments(self, parser):
        parser.add_argument("--status", action="store_true")
        parser.add_argument("--upload", action="store_true")
        parser.add_argument("--verify", action="store_true")
        parser.add_argument("--prune", action="store_true")
        parser.add_argument("--restore-test", action="store_true")
        parser.add_argument("--fetch", nargs="?", const="", default=None, metavar="NAME")
        parser.add_argument("--dest")

    def handle(self, *args, **o):
        if not offsite.ready():
            raise CommandError("Offsite backups are not set up (Settings → Backups → Offsite settings).")
        if o["upload"]:
            self.stdout.write(offsite.sync(force=True))
        if o["verify"]:
            v = offsite.verify()
            self.stdout.write(f"integrity check: {'OK' if v['ok'] else 'FAILED'} ({v['checked']} copies) {v['detail']}")
        if o["prune"]:
            removed = offsite.prune()
            ret = offsite.state().get("retention") or {}
            self.stdout.write(f"retention: removed {len(removed)}, locked {len(ret.get('blocked') or [])} {ret.get('error', '')}")
        if o["restore_test"]:
            r = offsite.restore_test()
            self.stdout.write(f"restore test of {r['name']}: {'OK' if r['ok'] else 'FAILED'} {r['detail']}")
        if o["fetch"] is not None:
            if not o["dest"]:
                raise CommandError("Add --dest DIR (an empty folder outside the backups folder).")
            try:
                out = offsite.fetch(o["fetch"] or None, o["dest"])
            except Exception as exc:
                raise CommandError(str(exc)) from None
            self.stdout.write(f"Downloaded and decrypted {out['name']} into {out['folder']}. "
                              f"To put it back: manage.py restore_backup {out['folder']} --yes")
        if o["status"] or not any(o[k] for k in ("upload", "verify", "prune", "restore_test")) and o["fetch"] is None:
            s = offsite.status()
            self.stdout.write(f"{s['provider']} {s['cfg'].get('bucket')}/{offsite.prefix()}  copies: {s['remote'].get('count', 0)}"
                              f"  newest: {s['remote'].get('newest') or '-'}")
            for p in offsite.problems():
                self.stdout.write(f"  [{p['level']}] {p['text']} {p['detail']}")
