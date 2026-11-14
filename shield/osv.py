"""Known vulnerabilities in the Python packages Technting CMS runs on, from the free OSV.dev API (no key, no limits).

Checks the versions actually installed (what runs), marks the ones listed in requirements.txt, and shows the
fixed versions. Results: VAR_DIR/shield/osv.json.
"""
import json
import re
import time
import urllib.request
from importlib import metadata
from pathlib import Path

from django.conf import settings

from . import conf

BATCH = "https://api.osv.dev/v1/querybatch"
VULN = "https://api.osv.dev/v1/vulns/"
ORDER = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2, "MEDIUM": 2, "LOW": 3, "": 4}


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def installed():
    seen = {}
    for d in metadata.distributions():
        name = d.metadata.get("Name")
        if name and _norm(name) not in seen:
            seen[_norm(name)] = (name, d.version)
    return sorted(seen.values(), key=lambda x: x[0].lower())


def required():
    p = Path(settings.BASE_DIR) / "requirements.txt"
    names = set()
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", line)
            if m and not line.strip().startswith("#"):
                names.add(_norm(m.group(1)))
    return names


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "User-Agent": conf.USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read(32 * 1024 * 1024))


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": conf.USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read(4 * 1024 * 1024))


def severity(v):
    s = str((v.get("database_specific") or {}).get("severity") or "").upper()
    if s in ORDER:
        return s
    for item in v.get("severity") or []:  # a CVSS vector only: keep it simple and call it medium
        if item.get("score"):
            return "MODERATE"
    return ""


def fixed_versions(v, package):
    out = []
    for a in v.get("affected") or []:
        if _norm((a.get("package") or {}).get("name", "")) != _norm(package):
            continue
        for rng in a.get("ranges") or []:
            out += [e["fixed"] for e in rng.get("events") or [] if e.get("fixed")]
    return sorted(set(out))


def scan():
    pkgs = installed()
    direct = required()
    result = {"checked_at": time.time(), "packages": len(pkgs), "findings": [], "error": ""}
    queries = [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v} for n, v in pkgs]
    ids = []
    for i in range(0, len(queries), 500):
        res = _post(BATCH, {"queries": queries[i:i + 500]})
        for (name, version), r in zip(pkgs[i:i + 500], res.get("results") or []):
            ids += [(name, version, x["id"]) for x in r.get("vulns") or []]
    for name, version, vid in ids:
        v = _get(VULN + vid)
        result["findings"].append({
            "package": name, "version": version, "direct": _norm(name) in direct, "id": vid,
            "aliases": [a for a in v.get("aliases") or [] if a.startswith("CVE-")][:3],
            "summary": (v.get("summary") or (v.get("details") or "")[:200]).strip(), "severity": severity(v),
            "fixed": fixed_versions(v, name), "url": f"https://osv.dev/vulnerability/{vid}"})
    result["findings"].sort(key=lambda f: (ORDER.get(f["severity"], 4), f["package"].lower()))
    return result


def path():
    return conf.data_dir() / "osv.json"


def load():
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run():
    """Scan and save. Returns (result, new findings since the last scan)."""
    old = load() or {}
    try:
        result = scan()
    except Exception as exc:
        result = dict(old, error=f"{type(exc).__name__}: {str(exc)[:160]}", tried_at=time.time())
        path().write_text(json.dumps(result, indent=1), encoding="utf-8")
        return result, []
    known = {(f["package"], f["id"]) for f in old.get("findings") or []}
    new = [f for f in result["findings"] if (f["package"], f["id"]) not in known]
    path().write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result, (new if old else [])
