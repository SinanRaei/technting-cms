"""Invitations: signed, time-limited, single-use links where a new user sets their own password.

The token signs the user id and a fingerprint of the current password hash. Setting a password
changes the hash, so the link stops working after one use; the signature carries its own expiry.
"""
import hashlib
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import timezone

SALT = "technting_cms.invite"


def _fingerprint(user):
    return hashlib.sha256((user.password or "").encode()).hexdigest()[:16]


def make_token(user):
    return signing.dumps({"u": user.pk, "f": _fingerprint(user)}, salt=SALT, compress=True)


def check_token(token, days):
    try:
        data = signing.loads(token, salt=SALT, max_age=timedelta(days=days))
    except signing.BadSignature:  # includes SignatureExpired
        return None
    user = get_user_model().objects.filter(pk=data.get("u"), is_active=True).first()
    if user is None or data.get("f") != _fingerprint(user):
        return None
    return user


def invite_url(user):
    host = (settings.CSRF_TRUSTED_ORIGINS or [settings.TECHNTING_CMS_ADMIN_URL])[0].rstrip("/")
    return f"{host}/invite/{make_token(user)}/"


def build_email(user, url, days, full_name="", invited_by=""):
    expires = timezone.localtime() + timedelta(days=days)
    ctx = {"user": user, "url": url, "days": days, "host": settings.TECHNTING_CMS_ADMIN_URL, "full_name": full_name or user.get_username(), "invited_by": invited_by,
           "expires_en": expires.strftime("%d %B %Y"), "expires_iso": expires.strftime("%Y-%m-%d"),
           "role_en": "Administrator" if user.is_superuser else "Editor", "role_ar": "مدير" if user.is_superuser else "محرّر"}
    text = render_to_string("cms/email/invite.txt", ctx)
    html = render_to_string("cms/email/invite.html", ctx)
    from . import mail
    msg = EmailMultiAlternatives(subject="Your Technting CMS account · دعوة إلى لوحة تحكم Technting", body=text,
                                 from_email=mail.sender(), to=[user.email], connection=mail.connection())
    msg.attach_alternative(html, "text/html")
    return msg
