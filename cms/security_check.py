"""Security overview (in the spirit of Wordfence and Solid Security): accounts, sign-in attempts, the public site's
security headers and certificates, and backups. It only reports; changes stay with an administrator or developer."""
import socket
import ssl
import urllib.request
from datetime import datetime, timedelta, timezone as dt_tz
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Count, Max
from django.utils import timezone

HEADERS = [
    ("strict-transport-security", "HSTS", "Browsers always use HTTPS for the site, even if someone types http://."),
    ("x-content-type-options", "X-Content-Type-Options", "Stops browsers from guessing file types, which blocks some attacks."),
    ("x-frame-options", "X-Frame-Options", "Stops other sites from showing our pages inside a frame (clickjacking)."),
    ("referrer-policy", "Referrer-Policy", "Limits how much of our addresses is shared with other sites."),
    ("content-security-policy", "Content-Security-Policy", "Lists the places scripts may load from; the strongest defence against injected scripts."),
    ("permissions-policy", "Permissions-Policy", "Turns off browser features the site does not use, such as the camera."),
]
UA = "Mozilla/5.0 (Technting-CMS security check)"


def _headers(url):
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as r:
        return {k.lower(): v for k, v in r.headers.items()}


def _cert_days(host):
    ctx = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=8) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as s:
            not_after = s.getpeercert()["notAfter"]
    end = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt_tz.utc)
    return (end - datetime.now(dt_tz.utc)).days


def public_checks(force=False):
    """Headers and certificates of the public site and the dashboard. Cached for 6 hours."""
    data = None if force else cache.get("security-public")
    if data:
        return data
    data = {"checked_at": timezone.now().isoformat(), "sites": []}
    for label, url in (("example.com", settings.TECHNTING_CMS_SITE_URL + "/"), ("Dashboard", settings.TECHNTING_CMS_ADMIN_URL + "/login/")):
        site = {"label": label, "url": url, "headers": [], "error": ""}
        try:
            h = _headers(url)
            csp = h.get("content-security-policy", "")
            for key, name, why in HEADERS:
                ok = key in h or (key == "x-frame-options" and "frame-ancestors" in csp)
                site["headers"].append({"name": name, "ok": ok, "why": why, "value": h.get(key, "")[:120]})
        except Exception as exc:
            site["error"] = type(exc).__name__
        try:
            site["cert_days"] = _cert_days(urlparse(url).hostname)
        except Exception:
            site["cert_days"] = None
        data["sites"].append(site)
    cache.set("security-public", data, 6 * 3600)
    return data


def accounts():
    from .models import Setting, UserSecurity
    from .roles import role_of
    User = get_user_model()
    two_fa = set(UserSecurity.objects.filter(enabled=True).values_list("user_id", flat=True))
    now = timezone.now()
    rows = []
    from django.db.models import Q
    for u in User.objects.filter(is_active=True).filter(Q(is_staff=True) | Q(is_superuser=True)).order_by("username"):
        idle = (now - u.last_login).days if u.last_login else None
        rows.append({"id": u.pk, "username": u.get_username(), "name": u.get_full_name(), "role": role_of(u),
                     "admin": u.is_superuser, "two_fa": u.pk in two_fa, "last_login": u.last_login, "idle_days": idle})
    required = bool(Setting.objects.filter(key="require_2fa").values_list("value", flat=True).first())
    return rows, required


def sign_ins(days=30):
    from .models import AuditEvent
    since = timezone.now() - timedelta(days=days)
    failed = AuditEvent.objects.filter(action="login_failed", created_at__gte=since)
    by_ip = list(failed.values("ip").annotate(n=Count("id"), last=Max("created_at")).order_by("-n")[:10])
    by_user = list(failed.values("username").annotate(n=Count("id"), last=Max("created_at")).order_by("-n")[:10])
    ok = AuditEvent.objects.filter(action="login", created_at__gte=since).count()
    return {"failed": failed.count(), "ok": ok, "by_ip": by_ip, "by_user": by_user}


def backup_age_hours():
    root = Path(settings.VAR_DIR).parent / "backups" / "technting-cms"
    snaps = sorted(root.glob("technting-cms-*")) if root.exists() else []
    if not snaps:
        return None
    return round((datetime.now().timestamp() - snaps[-1].stat().st_mtime) / 3600)


def findings(rows, required, public, logins, backup_hours):
    """Ordered list of {level: high|medium|low|ok, text, detail} for the summary."""
    out = []
    admins_without = [r["username"] for r in rows if r["admin"] and not r["two_fa"]]
    others_without = [r["username"] for r in rows if not r["admin"] and not r["two_fa"]]
    if admins_without:
        out.append({"level": "high", "text": "Administrators without two-step verification", "detail": ", ".join(admins_without)})
    if others_without:
        out.append({"level": "medium", "text": "Users without two-step verification", "detail": ", ".join(others_without)})
    if not required:
        out.append({"level": "medium", "text": "Two-step verification is not required for everyone (Settings)", "detail": ""})
    idle = [r["username"] for r in rows if r["idle_days"] is not None and r["idle_days"] > 90]
    if idle:
        out.append({"level": "low", "text": "Accounts not used for more than 90 days: consider turning them off", "detail": ", ".join(idle)})
    if logins["failed"] >= 20:
        out.append({"level": "medium", "text": "Many failed sign-ins in the last 30 days", "detail": str(logins["failed"])})
    for s in public["sites"]:
        missing = [h["name"] for h in s["headers"] if not h["ok"]]
        if s.get("error"):
            out.append({"level": "medium", "text": "Could not check the site", "detail": f"{s['label']}: {s['error']}"})
        elif missing:
            level = "medium" if any(m in ("HSTS", "X-Content-Type-Options", "X-Frame-Options") for m in missing) else "low"
            out.append({"level": level, "text": "Security headers missing", "detail": f"{s['label']}: {', '.join(missing)}"})
        if s.get("cert_days") is not None and s["cert_days"] < 14:
            out.append({"level": "high", "text": "Certificate expires soon", "detail": f"{s['label']}: {s['cert_days']}"})
    if backup_hours is None:
        out.append({"level": "high", "text": "No backup found", "detail": ""})
    elif backup_hours > 48:
        out.append({"level": "high", "text": "The last backup is more than two days old", "detail": f"{backup_hours} h"})
    from . import offsite
    if offsite.enabled():
        out += [{k: p[k] for k in ("level", "text", "detail")} for p in offsite.problems(include_local=False)]
    else:
        out.append({"level": "medium", "text": "Backups are kept only on the server (turn on Technting Backup)", "detail": ""})
    if settings.DEBUG:
        out.append({"level": "high", "text": "Debug mode is on", "detail": ""})
    if not out:
        out.append({"level": "ok", "text": "No problems found", "detail": ""})
    return out
