"""Lookalike domains: names one typo away from ours (example.co, examp1e.com, example-login.com...) that
someone registers to send phishing emails or host a fake copy of the site. Checked once a day through public DNS
(free): a name with name servers is registered, a name with mail servers can send email. Certificates for names
that contain ours are also looked up in Certificate Transparency (crt.sh), best effort.
The first check learns what already exists; a name registered later is an alert.
"""
import json
import time

from . import conf, ct, dns

TLDS = ["com", "net", "org", "co", "io", "ai", "me", "info", "app", "online", "tech", "sa", "com.sa", "ae", "jo", "com.jo"]
WORDS = ["login", "secure", "support", "mail", "portal", "sa", "uae", "jo", "ksa", "group"]
LOOKS_LIKE = {"i": ["l", "1"], "l": ["i", "1"], "m": ["rn", "nn"], "o": ["0"], "e": ["3"], "a": ["4"], "g": ["q"], "n": ["m"]}
MAX_NAMES = 160


def variants(domain):
    """Lookalike names for `domain` (label + public suffix), our own name excluded."""
    label, _, suffix = domain.partition(".")
    names = set()
    typos = set()
    for i in range(len(label)):
        typos.add(label[:i] + label[i + 1:])                                    # a letter left out
        typos.add(label[:i] + label[i] + label[i:])                             # a letter doubled
        if i < len(label) - 1:
            typos.add(label[:i] + label[i + 1] + label[i] + label[i + 2:])      # two letters swapped
        for other in LOOKS_LIKE.get(label[i], []):
            typos.add(label[:i] + other + label[i + 1:])                        # a letter that looks alike
        if 0 < i:
            typos.add(label[:i] + "-" + label[i:])                              # a hyphen
    typos.discard(label)
    names.update(f"{t}.{suffix}" for t in typos if len(t) > 2)
    names.update(f"{label}.{tld}" for tld in TLDS if tld != suffix)
    names.update(f"{label}-{w}.{suffix}" for w in WORDS)
    names.update(f"{w}-{label}.{suffix}" for w in ("my", "secure", "login"))
    names.discard(domain)
    own = set(conf.words("own_domains"))
    return sorted(n for n in names if n not in own)[:MAX_NAMES]


def lookup(name):
    """{"registered": bool, "mail": bool, "web": bool} or None when DNS could not be asked."""
    ns = dns.query(name, "NS")
    if ns is None:
        return None
    if ns["status"] == dns.NXDOMAIN:
        return {"registered": False, "mail": False, "web": False}
    mx = dns.query(name, "MX") or {"answers": []}
    a = dns.query(name, "A") or {"answers": []}
    registered = bool(ns["answers"]) or bool(mx["answers"]) or bool(a["answers"])
    return {"registered": registered, "mail": bool(mx["answers"]), "web": bool(a["answers"])}


def from_ct(domain):
    """Other domains whose certificates contain our name (best effort: crt.sh is slow at times)."""
    label = domain.split(".")[0]
    try:
        rows = ct._get(ct.CRTSH + f"q=%25{label}%25&output=json&exclude=expired", timeout=40)
    except Exception:
        return None
    out = set()
    for r in rows:
        for n in (r.get("name_value") or "").split("\n"):
            n = n.strip().lower().lstrip("*.")
            if label in n and not (n == domain or n.endswith("." + domain)):
                out.add(n)
    own = set(conf.words("own_domains"))
    return sorted(n for n in out if n not in own)[:100]


def path():
    return conf.data_dir() / "lookalike.json"


def load():
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run(pause=0.05):
    """Check and save. Returns (state, newly registered names)."""
    domain = conf.site_domain()
    state = load() or {"found": {}, "checked": 0}
    first = not state.get("first_checked")
    found, new, failed = dict(state.get("found") or {}), [], 0
    names = variants(domain)
    for name in names:
        r = lookup(name)
        if r is None:
            failed += 1
            continue
        if r["registered"]:
            if name not in found:
                found[name] = dict(r, first_seen=time.time(), source="dns")
                if not first:
                    new.append(name)
            else:
                found[name].update(r)
        else:
            found.pop(name, None)
        time.sleep(pause)
    ct_names = from_ct(domain)
    for name in ct_names or []:
        if name not in found:
            found[name] = {"registered": True, "mail": False, "web": True, "first_seen": time.time(), "source": "certificate"}
            if not first:
                new.append(name)
    for name in conf.words("own_domains"):
        found.pop(name, None)
    state.update(domain=domain, found=found, checked=len(names), failed=failed, ct_ok=ct_names is not None, checked_at=time.time())
    if first and failed < len(names):
        state["first_checked"] = time.time()
    path().write_text(json.dumps(state, indent=1), encoding="utf-8")
    return state, new


def rows(state):
    found = (state or {}).get("found") or {}
    return [dict(v, name=k, first_date=time.strftime("%Y-%m-%d", time.localtime(v.get("first_seen", 0))))
            for k, v in sorted(found.items(), key=lambda kv: -kv[1].get("first_seen", 0))]
