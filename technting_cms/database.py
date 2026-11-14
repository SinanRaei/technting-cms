"""DATABASES["default"] from the TECHNTING_CMS_DB_* environment variables.

  TECHNTING_CMS_DB_ENGINE   sqlite (default, nothing to set up) | mysql (MySQL and MariaDB) | postgresql
  TECHNTING_CMS_DB_NAME     database name                     (mysql and postgresql)
  TECHNTING_CMS_DB_USER     database user                     (mysql and postgresql)
  TECHNTING_CMS_DB_PASSWORD that user's password             (mysql and postgresql)
  TECHNTING_CMS_DB_HOST     default 127.0.0.1
  TECHNTING_CMS_DB_PORT     default 3306 (mysql) or 5432 (postgresql)

The CMS never creates database users or passwords; see docs/INSTALL.md, "Database".
"""
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

ENGINES = {"sqlite": "django.db.backends.sqlite3", "mysql": "django.db.backends.mysql",
           "postgresql": "django.db.backends.postgresql"}
ALIASES = {"sqlite3": "sqlite", "mariadb": "mysql", "postgres": "postgresql"}
LABELS = {"sqlite": "SQLite", "mysql": "MySQL / MariaDB", "postgresql": "PostgreSQL"}
DEFAULT_PORTS = {"mysql": "3306", "postgresql": "5432"}
SQLITE_FILE = "technting_cms.sqlite3"


def engine_name(environ):
    """sqlite, mysql or postgresql. Unknown values stop the start with a clear message."""
    raw = (environ.get("TECHNTING_CMS_DB_ENGINE") or "sqlite").strip().lower()
    name = ALIASES.get(raw, raw)
    if name not in ENGINES:
        raise ImproperlyConfigured(f"TECHNTING_CMS_DB_ENGINE={raw!r} is not supported. "
                                   "Use sqlite (the default), mysql (also for MariaDB) or postgresql.")
    return name


def database_config(environ, var_dir):
    name = engine_name(environ)
    if name == "sqlite":
        return {
            "ENGINE": ENGINES["sqlite"],
            "NAME": Path(var_dir) / SQLITE_FILE,
            "OPTIONS": {"timeout": 20, "init_command": "PRAGMA journal_mode=WAL;"},
            # one connection per request, closed when it ends: after `manage.py demo_reset` no worker keeps the old data
            "CONN_MAX_AGE": 0,
        }

    def get(key, default=""):
        return (environ.get(f"TECHNTING_CMS_DB_{key}") or default).strip()

    password = environ.get("TECHNTING_CMS_DB_PASSWORD") or ""   # kept as typed
    missing = [f"TECHNTING_CMS_DB_{k}" for k, v in (("NAME", get("NAME")), ("USER", get("USER")), ("PASSWORD", password)) if not v]
    if missing:
        raise ImproperlyConfigured(f"TECHNTING_CMS_DB_ENGINE={name} needs {', '.join(missing)} "
                                   "(create the database and its user first, see docs/INSTALL.md).")
    port = get("PORT", DEFAULT_PORTS[name])
    if not port.isdigit() or not 0 < int(port) < 65536:
        raise ImproperlyConfigured(f"TECHNTING_CMS_DB_PORT={port!r} is not a port number.")
    config = {
        "ENGINE": ENGINES[name],
        "NAME": get("NAME"),
        "USER": get("USER"),
        "PASSWORD": password,
        "HOST": get("HOST", "127.0.0.1"),
        "PORT": port,
        "CONN_MAX_AGE": 0,
    }
    if name == "mysql":
        config["OPTIONS"] = {"charset": "utf8mb4", "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
                             "isolation_level": "read committed"}
        config["TEST"] = {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"}
    return config
