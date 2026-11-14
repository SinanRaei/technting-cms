"""Update Technting CMS from Settings, Updates (in the spirit of WordPress → Updates).

Two sources (mode()):
  release  the default: the published release zips. The update feed (TECHNTING_CMS_UPDATE_FEED, on technting.com)
           names the newest version and gives a short-lived HTTPS link to its zip. The zip must be a release of exactly
           that version (technting_cms/__init__.py inside it), with no links and no paths outside its folder.
  git      when TECHNTING_CMS_UPDATE_REMOTE is set, or the server already keeps a clone: a bare clone of the repository
           read with a read-only deploy key (ssh alias github-technting-cms), main branch.
An update runs as its own process (manage.py update_site) so it survives the restart it causes:

  1. download   the release zip, or fetch main from Git
  2. backup     database + media (manage.py backup) and the current code
  3. files      write the new code (git archive), remove files the update deleted
  4. packages   pip install when requirements.txt changed
  5. database   migrate (run with the new code)
  6. static     collectstatic
  7. restart    graceful reload: SIGHUP to the gunicorn master (same user, no root needed)
  8. check      the dashboard answers again
  9. publish    rebuild the site with the new theme and code

If a step from 3 on fails, the old code (and, when migrations ran, the database) is put back and the site reloads.
Progress goes to VAR_DIR/update.json; the installed version to VAR_DIR/version.json. A release install also keeps the
list of files it wrote (VAR_DIR/release-files.json, so the next release can remove the files it dropped) and writes
code-manifest.json for the Shield integrity check.
"""
import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import re
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone

PATHS = ["cms", "crm", "shield", "themes", "plugins", "technting_cms", "requirements.txt", "manage.py"]  # minimum; see tree_paths()
SKIP = {".gitignore", ".env.example", "deploy", "README.md"}   # repo files the running site does not need


def tree_paths(ref):
    """Top-level folders and files of a commit that make up the site. Read from the new commit itself, so a new app
    folder added by an update is installed by that same update (a fixed list in the running code cannot know it)."""
    return site_paths(git("ls-tree", "--name-only", ref).decode("utf-8").split())


def site_paths(names):
    """The top-level names (of a commit or a release) that the updater installs."""
    names = set(names)
    return sorted({n for n in names if n not in SKIP} | ({p for p in PATHS} & names))


REMOTE = (getattr(settings, "TECHNTING_CMS_UPDATE_REMOTE", "") or "").strip()
BRANCH = "main"
FEED = getattr(settings, "TECHNTING_CMS_UPDATE_FEED", "https://technting.com/wp-json/technting/v1/cms-update")
MAX_RELEASE_BYTES = 200 * 1024 * 1024
VERSION = re.compile(r"\d+\.\d+\.\d+")


def mode():
    """'git' when a Git remote is set (or this server already keeps a clone from one), else 'release'."""
    return "git" if REMOTE or src_dir().exists() else "release"


def _vt(v):
    return tuple(int(x) for x in v.split(".")) if VERSION.fullmatch(str(v or "")) else (0, 0, 0)


def code_version():
    """The version of the code on disk (technting_cms/__init__.py), '' when it cannot be read."""
    try:
        text = (base_dir() / "technting_cms" / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return m.group(1) if m and VERSION.fullmatch(m.group(1)) else ""


def release_info(version, **extra):
    return {"version": version, "commit": "v" + version, "short": version, "date": "", "subject": f"Technting CMS {version}", **extra}


def _agent():
    return {"User-Agent": f"TechntingCMS/{code_version() or 'unknown'} (+https://technting.com/products/cms/)"}


def fetch_release():
    """Ask the update feed for the newest release: {version, file, url}."""
    inst = installed() or {}
    url = FEED + ("&" if "?" in FEED else "?") + urllib.parse.urlencode({"v": inst.get("version", "")})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={**_agent(), "Accept": "application/json"}), timeout=20) as r:
            data = json.loads(r.read(65536).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"The update server answered {exc.code}.") from None
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Could not read the update server ({type(exc).__name__}).") from None
    if not isinstance(data, dict):
        raise RuntimeError("The update server sent an answer this version cannot read.")
    version, link = str(data.get("version", "")), str(data.get("url", ""))
    if not VERSION.fullmatch(version) or not link.startswith("https://"):
        raise RuntimeError("The update server sent an answer this version cannot read.")
    return release_info(version, file=str(data.get("file", ""))[:120], url=link)


def download_release(info):
    """Download the release zip of `info` into VAR_DIR/releases/ (the last two are kept) and return its path."""
    folder = _var("releases")
    folder.mkdir(exist_ok=True)
    path = folder / f"technting-cms-{info['version']}.zip"
    tmp = path.with_suffix(".part")
    size = 0
    try:
        with urllib.request.urlopen(urllib.request.Request(info["url"], headers=_agent()), timeout=60) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RELEASE_BYTES:
                    raise Step("The release file is too large.")
                f.write(chunk)
    except urllib.error.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        raise Step(f"The download answered {exc.code}. Press Check for updates and try again.") from None
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise Step(f"The download failed ({type(exc).__name__}).") from None
    except Step:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)
    keep = {p.name for p in sorted(folder.glob("technting-cms-*.zip"), key=lambda q: q.stat().st_mtime)[-2:]} | {path.name}
    for old in folder.glob("technting-cms-*.zip"):
        if old.name not in keep:
            old.unlink(missing_ok=True)
    return path


def read_release(path, version):
    """The files of a release zip as {path inside the release: bytes}, without its top folder. Refuses a zip that is not
    a Technting CMS release of `version`, or that holds links or paths outside its folder."""
    out, tops = {}, set()
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        raise Step("The downloaded file is not a valid zip.") from None
    with z:
        for i in z.infolist():
            name = i.filename.replace("\\", "/")
            if name.endswith("/"):
                continue
            if (i.external_attr >> 16) & 0o170000 == 0o120000:
                raise Step(f"The release holds a link: {name[:80]}")
            top, _, rel = name.partition("/")
            parts = rel.split("/")
            if not top or not rel or name.startswith("/") or ":" in name or ".." in parts or "" in parts or "." in parts:
                raise Step(f"Unexpected path in the release: {name[:80]}")
            tops.add(top)
            out[rel] = z.read(i)
    m = re.search(r'__version__\s*=\s*"([^"]+)"', out.get("technting_cms/__init__.py", b"").decode("utf-8", "replace"))
    if len(tops) != 1 or "manage.py" not in out or not m:
        raise Step("The downloaded file is not a Technting CMS release.")
    if m.group(1) != version:
        raise Step(f"The downloaded release is {m.group(1)}, not {version}.")
    return out


def _tar_of(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for rel in sorted(files):
            ti = tarfile.TarInfo(rel)
            ti.size, ti.mtime = len(files[rel]), int(time.time())
            ti.mode = 0o755 if rel.endswith(".sh") else 0o644
            tar.addfile(ti, io.BytesIO(files[rel]))
    return buf.getvalue()


def installed_paths():
    """The top-level names the last release install wrote (None outside release mode or before one)."""
    names = _read("release-files.json") if mode() == "release" else None
    return site_paths({str(n).split("/")[0] for n in names}) if isinstance(names, list) and names else None


def write_manifest(files, version):
    """code-manifest.json for the Shield integrity check: Git blob hashes of the files the release installed."""
    blob = {rel: hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() for rel, data in files.items()}
    (base_dir() / "code-manifest.json").write_text(
        json.dumps({"commit": "v" + version, "created": time.time(), "files": blob}, indent=0), encoding="utf-8")


def base_dir():
    return Path(getattr(settings, "TECHNTING_CMS_UPDATE_TARGET", settings.BASE_DIR))


def src_dir():
    return Path(getattr(settings, "TECHNTING_CMS_UPDATE_SRC", Path(settings.BASE_DIR).parent / "technting-cms-src.git"))


def _refuse_in_demo():
    if getattr(settings, "TECHNTING_CMS_DEMO_MODE", False):
        raise RuntimeError("Updates are turned off in the public demo.")


def _var(name):
    return Path(settings.VAR_DIR) / name


def _read(name):
    try:
        return json.loads(_var(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(name, data):
    tmp = _var(name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, _var(name))


def git(*args, timeout=120):
    r = subprocess.run(["git", "--git-dir", str(src_dir()), *args], capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).decode("utf-8", "replace").strip()[:400] or f"git {args[0]} failed")
    return r.stdout


def fetch():
    """Find the newest release (or download the latest main). Returns its info."""
    _refuse_in_demo()
    if mode() == "release":
        info = fetch_release()
        _write("update_check.json", {"checked_at": timezone.now().isoformat(), "latest": {k: v for k, v in info.items() if k != "url"}})
        return info
    if not src_dir().exists():
        r = subprocess.run(["git", "clone", "--bare", "--single-branch", "--branch", BRANCH, REMOTE, str(src_dir())],
                           capture_output=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:400])
    git("fetch", "--quiet", "origin", f"+refs/heads/{BRANCH}:refs/heads/{BRANCH}", timeout=180)
    info = commit_info(BRANCH)
    _write("update_check.json", {"checked_at": timezone.now().isoformat(), "latest": info})
    return info


def commit_info(ref):
    out = git("log", "-1", "--format=%H%x1f%h%x1f%cI%x1f%s", ref).decode("utf-8").strip()
    full, short, when, subject = out.split("\x1f", 3)
    return {"commit": full, "short": short, "date": when, "subject": subject}


def installed():
    """The installed version. For a release install the code on disk decides (an update by hand counts too)."""
    v = _read("version.json")
    if mode() == "release":
        cv = code_version()
        if cv and (not v or v.get("version") != cv):
            return {**release_info(cv), "installed_at": "", "by": ""}
    return v


def latest():
    return (_read("update_check.json") or {}).get("latest")


def pending():
    """Commits on main that are not installed yet, newest first."""
    inst, last = installed(), latest()
    if not last:
        return []
    if mode() == "release":
        if VERSION.fullmatch(str(last.get("version", ""))) and _vt(last["version"]) > _vt((inst or {}).get("version")):
            return [{"short": last["version"], "date": "", "subject": last.get("subject", "")}]
        return []
    rng = f"{inst['commit']}..{last['commit']}" if inst else last["commit"]
    try:
        out = git("log", "--format=%h%x1f%cI%x1f%s", "-n", "50", rng).decode("utf-8").strip()
    except RuntimeError:
        return []
    return [dict(zip(("short", "date", "subject"), line.split("\x1f", 2))) for line in out.splitlines() if line]


def state():
    return _read("update.json") or {}


# ---------------------------------------------------------------- the update itself (runs in its own process)
class Step(Exception):
    pass


def _run(cmd, timeout=600):
    r = subprocess.run(cmd, cwd=str(base_dir()), capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise Step((r.stderr or r.stdout).decode("utf-8", "replace").strip()[-600:])
    return r.stdout.decode("utf-8", "replace")


def _python():
    venv = base_dir() / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(venv) if venv.exists() else sys.executable


def _code_tarball(dest, paths=PATHS):
    with tarfile.open(dest, "w:gz") as tar:
        for p in sorted(set(paths) | set(PATHS)):
            f = base_dir() / p
            if f.exists():
                tar.add(f, arcname=p, filter=lambda ti: None if "__pycache__" in ti.name or ti.name.endswith(".pyc") else ti)


def _extract(data, target):
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(target, filter="data")


def _gunicorn_pid():
    r = subprocess.run(["systemctl", "show", "-p", "MainPID", "--value", "technting-cms"], capture_output=True, text=True, timeout=10)
    pid = int((r.stdout or "0").strip() or 0)
    if not pid:
        raise Step("Could not find the running dashboard process.")
    return pid


def _check(timeout=30):
    deadline = time.time() + timeout
    url = getattr(settings, "TECHNTING_CMS_UPDATE_CHECK_URL", "http://127.0.0.1:18150/login/")
    last = ""
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, headers={"Host": urllib.parse.urlparse(settings.TECHNTING_CMS_ADMIN_URL).netloc,
                                                       "X-Forwarded-Proto": "https"})
            with urllib.request.urlopen(req, timeout=5) as r:
                if r.status == 200:
                    return
                last = str(r.status)
        except Exception as exc:
            last = type(exc).__name__
        time.sleep(2)
    raise Step(f"The dashboard did not answer after the restart ({last}).")


def run_update(username="", restart=True):
    """Do the update. Returns True on success. Never raises."""
    lock = _var("update.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        return False
    st = {"running": True, "ok": None, "started_at": timezone.now().isoformat(), "by": username, "steps": [], "rolled_back": False}
    _write("update.json", st)

    def step(name, fn):
        st["steps"].append({"name": name, "status": "running", "detail": ""})
        _write("update.json", st)
        try:
            detail = fn() or ""
            st["steps"][-1].update(status="done", detail=str(detail)[:300])
        except Exception as exc:
            st["steps"][-1].update(status="failed", detail=str(exc)[:600])
            _write("update.json", st)
            raise
        _write("update.json", st)

    before = installed()
    release = mode() == "release"
    ctx = {"migrated": False, "code_tar": None, "backup": None, "files": None}
    try:
        info = {}

        def download():
            info.update(fetch())
            if release and _vt(info["version"]) > _vt((before or {}).get("version")):
                ctx["files"] = read_release(download_release(info), info["version"])
                return f"{info['version']} ({len(ctx['files'])} files)"
            return f"{info.get('short')} {info.get('subject', '')}"
        step("download", download)
        st["from"], st["to"] = (before or {}).get("short", ""), info["short"]
        if before and (before["commit"] == info["commit"] or (release and ctx["files"] is None)):
            st.update(running=False, ok=True, finished_at=timezone.now().isoformat(), note="already up to date")
            _write("update.json", st)
            return True

        def backup():
            out = io.StringIO()
            from django.core.management import call_command
            call_command("backup", stdout=out)
            root = Path(settings.VAR_DIR).parent / "backups" / "technting-cms"
            snaps = sorted(root.glob("technting-cms-*"))
            ctx["backup"] = str(snaps[-1]) if snaps else None
            code_dir = Path(settings.VAR_DIR).parent / "backups" / "code"
            code_dir.mkdir(parents=True, exist_ok=True)
            ctx["code_tar"] = code_dir / f"code-{(before or {}).get('short', 'unknown')}-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
            ctx["paths"] = site_paths({n.split("/")[0] for n in ctx["files"]}) if release else tree_paths(info["commit"])
            _code_tarball(ctx["code_tar"], ctx["paths"])
            return Path(ctx["backup"]).name if ctx["backup"] else ""
        step("backup", backup)

        changed_reqs = {"value": True}

        def files():
            paths = ctx["paths"]
            removed = []
            if release:
                new = {rel: data for rel, data in ctx["files"].items() if rel.split("/")[0] in paths}
                ctx["installed"] = new
                data = _tar_of(new)
                old = _read("release-files.json")
                removed = [str(n) for n in old if n not in new and str(n).split("/")[0] in paths] if isinstance(old, list) else []
                try:
                    changed_reqs["value"] = (base_dir() / "requirements.txt").read_bytes() != new.get("requirements.txt")
                except OSError:
                    pass
            else:
                data = git("archive", "--format=tar", info["commit"], *paths, timeout=180)
            if before and not release:
                try:
                    names = git("diff", "--name-only", "--diff-filter=D", before["commit"], info["commit"], "--", *paths).decode().split()
                    removed = [n for n in names if n]
                    req = git("diff", "--name-only", before["commit"], info["commit"], "--", "requirements.txt").decode().strip()
                    changed_reqs["value"] = bool(req)
                except RuntimeError:
                    pass
            with tarfile.open(fileobj=io.BytesIO(data)) as tar:
                ctx["new_files"] = [m.name for m in tar.getmembers() if m.isfile() and not (base_dir() / m.name).exists()]
            _extract(data, base_dir())
            for n in removed:
                (base_dir() / n).unlink(missing_ok=True)
            return f"{len(removed)} removed" if removed else ""
        step("files", files)

        def packages():
            _run([_python(), "-m", "pip", "install", "--quiet", "-r", "requirements.txt"], timeout=900)

        def database():
            ctx["migrated"] = True
            return _run([_python(), "manage.py", "migrate", "--noinput"])[-200:]

        def reload():
            os.kill(_gunicorn_pid(), signal.SIGHUP)

        if changed_reqs["value"] and (base_dir() / ".venv").exists():
            step("packages", packages)
        step("database", database)
        step("static", lambda: _run([_python(), "manage.py", "collectstatic", "--noinput"])[-120:])
        if restart:
            step("restart", reload)
            step("check", _check)
        step("publish", lambda: _run([_python(), "manage.py", "publish"], timeout=600)[-200:])
        if release:
            _write("release-files.json", sorted(ctx["installed"]))
            write_manifest(ctx["installed"], info["version"])
            info.pop("url", None)
        _write("version.json", {**info, "installed_at": timezone.now().isoformat(), "by": username})
        st.update(running=False, ok=True, finished_at=timezone.now().isoformat())
        _write("update.json", st)
        return True
    except Exception as exc:
        st["error"] = str(exc)[:600]
        try:
            if ctx["code_tar"] and Path(ctx["code_tar"]).exists():
                with open(ctx["code_tar"], "rb") as f:
                    _extract(f.read(), base_dir())
                for n in ctx.get("new_files", []):   # files the failed update added
                    (base_dir() / n).unlink(missing_ok=True)
                if ctx["migrated"] and ctx["backup"]:
                    _run([_python(), "manage.py", "restore_backup", ctx["backup"], "--yes"], timeout=600)
                if restart:
                    os.kill(_gunicorn_pid(), signal.SIGHUP)
                st["rolled_back"] = True
        except Exception as exc2:
            st["rollback_error"] = str(exc2)[:400]
        st.update(running=False, ok=False, finished_at=timezone.now().isoformat())
        _write("update.json", st)
        return False
    finally:
        lock.unlink(missing_ok=True)


def start_in_background(username):
    """Launch manage.py update_site detached, so the reload it causes does not stop it."""
    _refuse_in_demo()
    log = open(_var("update.log"), "ab")
    kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": 0x00000008}
    subprocess.Popen([_python(), "manage.py", "update_site", "--by", username], cwd=str(base_dir()),
                     stdout=log, stderr=log, stdin=subprocess.DEVNULL, **kw)
