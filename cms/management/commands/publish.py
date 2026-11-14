from django.core.management.base import BaseCommand, CommandError

from cms.publish import publish_site


class Command(BaseCommand):
    help = "Build the public site and sync it into TECHNTING_CMS_OUTPUT_DIR (also publishes due scheduled pages)."

    def handle(self, *args, **opts):
        log = publish_site()
        if not log.ok:
            raise CommandError(log.message)
        self.stdout.write(self.style.SUCCESS(log.message))
