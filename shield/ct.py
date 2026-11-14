"""Certificate Transparency monitor: every certificate a public authority issues for our domain is logged in public
CT logs. A certificate nobody on the team asked for can mean someone is preparing a fake copy of the site.

Source: crt.sh JSON (free, no key; slow at times, so a failure means "not checked", never "no certificates"), with
Cert Spotter's keyless API as a fallback (a few requests an hour). The first check learns what exists; afterwards a
renewal by an authority we already use is a low note, and a new name or a new authority is an alert.
"""
import json
import re
import time
import urllib.parse
import urllib.request

from . import conf

CRTSH = "https://crt.sh/?"
CERTSPOTTER = "https://api.certspotter.com/v1/issuances?"
KEEP = 600


def _get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": conf.USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(20 * 1024 * 1024))


def _issuer_org(name):
    m = re.search(r"O=(\"[^\"]+\"|[^,]+)", name or "")
    return (m.group(1).strip('"') if m else (name or "")).strip()


def fetch_crtsh(domain):
    rows = _get(CRTSH + urllib.parse.urlencode({"q": f"%.{domain}", "output": "json", "exclude": "expired"}))
    rows += _get(CRTSH + urllib.parse.urlencode({"q": domain, "output": "json", "exclude": "expired"}))
    out = {}
    for r in rows:
        names = sorted({n.strip().lower() for n in (r.get("name_value") or "").split("\n") if n.strip()})
        out[str(r["id"])] = {"names": names, "issuer": _issuer_org(r.get("issuer_name")), "not_before": r.get("not_before", "")[:10],
                             "not_after": r.get("not_after", "")[:10], "url": f"https://crt.sh/?id={r['id']}"}
    return out


def fetch_certspotter(domain):
    rows = _get(CERTSPOTTER + urllib.parse.urlencode({"domain": domain, "include_subdomains": "true", "expand": ["dns_names", "issuer"]}, doseq=True))
    out = {}
    for r in rows:
        issuer = r.get("issuer") or {}
        out["cs-" + str(r["id"])] = {"names": sorted(n.lower() for n in r.get("dns_names") or []),
                                     "issuer": _issuer_org(issuer.get("name") if isinstance(issuer, dict) else ""),
                                     "not_before": (r.get("not_before") or "")[:10], "not_after": (r.get("not_after") or "")[:10],
                                     "url": f"https://sslmate.com/certspotter/view?domain={domain}"}
    return out


def path():
    return conf.data_dir() / "ct.json"


def load():
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run():
    """Check and save. Returns (state, new certificates as [(id, cert, level)])."""
    domain = conf.site_domain()
    state = load() or {"certs": {}, "names": [], "issuers": []}
    state["domain"] = domain
    try:
        try:
            certs, source = fetch_crtsh(domain), "crt.sh"
        except Exception:
            certs, source = fetch_certspotter(domain), "Cert Spotter"
    except Exception as exc:
        state.update(error=f"{type(exc).__name__}: {str(exc)[:160]}", tried_at=time.time())
        path().write_text(json.dumps(state, indent=1), encoding="utf-8")
        return state, []
    first = not state["certs"]
    if first:
        state["first_checked"] = time.time()
    names, issuers = set(state["names"]), set(state["issuers"])
    new = []
    for cid, c in sorted(certs.items()):
        if cid in state["certs"]:
            continue
        if not first:
            fresh_names = [n for n in c["names"] if n not in names]
            level = "high" if fresh_names or c["issuer"] not in issuers else "low"
            new.append((cid, dict(c, new_names=fresh_names), level))
        state["certs"][cid] = dict(c, seen=time.time())
        names.update(c["names"])
        issuers.add(c["issuer"])
    if len(state["certs"]) > KEEP:  # keep the newest
        keep = sorted(state["certs"].items(), key=lambda kv: kv[1].get("seen", 0))[-KEEP:]
        state["certs"] = dict(keep)
    state.update(names=sorted(names), issuers=sorted(issuers), checked_at=time.time(), source=source, error="")
    path().write_text(json.dumps(state, indent=1), encoding="utf-8")
    return state, new


def recent(state, n=25):
    rows = sorted((state or {}).get("certs", {}).items(), key=lambda kv: kv[1].get("not_before", ""), reverse=True)[:n]
    return [dict(c, id=cid) for cid, c in rows]
