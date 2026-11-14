"""Write the security log and manage blocks (manual and automatic)."""
import logging
import time
from datetime import timedelta

from django.core.cache import cache, caches
from django.db.models import F
from django.utils import timezone

from . import conf
from .netset import parse_ip, parse_net

log = logging.getLogger(__name__)
KEEP_DAYS = 90
MAX_ROWS = 100_000
REPEAT_SECONDS = 300     # the same address + rule within 5 minutes adds to the count instead of a new line

RULES = {
    "feed:spamhaus-drop": "On the Spamhaus DROP list", "feed:firehol-level1": "On the FireHOL level 1 list",
    "feed:tor-exits": "Tor exit node", "manual": "Blocked by an administrator", "auto": "Blocked automatically",
    "country": "Country not allowed", "dashboard_country": "Country not allowed for the dashboard",
    "scanner": "Probe for a known weak spot", "bad_agent": "Attack tool", "attack:sqli": "SQL injection attempt",
    "attack:xss": "Script injection attempt (XSS)", "attack:traversal": "Attempt to read server files",
    "attack:rce": "Attempt to run commands", "rate": "Too many requests", "direct": "Request did not come through Cloudflare",
    "login_failed": "Wrong password", "bad_username": "Sign-in with a blocked user name", "lockout": "Locked out after wrong passwords",
    "login": "Signed in", "new_device": "Sign-in from a new device", "new_country": "Sign-in from a new country",
    "guessing": "Many wrong passwords for one account", "breached_password": "Password found in a data breach",
    "reputation": "Address with a bad reputation (AbuseIPDB)",
    "integrity": "Code files changed", "web_root": "Unexpected file in the public website folder",
    "vuln": "Vulnerable package", "ct_new": "New certificate for our domain", "feed_failed": "A threat list could not be updated",
    "sessions_ended": "Other sessions signed out", "turnstile": "Failed the human check (Turnstile)",
    "domain_dns": "Domain records changed", "lookalike": "Lookalike domain registered", "media": "Suspicious file in the media library",
    "public_changed": "Public website file changed outside the CMS", "public_extra": "New file on the public website",
}


def label(rule):
    return RULES.get(rule, rule)


def record(rule, *, kind="firewall", severity="low", action="logged", ip="", request=None, username="", detail=""):
    """Add a log line (or count a repeat). Never raises."""
    from .models import Event
    try:
        key = f"shield-ev:{rule}:{ip}:{username}"
        eid = cache.get(key) if kind != "scan" else None  # scan results are each worth their own line
        if eid and Event.objects.filter(pk=eid).update(count=F("count") + 1, last_at=timezone.now(), action=action):
            return eid
        from .firewall import country
        meta = request.META if request is not None else {}
        ev = Event.objects.create(kind=kind, rule=rule[:40], severity=severity, action=action, ip=ip[:64],
                                  country=country(request) if request is not None else "",
                                  method=(getattr(request, "method", None) or "")[:8],
                                  path=(request.get_full_path() if request is not None else "")[:300],
                                  user_agent=(meta.get("HTTP_USER_AGENT") or "")[:300], username=username[:150], detail=str(detail)[:500])
        cache.set(key, ev.pk, REPEAT_SECONDS)
        return ev.pk
    except Exception:
        log.exception("shield: could not write the security log")
        return None


def prune():
    from .models import Event
    removed, _ = Event.objects.filter(last_at__lt=timezone.now() - timedelta(days=KEEP_DAYS)).delete()
    over = Event.objects.count() - MAX_ROWS
    if over > 0:
        ids = list(Event.objects.order_by("last_at").values_list("pk", flat=True)[:over])
        removed += Event.objects.filter(pk__in=ids).delete()[0]
    return removed


def bucket(ip):
    """What counters and automatic blocks apply to: the address, or its /64 for IPv6 (one home or server gets a
    whole /64, so counting single IPv6 addresses would let an attacker change address on every try)."""
    a = parse_ip(ip)
    if a is not None and a.version == 6:
        return str(parse_net(f"{a}/64"))
    return ip


# ---------------------------------------------------------------- blocks
_blocks = {"at": 0, "set": None}


def active_blocks():
    """Blocks in force as a matcher, re-read from the database every 10 seconds per process."""
    from .models import Block
    if _blocks["set"] is None or time.monotonic() - _blocks["at"] > 10:
        now = timezone.now()
        # the reserved-range cut of NetSet does not apply here: an admin may block any network
        _blocks.update(at=time.monotonic(), set=_ExactSet([(b.network, (b.pk, b.source)) for b in Block.objects.all() if b.active(now)]))
    return _blocks["set"]


def blocked(ip):
    """The block's source ("manual" or "auto") when a block in force covers this address (and counts the hit), else None."""
    from .models import Block
    found = active_blocks().match(ip)
    if not found:
        return None
    pk, source = found
    Block.objects.filter(pk=pk).update(hits=F("hits") + 1)
    return source


def forget_blocks():
    _blocks["set"] = None


class _ExactSet:
    """A short list of networks (blocks, the allow list); each item is a network or (network, value)."""

    def __init__(self, items):
        self.nets = []
        for item in items:
            net, value = item if isinstance(item, tuple) else (item, True)
            n = parse_net(net)
            if n:
                self.nets.append((n, value))

    def match(self, ip):
        ip = parse_ip(ip) if isinstance(ip, str) else ip
        return next((v for n, v in self.nets if ip is not None and ip.version == n.version and ip in n), None)


def block_ip(ip, reason, minutes=None, source="auto", user=None):
    """Block an address or network now (unless it is allow-listed, a Cloudflare server or already blocked).
    Returns the Block or None."""
    from . import feeds
    from .models import Block
    net = parse_net(ip)
    if net is None or allowed(str(net.network_address)) or feeds.is_cloudflare(str(net.network_address)):
        return None
    if source == "auto" and active_blocks().match(str(net.network_address)):
        return None
    network = str(net) if net.num_addresses > 1 else str(net.network_address)
    if source == "auto" and minutes:
        # an address locked out before in the last day gets a longer block
        if not cache.add(f"shield-locked:{network}", 1, 86400):
            minutes = max(minutes, 24 * 60)
    b = Block.objects.create(network=network, reason=reason[:200], source=source, created_by=user,
                             expires_at=timezone.now() + timedelta(minutes=minutes) if minutes else None)
    forget_blocks()
    return b


def unblock(block):
    """Remove a block, and its rule at Cloudflare. If Cloudflare cannot be reached, the block is ended now and the
    next sync removes the rule. Returns an error message or ""."""
    from . import cloudflare
    try:
        cloudflare.remove(block)
    except Exception as exc:
        type(block).objects.filter(pk=block.pk).update(expires_at=timezone.now())
        forget_blocks()
        return str(exc)[:200]
    block.delete()
    forget_blocks()
    return ""


def strike(ip, rule, request=None, limit=3, window=600):
    """Count a bad request; after `limit` in `window` seconds the address is blocked for the lockout time.
    Counted in this process's memory (cache "shield"): fast, and an attacker gets at most a few more tries."""
    if not conf.protect():
        return False
    hot = caches["shield"]
    ip = bucket(ip)
    key = f"shield-strike:{ip}"
    n = hot.get(key, 0) + 1
    hot.set(key, n, window)
    if n >= limit:
        hot.delete(key)
        b = block_ip(ip, f"{label(rule)} ({n}×)", conf.number("lockout_minutes"))
        if b:
            record("auto", severity="medium", action="blocked", ip=ip, request=request, detail=b.reason)
        return bool(b)
    return False


_allow = {"raw": None, "set": None}


def allowed(ip):
    raw = conf.opt("allow_ips") or ""
    if _allow["raw"] != raw:
        _allow.update(raw=raw, set=_ExactSet(raw.replace(",", " ").split()))
    return bool(_allow["set"].match(ip))


def expired(cloudflare_on=False):
    """Blocks that ran out: removed (those with a Cloudflare rule only after the Cloudflare sync removed the rule;
    without a token nothing can remove it, and its notes say "Technting Shield" so it can be found in Cloudflare)."""
    from .models import Block
    gone = Block.objects.filter(expires_at__lte=timezone.now())
    if cloudflare_on:
        gone = gone.filter(cf_rule_id="")
    n = gone.count()
    gone.delete()
    if n:
        forget_blocks()
    return n

