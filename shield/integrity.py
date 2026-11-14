"""File integrity: compare the code on the server with the committed version.

The reference is, in this order:
  1. code-manifest.json in the code folder: Git blob hashes of every committed file, written by
     `manage.py shield manifest` from the commit being deployed (and uploaded with the code);
  2. the commit that Settings → Updates installed, read from the updater's own copy of the repository;
  3. the Git commit itself, when the code folder is a Git checkout;
  4. a baseline saved by the first scan (or by "Accept the current files" after a deployment).
The files checked are the ones the updater installs (cms.updater.tree_paths of the installed commit).
Hashes use Git's blob format, so a manifest and `git ls-tree` agree. The public website folder is also checked for
files a static site never needs (scripts such as .php), the usual sign of a web shell.
"""
import hashlib
import json
import subprocess
import time
from pathlib import Path

from django.conf import settings

from . import conf

def _paths():
    """The folders and files the updater installs: read from the installed commit when Updates installed one
    (so a new app folder is watched too), else its built-in minimum list."""
    from cms import updater
    if _cached["at"] and time.monotonic() - _cached["at"] < 60:
        return _cached["paths"]
    paths = list(updater.PATHS)
    try:
        commit = (updater.installed() or {}).get("commit")
        if commit and updater.src_dir().exists():
            paths = updater.tree_paths(commit)
        else:
            paths = updater.installed_paths() or paths
    except Exception:
        pass
    _cached.update(at=time.monotonic(), paths=paths)
    return paths


_cached = {"at": 0, "paths": []}


SKIP_PARTS = {"__pycache__", ".git", "node_modules", ".venv", "var", "var-live"}
SKIP_SUFFIXES = (".pyc", ".pyo", ".log", ".tmp")
WEB_ROOT_BAD = {".php", ".php3", ".php4", ".php5", ".php7", ".phtml", ".phar", ".py", ".pl", ".cgi", ".sh", ".asp", ".aspx",
                ".jsp", ".exe", ".dll", ".so", ".htaccess"}
MANIFEST = "code-manifest.json"


def blob_hash(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def base():
    return Path(settings.BASE_DIR)


def _wanted(rel):
    parts = rel.split("/")
    if SKIP_PARTS & set(parts) or rel.endswith(SKIP_SUFFIXES):
        return False
    return rel in _paths() or parts[0] in _paths()


def current():
    root, out = base(), {}
    for rel in _paths():
        if (root / rel).is_file():
            out[rel] = blob_hash((root / rel).read_bytes())
    for d in _paths():
        for p in (root / d).rglob("*") if (root / d).is_dir() else []:
            if p.is_file():
                rel = p.relative_to(root).as_posix()
                if _wanted(rel):
                    out[rel] = blob_hash(p.read_bytes())
    return out


def from_git(rev="HEAD", git_dir=None):
    where = ["--git-dir", str(git_dir)] if git_dir else ["-C", str(base())]
    try:
        res = subprocess.run(["git", *where, "ls-tree", "-r", rev], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode:
        return None
    files = {}
    for line in res.stdout.splitlines():
        meta, _, rel = line.partition("\t")
        mode, kind, sha = meta.split()
        if kind == "blob" and _wanted(rel):
            files[rel] = sha
    return files


def write_manifest(rev="HEAD"):
    files = from_git(rev)
    if files is None:
        raise RuntimeError("Not a Git checkout (or git is missing): run this where the code is committed.")
    commit = subprocess.run(["git", "-C", str(base()), "rev-parse", rev], capture_output=True, text=True).stdout.strip()
    (base() / MANIFEST).write_text(json.dumps({"commit": commit, "created": time.time(), "files": files}, indent=0), encoding="utf-8")
    return commit, len(files)


def _baseline_path():
    return conf.data_dir() / "integrity-baseline.json"


def reference():
    """(source, label, files)"""
    m = base() / MANIFEST
    if m.exists():
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
            return "manifest", data.get("commit", "")[:10], data["files"]
        except (ValueError, KeyError):
            pass
    try:
        from cms import updater
        commit = (updater.installed() or {}).get("commit")
        if commit and updater.src_dir().exists():
            files = from_git(commit, updater.src_dir())
            if files is not None:
                return "update", commit[:10], files
    except Exception:
        pass
    if (base() / ".git").exists():
        files = from_git()
        if files is not None:
            return "git", "HEAD", files
    try:
        data = json.loads(_baseline_path().read_text(encoding="utf-8"))
        return "baseline", time.strftime("%Y-%m-%d %H:%M", time.localtime(data["created"])), data["files"]
    except (OSError, ValueError, KeyError):
        return None, "", None


def accept():
    """Save the files as they are now as the baseline (after a deployment)."""
    files = current()
    _baseline_path().write_text(json.dumps({"created": time.time(), "files": files}, indent=0), encoding="utf-8")
    return len(files)


def web_root_findings():
    root = Path(settings.TECHNTING_CMS_OUTPUT_DIR)
    out = []
    if root.is_dir():
        for p in root.rglob("*"):
            if p.is_file() and (p.suffix.lower() in WEB_ROOT_BAD or p.name.lower() in WEB_ROOT_BAD):
                out.append(p.relative_to(root).as_posix())
                if len(out) >= 50:
                    break
    return out


def scan():
    source, label, ref = reference()
    if ref is None:
        accept()
        source, label, ref = reference()
    now = current()
    ref = {k: v for k, v in ref.items() if k != MANIFEST}
    now.pop(MANIFEST, None)
    changed = sorted(k for k in now if k in ref and now[k] != ref[k])
    added = sorted(k for k in now if k not in ref)
    missing = sorted(k for k in ref if k not in now)
    return {"checked_at": time.time(), "source": source, "label": label, "files": len(now), "changed": changed[:200],
            "added": added[:200], "missing": missing[:200], "web_root": web_root_findings()}


def path():
    return conf.data_dir() / "integrity.json"


def load():
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run():
    """Scan and save. Returns (result, things that are new since the last scan)."""
    old = load() or {}
    result = scan()
    path().write_text(json.dumps(result, indent=1), encoding="utf-8")
    seen = set(old.get("changed", []) + old.get("added", []) + old.get("missing", []))
    new = [f for f in result["changed"] + result["added"] + result["missing"] if f not in seen]
    new_web = [f for f in result["web_root"] if f not in set(old.get("web_root", []))]
    return result, new, new_web
