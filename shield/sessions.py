"""Signed-in sessions: list them and sign them out. Session keys are never shown; pages use a short hash instead."""
import hashlib

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.utils import timezone


def ref(key):
    return hashlib.sha256(("shield:" + key).encode()).hexdigest()[:20]


def active(user=None):
    users = {u.pk: u for u in get_user_model().objects.filter(is_staff=True)}
    rows = []
    for s in Session.objects.filter(expire_date__gt=timezone.now()):
        data = s.get_decoded()
        uid = data.get("_auth_user_id")
        u = users.get(int(uid)) if uid and str(uid).isdigit() else None
        if u is None or (user is not None and u.pk != user.pk):
            continue
        info = data.get("shield") or {}
        rows.append({"ref": ref(s.session_key), "key": s.session_key, "user": u, "ip": info.get("ip", ""), "country": info.get("country", ""),
                     "ua": info.get("ua", ""), "at": info.get("at", ""), "expires": s.expire_date})
    rows.sort(key=lambda r: r["at"], reverse=True)
    return rows


def end(ref_id):
    for r in active():
        if r["ref"] == ref_id:
            Session.objects.filter(session_key=r["key"]).delete()
            return r["user"]
    return None


def end_others(user, current_key):
    n = 0
    for r in active(user):
        if r["key"] != current_key:
            Session.objects.filter(session_key=r["key"]).delete()
            n += 1
    return n


def browser(ua):
    """A short, readable name for a user agent ("Chrome on Windows")."""
    ua = ua or ""
    name = next((b for k, b in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari")) if k in ua), "")
    system = next((s for k, s in (("Windows", "Windows"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                                  ("Mac OS X", "Mac"), ("Linux", "Linux")) if k in ua), "")
    return " · ".join(x for x in (name, system) if x) or (ua[:40] or "-")
