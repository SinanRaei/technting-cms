"""Technting Shield settings: the plugin's switch and its settings from the Plugins page, with defaults."""
import time
from pathlib import Path

from django.conf import settings

PLUGIN = "technting-shield"
DEFAULTS = {
    "protect": False,               # off = learning mode: everything is logged, nothing is blocked
    "block_feeds": True,
    "block_tor": False,
    "allow_ips": "",
    "blocked_countries": "",
    "dashboard_countries": "",
    "requests_per_minute": 120,
    "login_attempts": 5,
    "lockout_minutes": 60,
    "blocked_usernames": "admin\nadministrator\nroot\nwpadmin\ntest\nuser",
    "breached_passwords": True,
    "ct_domain": "",
    "abuseipdb_key": "",
    "abuseipdb_block_score": 90,
    "cloudflare_token": "",
    "cloudflare_zone": "",
    "own_domains": "",
    "security_contact": "",
    "turnstile_site_key": "",
    "turnstile_secret": "",
    "turnstile_forms": True,         # the same check on the website's enquiry and newsletter forms
}
SECRETS = {"abuseipdb_key", "cloudflare_token", "turnstile_secret"}
_cache = {"at": 0, "on": False, "opts": {}}


def _refresh():
    if time.monotonic() - _cache["at"] < 5:
        return
    from cms import plugins
    try:
        _cache["on"] = PLUGIN in plugins.enabled_names()
        _cache["opts"] = plugins.plugin_settings(PLUGIN)
    except Exception:  # database not ready (migrations); the firewall stays out of the way
        _cache["on"], _cache["opts"] = False, {}
    _cache["at"] = time.monotonic()


def reset():
    _cache["at"] = 0


def enabled():
    _refresh()
    return _cache["on"]


def opt(key):
    _refresh()
    value = _cache["opts"].get(key)
    if key in SECRETS:
        from cms.mail import decrypt
        return decrypt(value) if value else ""
    return DEFAULTS.get(key) if value is None else value


def number(key):
    try:
        return max(1, int(opt(key) or DEFAULTS[key]))
    except (TypeError, ValueError):
        return DEFAULTS[key]


def words(key):
    """A textarea or comma separated setting as a list of lowercase words."""
    import re
    return [w for w in re.split(r"[\s,;]+", str(opt(key) or "").lower()) if w]


def countries(key):
    return {c.upper() for c in words(key) if len(c) == 2}


def protect():
    return bool(opt("protect"))


def data_dir():
    d = Path(settings.VAR_DIR) / "shield"
    d.mkdir(parents=True, exist_ok=True)
    return d


def site_domain():
    from urllib.parse import urlparse
    return (opt("ct_domain") or urlparse(settings.TECHNTING_CMS_SITE_URL).hostname or "").strip().lower()


USER_AGENT = "Technting-CMS-Shield/1.0 (+https://example.com; security plugin of the site's own CMS)"
