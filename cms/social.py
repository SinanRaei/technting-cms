"""Social profiles, phone and WhatsApp for the public site (Settings -> Social profiles and phone).

Stored in Setting rows:
  "social_profiles": {"rows": [{"platform", "url", "label", "enabled", "footer"}]}   (one account per platform)
  "contact_phone":   "+1 555 010 0199"   (shown as typed; the tel: link uses the digits)
  "whatsapp":        "+1 555 010 0199"   (a number; the link is https://wa.me/<digits>)
  "links_scan_url":  ""                   (featured link on /links/; hidden while empty)

The footer (English and Arabic pages alike) shows one icon per enabled row; the Organization JSON-LD sameAs lists
every enabled URL once. Icons are inline SVG (no external hosts).
"""
import re

from markupsafe import Markup

_RECT = '<rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" stroke-width="2"/>'
_LINK = ('<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1.2 1.2M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.2-1.2" '
         'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>')
ICONS = {
    "linkedin": '<path fill="currentColor" d="M20.45 20.45h-3.55v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.06 2.06 0 1 1 0-4.13 2.06 2.06 0 0 1 0 4.13zm1.78 13.02H3.56V9h3.56v11.45zM22.23 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.73V1.73C24 .77 23.2 0 22.22 0z"/>',
    "x": '<path fill="currentColor" d="M18.9 1.15h3.68l-8.04 9.19L24 22.85h-7.4l-5.8-7.59-6.64 7.59H.47l8.6-9.83L0 1.15h7.6l5.24 6.93zm-1.29 19.5h2.04L6.49 3.24H4.3z"/>',
    "youtube": '<path fill="currentColor" d="M23.5 6.19a3 3 0 0 0-2.12-2.14C19.5 3.55 12 3.55 12 3.55s-7.5 0-9.38.5A3 3 0 0 0 .5 6.19C0 8.07 0 12 0 12s0 3.93.5 5.81a3 3 0 0 0 2.12 2.14c1.87.5 9.38.5 9.38.5s7.5 0 9.38-.5a3 3 0 0 0 2.12-2.14C24 15.93 24 12 24 12s0-3.93-.5-5.81zM9.55 15.57V8.43L15.82 12z"/>',
    "instagram": _RECT + '<circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="17.3" cy="6.7" r="1.3" fill="currentColor"/>',
    "facebook": '<path fill="currentColor" d="M24 12a12 12 0 1 0-13.88 11.85v-8.38H7.08V12h3.04V9.36c0-3 1.8-4.67 4.54-4.67 1.31 0 2.68.24 2.68.24v2.95h-1.51c-1.49 0-1.95.93-1.95 1.87V12h3.32l-.53 3.47h-2.79v8.38A12 12 0 0 0 24 12z"/>',
    "whatsapp": '<path d="M12 2.8a9.2 9.2 0 0 0-7.9 13.9L2.8 21.2l4.6-1.2A9.2 9.2 0 1 0 12 2.8z" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/>'
                '<path fill="currentColor" d="M9.1 7.3c-.2-.5-.5-.5-.7-.5h-.6c-.2 0-.5.1-.8.4-.3.3-1 1-1 2.4s1 2.8 1.2 3c.1.2 2 3.2 5 4.4 2.5 1 3 .8 3.5.7.5 0 1.7-.7 2-1.4.2-.7.2-1.2.2-1.4-.1-.1-.3-.2-.6-.3l-2-1c-.3-.1-.5-.1-.7.1l-.9 1.1c-.2.2-.3.2-.6.1-.3-.1-1.2-.5-2.3-1.4-.9-.8-1.4-1.7-1.6-2-.2-.3 0-.4.1-.6l.5-.5.3-.5c.1-.2 0-.4 0-.5z"/>',
    "tiktok": '<path d="M14 3v11.6a3.6 3.6 0 1 1-3.6-3.6M14 3c.4 2.6 2.3 4.4 5 4.6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    "telegram": '<path d="M21.5 3.6 2.6 10.9c-.8.3-.8 1.4 0 1.6l4.6 1.5 1.8 5.6c.2.7 1.1.9 1.6.4l2.6-2.5 4.7 3.5c.6.4 1.4.1 1.6-.6l3.2-15.5c.2-.8-.6-1.5-1.2-1.3zM9.6 14.2l8.2-7.3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>',
    "threads": '<path d="M16.6 11.2c-.6-2.4-2.4-3.3-4.3-3.3-2.5 0-4 1.7-4 1.7M17 12.5c0 2.2-1.6 3.7-4 3.7-1.8 0-3-.9-3-2.3 0-1.6 1.6-2.4 3.6-2.4 2.6 0 5.4.8 5.4 3.5 0 3.3-3.1 5.5-6.6 5.5-4.5 0-7.4-3.3-7.4-8.5S7.9 3.5 12.4 3.5c3.6 0 6 1.8 7 4.6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
    "link": _LINK,
}
PLATFORMS = [  # (code, label, icon)
    ("linkedin", "LinkedIn", "linkedin"), ("x", "X", "x"), ("youtube", "YouTube", "youtube"),
    ("instagram", "Instagram", "instagram"), ("facebook", "Facebook", "facebook"),
    ("whatsapp_channel", "WhatsApp channel", "whatsapp"), ("tiktok", "TikTok", "tiktok"), ("threads", "Threads", "threads"),
    ("telegram", "Telegram", "telegram"), ("bluesky", "Bluesky", "link"), ("mastodon", "Mastodon", "link"),
    ("github", "GitHub", "link"), ("huggingface", "Hugging Face", "link"), ("crunchbase", "Crunchbase", "link"),
    ("clutch", "Clutch", "link"), ("wellfound", "Wellfound", "link"), ("other", "Other", "link"),
]
PLATFORM_LABELS = {c: label for c, label, _ in PLATFORMS}
PLATFORM_ICONS = {c: icon for c, _, icon in PLATFORMS}
URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/[A-Za-z0-9/_.~%@!$&'()*+,;=:?#-]*)?$")
PHONE_RE = re.compile(r"^\+?[0-9 ().-]{6,30}$")


def icon_svg(platform, size=20):
    body = ICONS.get(PLATFORM_ICONS.get(platform, "link"), _LINK)
    return Markup(f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" aria-hidden="true" focusable="false">{body}</svg>')


def clean_row(row):
    """A stored row with known keys, or None when the URL is empty."""
    url = str(row.get("url") or "").strip()
    if not url:
        return None
    platform = row.get("platform") if row.get("platform") in PLATFORM_LABELS else "other"
    return {"platform": platform, "url": url[:300],
            "label": str(row.get("label") or "").strip()[:60], "enabled": bool(row.get("enabled")),
            "footer": bool(row.get("footer", True))}


def valid_url(url):
    return bool(URL_RE.fullmatch(url or ""))


def rows_from(settings_map):
    value = settings_map.get("social_profiles")
    rows = value.get("rows", []) if isinstance(value, dict) else []
    out = [clean_row(r) for r in rows if isinstance(r, dict)]
    return [r for r in out if r and valid_url(r["url"])]


def label_of(row):
    if row["platform"] == "other":
        return row["label"] or "Link"
    return PLATFORM_LABELS[row["platform"]]


def footer_links(settings_map):
    """Enabled footer rows, the same on English and Arabic pages."""
    seen, out = set(), []
    for r in rows_from(settings_map):
        if r["enabled"] and r["footer"] and r["url"] not in seen:
            seen.add(r["url"])
            out.append({"url": r["url"], "label": label_of(r), "platform": r["platform"], "icon": icon_svg(r["platform"])})
    return out


def same_as(settings_map):
    """Every enabled profile URL, once each, for the Organization JSON-LD."""
    seen = []
    for r in rows_from(settings_map):
        if r["enabled"] and r["url"] not in seen:
            seen.append(r["url"])
    return seen


def phone_digits(value):
    """'+1 555 010 0199' -> '+15550100199' (for tel: links)."""
    value = str(value or "").strip()
    digits = re.sub(r"\D", "", value)
    return ("+" + digits) if value.startswith("+") else digits


def contact(settings_map):
    """Phone and WhatsApp for templates: {"phone", "tel", "whatsapp", "wa_url"}; empty strings when not set."""
    phone = str(settings_map.get("contact_phone") or "").strip()
    wa = str(settings_map.get("whatsapp") or "").strip()
    wa_digits = re.sub(r"\D", "", wa)
    return {"phone": phone, "tel": phone_digits(phone) if phone else "", "whatsapp": wa,
            "wa_url": f"https://wa.me/{wa_digits}" if len(wa_digits) >= 6 else ""}
