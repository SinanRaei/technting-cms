"""The free Technting CMS licence (owner decision 2026-11-13).

Every download from technting.com comes with a free licence key, e-mailed with the download link. The setup wizard asks
for it (step "Licence key") and Settings, Licence changes it later. One licence covers one installation.

The check: POST TECHNTING_CMS_LICENCE_URL (https://licenses.technting.com/api/v1/plugins/cms/check) with
  {"license": key, "installation_id": a UUID made once per installation, "domain": the site's host,
   "current_version": the running version}
when the key is entered and then every CHECK_HOURS (12) hours from publish_due. Answers: "active"; "inactive_installation"
(the key already runs on another website); "revoked" (403); "invalid_license" or "no_license" (401). When the server
cannot be reached, the last good answer counts for its grace_days (30).

Without a valid licence (owner decision 2026-11-13) the dashboard shows a red warning and Settings, Updates is off. The
public site and everything else keep working. The public demo needs no licence.

Stored in the Setting "licence": key, status, checked_at, last_good_at, grace_days, last_error; the installation id in
the Setting "installation". Nothing else about the site is sent.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from django.conf import settings

SETTING = "licence"
CHECK_HOURS = 12
GRACE_DAYS = 30
KEY_RE = re.compile(r"TAI1\.[A-Za-z0-9_\-=+/.]{16,4000}")
GOOD = "active"
STATUSES = {"active", "inactive_installation", "revoked", "invalid_license", "no_license"}


def url():
    return getattr(settings, "TECHNTING_CMS_LICENCE_URL", "https://licenses.technting.com/api/v1/plugins/cms/check")


def demo():
    return bool(getattr(settings, "TECHNTING_CMS_DEMO_MODE", False))


def _get(key, default=None):
    from .models import Setting
    v = Setting.objects.filter(key=key).values_list("value", flat=True).first()
    return v if isinstance(v, dict) else (default if default is not None else {})


def _put(key, value):
    from .models import Setting
    Setting.objects.update_or_create(key=key, defaults={"value": value})


def stored():
    return _get(SETTING)


def installation_id():
    """A random UUID made once per installation (the licence server counts installations with it)."""
    v = _get("installation")
    if not v.get("id"):
        v = {"id": str(uuid.uuid4()), "created": time.time()}
        _put("installation", v)
    return v["id"]


def domain(site_url=None):
    host = urllib.parse.urlparse(site_url or settings.TECHNTING_CMS_SITE_URL).hostname or ""
    return host.lower()


def clean(key):
    """The key as pasted, without spaces and line breaks (e-mail clients wrap long lines)."""
    return re.sub(r"\s+", "", str(key or ""))


def looks_valid(key):
    return bool(KEY_RE.fullmatch(clean(key)))


def _version():
    from technting_cms import __version__
    return __version__


def ask(key, site_url=None):
    """One check with the licence server. Returns {"status", "reached", "grace_days", "error"}. "status" is one of
    STATUSES when the server answered, else "unreachable"."""
    body = json.dumps({"license": clean(key), "installation_id": installation_id(), "domain": domain(site_url),
                       "current_version": _version()}).encode()
    req = urllib.request.Request(url(), data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json", "User-Agent": f"TechntingCMS/{_version()}"})
    code, data = 0, {}
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            code, raw = r.status, r.read(65536)
    except urllib.error.HTTPError as exc:
        code, raw = exc.code, exc.read(65536) if exc.fp else b""
    except (OSError, ValueError) as exc:
        return {"status": "unreachable", "reached": False, "grace_days": None, "error": type(exc).__name__}
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    status = str(data.get("status") or data.get("error") or "")
    if code == 403:
        status = "revoked"
    elif code == 401 and status not in ("invalid_license", "no_license"):
        status = "invalid_license"
    if code not in (200, 401, 403) or status not in STATUSES:
        return {"status": "unreachable", "reached": False, "grace_days": None, "error": f"HTTP {code}"}
    try:
        grace = max(0, min(365, int(data.get("grace_days", GRACE_DAYS))))
    except (TypeError, ValueError):
        grace = GRACE_DAYS
    return {"status": status, "reached": True, "grace_days": grace, "error": ""}


def record(key, result, now=None):
    """Save a key and the answer about it. An unreachable server keeps the previous status and good time for this key;
    a new key the server could not check counts as good from now, for the grace period."""
    now = time.time() if now is None else now
    key = clean(key)
    old = stored()
    same = old.get("key") == key
    v = {"key": key, "checked_at": now, "grace_days": (old.get("grace_days") if same else None) or GRACE_DAYS,
         "status": old.get("status") if same else "unchecked", "last_good_at": old.get("last_good_at") if same else now,
         "last_error": ""}
    if result["reached"]:
        v["status"], v["grace_days"] = result["status"], result["grace_days"] or GRACE_DAYS
        if result["status"] == GOOD:
            v["last_good_at"] = now
    else:
        v["last_error"] = result.get("error") or "unreachable"
    _put(SETTING, v)
    return v


def check_now():
    """Check the stored key now (Settings, Licence and the twice-daily job). Returns the new state()."""
    v = stored()
    if v.get("key") and not demo():
        record(v["key"], ask(v["key"]))
    return state()


def run_due():
    """Called by publish_due every few minutes: one check every CHECK_HOURS hours. Returns lines for its output."""
    v = stored()
    if demo() or not v.get("key") or time.time() - float(v.get("checked_at") or 0) < CHECK_HOURS * 3600:
        return []
    st = check_now()
    return [f"licence: {st['status']}" + ("" if st["ok"] else " (updates are off)")]


def state(now=None):
    """{"ok", "status", "offline", "grace_left" (days), "key_hint", "checked_at"}. ok: updates allowed, no warning."""
    now = time.time() if now is None else now
    if demo():
        return {"ok": True, "status": "demo", "offline": False, "grace_left": None, "key_hint": "", "checked_at": None}
    v = stored()
    key = v.get("key") or ""
    out = {"status": v.get("status") or "no_key", "offline": bool(v.get("last_error")), "grace_left": None,
           "key_hint": (key[:10] + "…" + key[-6:]) if key else "", "checked_at": v.get("checked_at")}
    if not key:
        return {**out, "ok": False, "status": "no_key"}
    if out["status"] not in (GOOD, "unchecked"):
        return {**out, "ok": False}
    grace = float(v.get("grace_days") or GRACE_DAYS) * 86400
    left = float(v.get("last_good_at") or 0) + grace - now
    if out["offline"] or out["status"] == "unchecked":
        out["grace_left"] = max(0, int(left // 86400))
    if left <= 0:
        return {**out, "ok": False, "status": "grace_over"}
    return {**out, "ok": True}


def allows_updates():
    return state()["ok"]


# What the dashboard says, by status (English; Arabic in ui_i18n)
MESSAGES = {
    "no_key": "Add your Technting CMS licence key. Updates are off until then.",
    "inactive_installation": "This licence key already runs on another website. Fill in the download form on technting.com again to get a key for this website. Updates are off until then.",
    "revoked": "This licence key was cancelled. Fill in the download form on technting.com again to get a new key. Updates are off until then.",
    "invalid_license": "This licence key is not valid. Paste the key from your download e-mail as it is. Updates are off until then.",
    "no_license": "This licence key is not valid. Paste the key from your download e-mail as it is. Updates are off until then.",
    "grace_over": "The licence server could not be reached for 30 days, so the licence could not be checked. Check that this server can reach licenses.technting.com. Updates are off until then.",
}
