"""Create (or re-invite) a dashboard user and send a 10-day invitation link.

  python manage.py invite_user jane --email jane@example.com --name "Jane Doe" --role admin [--eml-dir DIR]

Sends the email when SMTP is configured (TECHNTING_CMS_SMTP_*). Otherwise, or with --eml-dir, writes a ready-to-send
.eml draft (opens as a new message in Outlook) and prints the link. The account has no usable password
until the user sets one through the link.
"""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from cms.invites import build_email, invite_url
from cms.views import INVITE_DAYS


class Command(BaseCommand):
    help = "Create a dashboard user and email them a 10-day invitation link."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", default="")
        parser.add_argument("--role", choices=["admin", "editor", "author"], default="editor")
        parser.add_argument("--eml-dir", default="")
        parser.add_argument("--invited-by", default="")

    def handle(self, *args, **o):
        U = get_user_model()
        user, created = U.objects.get_or_create(username=o["username"], defaults={"email": o["email"]})
        if not created and user.has_usable_password() and user.last_login:
            raise CommandError("This user already signed in. Use password_link to reset instead.")
        first, _, last = o["name"].partition(" ")
        user.email, user.first_name, user.last_name = o["email"], first, last
        user.is_active = True
        user.set_unusable_password()
        user.save()
        from cms.roles import set_role
        set_role(user, o["role"])
        url = invite_url(user)
        msg = build_email(user, url, INVITE_DAYS, full_name=o["name"], invited_by=o["invited_by"])
        from cms import mail
        if mail.ready() and not o["eml_dir"]:
            msg.send()
            self.stdout.write(self.style.SUCCESS(f"Invitation emailed to {user.email}."))
        else:
            folder = Path(o["eml_dir"] or Path(settings.VAR_DIR) / "invitations")
            folder.mkdir(parents=True, exist_ok=True)
            m = msg.message()
            m["X-Unsent"] = "1"  # Outlook opens it as a draft ready to send
            path = folder / f"invite-{user.username}.eml"
            path.write_bytes(m.as_bytes())
            self.stdout.write(self.style.WARNING(f"SMTP is not configured: draft written to {path}"))
        self.stdout.write(f"{'created' if created else 'updated'} {user.username} ({'admin' if user.is_superuser else 'editor'})")
        self.stdout.write(url)
