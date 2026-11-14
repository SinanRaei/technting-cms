"""Technting CMS plugin system.

A plugin is a folder in plugins/ with:
  plugin.json   {"name", "label", "version", "description", "settings": [field specs]}
                (field types: text, textarea, url, date, number, bool, select, and secret for API keys: stored
                 encrypted, never shown again; read them with secret(name, key))
  plugin.py     def register(api): ...   (called once per process for every enabled plugin)

Hooks (WordPress-style):
  filters  value = apply_filters(name, value, **context)
    "head_html"      list of HTML strings added to <head> of every public page   (page, lang)
    "body_end_html"  list of HTML strings added before </body>                    (page, lang)
    "body_start_html" list of HTML strings at the top of <body>, before the header (page, lang)
    "post_end_html"  list of HTML strings at the end of an article                 (page, lang)
    "sitemap_items"  list of sitemap item dicts                                    ()
  actions  do_action(name, **context)
    "publish_after"    (log, changed_urls, output_dir)  after a successful publish
    "form_submitted"   (submission)                     after an enquiry is stored
    "publish_build"    (target, ctx)                    while building, to write extra files
    "scheduled"        (log)                            every 5 minutes from publish_due; log(text) prints a line
    "backup_failed"    (error)                          when `manage.py backup` fails

Plugins are installed by a developer (copied into plugins/); administrators only enable,
disable and configure them in the dashboard. Code is never uploaded through the browser.
"""
import importlib.util
import json
import logging
from pathlib import Path

from django.conf import settings

log = logging.getLogger(__name__)
PLUGINS_DIR = Path(settings.BASE_DIR) / "plugins"


class PluginAPI:
    def __init__(self, name):
        self.name = name

    def add_filter(self, hook, fn, priority=10):
        _filters.setdefault(hook, []).append((priority, self.name, fn))
        _filters[hook].sort(key=lambda x: x[0])

    def add_action(self, hook, fn, priority=10):
        _actions.setdefault(hook, []).append((priority, self.name, fn))
        _actions[hook].sort(key=lambda x: x[0])

    def setting(self, key, default=""):
        return plugin_settings(self.name).get(key, default)


_filters, _actions, _loaded = {}, {}, {"state": None, "checked": 0}
_reported = set()  # (plugin, hook) failures already logged in this process


def _report(name, hook):
    if (name, hook) not in _reported:
        _reported.add((name, hook))
        log.exception("plugin %s failed in %s (further failures of this hook are not logged)", name, hook)


def available():
    """All installed plugins (enabled or not) with their manifest."""
    out = {}
    if PLUGINS_DIR.exists():
        for d in sorted(PLUGINS_DIR.iterdir()):
            mf = d / "plugin.json"
            if d.is_dir() and mf.exists() and (d / "plugin.py").exists():
                try:
                    spec = json.loads(mf.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                spec["name"] = d.name
                out[d.name] = spec
    return out


def enabled_names():
    from .models import Setting
    value = Setting.objects.filter(key="plugins_enabled").values_list("value", flat=True).first()
    return [n for n in (value or []) if isinstance(n, str)]


def plugin_settings(name):
    from .models import Setting
    return Setting.objects.filter(key=f"plugin:{name}").values_list("value", flat=True).first() or {}


SECRET_SAVED, SECRET_REMOVE = "__saved__", "__remove__"


def keep_secrets(spec, old, values, refused=None):
    """Settings of type "secret" (API keys) are stored encrypted and never sent back to the browser: an empty field
    keeps the saved value, SECRET_REMOVE deletes it, anything else replaces it. A field with "format": "json" (a key
    file) must hold a JSON object; otherwise the saved value stays and the field is added to `refused`."""
    from .mail import encrypt
    for f in spec.get("settings", []):
        if f.get("type") == "secret":
            v = values.get(f["name"]) or ""
            if v in ("", SECRET_SAVED) or (f.get("format") == "json" and v != SECRET_REMOVE and not _json_object(v)):
                if v not in ("", SECRET_SAVED) and refused is not None:
                    refused.append(f)
                values[f["name"]] = old.get(f["name"], "")
            else:
                values[f["name"]] = "" if v == SECRET_REMOVE else encrypt(v)
    return values


def _json_object(text):
    try:
        return isinstance(json.loads(text), dict)
    except ValueError:
        return False


def browser_settings(spec, values):
    """Settings for the Plugins page, with secrets replaced by a "saved" marker."""
    secret = {f["name"] for f in spec.get("settings", []) if f.get("type") == "secret"}
    return {k: (SECRET_SAVED if v else "") if k in secret else v for k, v in (values or {}).items()}


def secret(name, key):
    """A plugin's decrypted secret setting ("" when not set)."""
    from .mail import decrypt
    value = plugin_settings(name).get(key)
    return decrypt(value) if value else ""


def load(force=False):
    """(Re)register hooks of enabled plugins. Re-checks the enabled list at most every 2 seconds."""
    import time
    now = time.monotonic()
    if not force and now - _loaded.get("checked", 0) < 2:
        return
    _loaded["checked"] = now
    names = tuple(n for n in enabled_names() if n in available())
    if not force and _loaded["state"] == names:
        return
    _filters.clear()
    _actions.clear()
    _reported.clear()
    for name in names:
        try:
            spec = importlib.util.spec_from_file_location(f"technting_cms_plugin_{name.replace('-', '_')}", PLUGINS_DIR / name / "plugin.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.register(PluginAPI(name))
        except Exception:  # a broken plugin must never take the site down
            log.exception("plugin %s failed to load", name)
    _loaded["state"] = names


def apply_filters(hook, value, **context):
    load()
    for _, name, fn in _filters.get(hook, []):
        try:
            value = fn(value, **context)
        except Exception:
            _report(name, hook)
    return value


def do_action(hook, **context):
    load()
    for _, name, fn in _actions.get(hook, []):
        try:
            fn(**context)
        except Exception:
            _report(name, hook)
