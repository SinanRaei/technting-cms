"""Technting Backup pages: offsite settings and the buttons on the Backups page (cms/offsite.py does the work).

Google Drive is connected before saving: "Connect Google Drive" asks Google for a short code (device flow), the
admin types it at google.com/device, and "finish" fetches the refresh token. Until "Test and save", the connection
waits in the Setting "backup_pro_gdrive" (client secret, device code and refresh token encrypted)."""
import secrets
import shutil
import tarfile
import tempfile
from datetime import datetime, timedelta

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import backup_crypto, gdrive, mail, offsite
from .audit import audit
from .models import Setting
from .s3 import S3Error
from .views import _t, admin_required

TEXT_FIELDS = ("provider", "account_id", "region", "endpoint", "bucket", "prefix", "access_key", "client_id")
DRIVE_KEY = "backup_pro_gdrive"


def _drive_conn():
    return Setting.objects.filter(key=DRIVE_KEY).values_list("value", flat=True).first() or {}


def _form_config(post, current):
    cfg = {k: post.get(k, "").strip() for k in TEXT_FIELDS}
    cfg["account_id"] = cfg["account_id"].lower()
    cfg["prefix"] = cfg["prefix"].strip("/") or "technting-cms"
    if cfg["provider"] == "gdrive":
        cfg.update(account_id="", region="", endpoint="", access_key="",
                   bucket=post.get("drive_folder", "").strip() or offsite.DRIVE_FOLDER)
    else:
        cfg["client_id"] = ""
    for k, default in offsite.DEFAULT_KEEP.items():
        try:
            cfg[k] = int(post.get(k) or default)
        except ValueError:
            cfg[k] = -1
    try:
        cfg["quota_gb"] = float(post.get("quota_gb") or offsite.DEFAULT_QUOTA_GB)
    except ValueError:
        cfg["quota_gb"] = -1
    for k in ("passphrase", "key_id", "saved_at"):
        if current.get(k):
            cfg[k] = current[k]
    if cfg["provider"] == "gdrive":
        for src in (_drive_conn(), current if current.get("provider") == "gdrive" else {}):
            if src.get("refresh") and src.get("client_id") == cfg["client_id"]:
                cfg.update(secret=src["secret"], refresh=src["refresh"], account=src.get("account", ""))
                break
        return cfg
    secret = post.get("secret_key", "").strip()
    if secret:
        cfg["secret"] = mail.encrypt(secret)
    elif current.get("secret") and current.get("provider") != "gdrive" and current.get("access_key") == cfg["access_key"]:
        cfg["secret"] = current["secret"]   # empty field keeps the saved secret for the same key
    return cfg


def _drive_url():
    return reverse("cms:offsite_settings") + "?provider=gdrive"


def _drive_connect(request, current):
    """Ask Google for a sign-in code for the client ID on the form."""
    client_id = request.POST.get("client_id", "").strip()
    secret = request.POST.get("client_secret", "").strip()
    errors = [] if offsite.DRIVE_CLIENT_ID.fullmatch(client_id) else ["The Google client ID ends with .apps.googleusercontent.com"]
    if secret:
        secret = mail.encrypt(secret)
    else:   # an empty field keeps the secret saved for the same client
        secret = next((src["secret"] for src in (_drive_conn(), current)
                       if src.get("secret") and src.get("client_id") == client_id), "")
    if not secret:
        errors.append("Enter the Google client secret.")
    if errors:
        for e in errors:
            messages.error(request, _t(request, e))
        return redirect(_drive_url())
    try:
        out = gdrive.device_start(client_id)
    except S3Error as exc:
        messages.error(request, _t(request, "Google refused:") + f" {exc.code} ({exc.status})")
        return redirect(_drive_url())
    except (OSError, ValueError) as exc:
        messages.error(request, _t(request, "Could not reach Google:") + f" {type(exc).__name__}")
        return redirect(_drive_url())
    expires = timezone.now() + timedelta(seconds=int(out.get("expires_in", 1800)))
    Setting.objects.update_or_create(key=DRIVE_KEY, defaults={"value": {
        "client_id": client_id, "secret": secret, "device": mail.encrypt(out["device_code"]), "user_code": out["user_code"],
        "url": out["verification_url"], "expires": expires.isoformat()}})
    audit(request, "offsite_gdrive_connect", client_id)
    return redirect(_drive_url())


def _drive_finish(request):
    """Check once whether the admin allowed access at google.com/device; keep the refresh token if so."""
    conn = _drive_conn()
    if not conn.get("device"):
        messages.error(request, _t(request, "Press Connect Google Drive first."))
        return redirect(_drive_url())
    if datetime.fromisoformat(conn["expires"]) < timezone.now():
        messages.error(request, _t(request, "The code expired. Press Connect Google Drive again."))
        return redirect(_drive_url())
    secret = mail.decrypt(conn["secret"])
    try:
        refresh = gdrive.device_poll(conn["client_id"], secret, mail.decrypt(conn["device"]))
    except S3Error as exc:
        if exc.code == "slow_down":
            messages.warning(request, _t(request, "Google is still waiting. Wait a few seconds and press the button again."))
        elif exc.code == "access_denied":
            messages.error(request, _t(request, "Access was refused in Google. Press Connect Google Drive to try again."))
        else:
            messages.error(request, _t(request, "Google refused:") + f" {exc.code} ({exc.status})")
        return redirect(_drive_url())
    except (OSError, ValueError) as exc:
        messages.error(request, _t(request, "Could not reach Google:") + f" {type(exc).__name__}")
        return redirect(_drive_url())
    if refresh is None:
        messages.warning(request, _t(request, "Google is still waiting. Enter the code at the address shown, allow access, then press the button again."))
        return redirect(_drive_url())
    account = gdrive.Drive(conn["client_id"], secret, refresh, offsite.DRIVE_FOLDER).account()
    Setting.objects.update_or_create(key=DRIVE_KEY, defaults={"value": {
        "client_id": conn["client_id"], "secret": conn["secret"], "refresh": mail.encrypt(refresh), "account": account,
        "connected_at": timezone.now().isoformat()}})
    audit(request, "offsite_gdrive_connected", account)
    messages.success(request, _t(request, "Google Drive is connected. Now set the passphrase and press Test and save."))
    return redirect(_drive_url())


@admin_required
def offsite_settings(request):
    current = offsite.config()
    if request.method == "POST":
        if request.POST.get("action") == "gdrive_connect":
            return _drive_connect(request, current)
        if request.POST.get("action") == "gdrive_finish":
            return _drive_finish(request)
        if request.POST.get("action") == "remove":
            Setting.objects.filter(key__in=["backup_pro", "backup_pro_state", DRIVE_KEY]).delete()
            audit(request, "offsite_settings_remove")
            messages.success(request, _t(request, "Offsite settings removed. Copies already in the bucket were not deleted."))
            return redirect("cms:backups")
        cfg = _form_config(request.POST, current)
        errors = [_t(request, e) for e in offsite.check_fields(cfg)]
        if cfg["provider"] == "gdrive" and not cfg.get("refresh"):
            errors.append(_t(request, "Connect Google Drive first: press Connect Google Drive and allow access."))
        elif not cfg.get("secret"):
            errors.append(_t(request, "Enter the secret access key."))
        passphrase = request.POST.get("passphrase", "")
        if passphrase or not current.get("passphrase"):
            if len(passphrase) < 12:
                errors.append(_t(request, "The passphrase must be at least 12 characters."))
            elif passphrase != request.POST.get("passphrase2", ""):
                errors.append(_t(request, "The two passphrases are not the same."))
            elif not request.POST.get("saved_passphrase"):
                errors.append(_t(request, "Confirm that you saved the passphrase somewhere safe."))
            else:
                cfg["passphrase"], cfg["key_id"] = mail.encrypt(passphrase), backup_crypto.key_id(passphrase)
        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "cms/offsite_settings.html", _context(request, cfg), status=400)
        try:
            offsite.test_connection(cfg)
        except S3Error as exc:
            messages.error(request, _t(request, "The storage refused the test:") + f" {exc.code} ({exc.status})")
            return render(request, "cms/offsite_settings.html", _context(request, cfg), status=400)
        except (OSError, ValueError) as exc:
            messages.error(request, _t(request, "Could not reach the storage:") + f" {type(exc).__name__}")
            return render(request, "cms/offsite_settings.html", _context(request, cfg), status=400)
        cfg.setdefault("saved_at", timezone.now().isoformat())
        moved = any(current.get(k) != cfg.get(k) for k in ("provider", "account_id", "region", "endpoint", "bucket", "prefix",
                                                           "client_id", "account"))
        changed_passphrase = current.get("key_id") and current["key_id"] != cfg["key_id"]
        Setting.objects.update_or_create(key="backup_pro", defaults={"value": cfg})
        Setting.objects.filter(key=DRIVE_KEY).delete()   # the Drive connection now lives in the saved settings
        if moved:
            offsite.update_state(upload={}, remote={}, verify={})
        audit(request, "offsite_settings_save", f"{offsite.PROVIDERS[cfg['provider']]} {cfg['bucket']}/{cfg['prefix']}")
        messages.success(request, _t(request, "Connection works. Offsite settings saved. The newest backup is copied within 5 minutes."))
        if changed_passphrase:
            messages.warning(request, _t(request, "Copies made before today need the old passphrase. Keep it until they are removed by the retention policy."))
        return redirect("cms:backups")
    return render(request, "cms/offsite_settings.html", _context(request, current))


def _context(request, cfg):
    saved, conn = offsite.config(), _drive_conn()
    on_drive = saved.get("provider") == "gdrive"
    pending = conn if conn.get("device") and datetime.fromisoformat(conn["expires"]) > timezone.now() else {}
    if conn.get("refresh"):
        connected = conn.get("account") or True
    elif on_drive and saved.get("refresh") and not pending:
        connected = saved.get("account") or True
    else:
        connected = False
    drive = {"client_id": cfg.get("client_id") or conn.get("client_id") or (saved.get("client_id") if on_drive else ""),
             "folder": cfg.get("bucket") if cfg.get("provider") == "gdrive" else offsite.DRIVE_FOLDER,
             "has_secret": bool(conn.get("secret") or on_drive and saved.get("secret")), "pending": pending,
             "connected": connected}
    provider = request.GET.get("provider")
    if provider not in offsite.PROVIDERS:
        provider = cfg.get("provider") or ("gdrive" if conn else "r2")
    return {"cfg": cfg, "has_secret": bool(saved.get("secret")) and not on_drive, "has_passphrase": bool(saved.get("passphrase")),
            "can_remove": bool(saved), "providers": offsite.PROVIDERS,
            "keep": {k: cfg.get(k, v) for k, v in offsite.DEFAULT_KEEP.items()},
            "quota_gb": cfg.get("quota_gb", offsite.DEFAULT_QUOTA_GB),
            "suggestion": offsite.suggest_passphrase(), "enabled": offsite.enabled(), "provider": provider, "drive": drive}


@admin_required
@require_POST
def offsite_run(request):
    action = request.POST.get("action")
    if action in ("alerts_on", "alerts_off"):
        offsite.set_alerts(request.user, action == "alerts_on")
        if action == "alerts_on" and not request.user.email:
            messages.warning(request, _t(request, "Add your email address in My account to receive alerts."))
        else:
            messages.success(request, _t(request, "Saved."))
    elif action in ("upload", "restore") and offsite.ready():
        if offsite.run_in_background(action):
            audit(request, "offsite_" + action)
            messages.success(request, _t(request, "Started. Reload this page in a minute to see the result."))
        else:
            messages.error(request, _t(request, "Another offsite job is running. Try again in a few minutes."))
    return redirect("cms:backups")


@admin_required
@require_POST
def offsite_download(request, name):
    """Download a copy from the storage, decrypt it here and hand it over as one .tar (the same layout as a local
    backup download), so a copy can be restored even when it is no longer on the server."""
    if not offsite.NAME.fullmatch(name) or not offsite.ready():
        raise Http404
    work = offsite.work_root() / f"download-{secrets.token_hex(6)}"
    try:
        offsite.fetch(name, work / name)
        buf = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for f in sorted((work / name).iterdir()):
                tar.add(f, arcname=f"{name}/{f.name}")
        buf.seek(0)
    except Exception as exc:   # shown to the admin; storage errors carry no secrets
        messages.error(request, _t(request, "Download failed:") + f" {offsite._err(exc)}")
        return redirect("cms:backups")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    audit(request, "offsite_download", name)
    return FileResponse(buf, as_attachment=True, filename=f"{name}-offsite.tar", content_type="application/x-tar")
