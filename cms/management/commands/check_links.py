"""Check the external links on published pages and articles now (normally monthly, from publish_due)."""
from django.core.management.base import BaseCommand

from cms import linkcheck


class Command(BaseCommand):
    help = "Check external links on published content."

    def handle(self, *args, **o):
        data = linkcheck.run()
        if not data:
            self.stdout.write("A check is already running.")
            return
        for i in data["items"]:
            if i["verdict"] != "ok":
                self.stdout.write(f"{i['verdict']:11} {i.get('status')} {i['url']}  <- {', '.join(i['where'][:3])}")
        self.stdout.write(self.style.SUCCESS(f"{data['count']} external links checked"))
