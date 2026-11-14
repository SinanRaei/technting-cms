"""Show system-written activity subjects in the dashboard language."""
from django import template

from cms.ui_i18n import tr, ui_lang

register = template.Library()
ARROW = " → "


@register.filter
def subj(text, request):
    """'New → Discovery', 'Reply to Layla', 'Website enquiry · Governance', 'Deal created' -> translated when Arabic."""
    text = text or ""
    lang = ui_lang(request)
    if lang != "ar":
        return text
    if ARROW in text:
        return ARROW.join(tr(p, lang) for p in text.split(ARROW))
    if text.startswith("First contact with "):
        return "أول تواصل مع " + text[len("First contact with "):]
    if text.startswith("Reply to "):
        return "الرد على " + text[len("Reply to "):]
    if text.startswith("Website enquiry"):
        rest = text[len("Website enquiry"):].lstrip(" ·")
        return tr("Website enquiry", lang) + (" · " + tr(rest, lang) if rest else "")
    return tr(text, lang)
