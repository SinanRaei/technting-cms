"""DNS lookups over HTTPS (free, no key): Cloudflare's resolver, with Google's as a fallback. Answers are short
dicts, never raises: a lookup that fails returns None, so a check reports "not checked" instead of a false alarm."""
import json
import logging
import urllib.parse
import urllib.request

from . import conf

log = logging.getLogger(__name__)
RESOLVERS = ["https://cloudflare-dns.com/dns-query?", "https://dns.google/resolve?"]
TYPES = {"A": 1, "NS": 2, "CNAME": 5, "MX": 15, "TXT": 16, "AAAA": 28, "DS": 43, "CAA": 257}
NOERROR, NXDOMAIN = 0, 3


def query(name, rtype):
    """{"status": 0 | 3 | ..., "secure": DNSSEC validated?, "answers": [record data of that type]} or None."""
    params = urllib.parse.urlencode({"name": name, "type": rtype})
    for base in RESOLVERS:
        req = urllib.request.Request(base + params, headers={"Accept": "application/dns-json", "User-Agent": conf.USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                d = json.loads(r.read(500_000))
        except Exception as exc:
            log.info("DNS over HTTPS %s failed: %s", base, type(exc).__name__)
            continue
        want = TYPES[rtype]
        answers = [a.get("data", "") for a in d.get("Answer") or [] if a.get("type") == want]
        return {"status": d.get("Status"), "secure": bool(d.get("AD")), "answers": answers}
    return None


def txt(name):
    """TXT records as plain strings (quotes removed, split strings joined), or None."""
    r = query(name, "TXT")
    if r is None:
        return None
    return ["".join(part for part in _unquote(a)) for a in r["answers"]]


def _unquote(data):
    out, cur, inside = [], "", False
    for ch in data:
        if ch == '"':
            if inside:
                out.append(cur)
                cur = ""
            inside = not inside
        elif inside:
            cur += ch
    return out or [data]
