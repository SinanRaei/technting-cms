from django import template

from ..theme import load_theme
from ..ui_i18n import count as _count
from ..ui_i18n import publish_summary
from ..ui_i18n import tr as _tr
from ..ui_i18n import ui_lang

register = template.Library()


@register.simple_tag(takes_context=True)
def ago(context, value):
    """{% ago t.updated_at %} -> "25 minutes ago", or "منذ 25 دقيقة" in Arabic (Django's own Arabic plural forms)."""
    from django.utils import translation
    from django.utils.timesince import timesince
    lang = ui_lang(context.get("request"))
    with translation.override(lang):
        span = timesince(value, depth=1)
    num, _, word = span.partition("\xa0")
    if num == "0":
        return "الآن" if lang == "ar" else "just now"
    if lang != "ar":
        return f"{span} ago"
    # Arabic says the singular and the dual without the number: "منذ دقيقة"، "منذ دقيقتين"
    return f"منذ {word}" if num in ("1", "2") else f"منذ {span}"


@register.simple_tag(takes_context=True)
def tr(context, text, **kwargs):
    """{% tr "Pages" %} -> interface string in the editor's chosen language."""
    out = _tr(text, ui_lang(context.get("request")))
    return out.format(**kwargs) if kwargs else out


@register.simple_tag(takes_context=True)
def count(context, n, text):
    """{% count n "pages checked" %} -> "78 pages checked", or Arabic that agrees with the number."""
    return _count(n, text, ui_lang(context.get("request")))


@register.filter
def pubmsg(message, request):
    """Publish log line in the editor's language: {{ l.message|pubmsg:request }}."""
    return publish_summary(message, ui_lang(request))


@register.filter
def tl(text, request):
    """Theme label (block, field or collection name): {{ c.label|tl:request }}."""
    if ui_lang(request) != "ar":
        return text
    return load_theme().admin_strings.get("ar", {}).get(text, _tr(text, "ar"))
