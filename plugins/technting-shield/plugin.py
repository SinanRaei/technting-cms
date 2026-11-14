"""Technting Shield. The work happens in the `shield` app: the firewall middleware, sign-in signals, the password
validator and the periodic jobs (publish_due) all check that this plugin is enabled, so turning it off in Plugins
turns all of it off. The public pages get one file from it: /.well-known/security.txt, when a contact is set."""
from datetime import timedelta


def register(api):
    from shield import conf
    conf.reset()  # pick up new settings at once after Plugins → Save

    def security_txt(target, ctx=None, **_):
        """RFC 9116: tells security researchers how to report a problem. Rewritten at every publish, so the
        Expires date (one year ahead) never runs out while the site is maintained."""
        from django.conf import settings
        from django.utils import timezone
        contact = (api.setting("security_contact") or "").strip()
        if not contact:
            return
        if "@" in contact and not contact.startswith("mailto:"):
            contact = "mailto:" + contact
        expires = (timezone.now() + timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z")
        site = settings.TECHNTING_CMS_SITE_URL
        body = (f"Contact: {contact}\nExpires: {expires}\nPreferred-Languages: en, ar\n"
                f"Canonical: {site}/.well-known/security.txt\n")
        (target / ".well-known").mkdir(parents=True, exist_ok=True)
        (target / ".well-known" / "security.txt").write_text(body, encoding="utf-8")
    api.add_action("publish_build", security_txt)
