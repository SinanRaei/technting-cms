"""Technting CMS settings. Everything deployment-specific comes from environment variables (see .env.example)."""
import os
from pathlib import Path

from .database import database_config, engine_name

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, str(default)).lower() in {"1", "true", "yes", "on"}


def load_env_file(path):
    """Minimal KEY=VALUE loader so the app runs the same under systemd and locally."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


# Values set by the real environment (systemd, Docker compose) win over files; the setup wizard shows them read-only
TECHNTING_CMS_ENV_FROM_PROCESS = frozenset(k for k in os.environ if k.startswith("TECHNTING_CMS_"))
load_env_file(BASE_DIR / ".env")

DEBUG = env_bool("TECHNTING_CMS_DEBUG", False)
SECRET_KEY = env("TECHNTING_CMS_SECRET_KEY") or ("dev-only-insecure-key" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Set TECHNTING_CMS_SECRET_KEY (or TECHNTING_CMS_DEBUG=1 for local development).")

ALLOWED_HOSTS = [h.strip() for h in env("TECHNTING_CMS_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("TECHNTING_CMS_CSRF_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "cms",
    "crm",
    "shield",
    "formbuilder",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "cms.middleware.SetupMiddleware",  # sends the dashboard to /setup/ until the first administrator exists
    "cms.middleware.DemoModeMiddleware",  # does nothing unless TECHNTING_CMS_DEMO_MODE is on
    "shield.firewall.ShieldMiddleware",  # does nothing unless the Technting Shield plugin is enabled
    "cms.middleware.Require2FAMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "cms.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "technting_cms.urls"
WSGI_APPLICATION = "technting_cms.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "cms.context.cms_context",
            ],
        },
    },
]

VAR_DIR = Path(env("TECHNTING_CMS_VAR_DIR", BASE_DIR / "var"))
VAR_DIR.mkdir(parents=True, exist_ok=True)
# Written by the setup wizard when .env cannot be written (Docker: read-only code folder). .env and the environment win.
load_env_file(VAR_DIR / "site.env")

# Database: SQLite unless TECHNTING_CMS_DB_ENGINE=mysql (MySQL, MariaDB) or postgresql (technting_cms/database.py)
TECHNTING_CMS_DB_ENGINE = engine_name(os.environ)
DATABASES = {"default": database_config(os.environ, VAR_DIR)}
# mysql.W003 warns that some MySQL/MariaDB setups cannot index a unique field longer than 255 characters. Django 5.2
# needs MySQL 8.0.11+ or MariaDB 10.5+, where InnoDB keys take 3072 bytes: 500 characters of utf8mb4 is 2000 bytes.
SILENCED_SYSTEM_CHECKS = ["mysql.W003"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "shield.pwned.PwnedPasswordValidator"},  # only while the Technting Shield plugin is enabled
]

LANGUAGE_CODE = "en"
TIME_ZONE = env("TECHNTING_CMS_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = Path(env("TECHNTING_CMS_STATIC_ROOT", VAR_DIR / "static"))
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("TECHNTING_CMS_MEDIA_ROOT", VAR_DIR / "media"))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024  # form fields; files stream to disk
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

PASSWORD_RESET_TIMEOUT = 60 * 60  # one-time password links expire after an hour
AUTHENTICATION_BACKENDS = ["cms.auth_backends.UsernameOrEmailBackend"]  # user name or work email
LOGIN_URL = "cms:login"
LOGIN_REDIRECT_URL = "cms:dashboard"

# Public site generation
TECHNTING_CMS_THEME = env("TECHNTING_CMS_THEME", "technting")
TECHNTING_CMS_THEMES_DIR = BASE_DIR / "themes"
TECHNTING_CMS_SITE_URL = env("TECHNTING_CMS_SITE_URL", "https://example.com").rstrip("/")
TECHNTING_CMS_SITE_NAME = env("TECHNTING_CMS_SITE_NAME", "Technting")  # public site name: titles, emails, schema.org
TECHNTING_CMS_LEADS_EMAIL = env("TECHNTING_CMS_LEADS_EMAIL", "leads@example.com")  # default inbox for enquiries (Settings can override)
TECHNTING_CMS_ADMIN_URL = env("TECHNTING_CMS_ADMIN_URL", "https://cms.example.com").rstrip("/")  # dashboard host (stats beacon)
TECHNTING_CMS_OUTPUT_DIR = Path(env("TECHNTING_CMS_OUTPUT_DIR", VAR_DIR / "public"))
TECHNTING_CMS_PUBLIC_MEDIA_PREFIX = "/uploads/"
# Settings -> Updates (cms/updater.py): by default the published releases, from the update feed on technting.com.
# Set TECHNTING_CMS_UPDATE_REMOTE to a Git remote (read-only deploy key under the ssh alias github-technting-cms) to
# update from Git main instead; the updater only reads either source
TECHNTING_CMS_UPDATE_FEED = env("TECHNTING_CMS_UPDATE_FEED", "https://technting.com/wp-json/technting/v1/cms-update").strip()
TECHNTING_CMS_UPDATE_REMOTE = env("TECHNTING_CMS_UPDATE_REMOTE", "").strip()

# First-run setup wizard: optional key asked once before /setup/ opens (install.sh sets one)
TECHNTING_CMS_SETUP_TOKEN = env("TECHNTING_CMS_SETUP_TOKEN", "").strip()
# Public demo server (cms/demo.py): risky actions are refused, email goes to the console and `manage.py demo_reset`
# rebuilds the demo. The login page shows the shared demo account; set both values in the environment, never in code
TECHNTING_CMS_DEMO_MODE = env_bool("TECHNTING_CMS_DEMO_MODE", False)
TECHNTING_CMS_DEMO_USER = env("TECHNTING_CMS_DEMO_USER", "").strip()
TECHNTING_CMS_DEMO_PASSWORD = env("TECHNTING_CMS_DEMO_PASSWORD", "")

# Shared cache (login and enquiry rate limits must be shared by all gunicorn workers)
CACHES = {"default": {"BACKEND": "django.core.cache.backends.filebased.FileBasedCache", "LOCATION": str(VAR_DIR / "cache")},
          # Technting Shield's per-minute request counters: in memory, per process, so busy pages never write to disk
          "shield": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "shield", "OPTIONS": {"MAX_ENTRIES": 20000}}}

# Outgoing email for enquiry notifications (optional; the dashboard inbox works without it)
EMAIL_HOST = env("TECHNTING_CMS_SMTP_HOST", "")
EMAIL_PORT = int(env("TECHNTING_CMS_SMTP_PORT", "465"))
EMAIL_USE_SSL = env("TECHNTING_CMS_SMTP_SECURITY", "ssl") == "ssl"
EMAIL_USE_TLS = env("TECHNTING_CMS_SMTP_SECURITY", "ssl") == "starttls"
EMAIL_HOST_USER = env("TECHNTING_CMS_SMTP_USERNAME", "")
EMAIL_HOST_PASSWORD = env("TECHNTING_CMS_SMTP_PASSWORD", "")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER or "webmaster@localhost"
EMAIL_TIMEOUT = 15
if TECHNTING_CMS_DEMO_MODE:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # the public demo never sends email

# Set TECHNTING_CMS_HTTPS=0 only to try the dashboard over plain http on a local network address
TECHNTING_CMS_HTTPS = env_bool("TECHNTING_CMS_HTTPS", True)

if not DEBUG:
    SESSION_COOKIE_SECURE = TECHNTING_CMS_HTTPS
    CSRF_COOKIE_SECURE = TECHNTING_CMS_HTTPS
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_AGE = 60 * 60 * 12
    X_FRAME_OPTIONS = "DENY"  # the dashboard is never framed (previews open in a new tab)
    SECURE_HSTS_SECONDS = 31536000 if TECHNTING_CMS_HTTPS else 0  # the dashboard host only; no includeSubDomains / preload
    # HTTP -> HTTPS is enforced by nginx and Cloudflare in front of gunicorn
    SILENCED_SYSTEM_CHECKS = SILENCED_SYSTEM_CHECKS + ["security.W008"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
