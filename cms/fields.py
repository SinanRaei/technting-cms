"""Clean editor input against theme field specs before it is stored.

The browser sends JSON; nothing is trusted. Unknown keys are dropped, types are coerced,
rich text is sanitised with nh3, and raw HTML ("code") is accepted only from admins.
"""
import re

import nh3

RICH_TAGS = {"img", "figure", "figcaption", "p", "br", "strong", "b", "em", "i", "u", "a", "ul", "ol", "li", "h2", "h3", "h4", "blockquote",
             "code", "pre", "hr", "span", "sup", "sub", "table", "thead", "tbody", "tr", "th", "td"}
RICH_ATTRS = {"img": {"src", "alt", "width", "height", "loading"}, "a": {"href", "title", "target"}, "span": {"lang", "dir"}, "p": {"dir", "lang"},
              "th": {"colspan", "rowspan"}, "td": {"colspan", "rowspan"}}


def clean_rich(html):
    return nh3.clean(html or "", tags=RICH_TAGS, attributes=RICH_ATTRS, url_schemes={"http", "https", "mailto", "tel"},
                     link_rel="noopener")


def clean_url(value):
    value = str(value or "").strip()
    if value.lower().startswith(("javascript:", "data:", "vbscript:")):
        return ""
    return value[:1000]


def clean_value(field, value, allow_code=False):
    t = field["type"]
    if t in {"text", "textarea"}:
        return str(value or "")[:20000]
    if t == "secret":  # plugin API keys; cms.plugins.keep_secrets encrypts them before they are stored
        return str(value or "").strip()[:20000 if field.get("multiline") else 500]
    if t == "richtext":
        return clean_rich(value)
    if t == "url":
        return clean_url(value)
    if t == "link":
        value = value if isinstance(value, dict) else {}
        return {"label": str(value.get("label", ""))[:300], "url": clean_url(value.get("url"))}
    if t in {"image", "video"}:
        return int(value) if str(value or "").isdigit() else None
    if t == "select":
        options = field.get("options", [])
        return value if value in options else (options[0] if options else "")
    if t == "bool":
        return bool(value)
    if t == "number":
        try:
            return float(value) if "." in str(value) else int(value)
        except (TypeError, ValueError):
            return None
    if t == "entry":
        return str(value or "")[:80]
    if t == "entries":
        return [str(v)[:80] for v in (value or []) if v][:200]
    if t == "date":
        value = str(value or "")[:10]
        return value if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else ""
    if t == "code":
        return str(value or "") if allow_code else ""
    if t == "repeater":
        rows = value if isinstance(value, list) else []
        return [clean_fields(field.get("fields", []), r if isinstance(r, dict) else {}, allow_code) for r in rows][:200]
    return None


def clean_fields(fields, data, allow_code=False):
    data = data if isinstance(data, dict) else {}
    return {f["name"]: clean_value(f, data.get(f["name"]), allow_code) for f in fields}


DEVICES = ("phone", "tablet", "desktop")


def clean_visibility(b):
    """Per-block display settings kept next to "data": hidden (not on the public site) and devices (screen sizes
    it shows on). Only stored when they differ from the default (shown, on every screen)."""
    out = {}
    if b.get("hidden") is True:
        out["hidden"] = True
    devices = b.get("devices")
    if isinstance(devices, list):
        devices = [d for d in DEVICES if d in devices]
        if devices and len(devices) < len(DEVICES):
            out["devices"] = devices
    return out


def clean_blocks(theme, blocks, allow_code=False):
    out = []
    for b in blocks if isinstance(blocks, list) else []:
        if not isinstance(b, dict) or b.get("type") not in theme.blocks:
            continue
        spec = theme.blocks[b["type"]]
        out.append({"id": str(b.get("id") or "")[:20], "type": b["type"],
                    "data": clean_fields(spec.get("fields", []), b.get("data"), allow_code), **clean_visibility(b)})
    return out
