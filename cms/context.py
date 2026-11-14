from django.conf import settings

from .theme import load_theme


def cms_context(request):
    site = {"site_name": settings.TECHNTING_CMS_SITE_NAME, "site_host": settings.TECHNTING_CMS_SITE_URL.split("//")[-1],
            "demo_mode": settings.TECHNTING_CMS_DEMO_MODE}
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return site
    from .models import FormSubmission
    theme = load_theme()
    from .ui_i18n import ui_lang
    lang = ui_lang(request)
    from .ui_i18n import JS_AR
    from django.urls import reverse
    ui_data = {"t": JS_AR, "labels": theme.admin_strings.get("ar", {})} if lang == "ar" else {}
    ui_data["collections"] = {k: {"label": v["label"], "url": reverse("cms:entries", args=[k])} for k, v in theme.collections.items()}
    from .roles import AUTHOR_COLLECTIONS, role_of
    role = role_of(request.user)
    return {**site, "cms_role": role, "cms_author_collections": AUTHOR_COLLECTIONS, "cms_theme": theme, "cms_collections": theme.collections, "ui_lang": lang, "ui_dir": "rtl" if lang == "ar" else "ltr", "ui_data": ui_data,
            "cms_inbox_new": FormSubmission.objects.filter(status=FormSubmission.NEW).count(),
            "crm_new_leads": _crm_new(), "shield_on": _shield_on(), "cms_licence": _licence(role)}


def _licence(role):
    """The licence warning for administrators (cms/licence.py): None when all is well."""
    if role != "admin":
        return None
    try:
        from . import licence
        st = licence.state()
    except Exception:
        return None
    return None if st["ok"] else {"status": st["status"], "message": licence.MESSAGES.get(st["status"], licence.MESSAGES["no_key"])}


def _shield_on():
    try:
        from shield import conf
        return conf.enabled()
    except Exception:
        return False


def _crm_new():
    try:
        from crm.models import Deal, Stage
        return Deal.objects.filter(stage=Stage.NEW, first_response_at__isnull=True).count()
    except Exception:
        return 0
