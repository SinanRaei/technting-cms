from django.core.management.base import BaseCommand

from formbuilder.retention import prune


class Command(BaseCommand):
    help = "Delete form answers past their retention period and unfinished drafts past their draft period."

    def handle(self, *args, **opts):
        done, drafts = prune()
        self.stdout.write(f"forms: removed {done} answers past retention and {drafts} old drafts")
