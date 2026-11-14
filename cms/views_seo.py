"""SEO page (Technting SEO): Google search, index status, PageSpeed and Bing in one place. Data comes from cms/seo_pro.py."""
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import seo_pro
from .audit import audit
from .models import Language
from .views import _t, admin_required, editor_required

SOURCES = (("search", "Google search", "google"), ("inspect", "Index status (Google)", "google"),
           ("pagespeed", "PageSpeed Insights", "pagespeed"), ("bing", "Bing", "bing"))


def explain(source, st):
    """A failure in words the team can act on (the service's own message is shown too)."""
    code, google = st.get("code"), source in ("search", "inspect")
    if google and code == 403:
        return "Google refused access. Add the service account email as a user in Search Console and check the property address."
    if google and code == 404:
        return "Search Console has no property with this address. Check the property address in the plugin settings."
    if google and code in (400, 401) or "invalid_grant" in (st.get("error") or ""):
        return "Google did not accept the key file. Upload a new JSON key."
    if code == 429:
        return "The free daily limit is used up. It tries again later by itself."
    if source == "pagespeed" and code in (400, 403):
        return "The PageSpeed key was not accepted. Check the key and that PageSpeed Insights API is turned on in Google Cloud."
    if source == "bing" and code in (400, 401, 403):
        return "Bing did not accept the key, or the site is not in Bing Webmaster Tools yet."
    return "The service did not answer as expected. It tries again later."


def _when(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


@editor_required
def seo_view(request):
    on = seo_pro.enabled()
    c = seo_pro.conf() if on else {"google": None, "pagespeed": "", "bing": "", "property": ""}
    st = seo_pro.status()
    sources = []
    for key, label, needs in SOURCES:
        s = st.get(key) or {}
        ready = bool(c[needs])
        state = "off" if not (on and ready) else "never" if not s else "ok" if s.get("ok") else "error"
        sources.append({"key": key, "label": label, "state": state, "at": _when(s.get("at")), "error": s.get("error", ""),
                        "explain": explain(key, s) if state == "error" else ""})
    search, inspect, speed, bing = (seo_pro.search_report(), seo_pro.inspect_report(), seo_pro.pagespeed_report(),
                                    seo_pro.load("bing.json")) if on else (None, None, None, None)
    keywords = seo_pro.keyword_report() if on else None
    sitemaps = seo_pro.load("sitemaps.json") if on else None
    for obj, stamp in ((search, "fetched_at"), (inspect, "checked_at"), (bing, "fetched_at"), (sitemaps, "checked_at")):
        if obj:
            obj["when"] = _when(obj.get(stamp))
    if speed:
        for r in speed["rows"]:
            f = r.get("field") or {}
            r["lcp_s"] = round(f["lcp_ms"] / 1000, 1) if f.get("lcp_ms") is not None else None
    names = {l.code: l.name for l in Language.objects.all()}
    if search:
        for l in search["langs"]:
            l["name"] = names.get(l["code"], l["code"])
    return render(request, "cms/seo.html", {
        "on": on, "sources": sources, "search": search, "inspect": inspect, "speed": speed, "bing": bing,
        "keywords": keywords, "sitemaps": sitemaps, "site_url": settings.TECHNTING_CMS_SITE_URL,
        "property": c["property"], "client_email": (c["google"] or {}).get("client_email", ""),
        "key_problem": seo_pro.key_problem(c["google"]) if c["google"] else "", "refreshing": seo_pro.refreshing(),
        "set_up": on and bool(c["google"]), "names": names})


@admin_required
@require_POST
def seo_refresh(request):
    if not seo_pro.enabled():
        messages.error(request, _t(request, "Turn on Technting SEO in Plugins first."))
    elif seo_pro.refresh_in_background(pagespeed_restart=request.POST.get("pagespeed") == "1"):
        audit(request, "seo_refresh", "pagespeed" if request.POST.get("pagespeed") == "1" else "search")
        messages.success(request, _t(request, "Refreshing in the background. Reload this page in a minute or two."))
    else:
        messages.info(request, _t(request, "A refresh is already running."))
    return redirect("cms:seo")
