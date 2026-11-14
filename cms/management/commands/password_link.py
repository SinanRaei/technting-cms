"""Print a one-time link where a user sets their own dashboard password (valid 1 hour, single use)."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.management.base import BaseCommand, CommandError
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class Command(BaseCommand):
    help = "Create a one-time password setup link for a dashboard user."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **opts):
        user = get_user_model().objects.filter(username=opts["username"], is_active=True).first()
        if not user:
            raise CommandError("No active user with that username.")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        host = (settings.CSRF_TRUSTED_ORIGINS or [settings.TECHNTING_CMS_ADMIN_URL])[0].rstrip("/")
        self.stdout.write(f"{host}/set-password/{uid}/{token}/")
