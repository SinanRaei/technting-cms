"""Theme loading. A theme is a folder with theme.json, Jinja2 templates and static assets.

theme.json declares:
  templates    page templates the editor can choose, each with optional shared fields
  blocks       block types for the page builder: label, icon, group, fields
  collections  structured record types (like custom post types) with their fields
  strings      UI strings per language used by templates ({{ t('read_more') }})

Field spec: {"name", "label", "type", "help", "required", "translatable", "options",
             "fields" (repeater), "collection" (entry / entries), "default"}
Types: text, textarea, richtext, url, link, image, select, bool, number, repeater,
       entry, entries, code
"""
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings

FIELD_TYPES = {"text", "textarea", "richtext", "url", "link", "image", "select", "bool",
               "number", "repeater", "entry", "entries", "code", "date", "video"}


class ThemeError(Exception):
    pass


class Theme:
    def __init__(self, path: Path):
        self.path = path
        spec = json.loads((path / "theme.json").read_text(encoding="utf-8"))
        self.name = spec.get("name", path.name)
        self.label = spec.get("label", self.name)
        self.templates = spec.get("templates", {"default": {"label": "Default"}})
        self.blocks = spec.get("blocks", {})
        self.collections = spec.get("collections", {})
        self.strings = spec.get("strings", {})
        self.assets = spec.get("assets", [])
        self.outputs = spec.get("outputs", [])
        self.admin_strings = spec.get("admin_strings", {})
        self.root_files = spec.get("root_files", {})       # {"favicon.ico": "img/favicon.ico"}: copied to the site root
        self._validate()

    @property
    def templates_dir(self):
        return self.path / "templates"

    @property
    def static_dir(self):
        return self.path / "static"

    def _validate(self):
        def check_fields(owner, fields):
            names = set()
            for f in fields:
                if f.get("type") not in FIELD_TYPES:
                    raise ThemeError(f"{owner}: field {f.get('name')} has unknown type {f.get('type')}")
                if f["name"] in names:
                    raise ThemeError(f"{owner}: duplicate field {f['name']}")
                names.add(f["name"])
                if f["type"] == "repeater":
                    check_fields(f"{owner}.{f['name']}", f.get("fields", []))
                if f["type"] in {"entry", "entries"} and f.get("collection") not in self.collections:
                    raise ThemeError(f"{owner}: field {f['name']} points to unknown collection {f.get('collection')}")

        for key, b in self.blocks.items():
            check_fields(f"block {key}", b.get("fields", []))
            if not (self.templates_dir / "blocks" / f"{key}.html").exists():
                raise ThemeError(f"block {key}: missing templates/blocks/{key}.html")
        for key, c in self.collections.items():
            check_fields(f"collection {key}", c.get("fields", []))
            if c.get("route") and not (self.templates_dir / f"{c.get('route_template', key)}.html").exists():
                raise ThemeError(f"collection {key}: missing templates/{c.get('route_template', key)}.html")
        for key, tpl in self.templates.items():
            check_fields(f"template {key}", tpl.get("fields", []))
            if not (self.templates_dir / f"{key}.html").exists():
                raise ThemeError(f"template {key}: missing templates/{key}.html")

    def block_groups(self):
        groups = {}
        for key, b in self.blocks.items():
            groups.setdefault(b.get("group", "Content"), []).append({"type": key, **b})
        return groups

    def string(self, key, lang):
        value = self.strings.get(key)
        if isinstance(value, dict):
            return value.get(lang) or value.get("en") or key
        return value or key

    def routed_collections(self):
        return {k: c for k, c in self.collections.items() if c.get("route")}

    def collection_fields(self, collection, translatable=None):
        fields = self.collections[collection].get("fields", [])
        if translatable is None:
            return fields
        return [f for f in fields if bool(f.get("translatable")) == translatable]


@lru_cache(maxsize=4)
def load_theme(name=None) -> Theme:
    name = name or settings.TECHNTING_CMS_THEME
    path = Path(settings.TECHNTING_CMS_THEMES_DIR) / name
    if not (path / "theme.json").exists():
        raise ThemeError(f"Theme '{name}' not found in {settings.TECHNTING_CMS_THEMES_DIR}")
    return Theme(path)


def reload_theme():
    load_theme.cache_clear()
    return load_theme()
