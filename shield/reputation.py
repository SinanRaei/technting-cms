"""Optional address reputation from AbuseIPDB (API v2 "check").

Off until an administrator enters a key. AbuseIPDB's terms (checked 2026-10-16) allow the free plan only for
non-commercial use, so a business site needs at least their Basic plan. Answers are cached for a day and the plugin
stays under 900 checks a day; any failure means "unknown" and never blocks anyone.
"""
import json
import logging
import urllib.parse
import urllib.request
from datetime import date

from django.core.cache import cache

from . import conf
from .netset import is_public

log = logging.getLogger(__name__)
API = "https://api.abuseipdb.com/api/v2/check"
DAILY_BUDGET = 900


def check(ip, force=False):
    """{"score", "country", "isp", "reports", "tor", "usage"} or None."""
    key = conf.opt("abuseipdb_key")
    if not key or not is_public(ip):
        return None
    ck = f"shield-abuse:{ip}"
    cached = cache.get(ck)
    if cached is not None and not force:
        return cached or None
    budget = f"shield-abuse-n:{date.today().isoformat()}"
    if cache.get(budget, 0) >= DAILY_BUDGET:
        return None
    cache.set(budget, cache.get(budget, 0) + 1, 2 * 86400)
    url = API + "?" + urllib.parse.urlencode({"ipAddress": ip, "maxAgeInDays": 90})
    req = urllib.request.Request(url, headers={"Key": key, "Accept": "application/json", "User-Agent": conf.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            d = json.loads(r.read(200_000))["data"]
    except Exception as exc:
        log.warning("AbuseIPDB check failed: %s", type(exc).__name__)
        cache.set(ck, {}, 600)
        return None
    out = {"score": int(d.get("abuseConfidenceScore") or 0), "country": d.get("countryCode") or "", "isp": (d.get("isp") or "")[:100],
           "reports": int(d.get("totalReports") or 0), "tor": bool(d.get("isTor")), "usage": d.get("usageType") or ""}
    cache.set(ck, out, 86400)
    return out
