"""Sign-in protection through Django's auth signals: lockouts, blocked user names, password-guessing alerts,
new-device and new-country alerts. Nothing here may stop a sign-in because of an error."""
import hashlib
import logging
import secrets

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.cache import cache
from django.dispatch import receiver
from django.utils import timezone

from . import conf, events

log = logging.getLogger(__name__)
GUESS_LIMIT = 20          # wrong passwords for one user name within an hour, from any number of addresses


def _ip(request):
    from .firewall import client_ip
    return getattr(request, "shield_ip", None) or client_ip(request)


@receiver(user_login_failed)
def login_failed(sender, credentials=None, request=None, **kwargs):
    if request is None or not conf.enabled():
        return
    try:
        _login_failed(request, str((credentials or {}).get("username", ""))[:150])
    except Exception:
        log.exception("shield: login_failed hook")


def _login_failed(request, username):
    from django.contrib.auth import get_user_model

    from .netset import is_public
    ip = _ip(request)
    events.record("login_failed", kind="login", severity="low", ip=ip, request=request, username=username)
    if not is_public(ip) or events.allowed(ip):
        return
    protect = conf.protect()
    real_user = get_user_model().objects.filter(username=username, is_active=True).exists() if username else False
    if username.lower() in conf.words("blocked_usernames") and not real_user:
        events.record("bad_username", kind="login", severity="high", action="blocked" if protect else "logged", ip=ip,
                      request=request, username=username)
        if protect:
            events.block_ip(events.bucket(ip), f"Sign-in as \"{username}\"", conf.number("lockout_minutes"))
            return
    key = f"shield-lf:{events.bucket(ip)}"
    n = cache.get(key, 0) + 1
    cache.set(key, n, 900)
    if n >= conf.number("login_attempts"):
        cache.delete(key)
        events.record("lockout", kind="login", severity="medium", action="blocked" if protect else "logged", ip=ip,
                      request=request, username=username, detail=f"{n} wrong passwords in 15 minutes")
        if protect:
            events.block_ip(events.bucket(ip), f"{n} wrong passwords", conf.number("lockout_minutes"))
    from . import reputation
    rep = reputation.check(ip)
    if rep and rep["score"] >= conf.number("abuseipdb_block_score"):
        events.record("reputation", kind="login", severity="high", action="blocked" if protect else "logged", ip=ip,
                      request=request, username=username, detail=f"AbuseIPDB {rep['score']}% · {rep.get('isp', '')}")
        if protect:
            events.block_ip(ip, f"AbuseIPDB {rep['score']}%", 24 * 60)
    # someone guessing one real account's password from many addresses
    if real_user and get_user_model().objects.filter(username=username, is_staff=True).exists():
        gkey = f"shield-guess:{username.lower()}"
        g = cache.get(gkey, 0) + 1
        cache.set(gkey, g, 3600)
        if g == GUESS_LIMIT:
            events.record("guessing", kind="login", severity="high", action="alert", ip=ip, request=request, username=username,
                          detail=f"{g} wrong passwords in an hour")
            from . import alerts
            alerts.send_admins("guessing", detail=username)


@receiver(user_logged_in)
def logged_in(sender, request=None, user=None, **kwargs):
    if request is None or user is None or not conf.enabled():
        return
    try:
        _logged_in(request, user)
    except Exception:
        log.exception("shield: logged_in hook")


def _logged_in(request, user):
    from .firewall import DEVICE_COOKIE
    from .models import KnownDevice
    ip = _ip(request)
    from .firewall import country as cf_country
    country = cf_country(request)
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:300]
    request.session["shield"] = {"ip": ip, "country": country, "ua": ua, "at": timezone.now().isoformat()}
    token = request.COOKIES.get(DEVICE_COOKIE, "")
    device = hashlib.sha256(token.encode()).hexdigest() if token else ""
    known = KnownDevice.objects.filter(user=user)
    seen_countries = set(known.values_list("country", flat=True))
    first_ever = not seen_countries
    row = known.filter(device=device).first() if device else None
    if row is None:
        token = secrets.token_urlsafe(32)
        request._shield_device_token = token
        row = KnownDevice.objects.create(user=user, device=hashlib.sha256(token.encode()).hexdigest(), country=country, ip=ip,
                                         user_agent=ua)
        new_device = True
    else:
        new_device = False
    new_country = bool(country) and country not in ("XX", "T1") and country not in seen_countries
    KnownDevice.objects.filter(pk=row.pk).update(last_seen=timezone.now(), ip=ip, country=country or row.country)
    events.record("login", kind="login", severity="info", action="logged", ip=ip, request=request, username=user.get_username())
    if first_ever:
        return
    rule = "new_country" if new_country else "new_device" if new_device else None
    if rule:
        detail = f"{country or '-'} · {ip}"
        events.record(rule, kind="login", severity="high" if new_country else "medium", action="alert", ip=ip, request=request,
                      username=user.get_username(), detail=detail)
        from . import alerts
        alerts.send_user(user, rule, detail=detail, ua=ua)
