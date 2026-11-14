"""Outgoing email for Technting CMS.

The SMTP account is configured in the dashboard (Settings → Email) and stored in the
Setting "smtp"; the password is encrypted with a key derived from TECHNTING_CMS_SECRET_KEY, so a
copy of the database alone does not reveal it. TECHNTING_CMS_SMTP_* in .env still works as a fallback.
"""
import base64
import hashlib
import smtplib
import ssl

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.smtp import EmailBackend

PRESETS = {
    "gmail": {"host": "smtp.gmail.com", "port": 465, "security": "ssl"},
}


def _fernet():
    key = hashlib.sha256(("technting-cms-smtp:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(secret):
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError, AttributeError):
        return ""


def config():
    """Effective SMTP settings: dashboard first, then .env."""
    from .models import Setting
    s = Setting.objects.filter(key="smtp").values_list("value", flat=True).first() or {}
    if s.get("username") and s.get("password"):
        return {"host": s.get("host", "smtp.gmail.com"), "port": int(s.get("port", 465)), "security": s.get("security", "ssl"),
                "username": s["username"], "password": decrypt(s["password"]), "from_name": s.get("from_name") or settings.TECHNTING_CMS_SITE_NAME,
                "source": "dashboard"}
    if settings.EMAIL_HOST and settings.EMAIL_HOST_USER:
        return {"host": settings.EMAIL_HOST, "port": settings.EMAIL_PORT, "security": "ssl" if settings.EMAIL_USE_SSL else "starttls",
                "username": settings.EMAIL_HOST_USER, "password": settings.EMAIL_HOST_PASSWORD, "from_name": settings.TECHNTING_CMS_SITE_NAME, "source": "env"}
    return None


def ready():
    c = config()
    return bool(c and c["password"])


def test_login(host, port, security, username, password):
    """Raise smtplib / OSError exceptions when the account cannot sign in."""
    if settings.TECHNTING_CMS_DEMO_MODE:
        raise RuntimeError("Email is turned off in the public demo.")
    ctx = ssl.create_default_context()
    if security == "ssl":
        with smtplib.SMTP_SSL(host, port, timeout=15, context=ctx) as s:
            s.login(username, password)
    else:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls(context=ctx)
            s.login(username, password)


def connection():
    c = config()
    if not c:
        return None
    if settings.TECHNTING_CMS_DEMO_MODE:   # public demo: the message goes to the console (or locmem in tests), never out
        from django.core.mail import get_connection
        backend = settings.EMAIL_BACKEND
        return get_connection(backend if "smtp" not in backend else "django.core.mail.backends.console.EmailBackend")
    return EmailBackend(host=c["host"], port=c["port"], username=c["username"], password=c["password"],
                        use_ssl=c["security"] == "ssl", use_tls=c["security"] == "starttls", timeout=15)


def sender():
    c = config() or {}
    return f'{c.get("from_name", settings.TECHNTING_CMS_SITE_NAME)} <{c.get("username", "hello@example.com")}>'


def send(subject, text, to, html=None, reply_to=None):
    conn = connection()
    if conn is None:
        raise RuntimeError("Email is not set up. Open Settings → Email in the dashboard.")
    msg = EmailMultiAlternatives(subject=subject, body=text, from_email=sender(), to=list(to),
                                 reply_to=list(reply_to) if reply_to else None, connection=conn)
    if html:
        msg.attach_alternative(html, "text/html")
    msg.send()
