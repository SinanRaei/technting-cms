"""Breached-password protection with the free Pwned Passwords range API (haveibeenpwned.com).

Only the first 5 characters of the password's SHA-1 hash leave the server (k-anonymity), with padding so the answer's
size reveals nothing either. No key, no rate limit, no attribution required (checked 2026-10-16). When the service
cannot be reached the password is accepted: a network problem must never stop someone from setting a password.
"""
import hashlib
import logging
import urllib.request

from django.core.exceptions import ValidationError

from . import conf

log = logging.getLogger(__name__)
API = "https://api.pwnedpasswords.com/range/"
MESSAGES = {
    "en": "This password has appeared in data breaches ({n} times), so attackers try it early. Choose a different password.",
    "ar": "ظهرت كلمة المرور هذه في تسريبات بيانات سابقة، لذلك يجرّبها المهاجمون أولاً. اختاروا كلمة مرور أخرى.",
}


def breach_count(password):
    """How often the password appears in known breaches; 0 if never; None if the service could not be asked."""
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    req = urllib.request.Request(API + prefix, headers={"User-Agent": conf.USER_AGENT, "Add-Padding": "true"})
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            body = r.read(2_000_000).decode("ascii", "replace")
    except Exception as exc:
        log.warning("Pwned Passwords not reachable: %s", type(exc).__name__)
        return None
    for line in body.splitlines():
        h, _, n = line.strip().partition(":")
        if h == suffix:
            return int(n or 0)  # padding lines have a count of 0
    return 0


def active():
    return conf.enabled() and bool(conf.opt("breached_passwords"))


class PwnedPasswordValidator:
    """Django password validator (settings.AUTH_PASSWORD_VALIDATORS): used by My account, invitations,
    password links and new users. Does nothing while Technting Shield is off."""

    def validate(self, password, user=None):
        if not password or not active():
            return
        n = breach_count(password)
        if n:
            from .firewall import ui_lang
            raise ValidationError(MESSAGES.get(ui_lang.get(), MESSAGES["en"]).format(n=f"{n:,}"), code="password_breached")

    def get_help_text(self):
        return "Your password must not appear in known data breaches."


def check_after_login(request):
    """After a successful password step: warn (and alert) when the password in use is a breached one.
    The result is remembered per stored password hash, so each password is looked up once."""
    if not active():
        return
    from django.contrib import messages
    from django.contrib.auth import get_user_model
    from django.core.cache import cache
    from django.utils import timezone

    from cms.models import Setting

    from . import alerts, events
    user = get_user_model().objects.filter(username=request.POST.get("username", "")).first()
    password = request.POST.get("password", "")
    if not user or not password or not user.check_password(password):
        return
    key = f"shield-pw:{user.pk}"
    mark = hashlib.sha256(user.password.encode()).hexdigest()[:16]
    if cache.get(key) == mark:
        return
    n = breach_count(password)
    if n is None:
        return
    cache.set(key, mark, 30 * 86400)
    flags = Setting.objects.filter(key="shield:breached").values_list("value", flat=True).first() or {}
    if n:
        flags[str(user.pk)] = timezone.now().isoformat()
        from .firewall import ui_lang
        messages.warning(request, {"ar": "كلمة المرور التي تستخدمونها ظهرت في تسريبات بيانات. غيّروها الآن من «حسابي»."}.get(
            ui_lang.get(), "The password you use has appeared in data breaches. Change it now in My account."))
        events.record("breached_password", kind="login", severity="high", action="alert", ip=getattr(request, "shield_ip", ""),
                      request=request, username=user.get_username())
        alerts.send_user(user, "breached_password")
    else:
        flags.pop(str(user.pk), None)
    Setting.objects.update_or_create(key="shield:breached", defaults={"value": flags})
