"""Public website check: every file the CMS published must still be exactly what it published.

Publishing records a fingerprint (SHA-1) of each file in VAR_DIR/.technting-cms-manifest.json, outside the web root. A
public file that no longer matches means someone changed the website behind the CMS's back (defacement, an injected
script, a skimmer); a missing one means it was deleted. Files the CMS did not create are learnt on the first check;
new ones afterwards are reported. Checks are skipped while a publish is running.
Results: VAR_DIR/shield/public.json.
"""
import hashlib
import json
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from . import conf

MANIFEST = ".technting-cms-manifest.json"


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest():
    mf = Path(settings.VAR_DIR) / MANIFEST
    try:
        return json.loads(mf.read_text(encoding="utf-8")), mf.stat().st_mtime
    except (OSError, ValueError):
        return None, 0


def publishing():
    from cms.models import PublishLog
    _, mtime = _manifest()
    recent = PublishLog.objects.filter(finished_at__isnull=True, started_at__gte=timezone.now() - timedelta(minutes=15)).exists()
    return recent or time.time() - mtime < 120


def scan():
    """{"changed", "missing", "extra"} or None when there is nothing to compare with or a publish is running."""
    manifest, _ = _manifest()
    root = Path(settings.TECHNTING_CMS_OUTPUT_DIR)
    if not manifest or not root.is_dir() or publishing():
        return None
    changed, missing = [], []
    for rel, digest in manifest.items():
        p = root / rel
        if not p.is_file():
            missing.append(rel)
        elif _sha1(p) != digest:
            changed.append(rel)
    if changed or missing:  # a publish may have finished meanwhile: compare again with the newest fingerprints
        manifest, _ = _manifest()
        changed = [r for r in changed if r in manifest and (root / r).is_file() and _sha1(root / r) != manifest[r]]
        missing = [r for r in missing if r in manifest and not (root / r).is_file()]
    extra = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
                   and p.relative_to(root).as_posix() not in manifest)
    return {"checked_at": time.time(), "files": len(manifest), "changed": sorted(changed)[:200], "missing": sorted(missing)[:200],
            "extra": extra[:2000]}


def path():
    return conf.data_dir() / "public.json"


def load():
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run():
    """Check and save. Returns (result or None, new problems [(kind, file)])."""
    old = load() or {}
    res = scan()
    if res is None:
        return None, []
    # files the CMS never made: the first check learns them; later ones are new
    learnt = set(old.get("known_extra", res["extra"] if not old else []))
    res["known_extra"] = sorted(learnt)
    res["new_extra"] = [f for f in res["extra"] if f not in learnt][:200]
    res["extra_count"] = len(res.pop("extra"))
    seen = {("changed", f) for f in old.get("changed", [])} | {("missing", f) for f in old.get("missing", [])} | \
           {("extra", f) for f in old.get("new_extra", [])}
    new = [(k, f) for k in ("changed", "missing") for f in res[k] if (k, f) not in seen]
    new += [("extra", f) for f in res["new_extra"] if ("extra", f) not in seen]
    path().write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res, new


def accept():
    """Take today's unknown files as known (after a developer checked them)."""
    res = load() or {}
    manifest, _ = _manifest()
    root = Path(settings.TECHNTING_CMS_OUTPUT_DIR)
    extra = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
                   and p.relative_to(root).as_posix() not in (manifest or {}))
    res.update(known_extra=extra, new_extra=[])
    path().write_text(json.dumps(res, indent=1), encoding="utf-8")
    return len(extra)
