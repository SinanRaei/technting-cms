"""Domain and email security of our domain, from public DNS (free DNS over HTTPS):

- SPF and DMARC: without them anyone can send email that looks like it comes from @example.com;
- CAA: which certificate authorities may issue certificates for us (pairs with the certificate watch);
- DNSSEC;
- the site and the dashboard stay behind Cloudflare (an address outside Cloudflare exposes the server);
- changes to name servers (NS) or mail servers (MX): the usual sign of a hijacked domain.
Results: VAR_DIR/shield/domain.json. The first check learns the records; later changes are alerts.
"""
import json
import re
import time
from urllib.parse import urlparse

from django.conf import settings

from . import conf, dns, feeds


def hosts(domain):
    out = [domain, f"www.{domain}"]
    admin = (urlparse(settings.TECHNTING_CMS_ADMIN_URL).hostname or "").lower()
    if admin and admin not in out:
        out.append(admin)
    return out


def _spf(records):
    spf = [r for r in records if r.lower().startswith("v=spf1")]
    if not spf:
        return "high", "No SPF record: anyone can send email that looks like ours", ""
    if len(spf) > 1:
        return "medium", "More than one SPF record: receiving servers ignore them all", ""
    rule = spf[0].lower().split()[-1]
    if rule in ("+all", "all"):
        return "high", "SPF allows every server to send our email (+all)", spf[0]
    if rule == "?all":
        return "medium", "SPF does not say what to do with other servers (?all)", spf[0]
    return "ok", "SPF is set", spf[0]


def _dmarc(records):
    dm = [r for r in records if r.lower().startswith("v=dmarc1")]
    if not dm:
        return "high", "No DMARC record: fake emails in our name are not rejected", ""
    tags = dict(t.strip().split("=", 1) for t in dm[0].split(";") if "=" in t)
    policy = tags.get("p", "").strip().lower()
    if policy == "none":
        return "medium", "DMARC only watches (p=none): fake emails still arrive", dm[0]
    if "rua" not in {k.strip().lower() for k in tags}:
        return "low", "DMARC has no report address (rua): you never see who sends in your name", dm[0]
    return "ok", "DMARC is set", dm[0]


def check(domain=None):
    """Look everything up. Returns the result dict (also when some lookups failed)."""
    domain = domain or conf.site_domain()
    res = {"domain": domain, "checked_at": time.time(), "items": [], "records": {}, "failed": []}

    def item(level, text, detail=""):
        res["items"].append({"level": level, "text": text, "detail": detail})

    root_txt = dns.txt(domain)
    dmarc_txt = dns.txt(f"_dmarc.{domain}")
    if root_txt is None or dmarc_txt is None:
        res["failed"].append("TXT")
    else:
        item(*_spf(root_txt))
        item(*_dmarc(dmarc_txt))
    for rtype in ("NS", "MX", "CAA", "DS"):
        r = dns.query(domain, rtype)
        if r is None:
            res["failed"].append(rtype)
            continue
        res["records"][rtype] = sorted(a.lower().rstrip(".") for a in r["answers"])
    if "CAA" in res["records"]:
        if res["records"]["CAA"]:
            item("ok", "CAA lists the authorities that may issue our certificates", ", ".join(res["records"]["CAA"]))
        else:
            item("low", "No CAA record: any certificate authority may issue certificates for us", "")
    if "DS" in res["records"]:
        if res["records"]["DS"]:
            item("ok", "DNSSEC is on")
        else:
            item("low", "DNSSEC is off (can be turned on in Cloudflare with one click)")
    for host in hosts(domain):
        addrs = []
        for rtype in ("A", "AAAA"):
            r = dns.query(host, rtype)
            if r is None:
                res["failed"].append(f"{rtype} {host}")
                continue
            addrs += [a for a in r["answers"] if re.fullmatch(r"[0-9a-fA-F:.]+", a)]
        res["records"][f"A {host}"] = sorted(addrs)
        outside = [a for a in addrs if not feeds.is_cloudflare(a)]
        if outside:
            item("medium", "Not behind Cloudflare: the server's real address is public", f"{host}: {', '.join(outside)}")
    return res


def path():
    return conf.data_dir() / "domain.json"


def load():
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run():
    """Check and save. Returns (result, changes) where changes are [(record, old, new)] for NS, MX and addresses
    that left Cloudflare, compared with the previous check."""
    old = load() or {}
    res = check()
    changes = []
    before = old.get("records") or {}
    for key in ("NS", "MX"):
        if key in res["records"] and key in before and res["records"][key] != before[key]:
            changes.append((key, before[key], res["records"][key]))
    for key, now in res["records"].items():
        if key.startswith("A ") and key in before:
            left = [a for a in now if a not in before[key] and not feeds.is_cloudflare(a)]
            if left:
                changes.append((key, before[key], now))
    # a failed lookup keeps the last known records, so the next check still compares against them
    res["records"] = {**before, **res["records"]}
    path().write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res, changes
