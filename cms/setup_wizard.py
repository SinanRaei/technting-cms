"""First-run setup wizard (in the spirit of the WordPress five-minute install).

While the database has no users and the Setting "setup_complete" is missing, SetupMiddleware sends every dashboard
URL to /setup/. The wizard collects, one step at a time and kept in the session until the end:

  site        site name and public site URL
  languages   English, Arabic or both, and the default language
  admin       the first administrator (Django password validators apply)
  theme       one of the installed themes
  email       optional SMTP account, with a test email; can be skipped
  licence     the free licence key e-mailed with the download (required; cms/licence.py). Checked with the licence
              server for the site address of step 1; a key the server refuses is not accepted, and when the server
              cannot be reached the key is kept and checked again later. Not asked in the public demo.
  finish     optional demo content (manage.py seed_demo), then everything is saved at once

Where things are stored, the same places the rest of Technting CMS reads them from:
  site name, site URL, theme   TECHNTING_CMS_SITE_NAME / _SITE_URL / _THEME in the .env next to manage.py, or in
                               VAR_DIR/site.env when that file cannot be written (Docker: the code folder is read-only)
  languages                    Language rows
  email                        the Setting "smtp", password encrypted exactly like Settings -> Email (cms/mail.py)
  setup done                   the Setting "setup_complete"

After the finish the administrator is signed in, the site is published once and /setup/ answers 404. Gunicorn
workers are reloaded (SIGHUP to the master, like the updater) so every worker reads the new .env values.
An optional TECHNTING_CMS_SETUP_TOKEN (set by install.sh) must be given once before the wizard opens.
"""
import hmac
import json
import os
import re
import signal
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone, translation

from . import dbdump, ui_i18n
from .audit import audit

FLAG = "setup_complete"
STEPS = ("site", "languages", "admin", "theme", "email", "licence", "finish")
SESSION_KEY = "setup"
ENV_KEYS = {"site_name": "TECHNTING_CMS_SITE_NAME", "site_url": "TECHNTING_CMS_SITE_URL", "theme": "TECHNTING_CMS_THEME"}
LANGS = {
    "en": {"name": "English", "native_name": "English", "direction": "ltr", "locale": "en_GB"},
    "ar": {"name": "Arabic", "native_name": "العربية", "direction": "rtl", "locale": "ar_AR"},
}
POST_LIMIT, MAIL_LIMIT, TOKEN_LIMIT, WINDOW = 60, 5, 8, 900   # per address, per 15 minutes

_complete = False   # once setup is done it stays done, so each process stops asking the database


def is_complete():
    global _complete
    if not _complete:
        from .models import Setting
        _complete = Setting.objects.filter(key=FLAG).exists() or get_user_model().objects.exists()
    return _complete


def reset_cache():
    """Tests only: forget the cached answer."""
    global _complete
    _complete = False


# ---------------------------------------------------------------- .env values
def env_target():
    main = Path(settings.BASE_DIR) / ".env"
    if main.exists() and os.access(main, os.W_OK):
        return main
    return Path(settings.VAR_DIR) / "site.env"


def update_env_file(path, values):
    """Set KEY=VALUE lines in an env file, keeping every other line (and comments) as it is."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    left = dict(values)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in left:
            out.append(f"{key}={left.pop(key)}")
        else:
            out.append(line)
    if left and not path.exists():
        out.insert(0, "# Written by the Technting CMS setup wizard. Values in the real environment or in .env win.")
    out += [f"{k}={v}" for k, v in left.items()]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def locked(env_key):
    """True when the server environment itself sets this value (Docker compose, systemd): the wizard cannot change it."""
    return env_key in getattr(settings, "TECHNTING_CMS_ENV_FROM_PROCESS", ())


def apply_env(values):
    """Write the values to the env file and use them in this process right away."""
    values = {k: v for k, v in values.items() if not locked(k)}
    if not values:
        return None
    path = update_env_file(env_target(), values)
    for key, value in values.items():
        os.environ[key] = value
        setattr(settings, key, value.rstrip("/") if key == "TECHNTING_CMS_SITE_URL" else value)
    from .theme import reload_theme
    reload_theme()
    return path


def reload_workers(request):
    """Other gunicorn workers still hold the old values: ask the master for a graceful reload."""
    if str(request.META.get("SERVER_SOFTWARE", "")).startswith("gunicorn") and hasattr(signal, "SIGHUP"):
        try:
            os.kill(os.getppid(), signal.SIGHUP)
        except OSError:
            pass


# ---------------------------------------------------------------- helpers
def installed_themes():
    from .theme import Theme
    out = []
    root = Path(settings.TECHNTING_CMS_THEMES_DIR)
    for p in sorted(root.iterdir()) if root.exists() else []:
        if (p / "theme.json").exists():
            try:
                t = Theme(p)
            except Exception:
                continue
            spec = json.loads((p / "theme.json").read_text(encoding="utf-8"))
            out.append({"name": p.name, "label": t.label, "description": spec.get("description", "")})
    return out


def _ip(request):
    from .views import client_ip
    return client_ip(request)


def _limited(request, kind, limit):
    """Count one attempt; True when this address went over the limit."""
    key = f"setup-{kind}:{_ip(request)}"
    n = cache.get(key, 0)
    if n >= limit:
        return True
    cache.set(key, n + 1, WINDOW)
    return False


def _t(request, text):
    return ui_i18n.tr(text, ui_i18n.ui_lang(request))


def _data(request):
    return request.session.get(SESSION_KEY) or {}


def _save(request, step, value):
    data = _data(request)
    data[step] = value
    request.session[SESSION_KEY] = data


def first_open_step(data):
    for step in STEPS:
        if step == "finish" or step not in data:
            return step
    return "finish"


def _token_ok(request):
    token = getattr(settings, "TECHNTING_CMS_SETUP_TOKEN", "")
    if not token or request.session.get("setup_token_ok"):
        return True
    given = request.GET.get("token") or request.POST.get("setup_token") or ""
    if given and _limited(request, "token", TOKEN_LIMIT):
        return False
    if given and hmac.compare_digest(given.strip().encode(), token.encode()):
        request.session["setup_token_ok"] = True
        return True
    return False


# ---------------------------------------------------------------- the view
def wizard(request, step=None):
    if is_complete():
        raise Http404("Setup is complete.")
    if request.GET.get("ui") in {"en", "ar"}:
        request.session["ui_lang"] = request.GET["ui"]
    lang = ui_i18n.ui_lang(request)
    base = {"ui_lang": lang, "ui_dir": "rtl" if lang == "ar" else "ltr", "steps": STEPS,
            "version": _version(), "demo_mode": getattr(settings, "TECHNTING_CMS_DEMO_MODE", False)}
    if not _token_ok(request):
        error = _t(request, "That setup key is not correct.") if (request.GET.get("token") or request.POST.get("setup_token")) else None
        return render(request, "cms/setup/key.html", {**base, "step": "key", "error": error}, status=403 if error else 200)
    if request.method == "POST" and "setup_token" in request.POST:
        return redirect(request.path)   # the key form is not a step form
    data = _data(request)
    open_step = first_open_step(data)
    if step is None or step not in STEPS:
        return redirect("cms:setup_step", step=open_step)
    if STEPS.index(step) > STEPS.index(open_step):
        return redirect("cms:setup_step", step=open_step)
    if request.method == "POST":
        if _limited(request, "post", POST_LIMIT):
            messages.error(request, _t(request, "Too many attempts. Wait 15 minutes and try again."))
            return redirect("cms:setup_step", step=step)
        result = HANDLERS[step](request, data)
        if result is not None:
            return result
        data = _data(request)
    ctx = {**base, "step": step, "data": data, "num": STEPS.index(step) + 1, "total": len(STEPS),
           "done_steps": [s for s in STEPS if s in data], **CONTEXT.get(step, lambda r, d: {})(request, data)}
    ctx.update(getattr(request, "_setup_ctx", {}))
    return render(request, f"cms/setup/{step}.html", ctx)


def _version():
    from technting_cms import __version__
    return __version__


def _next(step):
    return redirect("cms:setup_step", step=STEPS[STEPS.index(step) + 1])


def _errors(request, errors, form):
    request._setup_ctx = {"errors": errors, "form": form}
    return None


def handle_site(request, data):
    name = re.sub(r"[\r\n]+", " ", request.POST.get("site_name", "")).strip()[:120]
    url = request.POST.get("site_url", "").strip().rstrip("/")[:300]
    errors = {}
    if locked(ENV_KEYS["site_name"]):
        name = settings.TECHNTING_CMS_SITE_NAME
    if locked(ENV_KEYS["site_url"]):
        url = settings.TECHNTING_CMS_SITE_URL
    if not name:
        errors["site_name"] = _t(request, "Enter the site name.")
    try:
        URLValidator(schemes=["http", "https"])(url)
        if " " in url or "#" in url:
            raise ValidationError("bad")
    except ValidationError:
        errors["site_url"] = _t(request, "Enter the full address, for example https://example.com")
    if errors:
        return _errors(request, errors, {"site_name": name, "site_url": url})
    _save(request, "site", {"site_name": name, "site_url": url})
    return _next("site")


def handle_languages(request, data):
    choice = request.POST.get("languages")
    default = request.POST.get("default")
    if choice not in {"en", "ar", "both"}:
        return _errors(request, {"languages": _t(request, "Choose the languages of the site.")}, request.POST)
    codes = ["en", "ar"] if choice == "both" else [choice]
    if default not in codes:
        default = codes[0]
    _save(request, "languages", {"codes": codes, "default": default, "choice": choice})
    return _next("languages")


def handle_admin(request, data):
    User = get_user_model()
    username = request.POST.get("username", "").strip()
    email = request.POST.get("email", "").strip()
    p1, p2 = request.POST.get("password", ""), request.POST.get("password2", "")
    errors = {}
    try:
        if not username:
            raise ValidationError(_t(request, "Enter a username."))
        if len(username) > 150:
            raise ValidationError(_t(request, "The username is too long."))
        User.username_validator(username)
    except ValidationError as exc:
        errors["username"] = _t(request, "Use letters, digits and @ . + - _ only.") if exc.code == "invalid" else exc.messages[0]
    try:
        validate_email(email)
    except ValidationError:
        errors["email"] = _t(request, "Enter a valid email address.")
    if p1 != p2:
        errors["password2"] = _t(request, "The two passwords do not match.")
    elif not p1:
        errors["password"] = _t(request, "Enter a password.")
    else:
        try:
            with translation.override(ui_i18n.ui_lang(request)):   # Django ships Arabic messages for its validators
                validate_password(p1, user=User(username=username, email=email))
        except ValidationError as exc:
            with translation.override(ui_i18n.ui_lang(request)):
                errors["password"] = " ".join(_password_message(request, e) for e in exc.error_list)
    if errors:
        return _errors(request, errors, {"username": username, "email": email})
    # only the hash is kept in the session; the password itself is never stored
    _save(request, "admin", {"username": username, "email": email, "password": make_password(p1)})
    return _next("admin")


def _password_message(request, error):
    # Django's Arabic catalogue has no plural form for the length rule, so that one message is ours
    if error.code == "password_too_short":
        n = (error.params or {}).get("min_length", 12)
        return _t(request, "This password is too short. It must contain at least {n} characters.").format(n=n)
    return " ".join(error.messages)


def handle_theme(request, data):
    names = {t["name"] for t in installed_themes()}
    theme = settings.TECHNTING_CMS_THEME if locked(ENV_KEYS["theme"]) else request.POST.get("theme", "")
    if theme not in names:
        return _errors(request, {"theme": _t(request, "Choose a theme.")}, request.POST)
    _save(request, "theme", {"name": theme})
    return _next("theme")


def _smtp_from_post(request):
    try:
        port = int(request.POST.get("port") or 0)
    except ValueError:
        port = 0
    return {"host": request.POST.get("host", "").strip()[:200], "port": port,
            "security": request.POST.get("security") if request.POST.get("security") in {"ssl", "starttls"} else "ssl",
            "username": request.POST.get("username", "").strip()[:200], "password": request.POST.get("password", "").strip(),
            "from_name": re.sub(r"[\r\n<>\"]+", " ", request.POST.get("from_name", "")).strip()[:80]}


def handle_email(request, data):
    from . import mail
    action = request.POST.get("action")
    if action == "skip":
        _save(request, "email", {})
        return _next("email")
    smtp = _smtp_from_post(request)
    saved = data.get("email") or {}
    if not smtp["password"] and saved.get("password") and saved.get("username") == smtp["username"]:
        smtp["password"] = mail.decrypt(saved["password"])   # keep the password typed before
    errors = {}
    if not smtp["host"]:
        errors["host"] = _t(request, "Enter the SMTP server.")
    if not 0 < smtp["port"] < 65536:
        errors["port"] = _t(request, "Enter the port, for example 465 or 587.")
    if not smtp["username"]:
        errors["username"] = _t(request, "Enter the SMTP username.")
    if not smtp["password"]:
        errors["password"] = _t(request, "Enter the SMTP password.")
    form = {k: v for k, v in smtp.items() if k != "password"}
    if errors:
        return _errors(request, errors, form)
    stored = {**smtp, "password": mail.encrypt(smtp["password"])}
    if action == "test":
        if _limited(request, "mail", MAIL_LIMIT):
            messages.error(request, _t(request, "Too many test emails. Wait 15 minutes and try again."))
            return _errors(request, {}, form)
        to = request.POST.get("test_to", "").strip() or (data.get("admin") or {}).get("email", "")
        try:
            validate_email(to)
            send_test(smtp, to)
            messages.success(request, _t(request, "Test email sent to") + f" {to}.")
        except ValidationError:
            messages.error(request, _t(request, "Enter a valid email address."))
        except Exception as exc:
            messages.error(request, _t(request, "Sending failed:") + f" {type(exc).__name__}")
        _save(request, "email_draft", stored)
        return _errors(request, {}, {**form, "test_to": to})
    _save(request, "email", stored)
    return _next("email")


def send_test(smtp, to):
    from django.core.mail import EmailMessage
    from django.core.mail.backends.smtp import EmailBackend
    if settings.TECHNTING_CMS_DEMO_MODE:
        raise RuntimeError("Email is turned off in the public demo.")
    conn = EmailBackend(host=smtp["host"], port=smtp["port"], username=smtp["username"], password=smtp["password"],
                        use_ssl=smtp["security"] == "ssl", use_tls=smtp["security"] == "starttls", timeout=15)
    sender = f'{smtp.get("from_name") or "Technting CMS"} <{smtp["username"] if "@" in smtp["username"] else "webmaster@localhost"}>'
    EmailMessage("Technting CMS test email · رسالة تجريبية",
                 "This is a test email from Technting CMS. Email delivery works.\n\nهذه رسالة تجريبية من Technting CMS. إرسال البريد يعمل.",
                 sender, [to], connection=conn).send()


LICENCE_REFUSED = {
    "inactive_installation": "This licence key already runs on another website. Fill in the download form on technting.com again to get a key for this website.",
    "revoked": "This licence key was cancelled. Fill in the download form on technting.com again to get a new key.",
    "invalid_license": "This licence key is not valid. Paste the key from your download e-mail as it is.",
    "no_license": "This licence key is not valid. Paste the key from your download e-mail as it is.",
}


def handle_licence(request, data):
    from . import licence
    if licence.demo():
        _save(request, "licence", {"key": "", "result": None})
        return _next("licence")
    key = licence.clean(request.POST.get("licence_key", ""))
    if not licence.looks_valid(key):
        return _errors(request, {"licence_key": _t(request, "Paste the licence key from your download e-mail. It starts with TAI1.")}, {"licence_key": key})
    result = licence.ask(key, (data.get("site") or {}).get("site_url"))
    if result["reached"] and result["status"] != licence.GOOD:
        return _errors(request, {"licence_key": _t(request, LICENCE_REFUSED.get(result["status"], LICENCE_REFUSED["invalid_license"]))},
                       {"licence_key": key})
    if not result["reached"]:
        messages.warning(request, _t(request, "The licence server could not be reached. The key is kept and checked again later."))
    _save(request, "licence", {"key": key, "result": result})
    return _next("licence")


def handle_finish(request, data):
    if any(s not in data for s in STEPS[:-1]):
        return redirect("cms:setup")
    user, log = finish(request, data, demo=request.POST.get("demo") == "on")
    if log is not None and log.ok:
        messages.success(request, _t(request, "Setup is complete. The site has been published."))
    elif log is not None:
        messages.error(request, _t(request, "Setup is complete, but publishing failed:") + f" {log.message[:200]}")
    return redirect("cms:dashboard")


def finish(request, data, demo=False):
    """Save everything, sign the administrator in and publish once. Returns (user, publish log)."""
    from .models import Language, Setting
    User = get_user_model()
    site, langs, admin, smtp = data["site"], data["languages"], data["admin"], data.get("email") or {}
    with transaction.atomic():
        for order, code in enumerate(langs["codes"]):
            Language.objects.update_or_create(code=code, defaults={
                **LANGS[code], "is_default": code == langs["default"], "url_prefix": "" if code == langs["default"] else code,
                "order": 0 if code == langs["default"] else order + 1})
        user = User(username=admin["username"], email=admin["email"], is_staff=True, is_superuser=True)
        user.password = admin["password"]
        user.save()
        if smtp:
            Setting.objects.update_or_create(key="smtp", defaults={"value": {
                **{k: smtp[k] for k in ("host", "port", "security", "username", "password")},
                "from_name": smtp.get("from_name") or site["site_name"]}})
        Setting.objects.update_or_create(key=FLAG, defaults={"value": {
            "at": timezone.now().isoformat(), "version": _version(), "by": admin["username"]}})
        lic = data.get("licence") or {}
        if lic.get("key"):
            from . import licence
            licence.record(lic["key"], lic.get("result") or {"reached": False, "error": "not checked"})
    global _complete
    _complete = True
    apply_env({ENV_KEYS["site_name"]: site["site_name"], ENV_KEYS["site_url"]: site["site_url"],
               ENV_KEYS["theme"]: data["theme"]["name"]})
    if demo:
        add_demo(langs["codes"])
    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    request.session.pop(SESSION_KEY, None)
    request.session["ui_lang"] = ui_i18n.ui_lang(request)
    audit(request, "setup_complete", site["site_url"])
    log = None
    try:
        from .publish import publish_site
        log = publish_site(user)
    except Exception as exc:   # the wizard is done either way; publishing can be repeated from the dashboard
        messages.error(request, _t(request, "Setup is complete, but publishing failed:") + f" {type(exc).__name__}")
    reload_workers(request)
    return user, log


def add_demo(codes):
    """manage.py seed_demo writes both languages; drop the one the site does not use."""
    import io
    from django.core.management import call_command
    from .models import EntryTranslation, Language, Menu, PageTranslation
    try:
        call_command("seed_demo", stdout=io.StringIO())
    except Exception:
        return False
    for lang in Language.objects.exclude(code__in=codes):
        PageTranslation.objects.filter(language=lang).delete()
        EntryTranslation.objects.filter(language=lang).delete()
        Menu.objects.filter(language=lang).delete()
        lang.delete()
    return True


HANDLERS = {"site": handle_site, "languages": handle_languages, "admin": handle_admin, "theme": handle_theme,
            "email": handle_email, "licence": handle_licence, "finish": handle_finish}


def _ctx_site(request, data):
    s = data.get("site") or {}
    current_url = settings.TECHNTING_CMS_SITE_URL
    return {"form": {"site_name": s.get("site_name") or settings.TECHNTING_CMS_SITE_NAME,
                     "site_url": s.get("site_url") or ("" if "example.com" in current_url else current_url)},
            "lock_name": locked(ENV_KEYS["site_name"]), "lock_url": locked(ENV_KEYS["site_url"])}


def _ctx_languages(request, data):
    s = data.get("languages") or {}
    return {"form": {"languages": s.get("choice", "both"), "default": s.get("default", "en")}}


def _ctx_admin(request, data):
    s = data.get("admin") or {}
    return {"form": {"username": s.get("username", ""), "email": s.get("email", "")}}


def _ctx_theme(request, data):
    current = (data.get("theme") or {}).get("name") or settings.TECHNTING_CMS_THEME
    return {"themes": installed_themes(), "form": {"theme": current}, "lock_theme": locked(ENV_KEYS["theme"])}


def _ctx_email(request, data):
    s = data.get("email_draft") or data.get("email") or {}
    return {"form": {"host": s.get("host", ""), "port": s.get("port", 465), "security": s.get("security", "ssl"),
                     "username": s.get("username", ""), "from_name": s.get("from_name", ""),
                     "test_to": (data.get("admin") or {}).get("email", "")},
            "has_password": bool(s.get("password"))}


def _ctx_finish(request, data):
    names = {"en": "English", "ar": "العربية"}
    langs = data.get("languages") or {}
    return {"summary": {"site": data.get("site") or {}, "languages": [names[c] for c in langs.get("codes", [])],
                        "default": names.get(langs.get("default"), ""), "admin": (data.get("admin") or {}).get("username", ""),
                        "theme": (data.get("theme") or {}).get("name", ""), "email": bool(data.get("email")),
                        "database": dbdump.describe()},
            "env_file": str(env_target())}


def _ctx_licence(request, data):
    from . import licence
    return {"form": {"licence_key": (data.get("licence") or {}).get("key", "")}, "licence_demo": licence.demo()}


CONTEXT = {"site": _ctx_site, "languages": _ctx_languages, "admin": _ctx_admin, "theme": _ctx_theme,
           "email": _ctx_email, "licence": _ctx_licence, "finish": _ctx_finish}


# ---------------------------------------------------------------- Arabic interface strings
for _k, _v in {
    "Set up Technting CMS": "إعداد Technting CMS", "Setup": "الإعداد", "Step": "الخطوة", "of": "من",
    "Site": "الموقع", "Languages": "اللغات", "Administrator": "المسؤول", "Theme": "القالب", "Email": "البريد الإلكتروني",
    "Finish": "الإنهاء", "Continue": "متابعة", "Back": "رجوع", "Setup key": "مفتاح الإعداد",
    "Enter the setup key printed by the installer.": "أدخلوا مفتاح الإعداد الذي طبعه برنامج التثبيت.",
    "That setup key is not correct.": "مفتاح الإعداد غير صحيح.",
    "Welcome. A few questions and your site is ready. You can change all of this later in the dashboard.":
        "أهلاً بكم. بضعة أسئلة ويصبح موقعكم جاهزاً. يمكنكم تغيير كل ذلك لاحقاً من لوحة التحكم.",
    "Site name": "اسم الموقع", "Shown in page titles, emails and search results.": "يظهر في عناوين الصفحات والرسائل ونتائج البحث.",
    "Site address": "عنوان الموقع",
    "The public address visitors will use, for example https://example.com": "العنوان العام الذي سيستخدمه الزوار، مثل https://example.com",
    "Set by the server environment. Change it there.": "قيمة محددة في بيئة الخادم، وتُغيَّر من هناك.",
    "Enter the site name.": "أدخلوا اسم الموقع.",
    "Enter the full address, for example https://example.com": "أدخلوا العنوان كاملاً، مثل https://example.com",
    "Which languages will the site use?": "ما اللغات التي سيستخدمها الموقع؟", "English only": "الإنجليزية فقط",
    "Arabic only": "العربية فقط", "English and Arabic": "الإنجليزية والعربية", "Default language": "اللغة الافتراضية",
    "The default language lives at the site root; the other one gets its own prefix, such as /ar/.":
        "تكون اللغة الافتراضية في جذر الموقع، وتأخذ اللغة الأخرى بادئة خاصة بها مثل ⁦/ar/⁩.",
    "Choose the languages of the site.": "اختاروا لغات الموقع.",
    "The first account has full access: users, settings, plugins and updates.":
        "يملك الحساب الأول صلاحيات كاملة: المستخدمون والإعدادات والإضافات والتحديثات.",
    "Username": "اسم المستخدم", "Work email": "البريد الإلكتروني للعمل", "Password": "كلمة المرور",
    "Password again": "كلمة المرور مرة أخرى",
    "At least 12 characters. Avoid common words and your username.": "اثنا عشر حرفاً على الأقل. تجنّبوا الكلمات الشائعة واسم المستخدم.",
    "Enter a username.": "أدخلوا اسم المستخدم.", "The username is too long.": "اسم المستخدم طويل جداً.",
    "Use letters, digits and @ . + - _ only.": "استخدموا الحروف والأرقام والرموز ⁦@ . + - _⁩ فقط.",
    "Enter a valid email address.": "أدخلوا عنوان بريد إلكتروني صحيحاً.", "The two passwords do not match.": "كلمتا المرور غير متطابقتين.",
    "Enter a password.": "أدخلوا كلمة المرور.",
    "This password is too short. It must contain at least {n} characters.": "كلمة المرور قصيرة جداً، ويجب ألا تقل عن {n} حرفاً.", "Choose a theme.": "اختاروا قالباً.",
    "The theme decides how the public site looks. Copy a theme folder in themes/ to make your own.":
        "يحدد القالب شكل الموقع العام. لإنشاء قالب خاص بكم، انسخوا أحد المجلدات داخل المجلد themes.",
    "Outgoing email (optional)": "البريد الصادر (اختياري)",
    "Used for enquiry copies, invitations and password links. You can skip this and set it later under Settings, Email.":
        "يُستخدم لإرسال نسخ الاستفسارات والدعوات وروابط كلمات المرور. يمكنكم تخطي هذه الخطوة وضبطه لاحقاً من الإعدادات ثم البريد.",
    "SMTP server": "خادم SMTP", "Port": "المنفذ", "Security": "الأمان", "SSL (usually port 465)": "SSL (عادةً المنفذ 465)",
    "STARTTLS (usually port 587)": "STARTTLS (عادةً المنفذ 587)", "SMTP username": "اسم مستخدم SMTP", "SMTP password": "كلمة مرور SMTP",
    "Sender name": "اسم المرسل", "Send a test email to": "إرسال رسالة تجريبية إلى", "Send test email": "إرسال رسالة تجريبية",
    "Skip this step": "تخطي هذه الخطوة", "Save and continue": "حفظ ومتابعة",
    "Leave empty to keep the password you typed before.": "اتركوه فارغاً للإبقاء على كلمة المرور التي أدخلتموها من قبل.",
    "Enter the SMTP server.": "أدخلوا خادم SMTP.", "Enter the port, for example 465 or 587.": "أدخلوا المنفذ، مثل 465 أو 587.",
    "Enter the SMTP username.": "أدخلوا اسم مستخدم SMTP.", "Enter the SMTP password.": "أدخلوا كلمة مرور SMTP.",
    "Too many test emails. Wait 15 minutes and try again.": "رسائل تجريبية كثيرة. انتظروا 15 دقيقة ثم حاولوا مجدداً.",
    "Test email sent to": "أُرسلت الرسالة التجريبية إلى", "Sending failed:": "فشل الإرسال:",
    "Too many attempts. Wait 15 minutes and try again.": "محاولات كثيرة. انتظروا 15 دقيقة ثم حاولوا مجدداً.",
    "Check and finish": "المراجعة والإنهاء", "Not set up": "غير مُعدّ", "Set up": "مُعدّ",
    "Add demo content": "إضافة محتوى تجريبي",
    "A home page, a privacy page and the header menu, so you can see the theme at work. Edit or delete them later.":
        "صفحة رئيسية وصفحة للخصوصية وقائمة الترويسة، لتروا القالب وهو يعمل. يمكنكم تعديلها أو حذفها لاحقاً.",
    "This server runs in demo mode.": "يعمل هذا الخادم في وضع العرض التجريبي.",
    "Finish setup": "إنهاء الإعداد",
    "The site name, address and theme are saved in": "يُحفظ اسم الموقع وعنوانه والقالب في الملف",
    "Setup is complete. The site has been published.": "اكتمل الإعداد، ونُشر الموقع.",
    "Setup is complete, but publishing failed:": "اكتمل الإعداد، لكن النشر فشل:",
    "Interface language": "لغة الواجهة", "Version": "الإصدار",
    "Database": "قاعدة البيانات",
    "Licence key": "مفتاح الرخصة",
    "Paste the free licence key from the e-mail that brought your download link. One licence covers one website.":
        "الصقوا مفتاح الرخصة المجاني من الرسالة التي وصلكم فيها رابط التنزيل. تغطي الرخصة الواحدة موقعاً واحداً.",
    "The key, a random id of this installation, the site address and the version are sent to licenses.technting.com to check it, now and twice a day.":
        "يُرسل المفتاح ومعرّف عشوائي لهذا التثبيت وعنوان الموقع ورقم الإصدار إلى licenses.technting.com للتحقق منه، الآن ومرتين يومياً.",
    "No key on technting.com yet? Fill in the download form there and it comes by e-mail.":
        "ليس لديكم مفتاح بعد؟ املؤوا نموذج التنزيل في technting.com ويصلكم بالبريد.",
    "The public demo needs no licence key.": "لا يحتاج العرض التجريبي العام إلى مفتاح رخصة.",
    "Paste the licence key from your download e-mail. It starts with TAI1.": "الصقوا مفتاح الرخصة من رسالة التنزيل، وهو يبدأ بـ ⁦TAI1.⁩",
    "This licence key already runs on another website. Fill in the download form on technting.com again to get a key for this website.":
        "مفتاح الرخصة هذا يعمل على موقع آخر. املؤوا نموذج التنزيل في technting.com مرة أخرى لتحصلوا على مفتاح لهذا الموقع.",
    "This licence key was cancelled. Fill in the download form on technting.com again to get a new key.":
        "أُلغي مفتاح الرخصة هذا. املؤوا نموذج التنزيل في technting.com مرة أخرى لتحصلوا على مفتاح جديد.",
    "This licence key is not valid. Paste the key from your download e-mail as it is.":
        "مفتاح الرخصة هذا غير صالح. الصقوا المفتاح من رسالة التنزيل كما هو.",
    "The licence server could not be reached. The key is kept and checked again later.":
        "تعذّر الوصول إلى خادم الرخص. حُفظ المفتاح وسيُتحقق منه لاحقاً.",
    "Set with TECHNTING_CMS_DB_ENGINE in the server environment.": "تُحدَّد بالمتغير TECHNTING_CMS_DB_ENGINE في بيئة الخادم.",
}.items():
    ui_i18n.AR.setdefault(_k, _v)
