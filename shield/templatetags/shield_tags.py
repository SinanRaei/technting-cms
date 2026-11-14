from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def turnstile_widget():
    """The Turnstile box on the sign-in page, when Technting Shield has Turnstile keys; otherwise nothing."""
    from shield import turnstile
    try:
        return mark_safe(turnstile.widget()) if turnstile.active() else ""
    except Exception:  # never break the sign-in page
        return ""
