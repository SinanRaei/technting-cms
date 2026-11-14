"""Update Technting CMS to the newest release, or to Git main (see cms/updater.py).

  python manage.py update_site                   update (backup, files, migrate, reload, publish)
  python manage.py update_site --check           only look for and list what is new
  python manage.py update_site --mark-installed  record the installed version (first setup)
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from cms import updater


class Command(BaseCommand):
    help = "Update Technting CMS to the newest release (or Git main)."

    def add_arguments(self, parser):
        parser.add_argument("--by", default="")
        parser.add_argument("--check", action="store_true")
        parser.add_argument("--mark-installed", action="store_true")
        parser.add_argument("--no-restart", action="store_true")

    def handle(self, *args, **o):
        if o["mark_installed"] and updater.mode() == "release":
            info = updater.installed() or {}   # the version of the code on disk
            if not info.get("version"):
                self.stderr.write("No version in technting_cms/__init__.py.")
                return
            updater._write("version.json", {**info, "installed_at": timezone.now().isoformat(), "by": o["by"] or "setup"})
            self.stdout.write(f"installed {info['version']}")
            return
        if o["check"] or o["mark_installed"]:
            info = updater.fetch()
            if o["mark_installed"]:
                updater._write("version.json", {**info, "installed_at": timezone.now().isoformat(), "by": o["by"] or "setup"})
            self.stdout.write(f"latest {info['short']} {info['subject']}")
            for c in updater.pending():
                self.stdout.write(f"  new: {c['short']} {c['subject']}")
            return
        from cms import licence
        if not licence.allows_updates():
            self.stderr.write("Updates are off: " + licence.MESSAGES.get(licence.state()["status"], licence.MESSAGES["no_key"])
                              + " Add or fix the key in Settings, Licence.")
            return
        ok = updater.run_update(o["by"], restart=not o["no_restart"])
        st = updater.state()
        for s in st.get("steps", []):
            self.stdout.write(f"{s['status']:8} {s['name']} {s.get('detail', '')[:120]}")
        self.stdout.write("OK" if ok else f"FAILED ({st.get('error', '')})")
