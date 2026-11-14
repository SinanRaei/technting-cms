"""Technting Backup: encrypted offsite copies of the nightly backups (in the spirit of UpdraftPlus Premium).

  * Every snapshot made by `manage.py backup` is encrypted on the server (cms/backup_crypto.py) and copied to
    S3-compatible storage the site owner chooses: Cloudflare R2, Backblaze B2 or any S3 bucket (cms/s3.py), or a
    folder in Google Drive (cms/gdrive.py, same methods).
  * Each copy has an index (offsite.json) with the size, SHA-256 and MD5 of every encrypted file. The index is
    written last, so a copy without one is unfinished. Sizes and checksums are checked after every upload and
    every day; once a month the newest copy is downloaded, decrypted and opened in a throwaway folder.
  * Retention keeps the newest copy of each of the last 14 days, 8 weeks and 12 months (configurable). It runs after
    each upload and once a day; a copy a bucket lock still protects is skipped and tried again the next day.
  * A storage limit (10 GB by default, the free tier of R2 and B2) warns at 80 % and alerts at 95 %.
  * Opted-in administrators get an email when a backup, upload, check or restore test fails, or when the newest
    backup is more than 36 hours old.
Runs from publish_due (every 5 minutes) through the plugin's "scheduled" action. Settings live in the Setting
"backup_pro" (secret key, Google refresh token and passphrase encrypted like the SMTP
password); progress in "backup_pro_state".
"""
import json
import os
import re
import secrets
import shutil
import sqlite3
import tarfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from . import backup_crypto, dbdump
from .gdrive import Drive
from .s3 import S3, S3Error

PLUGIN = "backup-pro"
FILES = ("media.tar.gz", "manifest.json")      # always present, with one database file (dbdump.DB_FILES)


def snapshot_files(manifest):
    """Files to upload for one snapshot: the database file the manifest names, the fixed ones and every other
    archive it lists."""
    from .management.commands.backup import archives
    files = [dbdump.manifest_file(manifest)] + list(FILES)
    return files + [name for name, _ in archives(manifest) if name not in files]
NAME = re.compile(r"technting-cms-(\d{8}-\d{6})")
STALE_HOURS = 36
RETRY_MINUTES = 60
RESTORE_EVERY_DAYS = 30
ALERT_REPEAT_HOURS = 24
DEFAULT_KEEP = {"keep_daily": 14, "keep_weekly": 8, "keep_monthly": 12}
DEFAULT_QUOTA_GB = 10
PROVIDERS = {"r2": "Cloudflare R2", "b2": "Backblaze B2", "s3": "S3-compatible", "gdrive": "Google Drive"}
DRIVE_FOLDER = "Technting CMS backups"
DRIVE_CLIENT_ID = re.compile(r"[0-9]+-[A-Za-z0-9_]+\.apps\.googleusercontent\.com")


# ---------------------------------------------------------------- settings and state
def _setting(key):
    from .models import Setting
    return Setting.objects.filter(key=key).values_list("value", flat=True).first() or {}


def _save(key, value):
    from .models import Setting
    Setting.objects.update_or_create(key=key, defaults={"value": value})


def config():
    return _setting("backup_pro")


def state():
    return _setting("backup_pro_state")


def update_state(**parts):
    s = state()
    s.update(parts)
    _save("backup_pro_state", s)
    return s


def enabled():
    from . import plugins
    return PLUGIN in plugins.enabled_names()


def endpoint(cfg):
    p = cfg.get("provider")
    if p == "r2":
        return f"https://{cfg.get('account_id', '')}.r2.cloudflarestorage.com", "auto"
    if p == "b2":
        return f"https://s3.{cfg.get('region', '')}.backblazeb2.com", cfg.get("region", "")
    if p == "gdrive":
        return "https://drive.google.com", ""
    return cfg.get("endpoint", ""), cfg.get("region") or "auto"


def secrets_of(cfg):
    """(secret key, passphrase) in clear, or empty strings when missing or SECRET_KEY changed.
    For Google Drive the secret is the OAuth client secret."""
    from .mail import decrypt
    return decrypt(cfg.get("secret", "")), decrypt(cfg.get("passphrase", ""))


def ready(cfg=None):
    cfg = cfg if cfg is not None else config()
    secret, passphrase = secrets_of(cfg)
    if cfg.get("provider") == "gdrive":
        from .mail import decrypt
        return bool(cfg.get("bucket") and cfg.get("client_id") and secret and decrypt(cfg.get("refresh", "")) and passphrase)
    return bool(cfg.get("bucket") and cfg.get("access_key") and secret and passphrase)


def client(cfg=None):
    """Storage client: S3 for R2, B2 and S3; Drive for Google Drive, where "bucket" is the Drive folder name."""
    cfg = cfg if cfg is not None else config()
    if cfg.get("provider") == "gdrive":
        from .mail import decrypt
        return Drive(cfg["client_id"], secrets_of(cfg)[0], decrypt(cfg.get("refresh", "")), cfg["bucket"])
    url, region = endpoint(cfg)
    return S3(url, region, cfg["bucket"], cfg["access_key"], secrets_of(cfg)[0])


def prefix(cfg=None):
    cfg = cfg if cfg is not None else config()
    return (cfg.get("prefix") or "technting-cms").strip("/") + "/"


def suggest_passphrase():
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(5))


def check_fields(cfg):
    """Problems with the settings form values (English; translated in the view)."""
    errors = []
    if cfg.get("provider") not in PROVIDERS:
        errors.append("Choose a storage provider.")
    if cfg.get("provider") == "r2" and not re.fullmatch(r"[0-9a-f]{32}", cfg.get("account_id", "")):
        errors.append("The Cloudflare account ID is 32 letters and numbers (R2 → Overview).")
    if cfg.get("provider") == "b2" and not re.fullmatch(r"[a-z]{2}-[a-z]+-\d{3}", cfg.get("region", "")):
        errors.append("Enter the Backblaze region, for example us-west-004.")
    if cfg.get("provider") == "s3" and not re.match(r"(https://[A-Za-z0-9.-]+|http://(127\.0\.0\.1|localhost))(:\d+)?/?$", cfg.get("endpoint", "")):
        errors.append("Enter the storage address, starting with https://")
    if cfg.get("provider") == "gdrive":
        if not DRIVE_CLIENT_ID.fullmatch(cfg.get("client_id", "")):
            errors.append("The Google client ID ends with .apps.googleusercontent.com")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,59}", cfg.get("bucket", "")):
            errors.append("The Google Drive folder name may use letters, numbers, spaces, dots and dashes.")
    else:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", cfg.get("bucket", "")):
            errors.append("Enter the bucket name (small letters, numbers and dashes).")
        if not cfg.get("access_key"):
            errors.append("Enter the access key ID.")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,60}(/[A-Za-z0-9._-]{1,60})*", cfg.get("prefix", "")):
        errors.append("The folder name may use letters, numbers, dots, dashes and /.")
    if not 0 <= float(cfg.get("quota_gb", DEFAULT_QUOTA_GB)) <= 100000:
        errors.append("Enter the storage limit in GB (0 for no limit).")
    for k in DEFAULT_KEEP:
        if not 0 <= int(cfg.get(k, 0)) <= 400:
            errors.append("Keep between 0 and 400 copies.")
            break
    if int(cfg.get("keep_daily", 0)) < 1:
        errors.append("Keep at least one daily copy.")
    return errors


def test_connection(cfg):
    """Write, list, read and delete a small file: the four rights the backups need. Raises on failure."""
    cli = client(cfg)
    key = prefix(cfg) + ".technting-cms-connection-test"
    data = f"Technting CMS connection test {timezone.now().isoformat()}".encode()
    cli.put_bytes(key, data, "text/plain")
    if not any(o["key"] == key for o in cli.list(prefix(cfg) + ".technting-cms")):
        raise S3Error(0, "ListFailed", "the test file was written but not listed")
    if cli.get_bytes(key) != data:
        raise S3Error(0, "ReadFailed", "the test file came back different")
    cli.delete(key)


# ---------------------------------------------------------------- local snapshots
def backup_root():
    return Path(settings.VAR_DIR).parent / "backups" / "technting-cms"


def work_root():
    """Throwaway space for encryption and restore tests (outside backup_root, so pruning never sees it)."""
    return Path(settings.VAR_DIR).parent / "backups" / "offsite-work"


def snapshot_time(name):
    m = NAME.fullmatch(name)
    return timezone.make_aware(datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")) if m else None


def local_snapshots():
    """Finished local snapshots (manifest written), oldest first."""
    root = backup_root()
    return sorted(p for p in root.glob("technting-cms-*") if root.exists() and p.is_dir() and NAME.fullmatch(p.name)
                  and (p / "manifest.json").exists())


@contextmanager
def _lock(name="offsite"):
    """One offsite job at a time across processes (timer, dashboard). A lock older than 6 hours is stale."""
    path = Path(settings.VAR_DIR) / f"{name}.lock"
    try:
        if time.time() - path.stat().st_mtime > 6 * 3600:
            path.unlink()
    except OSError:
        pass
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        yield False
        return
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield True
    finally:
        path.unlink(missing_ok=True)


def busy():
    return (Path(settings.VAR_DIR) / "offsite.lock").exists()


# ---------------------------------------------------------------- upload
def _err(exc):
    if isinstance(exc, S3Error):
        return str(exc)[:300]
    return f"{type(exc).__name__}: {str(exc)[:200]}"


def upload(folder, cfg=None):
    """Encrypt and upload one snapshot folder, then check every object. Returns the index written."""
    from .management.commands.backup import sha256
    cfg = cfg if cfg is not None else config()
    _, passphrase = secrets_of(cfg)
    cli, base = client(cfg), prefix(cfg) + folder.name + "/"
    from .management.commands.backup import archives
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for name, key in archives(manifest):
        if sha256(folder / name) != manifest[key]["sha256"]:
            raise ValueError(f"local {name} does not match its checksum; not uploading a damaged backup")
    work = work_root() / ("upload-" + folder.name)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        index = {"format": 1, "snapshot": folder.name, "created": manifest.get("created"), "key_id": cfg.get("key_id", ""),
                 "cipher": "AES-256-GCM, scrypt key (cms/backup_crypto.py)", "files": {}}
        for name in snapshot_files(manifest):
            enc = work / (name + ".enc")
            size, sha, md5 = backup_crypto.encrypt_file(folder / name, enc, passphrase)
            cli.put_file(base + enc.name, enc, sha, size)
            index["files"][enc.name] = {"bytes": size, "sha256": sha, "md5": md5}
            enc.unlink()
        for name, meta in index["files"].items():
            got = cli.head(base + name)
            if not got or got["size"] != meta["bytes"] or ("-" not in got["etag"] and got["etag"] and got["etag"] != meta["md5"]):
                raise ValueError(f"{name} did not arrive complete")
        index["uploaded"] = timezone.now().isoformat()
        cli.put_bytes(base + "offsite.json", json.dumps(index, indent=1).encode())
        return index
    finally:
        shutil.rmtree(work, ignore_errors=True)


def remote_snapshots(cli=None, cfg=None):
    """Copies in the bucket: [{name, bytes, complete, modified}], newest first."""
    cfg = cfg if cfg is not None else config()
    cli = cli or client(cfg)
    base = prefix(cfg)
    groups = {}
    for o in cli.list(base):
        rest = o["key"][len(base):]
        if "/" not in rest:
            continue
        name, file = rest.split("/", 1)
        if not NAME.fullmatch(name):
            continue
        g = groups.setdefault(name, {"name": name, "bytes": 0, "files": {}, "modified": ""})
        g["bytes"] += o["size"]
        g["files"][file] = o
        g["modified"] = max(g["modified"], o["modified"])
    out = []
    for g in groups.values():
        g["complete"] = "offsite.json" in g["files"]
        out.append(g)
    return sorted(out, key=lambda g: g["name"], reverse=True)


def keep_reasons(names, daily, weekly, monthly):
    """{name: ["newest", "daily", "weekly", "monthly"]} for the copies to keep: the newest copy of each of the last
    `daily` days, `weekly` ISO weeks and `monthly` months, and always the newest copy."""
    dated = sorted(((snapshot_time(n), n) for n in names if snapshot_time(n)), reverse=True)
    reasons = {dated[0][1]: ["newest"]} if dated else {}
    rules = (("daily", daily, lambda d: d.date()), ("weekly", weekly, lambda d: d.isocalendar()[:2]),
             ("monthly", monthly, lambda d: (d.year, d.month)))
    for label, count, bucket in rules:
        seen = set()
        for d, n in dated:
            b = bucket(timezone.localtime(d))
            if b in seen:
                continue
            if len(seen) >= count:
                break
            seen.add(b)
            reasons.setdefault(n, []).append(label)
    return reasons


def keep_set(names, daily, weekly, monthly):
    return set(keep_reasons(names, daily, weekly, monthly))


def _keep_counts(cfg):
    return [int(cfg.get(k, v)) for k, v in DEFAULT_KEEP.items()]


def apply_retention(cli, snaps, cfg):
    """Delete copies outside the retention policy and unfinished uploads older than two days.

    Returns (names removed, names that could not be deleted). A copy that cannot be deleted yet, for example because
    a bucket lock protects it for some days, is simply tried again on the next run."""
    keep = keep_set([s["name"] for s in snaps if s["complete"]], *_keep_counts(cfg))
    old = timezone.now() - timedelta(days=2)
    removed, blocked = [], []
    for s in snaps:
        stale_partial = not s["complete"] and (snapshot_time(s["name"]) or old) < old
        if (s["complete"] and s["name"] not in keep) or stale_partial:
            try:
                # the index goes first, so an interrupted delete leaves an unfinished copy that is cleaned up later
                for f in sorted(s["files"], key=lambda f: f != "offsite.json"):
                    cli.delete(s["files"][f]["key"])
                removed.append(s["name"])
            except S3Error:
                blocked.append(s["name"])
    return removed, blocked


def prune(cli=None, cfg=None):
    """Apply retention and remember the result. Failures here never mark an upload as failed."""
    cfg = cfg if cfg is not None else config()
    try:
        cli = cli or client(cfg)
        remote = remote_snapshots(cli, cfg)
        removed, blocked = apply_retention(cli, remote, cfg)
        gone = set(removed)
        update_state(retention={"at": timezone.now().isoformat(), "ok": True, "removed": removed, "blocked": blocked},
                     remote=_remember_remote([s for s in remote if s["name"] not in gone], cfg))
        return removed
    except Exception as exc:
        update_state(retention={"at": timezone.now().isoformat(), "ok": False, "removed": [], "blocked": [], "error": _err(exc)})
        return []


def _remember_remote(snaps, cfg=None, ok=True, error=""):
    cfg = cfg if cfg is not None else config()
    done = [s for s in snaps if s["complete"]]
    reasons = keep_reasons([s["name"] for s in done], *_keep_counts(cfg))
    return {"checked_at": timezone.now().isoformat(), "ok": ok, "error": error, "count": len(done),
            "bytes": sum(s["bytes"] for s in snaps), "names": [s["name"] for s in done][:400],
            "copies": [{"name": s["name"], "bytes": s["bytes"], "keep": reasons.get(s["name"], [])} for s in done][:400],
            "newest": done[0]["name"] if done else ""}


def sync(force=False, log=None):
    """Upload the newest local snapshot if it is not offsite yet, then apply retention."""
    cfg = config()
    if not ready(cfg):
        return "not set up"
    snaps = local_snapshots()
    if not snaps:
        return "no local backup"
    newest, st = snaps[-1], state()
    last = st.get("upload") or {}
    if last.get("name") == newest.name and last.get("ok"):
        return "up to date"
    if not force and not last.get("ok") and last.get("at") and \
            datetime.fromisoformat(last["at"]) > timezone.now() - timedelta(minutes=RETRY_MINUTES):
        return "waiting to retry"
    started = time.monotonic()
    try:
        index = upload(newest, cfg)
        update_state(upload={"name": newest.name, "at": timezone.now().isoformat(), "ok": True, "error": "",
                             "bytes": sum(f["bytes"] for f in index["files"].values()),
                             "seconds": round(time.monotonic() - started, 1)})
    except Exception as exc:
        update_state(upload={"name": newest.name, "at": timezone.now().isoformat(), "ok": False, "error": _err(exc)})
        msg = f"upload of {newest.name} failed: {_err(exc)}"
    else:
        removed = prune(cfg=cfg)
        msg = f"uploaded {newest.name}; removed {len(removed)} old copies"
    if log:
        log(f"offsite: {msg}")
    return msg


# ---------------------------------------------------------------- checks
def verify(cfg=None):
    """Compare every copy in the bucket with its index (sizes and MD5 from the listing; no download)."""
    cfg = cfg if cfg is not None else config()
    cli = client(cfg)
    problems = []
    try:
        snaps = remote_snapshots(cli, cfg)
        for s in snaps:
            if not s["complete"]:
                continue
            index = json.loads(cli.get_bytes(s["files"]["offsite.json"]["key"]))
            for name, meta in index.get("files", {}).items():
                got = s["files"].get(name)
                if not got:
                    problems.append(f"{s['name']}: {name} is missing")
                elif got["size"] != meta["bytes"] or ("-" not in got["etag"] and got["etag"] and got["etag"] != meta["md5"]):
                    problems.append(f"{s['name']}: {name} changed")
        result = {"at": timezone.now().isoformat(), "ok": not problems, "checked": sum(1 for s in snaps if s["complete"]),
                  "detail": "; ".join(problems[:5])}
        update_state(verify=result, remote=_remember_remote(snaps))
    except Exception as exc:
        result = {"at": timezone.now().isoformat(), "ok": False, "checked": 0, "detail": _err(exc)}
        update_state(verify=result)
    return result


def restore_test(name=None, cfg=None):
    """Download a copy (the newest by default), decrypt it and open it in a throwaway folder."""
    cfg = cfg if cfg is not None else config()
    _, passphrase = secrets_of(cfg)
    work = work_root() / "restore-test"
    shutil.rmtree(work, ignore_errors=True)
    result = {"at": timezone.now().isoformat(), "ok": False, "name": name or "", "detail": ""}
    try:
        work.mkdir(parents=True)
        out = fetch(name, work, cfg, passphrase)
        result["name"] = out["name"]
        manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
        pages, entries = open_database(work, manifest)
        media = work / "media"
        with tarfile.open(work / "media.tar.gz", "r:gz") as tar:
            tar.extractall(media, filter="data")
        files = sum(1 for f in media.rglob("*") if f.is_file())
        if files != manifest["media"]["files"]:
            raise ValueError(f"{files} media files restored, the backup lists {manifest['media']['files']}")
        detail = f"{pages} pages, {entries} records, {files} media files"
        result.update(ok=True, pages=pages, entries=entries, files=files, detail=detail)
    except Exception as exc:
        result["detail"] = _err(exc)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    update_state(restore=result)
    return result


def open_database(folder, manifest):
    """Open the database file of a downloaded copy. Returns (pages, entries). SQLite: integrity check and counts.
    MySQL / MariaDB and PostgreSQL dumps: read to the end (complete, creates the content tables); the counts are the
    ones recorded at backup time, since loading the dump would need a database server."""
    engine, file = dbdump.manifest_engine(manifest), folder / dbdump.manifest_file(manifest)
    if engine == "sqlite":
        with sqlite3.connect(str(file)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("the database copy is damaged")
            pages = db.execute("SELECT COUNT(*) FROM cms_page").fetchone()[0]
            entries = db.execute("SELECT COUNT(*) FROM cms_entry").fetchone()[0]
        db.close()
        return pages, entries
    try:
        found = dbdump.check_dump(file, engine, tables=("cms_page", "cms_entry"))
    except dbdump.DumpError as exc:
        raise ValueError(str(exc)) from None
    if found != {"cms_page", "cms_entry"}:
        raise ValueError("the database dump has no content tables")
    db = manifest["database"]
    return db.get("pages", 0), db.get("entries", 0)


def fetch(name, dest, cfg=None, passphrase=None):
    """Download and decrypt a copy into dest (a folder `manage.py restore_backup` accepts). Checks every checksum."""
    from .management.commands.backup import sha256
    cfg = cfg if cfg is not None else config()
    passphrase = passphrase or secrets_of(cfg)[1]
    cli = client(cfg)
    if not name:
        done = [s for s in remote_snapshots(cli, cfg) if s["complete"]]
        if not done:
            raise ValueError("no finished copy in the bucket")
        name = done[0]["name"]
    if not NAME.fullmatch(name):
        raise ValueError("unknown copy name")
    base = prefix(cfg) + name + "/"
    index = json.loads(cli.get_bytes(base + "offsite.json"))
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    # every file the index lists that a backup can contain
    from .management.commands.backup import ARCHIVES
    known = set(FILES) | {name for name, _ in ARCHIVES}
    names = [n[:-4] for n in index["files"] if n.endswith(".enc") and n[:-4] in known]
    for file in FILES:
        if file not in names:
            raise ValueError(f"{file}.enc is missing from this copy")
    if not any(file in names for file in dbdump.DB_FILES):
        raise ValueError("the database file is missing from this copy")
    for file in names:
        enc = dest / (file + ".enc")
        meta = index["files"][enc.name]
        if cli.get_to_file(base + enc.name, enc) != meta["sha256"]:
            raise ValueError(f"{enc.name} downloaded does not match its checksum")
        try:
            backup_crypto.decrypt_file(enc, dest / file, passphrase)
        except backup_crypto.DecryptError as exc:
            hint = " (this copy was made with an older passphrase)" if index.get("key_id") != cfg.get("key_id") else ""
            raise ValueError(f"{file}: {exc}{hint}") from None
        enc.unlink()
    from .management.commands.backup import archives
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    for file, key in archives(manifest):
        if sha256(dest / file) != manifest[key]["sha256"]:
            raise ValueError(f"{file} does not match the checksum made at backup time")
    return {"name": name, "folder": str(dest)}


# ---------------------------------------------------------------- problems and alerts
def _age_hours(iso_or_dt, now):
    if not iso_or_dt:
        return None
    dt = datetime.fromisoformat(iso_or_dt) if isinstance(iso_or_dt, str) else iso_or_dt
    return (now - dt).total_seconds() / 3600


def problems(now=None, include_local=True):
    """[{key, level, text, detail}] about backups. Keys of level "high" are emailed to opted-in admins."""
    now = now or timezone.now()
    out = []
    if include_local:
        snaps = local_snapshots()
        age = _age_hours(snapshot_time(snaps[-1].name), now) if snaps else None
        if age is None or age > STALE_HOURS:
            out.append({"key": "backup_stale", "level": "high", "text": "The last backup is more than 36 hours old",
                        "detail": f"{round(age)} h" if age is not None else ""})
        failed = _setting("backup_failed")
        if failed.get("at") and (not snaps or datetime.fromisoformat(failed["at"]) > snapshot_time(snaps[-1].name)):
            out.append({"key": "backup_failed", "level": "high", "text": "The last backup failed", "detail": failed.get("error", "")})
    if not enabled():
        return out
    cfg, st = config(), state()
    if not ready(cfg):
        out.append({"key": "offsite_not_set_up", "level": "medium", "text": "Offsite backups are not set up", "detail": ""})
        return out
    up = st.get("upload") or {}
    if up and not up.get("ok"):
        out.append({"key": "upload_failed", "level": "high", "text": "Copying the backup offsite failed", "detail": up.get("error", "")})
    remote = st.get("remote") or {}
    newest = snapshot_time(remote.get("newest", "")) if remote.get("newest") else None
    since = newest or (datetime.fromisoformat(cfg["saved_at"]) if cfg.get("saved_at") else now)
    if _age_hours(since, now) > STALE_HOURS:
        out.append({"key": "offsite_stale", "level": "high", "text": "The newest offsite copy is more than 36 hours old",
                    "detail": f"{round(_age_hours(newest, now))} h" if newest else ""})
    v = st.get("verify") or {}
    if v and not v.get("ok"):
        out.append({"key": "verify_failed", "level": "high", "text": "The offsite copies failed the integrity check", "detail": v.get("detail", "")})
    r = st.get("restore") or {}
    if r and not r.get("ok"):
        out.append({"key": "restore_failed", "level": "high", "text": "The monthly restore test failed", "detail": r.get("detail", "")})
    restore_age = _age_hours(r.get("at") or cfg.get("saved_at"), now) or 0
    if restore_age > (RESTORE_EVERY_DAYS + 10) * 24:
        out.append({"key": "restore_overdue", "level": "medium", "text": "No restore test in the last 40 days", "detail": ""})
    ret = st.get("retention") or {}
    if ret and not ret.get("ok"):
        out.append({"key": "retention_failed", "level": "medium", "text": "Old offsite copies could not be removed", "detail": ret.get("error", "")})
    stuck = [n for n in ret.get("blocked") or [] if _age_hours(snapshot_time(n), now) > 45 * 24]
    if stuck:
        out.append({"key": "retention_blocked", "level": "medium", "text": "Some old offsite copies cannot be deleted (check the bucket lock)",
                    "detail": ", ".join(stuck[:3])})
    quota = quota_bytes(cfg)
    used = remote.get("bytes") or 0
    if quota and used > quota * 0.8:
        out.append({"key": "quota", "level": "high" if used > quota * 0.95 else "medium",
                    "text": "Offsite storage is almost full", "detail": f"{used / 1e9:.1f} / {quota / 1e9:.0f} GB"})
    return out


def quota_bytes(cfg=None):
    """The storage size to stay under (R2 and B2 are free up to 10 GB); 0 means no limit."""
    cfg = cfg if cfg is not None else config()
    try:
        return int(float(cfg.get("quota_gb", DEFAULT_QUOTA_GB)) * 1e9)
    except (TypeError, ValueError):
        return int(DEFAULT_QUOTA_GB * 1e9)


def alert_recipients():
    from django.contrib.auth import get_user_model
    ids = _setting("backup_alerts").get("users") or []
    return list(get_user_model().objects.filter(pk__in=ids, is_active=True, is_superuser=True).exclude(email=""))


def wants_alerts(user):
    return user.pk in (_setting("backup_alerts").get("users") or [])


def set_alerts(user, on):
    ids = set(_setting("backup_alerts").get("users") or [])
    (ids.add if on else ids.discard)(user.pk)
    _save("backup_alerts", {"users": sorted(ids)})


def check_alerts(now=None):
    """Email new high problems (and repeat daily while they last). Returns the number of emails sent."""
    from . import mail
    from .ui_i18n import tr
    now = now or timezone.now()
    high = [p for p in problems(now) if p["level"] == "high"]
    sent_at = state().get("alerts") or {}
    due = [p for p in high if not sent_at.get(p["key"]) or _age_hours(sent_at[p["key"]], now) >= ALERT_REPEAT_HOURS]
    keep = {p["key"]: sent_at[p["key"]] for p in high if p["key"] in sent_at}   # solved problems are forgotten
    people = alert_recipients()
    sent = 0
    if due and people and mail.ready():
        lines = []
        for lang in ("en", "ar"):
            lines += [tr(p["text"], lang) + (f" ({p['detail']})" if p["detail"] else "") for p in due] + [""]
        body = "\n".join(["Technting CMS backups need attention · النسخ الاحتياطية تحتاج إلى انتباه", ""] + lines +
                         [f"{settings.TECHNTING_CMS_ADMIN_URL}/settings/backups/", "", "--",
                          "You get this email because you turned on backup alerts on the Backups page.",
                          "تصلكم هذه الرسالة لأنكم فعّلتم تنبيهات النسخ الاحتياطي في صفحة النسخ الاحتياطية."])
        try:
            mail.send("Technting CMS: backup problem · مشكلة في النسخ الاحتياطي", body, [u.email for u in people])
            sent = len(people)
            keep.update({p["key"]: now.isoformat() for p in due})
        except Exception:
            pass
    if keep != sent_at:
        update_state(alerts=keep)
    return sent


# ---------------------------------------------------------------- schedule
def tick(now=None, log=None):
    """Called every 5 minutes: upload, daily integrity check, monthly restore test, alerts."""
    from .demo import on as demo_on
    if demo_on():
        return   # the public demo never talks to offsite storage
    now = now or timezone.now()
    with _lock() as got:
        if not got:
            return
        if ready():
            sync(log=log)
            checked = (state().get("verify") or {}).get("at")
            if not checked or _age_hours(checked, now) >= 24:
                prune()   # also retries copies a bucket lock protected yesterday
                v = verify()
                if log and not v["ok"]:
                    log(f"offsite: integrity check failed: {v['detail']}")
            st = state()
            last = (st.get("restore") or {}).get("at")
            if (st.get("remote") or {}).get("count") and (not last or _age_hours(last, now) >= RESTORE_EVERY_DAYS * 24) \
                    and 3 <= timezone.localtime(now).hour < 6:
                r = restore_test()
                if log:
                    log(f"offsite: restore test {'passed' if r['ok'] else 'FAILED'}: {r['detail']}")
    n = check_alerts(now)
    if n and log:
        log(f"offsite: backup alert sent to {n} admin(s)")


def run_in_background(job):
    """Start an upload ("upload") or restore test ("restore") from the dashboard. False if one is already running."""
    from .demo import on as demo_on
    if busy() or demo_on():
        return False

    def run():
        from django.db import connection
        try:
            with _lock() as got:
                if got:
                    sync(force=True) if job == "upload" else restore_test()
        finally:
            connection.close()
    threading.Thread(target=run, daemon=True).start()
    return True


# ---------------------------------------------------------------- status for pages and the weekly summary
def status():
    cfg, st = config(), state()
    url, _ = endpoint(cfg) if cfg else ("", "")
    uploaded = set((st.get("remote") or {}).get("names") or [])
    return {"enabled": enabled(), "ready": ready(cfg), "cfg": cfg, "provider": PROVIDERS.get(cfg.get("provider"), ""),
            "endpoint": url, "upload": st.get("upload") or {}, "remote": st.get("remote") or {}, "verify": st.get("verify") or {},
            "restore": st.get("restore") or {}, "uploaded": uploaded, "busy": busy(), "quota": quota_bytes(cfg),
            "retention": st.get("retention") or {},
            "problems": problems(include_local=False) if enabled() else []}


def summary(now=None):
    """Language-neutral facts for the weekly summary, or None when the plugin is off."""
    if not enabled():
        return None
    st = state()
    remote = st.get("remote") or {}
    newest = snapshot_time(remote["newest"]) if remote.get("newest") else None
    r = st.get("restore") or {}
    return {"ready": ready(), "newest": timezone.localtime(newest) if newest else None, "count": remote.get("count", 0),
            "bytes": remote.get("bytes", 0), "restore_ok": r.get("ok") if r else None,
            "restore_at": timezone.localtime(datetime.fromisoformat(r["at"])) if r.get("at") else None}
