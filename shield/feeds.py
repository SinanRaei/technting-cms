"""Free threat lists, refreshed automatically and cached on disk (VAR_DIR/shield/feeds/).

Each list is fetched at most at the interval below, with a timeout and If-Modified-Since. A failed or suspiciously
small download never replaces the cached copy, so a source being down never empties a blocklist (and never blocks
anybody new). Terms checked 2026-10-16: Spamhaus DROP is free for any use (credit Spamhaus; not more than hourly),
FireHOL level1 is free (lists belong to their maintainers; it includes private ranges, which NetSet cuts out),
the Tor exit list is published so sites can choose what to do with Tor, Cloudflare publishes its own ranges.
"""
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone as dt_tz

from . import conf
from .netset import NetSet, parse_net

log = logging.getLogger(__name__)

FEEDS = {
    "spamhaus-drop": {"label": "Spamhaus DROP", "hours": 24, "kind": "block",
                      "urls": ["https://www.spamhaus.org/drop/drop_v4.json", "https://www.spamhaus.org/drop/drop_v6.json"],
                      "about": "Networks taken over by spammers and criminals (Spamhaus Don't Route Or Peer).",
                      "credit": "Data © The Spamhaus Project, spamhaus.org"},
    "firehol-level1": {"label": "FireHOL level 1", "hours": 24, "kind": "block",
                       "urls": ["https://iplists.firehol.org/files/firehol_level1.netset"],
                       "about": "Addresses attacking right now (DShield, abuse.ch, Spamhaus and others), with few false alarms.",
                       "credit": "iplists.firehol.org"},
    "tor-exits": {"label": "Tor exit nodes", "hours": 6, "kind": "tag",
                  "urls": ["https://check.torproject.org/torbulkexitlist"],
                  "about": "Addresses of the Tor network's exits. Logged by default; blocked only if you choose so.",
                  "credit": "The Tor Project"},
    "cloudflare": {"label": "Cloudflare addresses", "hours": 24 * 7, "kind": "trust",
                   "urls": ["https://www.cloudflare.com/ips-v4", "https://www.cloudflare.com/ips-v6"],
                   "about": "Cloudflare's own servers. Only requests from them may name the visitor's address.",
                   "credit": "cloudflare.com/ips"},
}
# Shipped copy of https://www.cloudflare.com/ips-v4 and ips-v6 (2026-10-16), used until the first download.
CLOUDFLARE_DEFAULT = ["173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
                      "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
                      "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
                      "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
                      "2a06:98c0::/29", "2c0f:f248::/32"]
MIN_ITEMS = {"spamhaus-drop": 100, "firehol-level1": 500, "tor-exits": 100, "cloudflare": 10}
MAX_BYTES = 8 * 1024 * 1024
_mem = {"checked": 0, "sets": {}, "mtimes": {}}


def _path(name):
    d = conf.data_dir() / "feeds"
    d.mkdir(exist_ok=True)
    return d / f"{name}.txt"


def _meta_path():
    return conf.data_dir() / "feeds.json"


def meta():
    try:
        return json.loads(_meta_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_meta(data):
    _meta_path().write_text(json.dumps(data, indent=1), encoding="utf-8")


def parse(name, text):
    """CIDRs / addresses from a downloaded list."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("{"):  # Spamhaus NDJSON: {"cidr": ..., "sblid": ...}; the last line is metadata
            try:
                cidr = json.loads(line).get("cidr")
            except ValueError:
                cidr = None
            if cidr:
                out.append(cidr)
            continue
        out.append(line.split(";")[0].split()[0])
    return out


def _download(url, since=None):
    headers = {"User-Agent": conf.USER_AGENT}
    if since:
        headers["If-Modified-Since"] = since
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read(MAX_BYTES + 1).decode("utf-8", "replace"), r.headers.get("Last-Modified")
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return None, since
        raise


def refresh(name, force=False):
    """Download one list if it is due. Returns a short status line, or "" when nothing was due."""
    spec, data = FEEDS[name], meta()
    m = data.get(name, {})
    last = m.get("tried_at", 0)
    if not force and time.time() - last < spec["hours"] * 3600:
        return ""
    m["tried_at"] = time.time()
    try:
        items, modified, unchanged = [], [], True
        for i, url in enumerate(spec["urls"]):
            lms = m.get("last_modified") or []
            since = lms[i] if i < len(lms) and not force and _path(name).exists() else None
            text, lm = _download(url, since)
            modified.append(lm)
            if text is None:
                continue
            unchanged = False
            if len(text) > MAX_BYTES:
                raise ValueError("list too large")
            items += [i for i in parse(name, text) if parse_net(i)]  # an error page parses to nothing
        if unchanged:
            m.update(ok=True, error="", checked_at=time.time())
            return f"{name}: not changed"
        # a partly unchanged pair (v4 changed, v6 not) is downloaded again in full next time
        if any(x is None for x in modified):
            modified = []
        if len(items) < MIN_ITEMS.get(name, 1) or (m.get("count") and len(items) < m["count"] * 0.5):
            raise ValueError(f"only {len(items)} entries; keeping the cached copy")
        tmp = _path(name).with_suffix(".tmp")
        tmp.write_text("\n".join(items) + "\n", encoding="utf-8")
        tmp.replace(_path(name))
        m.update(ok=True, error="", count=len(items), checked_at=time.time(), updated_at=time.time(), last_modified=modified)
        _mem["checked"] = 0
        return f"{name}: {len(items)} entries"
    except Exception as exc:  # keep the old copy; the firewall keeps working with it
        log.warning("shield feed %s failed: %s", name, exc)
        m.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:160]}")
        return f"{name}: failed ({m['error']})"
    finally:
        data[name] = m
        _save_meta(data)


def refresh_due(force=False):
    return [line for line in (refresh(n, force) for n in FEEDS) if line]


def _load():
    if time.monotonic() - _mem["checked"] < 30:
        return
    _mem["checked"] = time.monotonic()
    for name in FEEDS:
        p = _path(name)
        try:
            mtime = p.stat().st_mtime
        except OSError:
            mtime = None
        if name in _mem["sets"] and _mem["mtimes"].get(name) == mtime:
            continue
        items = p.read_text(encoding="utf-8").split() if mtime else []
        if name == "cloudflare":
            _mem["sets"][name] = NetSet(items + CLOUDFLARE_DEFAULT)
        else:
            # Cloudflare's own servers are never blocked, whatever a list says
            _mem["sets"][name] = NetSet(items, exclude=CLOUDFLARE_DEFAULT)
        _mem["mtimes"][name] = mtime


def lookup(ip):
    """Names of the lists that contain this address (the "cloudflare" list is not reported)."""
    try:
        _load()
        return [n for n, s in _mem["sets"].items() if n != "cloudflare" and ip in s]
    except Exception:
        log.exception("shield feed lookup failed")
        return []


def is_cloudflare(ip):
    try:
        _load()
        return ip in _mem["sets"]["cloudflare"]
    except Exception:
        return ip in NetSet(CLOUDFLARE_DEFAULT)


def status():
    """Rows for the dashboard."""
    data = meta()
    rows = []
    for name, spec in FEEDS.items():
        m = data.get(name, {})
        updated = m.get("updated_at")
        age_h = round((time.time() - updated) / 3600, 1) if updated else None
        rows.append({"name": name, "label": spec["label"], "about": spec["about"], "credit": spec["credit"], "kind": spec["kind"],
                     "count": m.get("count"), "ok": m.get("ok"), "error": m.get("error", ""), "every_hours": spec["hours"],
                     "updated": datetime.fromtimestamp(updated, dt_tz.utc) if updated else None,
                     "checked": datetime.fromtimestamp(m["checked_at"], dt_tz.utc) if m.get("checked_at") else None,
                     "stale": age_h is None or age_h > spec["hours"] * 3 + 24, "age_h": age_h})
    return rows
