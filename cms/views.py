"""Technting CMS dashboard views."""
import json
import mimetypes
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .fields import clean_blocks, clean_fields
from .media import MediaError, delete_media, media_json, save_upload
from .models import Entry, EntryTranslation, Language, Media, Menu, Page, PageTranslation, PublishLog, Redirect, Revision, Setting
from .publish import publish_site
from .render import RenderContext
from .audit import audit
from .roles import AUTHOR_COLLECTIONS, ROLES, can_edit_entry, is_author, is_sales, role_of, set_role
from .theme import load_theme

User = get_user_model()


# ---------------------------------------------------------------- access
def editor_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("Your account cannot edit this site.")
        if is_author(request.user):
            if request.method == "POST":
                return HttpResponseForbidden("Authors can only write blog posts.")
            return redirect("cms:entries", collection=sorted(AUTHOR_COLLECTIONS)[0])
        if is_sales(request.user):
            if request.method == "POST":
                return HttpResponseForbidden("Sales accounts use the CRM and the inbox only.")
            return redirect("crm:home")
        return view(request, *args, **kwargs)
    return wrapper


def crm_required(view):
    """Editors, admins and sales (CRM, inbox and stats). Authors are sent to their posts."""
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("Your account cannot open this page.")
        if is_author(request.user):
            if request.method == "POST":
                return HttpResponseForbidden("Authors can only write blog posts.")
            return redirect("cms:entries", collection=sorted(AUTHOR_COLLECTIONS)[0])
        return view(request, *args, **kwargs)
    return wrapper


def writer_required(view):
    """Editors, admins and authors. Views using it check collection and ownership for authors."""
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("Your account cannot edit this site.")
        if is_sales(request.user):
            return redirect("crm:home") if request.method == "GET" else HttpResponseForbidden("Sales accounts use the CRM and the inbox only.")
        if is_author(request.user) and kwargs.get("collection") and kwargs["collection"] not in AUTHOR_COLLECTIONS:
            return HttpResponseForbidden("Authors can only write blog posts.")
        return view(request, *args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            return HttpResponseForbidden("Only administrators can open this page.")
        return view(request, *args, **kwargs)
    return wrapper


def client_ip(request):
    # Technting Shield sets shield_ip after checking that the request really came through Cloudflare
    return getattr(request, "shield_ip", None) or request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR", "")


REMEMBER_DAYS = 30


def remember_session(request, remember):
    """"Keep me signed in": the session lasts 30 days, across browser restarts. Otherwise the normal 12 hours."""
    if remember:
        request.session.set_expiry(REMEMBER_DAYS * 24 * 3600)


def login_view(request):
    if request.user.is_authenticated:
        return redirect("cms:dashboard")
    from urllib.parse import urlencode

    from .ui_i18n import tr, ui_lang
    # interface language before sign-in: ?ui=en|ar, else the browser's first language
    if request.GET.get("ui") in {"en", "ar"}:
        request.session["ui_lang"] = request.GET["ui"]
    elif "ui_lang" not in request.session and request.META.get("HTTP_ACCEPT_LANGUAGE", "").lower().startswith("ar"):
        request.session["ui_lang"] = "ar"
    lang = ui_lang(request)
    error = None
    if request.method == "POST":
        key = f"login-fail:{client_ip(request)}"
        if cache.get(key, 0) >= 8:
            error = "Too many attempts. Wait 15 minutes and try again."
        else:
            user = authenticate(request, username=request.POST.get("username", ""), password=request.POST.get("password", ""))
            if user and (user.is_staff or user.is_superuser):
                cache.delete(key)
                sec = getattr(user, "security", None)
                if sec and sec.enabled:
                    # second step: remember who passed the password check, for 5 minutes
                    request.session["2fa_user"] = user.pk
                    request.session["2fa_backend"] = user.backend
                    request.session["2fa_until"] = int(timezone.now().timestamp()) + 300
                    request.session["2fa_next"] = safe_next(request.GET.get("next"))
                    request.session["2fa_remember"] = bool(request.POST.get("remember"))
                    return redirect("cms:login_verify")
                login(request, user)
                remember_session(request, request.POST.get("remember"))
                audit(request, "login")
                return redirect(safe_next(request.GET.get("next")) or "cms:dashboard")
            cache.set(key, cache.get(key, 0) + 1, 900)
            audit(request, "login_failed", username=request.POST.get("username", ""))
            error = "The username or password is not correct."
    demo = None
    if settings.TECHNTING_CMS_DEMO_MODE and settings.TECHNTING_CMS_DEMO_USER:   # the shared account of the public demo
        demo = {"user": settings.TECHNTING_CMS_DEMO_USER, "password": settings.TECHNTING_CMS_DEMO_PASSWORD}
    nxt = safe_next(request.GET.get("next"))
    switch = {code: "?" + urlencode({"ui": code, **({"next": nxt} if nxt else {})}) for code in ("en", "ar")}
    return render(request, "cms/login.html", {"error": tr(error, lang) if error else None, "demo": demo,
                                              "ui_lang": lang, "ui_dir": "rtl" if lang == "ar" else "ltr", "ui_switch": switch})


@require_POST
def logout_view(request):
    audit(request, "logout")
    logout(request)
    return redirect("cms:login")


# ---------------------------------------------------------------- helpers
def languages():
    return list(Language.objects.all())


def default_lang():
    return Language.objects.filter(is_default=True).first() or Language.objects.first()


def snapshot_translation(t):
    return {"title": t.title, "slug": t.slug, "blocks": t.blocks, "seo_title": t.seo_title,
            "seo_description": t.seo_description, "og_image": t.og_image_id, "noindex": t.noindex,
            "status": t.status, "publish_at": t.publish_at.isoformat() if t.publish_at else None,
            "page": {"template": t.page.template, "data": t.page.data, "parent": t.page.parent_id}}


def write_revision(kind, obj_id, lang, snapshot, user, note=""):
    Revision.objects.create(object_type=kind, object_id=obj_id, language=lang, snapshot=snapshot, note=note,
                            created_by=user if user.is_authenticated else None)
    # keep the last 50 revisions per object and language
    old = Revision.objects.filter(object_type=kind, object_id=obj_id, language=lang).order_by("-created_at")[50:]
    Revision.objects.filter(pk__in=[r.pk for r in old]).delete()


def _t(request, text):
    from .ui_i18n import tr, ui_lang
    return tr(text, ui_lang(request))


def _lock_name(request, kind, pk, lang):
    from .content_tools import lock_holder
    other = lock_holder(request, kind, pk, lang)
    return other["name"] if other else ""


def _pub(request, message):
    from .ui_i18n import publish_summary, ui_lang
    return publish_summary(message, ui_lang(request))


def publish_and_report(request, what="Site"):
    log = publish_site(request.user)
    if log.ok:
        messages.success(request, f"{_t(request, what)} {_t(request, 'saved and published.')} {_pub(request, log.message)}.")
    else:
        messages.error(request, f"{_t(request, 'Saved, but publishing failed:')} {log.message}")
    return log


def theme_json(theme):
    from . import demo
    blocks = {k: b for k, b in theme.blocks.items() if not demo.has_code_field(b)} if demo.on() else theme.blocks
    return json.dumps({"blocks": blocks, "collections": {k: {"label": c["label"], "singular": c.get("singular"),
                                                                    "title_field": c.get("title_field")} for k, c in theme.collections.items()},
                       "templates": theme.templates}, ensure_ascii=False)


# ---------------------------------------------------------------- dashboard
@editor_required
def dashboard(request):
    ctx = {
        "page_count": Page.objects.count(),
        "entry_counts": [(k, c["label"], Entry.objects.filter(collection=k).count()) for k, c in load_theme().collections.items()],
        "media_count": Media.objects.count(),
        "recent_pages": PageTranslation.objects.select_related("page", "language", "updated_by").order_by("-updated_at")[:6],
        "recent_entries": Entry.objects.select_related("updated_by").order_by("-updated_at")[:6],
        "last_publish": PublishLog.objects.first(),
        "publish_logs": PublishLog.objects.all()[:8],
        "awaiting_review": Entry.objects.filter(review_requested_at__isnull=False, is_published=False).select_related("created_by"),
        "health": health_summary(),
        "traffic": traffic_summary(),
        "seo": seo_summary(),
    }
    return render(request, "cms/dashboard.html", ctx)


def traffic_summary():
    from . import stats
    return stats.week_summary() if stats.enabled() else None


def seo_summary():
    try:
        from . import seo_pro
        return seo_pro.dashboard_summary()
    except Exception:  # a broken data file must not break the dashboard
        return None


def health_summary():
    from .health import load
    data = load()
    if not data:
        return None
    high = sum(1 for i in data["issues"] if HEALTH_SEVERITY.get(i["kind"]) == "high")
    return {"total": len(data["issues"]), "high": high, "pages": data["pages"], "checked_at": data["checked_at"]}


@editor_required
@require_POST
def publish_now(request):
    log = publish_site(request.user)
    audit(request, "publish", log.message if log.ok else "failed")
    (messages.success if log.ok else messages.error)(request, _t(request, "Site published." if log.ok else "Publishing failed:") + " " + _pub(request, log.message))
    return redirect(request.POST.get("next") or "cms:dashboard")


# ---------------------------------------------------------------- pages
@editor_required
def pages_list(request):
    q = request.GET.get("q", "").strip()
    pages = Page.objects.prefetch_related("translations__language").order_by("order", "id")
    if q:
        pages = pages.filter(Q(translations__title__icontains=q) | Q(key__icontains=q)).distinct()
    langs = languages()
    rows = []
    for p in pages:
        trs = {t.language.code: t for t in p.translations.all()}
        rows.append({"page": p, "trs": [(l, trs.get(l.code)) for l in langs], "main": trs.get(langs[0].code) or next(iter(trs.values()), None)})
    return render(request, "cms/pages_list.html", {"rows": rows, "langs": langs, "q": q})


@editor_required
def page_new(request):
    theme = load_theme()
    if request.method == "POST":
        title = request.POST.get("title", "").strip() or "Untitled page"
        lang = Language.objects.get(code=request.POST.get("language") or default_lang().code)
        template = request.POST.get("template") if request.POST.get("template") in theme.templates else "default"
        with transaction.atomic():
            page = Page.objects.create(template=template, order=Page.objects.count())
            slug = slugify(request.POST.get("slug") or title, allow_unicode=False) or f"page-{page.pk}"
            base, n = slug, 2
            while PageTranslation.objects.filter(language=lang, slug=slug, page__parent=None).exists():
                slug, n = f"{base}-{n}", n + 1
            blocks = [{"id": "hero1", "type": "page_hero", "data": {"title": "", "eyebrow": "", "lead": "", "text": ""}}] if "page_hero" in theme.blocks and template == "default" else []
            t = PageTranslation.objects.create(page=page, language=lang, title=title, slug=slug, blocks=blocks, updated_by=request.user)
        return redirect("cms:page_edit", page_id=page.pk, lang=lang.code)
    return render(request, "cms/page_new.html", {"templates": theme.templates, "langs": languages()})


@editor_required
def page_edit(request, page_id, lang):
    theme = load_theme()
    page = get_object_or_404(Page, pk=page_id)
    language = get_object_or_404(Language, code=lang)
    t = PageTranslation.objects.filter(page=page, language=language).first()
    created = False
    if t is None:
        # Start the new language from the default language's layout so translators replace text in place
        src = page.translations.order_by("language__order").first()
        t = PageTranslation(page=page, language=language, title=src.title if src else "", slug=src.slug if src else "",
                            blocks=src.blocks if src else [], status=PageTranslation.DRAFT)
        created = True

    if request.method == "POST":
        from .content_tools import follow_moves, live_urls
        urls_before = live_urls(page, language) if t.pk else {}
        try:
            blocks = json.loads(request.POST.get("blocks_json") or "[]")
            page_data = json.loads(request.POST.get("page_data_json") or "{}")
        except json.JSONDecodeError:
            messages.error(request, "The editor sent invalid data. Nothing was saved.")
            return redirect("cms:page_edit", page_id=page.pk, lang=lang)
        from . import demo
        if demo.on() and demo.code_blocks(theme, blocks):
            messages.error(request, _t(request, "Custom HTML blocks are turned off in the public demo. Remove the block and save again. Nothing was saved."))
            return redirect("cms:page_edit", page_id=page.pk, lang=lang)
        allow_code = request.user.is_superuser and not demo.on()
        t.title = request.POST.get("title", "").strip()[:250] or "Untitled page"
        if page.key != "home":
            t.slug = slugify(request.POST.get("slug", "") or t.title) or t.slug
        t.blocks = clean_blocks(theme, blocks, allow_code)
        t.seo_title = request.POST.get("seo_title", "")[:250]
        t.seo_description = request.POST.get("seo_description", "")[:320]
        og = request.POST.get("og_image", "")
        t.og_image_id = int(og) if og.isdigit() and Media.objects.filter(pk=og).exists() else None
        t.noindex = request.POST.get("noindex") == "on"
        when_off = request.POST.get("unpublish_at", "").strip()
        try:
            t.unpublish_at = timezone.make_aware(timezone.datetime.fromisoformat(when_off)) if when_off else None
        except ValueError:
            t.unpublish_at = None
        action = request.POST.get("action", "save")
        template = request.POST.get("template", page.template)
        if template in theme.templates:
            page.template = template
        page.data = clean_fields(theme.templates.get(page.template, {}).get("fields", []), page_data, allow_code)
        parent = request.POST.get("parent", "")
        page.parent_id = int(parent) if parent.isdigit() and int(parent) != page.pk else None
        if action == "publish":
            t.status = PageTranslation.PUBLISHED
            t.published_at = t.published_at or timezone.now()
        elif action == "schedule":
            when = request.POST.get("publish_at")
            try:
                t.publish_at = timezone.make_aware(timezone.datetime.fromisoformat(when)) if when else None
            except ValueError:
                t.publish_at = None
            t.status = PageTranslation.SCHEDULED if t.publish_at else t.status
        elif action == "unpublish":
            t.status = PageTranslation.DRAFT
        t.updated_by = request.user
        clash = PageTranslation.objects.filter(language=language, path=t.compute_path()).exclude(pk=t.pk).first()
        if clash:
            messages.error(request, f"Another page already uses the address {t.compute_path()} ({clash.title}). Change the slug.")
        else:
            with transaction.atomic():
                page.save()
                t.save()
                write_revision("page", t.pk, lang, snapshot_translation(t), request.user, action)
                audit(request, f"page_{action}", f"{t.compute_path()} ({lang})")
                moved = follow_moves(page, language, urls_before)
            for old, new in moved:
                audit(request, "redirect_auto", f"{old} → {new}")
                messages.info(request, _t(request, "The address changed, so visitors and search engines are sent from the old address to the new one:") + f" {old} → {new}")
            if t.status == PageTranslation.PUBLISHED or action == "unpublish":
                publish_and_report(request, "Page")
            elif action == "schedule" and t.publish_at:
                messages.success(request, f"Page scheduled for {timezone.localtime(t.publish_at):%Y-%m-%d %H:%M}.")
            else:
                messages.success(request, _t(request, "Draft saved."))
            return redirect("cms:page_edit", page_id=page.pk, lang=lang)

    other_pages = Page.objects.exclude(pk=page.pk).prefetch_related("translations")
    revisions = Revision.objects.filter(object_type="page", object_id=t.pk or 0).select_related("created_by")[:15] if t.pk else []
    return render(request, "cms/page_edit.html", {
        "page": page, "t": t, "language": language, "langs": languages(), "created": created,
        "trs": {x.language.code: x for x in page.translations.all()},
        "theme": theme, "theme_json": theme_json(theme), "blocks_json": json.dumps(t.blocks, ensure_ascii=False),
        "page_data_json": json.dumps(page.data, ensure_ascii=False), "other_pages": other_pages, "revisions": revisions,
        "og_media": media_json(t.og_image) if t.og_image_id else None,
        "lock_other": _lock_name(request, "page", t.pk, lang) if t.pk else "",
    })


@editor_required
def page_preview(request, page_id, lang):
    t = get_object_or_404(PageTranslation, page_id=page_id, language__code=lang)
    ctx = RenderContext(preview=True)
    t = next((x for x in ctx.translations if x.pk == t.pk), t)
    return HttpResponse(ctx.render(t))


@editor_required
@require_POST
def page_delete(request, page_id):
    page = get_object_or_404(Page, pk=page_id)
    if page.key in {"home", "privacy"}:
        messages.error(request, "This page is required by the theme and cannot be deleted.")
        return redirect("cms:pages")
    if page.children.exists():
        messages.error(request, "Move or delete the child pages first.")
        return redirect("cms:pages")
    title = str(page)
    page.delete()
    audit(request, "page_delete", title)
    publish_and_report(request, f"“{title}” deleted;")
    return redirect("cms:pages")


@editor_required
@require_POST
def revision_restore(request, revision_id):
    rev = get_object_or_404(Revision, pk=revision_id)
    if rev.object_type == "page":
        t = get_object_or_404(PageTranslation, pk=rev.object_id)
        s = rev.snapshot
        t.title, t.slug, t.blocks = s["title"], s["slug"], s["blocks"]
        t.seo_title, t.seo_description, t.noindex = s.get("seo_title", ""), s.get("seo_description", ""), s.get("noindex", False)
        t.updated_by = request.user
        t.save()
        write_revision("page", t.pk, t.language.code, snapshot_translation(t), request.user, f"restored #{rev.pk}")
        if t.status == PageTranslation.PUBLISHED:
            publish_and_report(request, "Revision restored and")
        else:
            messages.success(request, "Revision restored as draft.")
        return redirect("cms:page_edit", page_id=t.page_id, lang=t.language.code)
    entry = get_object_or_404(Entry, pk=rev.object_id)
    entry.data = rev.snapshot.get("data", entry.data)
    entry.save()
    for code, data in rev.snapshot.get("translations", {}).items():
        lang = Language.objects.filter(code=code).first()
        if lang:
            EntryTranslation.objects.update_or_create(entry=entry, language=lang, defaults={"data": data})
    publish_and_report(request, "Revision restored and")
    return redirect("cms:entry_edit", collection=entry.collection, entry_id=entry.pk, lang=rev.language or default_lang().code)


# ---------------------------------------------------------------- collections
@writer_required
def entries_list(request, collection):
    theme = load_theme()
    if collection not in theme.collections:
        raise Http404
    spec = theme.collections[collection]
    title_field = spec.get("title_field", "name")
    q = request.GET.get("q", "").strip().lower()
    lang = default_lang()
    rows = []
    qs = Entry.objects.filter(collection=collection).prefetch_related("translations__language")
    if is_author(request.user):
        qs = qs.filter(created_by=request.user)
    for e in qs:
        trs = {t.language.code: t.data for t in e.translations.all()}
        title = trs.get(lang.code, {}).get(title_field) or e.data.get(title_field) or e.key
        if q and q not in title.lower() and q not in e.key.lower():
            continue
        rows.append({"entry": e, "title": title, "langs": [l for l in languages() if l.code in trs]})
    return render(request, "cms/entries_list.html", {"collection": collection, "spec": spec, "rows": rows, "q": q, "langs": languages(),
                                                     "now": timezone.now()})


@writer_required
def entry_new(request, collection):
    theme = load_theme()
    if collection not in theme.collections:
        raise Http404
    if request.method == "POST":
        import re
        key = request.POST.get("key", "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", key) or Entry.objects.filter(collection=collection, key=key).exists():
            messages.error(request, "Choose a short, unique key (letters, numbers and dashes).")
        else:
            e = Entry.objects.create(collection=collection, key=key[:80], order=Entry.objects.filter(collection=collection).count(),
                                     is_published=False, updated_by=request.user, created_by=request.user)
            return redirect("cms:entry_edit", collection=collection, entry_id=e.pk, lang=default_lang().code)
    return render(request, "cms/entry_new.html", {"collection": collection, "spec": theme.collections[collection]})


@writer_required
def entry_edit(request, collection, entry_id, lang):
    theme = load_theme()
    if collection not in theme.collections:
        raise Http404
    spec = theme.collections[collection]
    entry = get_object_or_404(Entry, pk=entry_id, collection=collection)
    language = get_object_or_404(Language, code=lang)
    author = is_author(request.user)
    if not can_edit_entry(request.user, entry):
        messages.error(request, _t(request, "Only your own drafts can be edited. Ask an editor to change a published post."))
        return redirect("cms:entries", collection=collection)
    tr = EntryTranslation.objects.filter(entry=entry, language=language).first()
    shared_fields = theme.collection_fields(collection, translatable=False)
    tr_fields = theme.collection_fields(collection, translatable=True)
    if request.method == "POST":
        try:
            shared = json.loads(request.POST.get("shared_json") or "{}")
            translated = json.loads(request.POST.get("translated_json") or "{}")
        except json.JSONDecodeError:
            messages.error(request, "The editor sent invalid data. Nothing was saved.")
            return redirect("cms:entry_edit", collection=collection, entry_id=entry.pk, lang=lang)
        from .demo import on as demo_on
        allow_code = request.user.is_superuser and not demo_on()   # raw HTML is never stored in the public demo
        action = request.POST.get("action", "save")
        with transaction.atomic():
            entry.data = clean_fields(shared_fields, shared, allow_code)
            if not author:  # authors never change visibility; editors publish their drafts
                entry.is_published = request.POST.get("is_published") == "on"
                when = request.POST.get("publish_at", "").strip()
                try:
                    entry.publish_at = timezone.make_aware(timezone.datetime.fromisoformat(when)) if when else None
                except ValueError:
                    entry.publish_at = None
                when_off = request.POST.get("unpublish_at", "").strip()
                try:
                    entry.unpublish_at = timezone.make_aware(timezone.datetime.fromisoformat(when_off)) if when_off else None
                except ValueError:
                    entry.unpublish_at = None
            if action == "submit":
                entry.review_requested_at = timezone.now()
            elif entry.is_published:
                entry.review_requested_at = None
            order = request.POST.get("order", "")
            entry.order = int(order) if order.lstrip("-").isdigit() else entry.order
            entry.updated_by = request.user
            entry.save()
            EntryTranslation.objects.update_or_create(entry=entry, language=language,
                                                      defaults={"data": clean_fields(tr_fields, translated, allow_code)})
            snap = {"data": entry.data, "translations": {t.language.code: t.data for t in entry.translations.select_related("language")}}
            write_revision("entry", entry.pk, lang, snap, request.user, "submitted for review" if action == "submit" else "")
            audit(request, "entry_submit" if action == "submit" else "entry_save", f"{collection}:{entry.key} ({lang}){' visible' if entry.is_published else ''}")
        if author:
            if action == "submit":
                notify_review(request, entry, spec)
                messages.success(request, _t(request, "Sent for review. An editor will check and publish it."))
            else:
                messages.success(request, _t(request, "Draft saved."))
        else:
            publish_and_report(request, spec.get("singular", "Entry"))
            if entry.is_published and entry.publish_at and entry.publish_at > timezone.now():
                messages.info(request, _t(request, "Scheduled: it appears on the site at") +
                              f" {timezone.localtime(entry.publish_at):%Y-%m-%d %H:%M}.")
        return redirect("cms:entry_edit", collection=collection, entry_id=entry.pk, lang=lang)

    # options for entry / entries pickers
    pickers = {}
    for f in spec.get("fields", []) + [sf for f in spec.get("fields", []) if f["type"] == "repeater" for sf in f.get("fields", [])]:
        if f["type"] in {"entry", "entries"}:
            pickers[f["collection"]] = entry_options(theme, f["collection"])
    route = spec.get("route")
    live_url = None
    if route:
        prefix = f"/{language.url_prefix}" if language.url_prefix else ""
        live_url = settings.TECHNTING_CMS_SITE_URL + prefix + route.format(key=entry.key)
    revisions = Revision.objects.filter(object_type="entry", object_id=entry.pk).select_related("created_by")[:15]
    from .seo import entry_checks
    return render(request, "cms/entry_edit.html", {
        "author_mode": author, "seo_checks": entry_checks(theme, collection, entry, language),
        "collection": collection, "spec": spec, "entry": entry, "language": language, "langs": languages(),
        "has_tr": {t.language.code for t in entry.translations.select_related("language")},
        "shared_fields_json": json.dumps(shared_fields, ensure_ascii=False), "tr_fields_json": json.dumps(tr_fields, ensure_ascii=False),
        "shared_json": json.dumps(entry.data, ensure_ascii=False), "translated_json": json.dumps(tr.data if tr else {}, ensure_ascii=False),
        "pickers_json": json.dumps(pickers, ensure_ascii=False), "live_url": live_url, "revisions": revisions,
        "lock_other": _lock_name(request, "entry", entry.pk, lang),
        "fallback_json": json.dumps(
            (EntryTranslation.objects.filter(entry=entry, language=default_lang()).values_list("data", flat=True).first() or {})
            if language != default_lang() else {}, ensure_ascii=False),
    })


def notify_review(request, entry, spec):
    """Email editors and admins that an author submitted a draft (only when email is set up)."""
    from django.urls import reverse
    from . import mail
    if not mail.ready():
        return
    to = [u.email for u in User.objects.filter(is_active=True, is_staff=True) if u.email and role_of(u) in {"admin", "editor"}]
    if not to:
        return
    link = request.build_absolute_uri(reverse("cms:entry_edit", args=[entry.collection, entry.pk, default_lang().code]))
    who = request.user.get_full_name() or request.user.get_username()
    try:
        mail.send(f"Review requested: {spec.get('singular', 'Entry')} {entry.key} · طلب مراجعة",
                  f"{who} submitted \u201c{entry.key}\u201d for review.\n\nOpen it: {link}\n\n"
                  f"أرسل {who} المسودة \u201c{entry.key}\u201d للمراجعة. افتحها من الرابط أعلاه.", to)
    except Exception:  # the draft is saved either way; email is a convenience
        pass


def entry_options(theme, collection):
    spec = theme.collections[collection]
    tf = spec.get("title_field", "name")
    lang = default_lang()
    out = []
    for e in Entry.objects.filter(collection=collection).prefetch_related("translations__language"):
        trs = {t.language.code: t.data for t in e.translations.all()}
        out.append({"key": e.key, "label": f"{e.key} · {trs.get(lang.code, {}).get(tf) or e.data.get(tf) or ''}".strip(" ·")})
    return out


@editor_required
@require_POST
def entry_delete(request, collection, entry_id):
    entry = get_object_or_404(Entry, pk=entry_id, collection=collection)
    entry.delete()
    audit(request, "entry_delete", f"{collection}:{entry.key}")
    publish_and_report(request, f"{collection} “{entry.key}” deleted;")
    return redirect("cms:entries", collection=collection)


@editor_required
@require_POST
def entries_bulk(request, collection):
    theme = load_theme()
    if collection not in theme.collections:
        raise Http404
    action = request.POST.get("action")
    ids = [int(i) for i in request.POST.getlist("ids") if i.isdigit()]
    qs = Entry.objects.filter(collection=collection, pk__in=ids)
    n = qs.count()
    if not n or action not in ("show", "hide", "delete"):
        messages.error(request, _t(request, "Choose an action and at least one record."))
        return redirect("cms:entries", collection=collection)
    keys = ", ".join(qs.values_list("key", flat=True))[:250]
    if action == "delete":
        qs.delete()
    else:
        for e in qs:
            e.is_published = action == "show"
            if action == "show":
                e.review_requested_at = None
            e.updated_by = request.user
            e.save(update_fields=["is_published", "review_requested_at", "updated_by", "updated_at"])
    audit(request, f"entries_{action}", f"{collection}: {keys}")
    from .ui_i18n import count, ui_lang
    publish_and_report(request, _t(request, "Done:") + " " + count(n, "records", ui_lang(request)) + ";")
    return redirect("cms:entries", collection=collection)


@writer_required
def api_entries(request, collection):
    theme = load_theme()
    if collection not in theme.collections:
        raise Http404
    return JsonResponse({"items": entry_options(theme, collection)})


# ---------------------------------------------------------------- media
@writer_required
def media_library(request):
    q = request.GET.get("q", "").strip()
    items = Media.objects.all()
    if q:
        items = items.filter(Q(title__icontains=q) | Q(file__icontains=q))
    from .media_usage import usage_index
    used = usage_index()
    unused_only = request.GET.get("unused") == "1"
    rows = []
    for m in items:
        if unused_only and m.pk in used:
            continue
        j = media_json(m)
        j["used_in"] = [{"label": label, "url": url} for label, url in used.get(m.pk, [])[:8]]
        j["used_count"] = len(used.get(m.pk, []))
        rows.append(j)
        if len(rows) >= 300:
            break
    unused = sum(1 for m in Media.objects.only("pk") if m.pk not in used)
    return render(request, "cms/media.html", {"items": rows, "q": q, "langs": languages(), "unused_only": unused_only,
                                              "unused_total": unused})


@writer_required
def api_media(request):
    q = request.GET.get("q", "").strip()
    items = Media.objects.all()
    if q:
        items = items.filter(Q(title__icontains=q) | Q(file__icontains=q))
    if request.GET.get("images") == "1" or request.GET.get("kind") == "image":
        items = items.filter(mime__startswith="image/")
    elif request.GET.get("kind") == "video":
        items = items.filter(mime__startswith="video/")
    return JsonResponse({"items": [media_json(m) for m in items[:200]]})


@writer_required
@require_POST
def media_upload(request):
    files = request.FILES.getlist("files")
    done, errors = [], []
    for f in files[:20]:
        try:
            done.append(media_json(save_upload(f, request.user)))
            audit(request, "media_upload", f.name)
        except MediaError as exc:
            errors.append(f"{f.name}: {_t(request, str(exc))}")
    return JsonResponse({"items": done, "errors": errors}, status=200 if done or not errors else 400)


@writer_required
@require_POST
def media_update(request, media_id):
    m = get_object_or_404(Media, pk=media_id)
    m.title = request.POST.get("title", m.title)[:200]
    m.alt = {l.code: request.POST.get(f"alt_{l.code}", "")[:300] for l in languages()}
    m.save()
    return JsonResponse({"item": media_json(m)})


@editor_required
@require_POST
def media_delete(request, media_id):
    m = get_object_or_404(Media, pk=media_id)
    from .media_usage import usage_index
    if usage_index().get(m.pk):
        return JsonResponse({"error": _t(request, "This file is in use. Remove it from those pages first, or use Replace file.")}, status=400)
    delete_media(m)
    audit(request, "media_delete", m.title or m.file.name)
    return JsonResponse({"ok": True})


@editor_required
@require_POST
def media_replace(request, media_id):
    from .media_usage import replace_file
    m = get_object_or_404(Media, pk=media_id)
    upload = request.FILES.get("file")
    if not upload:
        return JsonResponse({"error": _t(request, "Choose a file.")}, status=400)
    try:
        replace_file(m, upload)
    except MediaError as exc:
        return JsonResponse({"error": _t(request, str(exc))}, status=400)
    audit(request, "media_replace", f"#{m.pk} {m.file.name}")
    log = publish_site(request.user)
    return JsonResponse({"item": media_json(m), "published": log.ok})


def serve_file(root, path):
    root = Path(root).resolve()
    target = (root / path).resolve()
    if root not in target.parents or not target.is_file():
        raise Http404
    ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    return FileResponse(open(target, "rb"), content_type=ctype)


@login_required
def serve_upload(request, path):
    return serve_file(settings.MEDIA_ROOT, path)


@login_required
def serve_asset(request, path):
    return serve_file(load_theme().static_dir, path)


# ---------------------------------------------------------------- menus, settings, redirects
@editor_required
def menus(request):
    langs = languages()
    keys = ["header", "footer"]
    if request.method == "POST":
        try:
            data = json.loads(request.POST.get("menus_json") or "{}")
        except json.JSONDecodeError:
            data = {}
        for key in keys:
            for l in langs:
                items = clean_menu(data.get(key, {}).get(l.code, []))
                Menu.objects.update_or_create(key=key, language=l, defaults={"items": items})
        audit(request, "menus_save")
        publish_and_report(request, "Menus")
        return redirect("cms:menus")
    current = {k: {l.code: (Menu.objects.filter(key=k, language=l).values_list("items", flat=True).first() or []) for l in langs} for k in keys}
    return render(request, "cms/menus.html", {"menus_json": json.dumps(current, ensure_ascii=False), "langs": langs})


def clean_menu(items, depth=0):
    from .fields import clean_url
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        row = {"label": str(it.get("label", ""))[:120], "url": clean_url(it.get("url"))}
        if it.get("contact"):
            row["contact"] = True
        if depth == 0 and it.get("children"):
            row["children"] = clean_menu(it["children"], 1)
        out.append(row)
    return out[:40]


@admin_required
def site_settings(request):
    langs = languages()
    if request.method == "POST":
        Setting.objects.update_or_create(key="contact_email", defaults={"value": request.POST.get("contact_email", "").strip()[:200]})
        from .forms_api import DEFAULT_LEADS_EMAIL, EMAIL_RE
        leads = request.POST.get("leads_email", "").strip()[:254]
        if leads and not EMAIL_RE.fullmatch(leads):
            messages.error(request, _t(request, "The leads email address is not valid. It was not changed."))
        else:
            Setting.objects.update_or_create(key="leads_email", defaults={"value": leads or DEFAULT_LEADS_EMAIL})
        from .models import UserSecurity
        from .demo import on as demo_on
        want_2fa = request.POST.get("require_2fa") == "on" and not demo_on()   # would lock the shared demo account
        if want_2fa and not UserSecurity.objects.filter(user=request.user, enabled=True).exists():
            messages.error(request, _t(request, "Turn on two-step verification for your own account first."))
            want_2fa = False
        Setting.objects.update_or_create(key="require_2fa", defaults={"value": want_2fa})
        Setting.objects.update_or_create(key="header_cta", defaults={"value": {
            l.code: {"label": request.POST.get(f"cta_label_{l.code}", "")[:80], "url": request.POST.get(f"cta_url_{l.code}", "")[:300]} for l in langs}})
        audit(request, "settings_save")
        publish_and_report(request, "Settings")
        return redirect("cms:settings")
    values = {s.key: s.value for s in Setting.objects.all()}
    from .forms_api import leads_email
    values["leads_email"] = leads_email()
    return render(request, "cms/settings.html", {"langs": langs, "values": values, "theme": load_theme(),
                                                 "redirects": Redirect.objects.all()})


@admin_required
@require_POST
def redirect_add(request):
    from .publish import valid_redirect
    src, dst = request.POST.get("source", "").strip(), request.POST.get("target", "").strip()
    if valid_redirect(src, dst):
        Redirect.objects.update_or_create(source=src, defaults={"target": dst})
        audit(request, "redirect_add", f"{src} -> {dst}")
        publish_and_report(request, "Redirect")
    else:
        messages.error(request, "Use a path such as /old-page/ for the old address, and /new-page/ or https://… for the new one (letters, numbers, - _ . / only).")
    return redirect("cms:settings")


@admin_required
@require_POST
def redirect_delete(request, redirect_id):
    audit(request, "redirect_delete", str(Redirect.objects.filter(pk=redirect_id).values_list("source", flat=True).first()))
    Redirect.objects.filter(pk=redirect_id).delete()
    publish_and_report(request, "Redirect removed;")
    return redirect("cms:settings")


# ---------------------------------------------------------------- users
@admin_required
def users(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        role = request.POST.get("role", "editor")
        role = role if role in ROLES else "editor"
        from django.contrib.auth.password_validation import ValidationError, validate_password
        if not username or User.objects.filter(username=username).exists():
            messages.error(request, "Choose a username that is not taken.")
        else:
            try:
                validate_password(password)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                u = User.objects.create_user(username=username, email=email, password=password, is_staff=True)
                set_role(u, role)
                audit(request, "user_create", f"{username} ({role})")
                messages.success(request, f"User {username} created.")
        return redirect("cms:users")
    rows = [(u, role_of(u)) for u in User.objects.order_by("username").prefetch_related("groups")]
    return render(request, "cms/users.html", {"users": rows, "roles": ROLES})


@admin_required
@require_POST
def user_role(request, user_id):
    u = get_object_or_404(User, pk=user_id)
    role = request.POST.get("role")
    if u == request.user:
        messages.error(request, _t(request, "You cannot change your own role."))
    elif role in ROLES:
        set_role(u, role)
        audit(request, "user_role", f"{u.get_username()} -> {role}")
        messages.success(request, _t(request, "Role updated."))
    return redirect("cms:users")


@admin_required
@require_POST
def user_toggle(request, user_id):
    u = get_object_or_404(User, pk=user_id)
    if u == request.user:
        messages.error(request, "You cannot deactivate your own account.")
    else:
        u.is_active = not u.is_active
        u.save(update_fields=["is_active"])
        audit(request, "user_activate" if u.is_active else "user_deactivate", u.get_username())
        messages.success(request, f"{u.username} is now {'active' if u.is_active else 'deactivated'}.")
    return redirect("cms:users")


@login_required
def account(request):
    if request.method == "POST":
        from django.contrib.auth import update_session_auth_hash
        from django.contrib.auth.password_validation import ValidationError, validate_password
        if request.POST.get("form") == "digest":
            from .digest import set_pref
            on = request.POST.get("digest") == "on"
            set_pref(request.user, on, request.POST.get("digest_lang", "en"))
            audit(request, "digest_on" if on else "digest_off")
            messages.success(request, _t(request, "Saved."))
            return redirect("cms:account")
        if not request.user.check_password(request.POST.get("current", "")):
            messages.error(request, _t(request, "Your current password is not correct."))
        else:
            try:
                validate_password(request.POST.get("new", ""), request.user)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                request.user.set_password(request.POST["new"])
                audit(request, "password_change")
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, _t(request, "Password changed."))
        return redirect("cms:account")
    from .digest import pref
    from . import mail
    from shield.alerts import pref as shield_pref
    return render(request, "cms/account.html", {"digest": pref(request.user), "mail_ready": mail.ready(),
                                                "shield_alerts": shield_pref(request.user)})


# ---------------------------------------------------------------- inbox
@crm_required
def inbox(request):
    from .forms_api import smtp_ready
    from .models import FormSubmission
    status = request.GET.get("status", "open")
    qs = FormSubmission.objects.all()
    if status == "open":
        qs = qs.exclude(status=FormSubmission.ARCHIVED)
    elif status in {"new", "read", "archived"}:
        qs = qs.filter(status=status)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(organisation__icontains=q) | Q(message__icontains=q)
                       | Q(topic__icontains=q) | Q(service__iexact=q))
    form = request.GET.get("form", "")
    if form in dict(FormSubmission.SOURCES):
        qs = qs.filter(source=form)
    elif form == "unsent":
        qs = qs.filter(email_sent=False)
    return render(request, "cms/inbox.html", {"items": qs[:500], "status": status, "q": q, "smtp": smtp_ready(), "form": form,
                                              "forms": FormSubmission.SOURCES, "unsent": FormSubmission.objects.filter(email_sent=False).exclude(status=FormSubmission.ARCHIVED).count(),
                                              "counts": {s: FormSubmission.objects.filter(status=s).count() for s in ("new", "read", "archived")}})


@crm_required
def inbox_item(request, sub_id):
    from .models import FormSubmission
    sub = get_object_or_404(FormSubmission, pk=sub_id)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            sub.delete()
            messages.success(request, _t(request, "Enquiry deleted permanently."))
            return redirect("cms:inbox")
        if action == "resend":
            from .forms_api import leads_email, send_copy
            if send_copy(sub):
                audit(request, "enquiry_resend", f"#{sub.pk}")
                messages.success(request, _t(request, "Email sent to") + " " + leads_email())
            else:
                messages.error(request, _t(request, "The email could not be sent. The enquiry is still saved here.") + " " + sub.email_error)
            return redirect("cms:inbox_item", sub_id=sub.pk)
        if action in {"new", "read", "archived"}:
            sub.status = action
        sub.note = request.POST.get("note", sub.note)[:4000]
        sub.save()
        messages.success(request, _t(request, "Saved."))
        return redirect("cms:inbox_item", sub_id=sub.pk)
    if sub.status == FormSubmission.NEW:
        sub.status = FormSubmission.READ
        sub.save(update_fields=["status"])
    from .forms_api import leads_email, service_label
    return render(request, "cms/inbox_item.html", {"sub": sub, "leads_email": leads_email(),
                                                   "service_label": service_label(sub.service) if sub.service else ""})


@admin_required
def inbox_export(request):
    import csv
    from .models import FormSubmission
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="enquiries.csv"'
    resp.write("\ufeff")  # Excel opens Arabic correctly with a BOM
    w = csv.writer(resp)
    w.writerow(["date", "status", "name", "email", "organisation", "phone", "interest", "service", "form", "topic", "page",
                "language", "message", "note", "emailed"])
    for s in FormSubmission.objects.all():
        w.writerow([timezone.localtime(s.created_at).strftime("%Y-%m-%d %H:%M"), s.status, s.name, s.email, s.organisation,
                    s.phone, s.interest, s.service, s.source, s.topic, s.page, s.language, s.message, s.note, "yes" if s.email_sent else "no"])
    return resp


@login_required
@require_POST
def set_ui_language(request):
    lang = request.POST.get("lang")
    if lang in {"en", "ar"}:
        request.session["ui_lang"] = lang
    return redirect(request.POST.get("next") or "cms:dashboard")


def set_password(request, uidb64, token):
    """One-time password setup / reset link created by `manage.py password_link`."""
    from django.contrib.auth.forms import SetPasswordForm
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_str
    from django.utils.http import urlsafe_base64_decode
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        return render(request, "cms/set_password.html", {"invalid": True}, status=400)
    form = SetPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()  # changing the password invalidates this link
        if getattr(getattr(user, "security", None), "enabled", False):
            return redirect("cms:login")  # the second step still applies
        login(request, user)
        audit(request, "login", "password link")
        return redirect("cms:dashboard")
    return render(request, "cms/set_password.html", {"form": form, "username": user.get_username()})


# ---------------------------------------------------------------- two-step verification
def safe_next(url):
    from django.utils.http import url_has_allowed_host_and_scheme
    return url if url and url_has_allowed_host_and_scheme(url, allowed_hosts=None) and url.startswith("/") else ""


def login_verify(request):
    from . import totp
    from .models import UserSecurity
    uid = request.session.get("2fa_user")
    if not uid or int(timezone.now().timestamp()) > request.session.get("2fa_until", 0):
        for k in ("2fa_user", "2fa_backend", "2fa_until", "2fa_next"):
            request.session.pop(k, None)
        return redirect("cms:login")
    error = None
    if request.method == "POST":
        key = f"2fa-fail:{uid}:{client_ip(request)}"
        if cache.get(key, 0) >= 6:
            error = "Too many attempts. Wait 15 minutes and try again."
        else:
            sec = UserSecurity.objects.select_related("user").get(user_id=uid)
            code = request.POST.get("code", "").strip()
            ok = False
            step = totp.verify(sec.totp_secret, code, sec.last_step)
            if step:
                sec.last_step = step
                sec.save(update_fields=["last_step"])
                ok = True
            elif len(code) > 8:
                remaining = totp.use_recovery_code(sec.recovery_codes, code)
                if remaining is not None:
                    sec.recovery_codes = remaining
                    sec.save(update_fields=["recovery_codes"])
                    ok = True
                    messages.warning(request, f"You signed in with a recovery code. {len(remaining)} codes are left.")
            if ok:
                user = sec.user
                user.backend = request.session.get("2fa_backend")
                nxt = request.session.get("2fa_next") or ""
                remember = request.session.get("2fa_remember")
                for k in ("2fa_user", "2fa_backend", "2fa_until", "2fa_next", "2fa_remember"):
                    request.session.pop(k, None)
                login(request, user)
                remember_session(request, remember)
                audit(request, "login", "two-step")
                cache.delete(key)
                return redirect(nxt or "cms:dashboard")
            cache.set(key, cache.get(key, 0) + 1, 900)
            audit(request, "login_failed", "two-step code", username=str(uid))
            error = "That code is not correct. Use the current code from your app, or a recovery code."
    return render(request, "cms/login_verify.html", {"error": error})


@login_required
def security(request):
    """Enable / disable two-step verification and regenerate recovery codes."""
    from . import totp
    from .models import UserSecurity
    sec, _ = UserSecurity.objects.get_or_create(user=request.user)
    ctx = {"sec": sec, "codes": None, "required": bool(Setting.objects.filter(key="require_2fa", value=True).exists())}
    action = request.POST.get("action") if request.method == "POST" else None

    if action == "confirm":
        secret = request.session.get("2fa_setup_secret")
        step = totp.verify(secret, request.POST.get("code"))
        if secret and step:
            plain, hashes = totp.new_recovery_codes()
            sec.totp_secret, sec.enabled, sec.last_step, sec.recovery_codes = secret, True, step, hashes
            sec.enabled_at = timezone.now()
            audit(request, "2fa_enable")
            sec.save()
            request.session.pop("2fa_setup_secret", None)
            ctx["codes"] = plain  # shown once
            messages.success(request, _t(request, "Two-step verification is on."))
            return render(request, "cms/security.html", ctx)
        messages.error(request, _t(request, "That code is not correct. Scan the QR code again and use the newest code."))
    elif action in {"disable", "regenerate"} and sec.enabled:
        if not request.user.check_password(request.POST.get("password", "")) or not totp.verify(sec.totp_secret, request.POST.get("code"), sec.last_step):
            messages.error(request, _t(request, "Your password or code is not correct."))
        elif action == "disable":
            if ctx["required"]:
                messages.error(request, _t(request, "Two-step verification is required on this site."))
            else:
                sec.enabled, sec.totp_secret, sec.recovery_codes = False, "", []
                audit(request, "2fa_disable")
                sec.save()
                messages.success(request, _t(request, "Two-step verification is off."))
        else:
            plain, hashes = totp.new_recovery_codes()
            sec.recovery_codes = hashes
            sec.save(update_fields=["recovery_codes"])
            ctx["codes"] = plain
            return render(request, "cms/security.html", ctx)
        return redirect("cms:security")

    if not sec.enabled:
        secret = request.session.get("2fa_setup_secret") or totp.new_secret()
        request.session["2fa_setup_secret"] = secret
        uri = totp.provisioning_uri(secret, f"{request.user.get_username()}@{settings.TECHNTING_CMS_ADMIN_URL.split('//')[-1]}")
        ctx.update(secret=" ".join(secret[i:i + 4] for i in range(0, len(secret), 4)), qr=totp.qr_svg(uri))
    ctx["codes_left"] = len(sec.recovery_codes)
    return render(request, "cms/security.html", ctx)


INVITE_DAYS = 10


def accept_invite(request, token):
    """Invitation link: the invited user chooses their own password (valid INVITE_DAYS, single use)."""
    from django.contrib.auth.forms import SetPasswordForm
    from .invites import check_token
    user = check_token(token, INVITE_DAYS)
    if user is None:
        return render(request, "cms/set_password.html", {"invalid": True}, status=400)
    form = SetPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()  # the password hash changes, so this link stops working
        user.backend = "django.contrib.auth.backends.ModelBackend"
        login(request, user)
        audit(request, "invite_accept")
        messages.success(request, _t(request, "Welcome. Turn on two-step verification to protect your account."))
        return redirect("cms:security")
    return render(request, "cms/set_password.html", {"form": form, "username": user.get_username()})



# ---------------------------------------------------------------- email settings and invitations
@admin_required
def email_settings(request):
    import smtplib
    from . import mail
    current = Setting.objects.filter(key="smtp").values_list("value", flat=True).first() or {}
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "remove":
            Setting.objects.filter(key="smtp").delete()
            audit(request, "email_settings_remove")
            messages.success(request, _t(request, "Email settings removed."))
            return redirect("cms:email_settings")
        if action == "test":
            to = request.POST.get("test_to", "").strip() or request.user.email
            try:
                mail.send("Technting CMS test email · رسالة تجريبية",
                          "This is a test email from Technting CMS. Email delivery works.\n\nهذه رسالة تجريبية من Technting CMS. إرسال البريد يعمل.", [to])
                messages.success(request, _t(request, "Test email sent to") + f" {to}.")
            except Exception as exc:
                messages.error(request, _t(request, "Sending failed:") + f" {type(exc).__name__}")
            return redirect("cms:email_settings")
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").replace(" ", "").strip()
        preset = mail.PRESETS["gmail"]
        if not password and current.get("password") and current.get("username") == username:
            password = mail.decrypt(current["password"])  # keep the saved password
        if not username or "@" not in username or not password:
            messages.error(request, _t(request, "Enter the Gmail address and its app password."))
            return redirect("cms:email_settings")
        try:
            mail.test_login(preset["host"], preset["port"], preset["security"], username, password)
        except smtplib.SMTPAuthenticationError:
            messages.error(request, _t(request, "Gmail rejected the sign-in. Check the address and use an app password (2-Step Verification must be on)."))
            return redirect("cms:email_settings")
        except Exception as exc:
            messages.error(request, _t(request, "Could not reach Gmail:") + f" {type(exc).__name__}")
            return redirect("cms:email_settings")
        Setting.objects.update_or_create(key="smtp", defaults={"value": {
            **preset, "username": username, "password": mail.encrypt(password),
            "from_name": request.POST.get("from_name", "").strip()[:80] or settings.TECHNTING_CMS_SITE_NAME}})
        audit(request, "email_settings_save", username)
        messages.success(request, _t(request, "Gmail sign-in works. Email settings saved."))
        return redirect("cms:email_settings")
    cfg = mail.config()
    return render(request, "cms/email_settings.html", {"current": current, "cfg": cfg})


@admin_required
@require_POST
def user_invite(request, user_id):
    """(Re)send the 10-day invitation to a user who has not set a password yet."""
    from . import mail
    from .invites import build_email, invite_url
    u = get_object_or_404(User, pk=user_id)
    if u.has_usable_password() or u.last_login:
        messages.error(request, _t(request, "This user has already set a password."))
        return redirect("cms:users")
    if not u.email:
        messages.error(request, _t(request, "Add an email address for this user first."))
        return redirect("cms:users")
    if not mail.ready():
        messages.error(request, _t(request, "Set up email first (Settings → Email)."))
        return redirect("cms:email_settings")
    try:
        build_email(u, invite_url(u), INVITE_DAYS, full_name=u.get_full_name() or u.get_username(),
                    invited_by=request.user.get_full_name() or request.user.get_username()).send()
        messages.success(request, _t(request, "Invitation sent to") + f" {u.email}.")
    except Exception as exc:
        messages.error(request, _t(request, "Sending failed:") + f" {type(exc).__name__}")
    return redirect("cms:users")


# ---------------------------------------------------------------- site health
HEALTH_LABELS = {
    "broken_link": "Broken internal link", "missing_title": "Missing page title", "long_title": "Title longer than 70 characters",
    "duplicate_title": "Same title on several pages", "missing_description": "Missing meta description",
    "missing_canonical": "Missing canonical link", "missing_h1": "No H1 heading", "multiple_h1": "More than one H1 heading",
    "image_no_alt": "Images without alt text",
    "a11y_no_lang": "Accessibility: page language not set", "a11y_empty_link": "Accessibility: links with no text or label",
    "a11y_empty_button": "Accessibility: buttons with no text or label", "a11y_unlabelled_field": "Accessibility: form fields without a label",
    "a11y_iframe_no_title": "Accessibility: embedded frames without a title", "a11y_heading_skip": "Accessibility: heading levels skipped",
    "a11y_vague_link": "Accessibility: vague link text (\"click here\", \"more\")", "a11y_duplicate_id": "Accessibility: the same id used twice",
    "speed_heavy_page": "Speed: page heavier than 1.5 MB", "speed_large_image": "Speed: images larger than 400 KB",
    "speed_image_no_size": "Speed: images without width and height (the page jumps while loading)",
    "speed_blocking_script": "Speed: scripts that delay the first paint",
    "schema_error": "Search: structured data (JSON-LD) with errors", "og_image": "Sharing image missing or smaller than 1200×630",
}
HEALTH_SEVERITY = {"broken_link": "high", "missing_title": "high", "missing_h1": "medium", "duplicate_title": "medium",
                   "missing_description": "medium", "missing_canonical": "medium", "multiple_h1": "low", "long_title": "low",
                   "image_no_alt": "low", "a11y_no_lang": "high", "a11y_empty_link": "medium", "a11y_empty_button": "medium",
                   "a11y_unlabelled_field": "medium", "a11y_iframe_no_title": "low", "a11y_heading_skip": "low", "a11y_vague_link": "low",
                   "a11y_duplicate_id": "low", "speed_heavy_page": "medium", "speed_large_image": "medium", "speed_image_no_size": "low",
                   "speed_blocking_script": "low", "schema_error": "medium", "og_image": "low"}


@editor_required
def site_health(request):
    from .health import load
    data = load()
    groups = []
    if data:
        by_kind = {}
        for i in data["issues"]:
            by_kind.setdefault(i["kind"], []).append(i)
        order = {"high": 0, "medium": 1, "low": 2}
        for kind, items in sorted(by_kind.items(), key=lambda kv: (order[HEALTH_SEVERITY.get(kv[0], "low")], kv[0])):
            groups.append({"kind": kind, "label": HEALTH_LABELS.get(kind, kind), "severity": HEALTH_SEVERITY.get(kind, "low"),
                           "items": items[:200], "count": len(items)})
    from . import linkcheck
    links = linkcheck.load()
    link_rows = [i for i in (links or {}).get("items", []) if i["verdict"] != "ok"]
    order = {"not_found": 0, "error": 1, "unreachable": 2, "blocked": 3}
    link_rows.sort(key=lambda i: (order.get(i["verdict"], 4), i["url"]))
    return render(request, "cms/health.html", {"data": data, "groups": groups, "site_url": settings.TECHNTING_CMS_SITE_URL,
                                               "links": links, "link_rows": link_rows,
                                               "links_broken": sum(1 for i in link_rows if i["verdict"] in ("not_found", "error"))})


@admin_required
@require_POST
def health_check_links(request):
    from . import linkcheck
    linkcheck.run_in_background()
    audit(request, "links_check")
    messages.info(request, _t(request, "Checking external links. Refresh this page in a minute or two."))
    return redirect("cms:health")


# ---------------------------------------------------------------- activity log
@admin_required
def activity(request):
    from .models import AuditEvent
    qs = AuditEvent.objects.all()
    who, what = request.GET.get("user", "").strip(), request.GET.get("action", "").strip()
    if who:
        qs = qs.filter(username=who)
    if what:
        qs = qs.filter(action=what)
    return render(request, "cms/activity.html", {
        "events": qs[:500], "who": who, "what": what,
        "users": AuditEvent.objects.exclude(username="").values_list("username", flat=True).distinct().order_by("username"),
        "actions": AuditEvent.objects.values_list("action", flat=True).distinct().order_by("action")})


# ---------------------------------------------------------------- plugins
@admin_required
def plugins_page(request):
    from . import plugins as P
    from .fields import clean_fields
    available = P.available()
    enabled = set(P.enabled_names())
    if request.method == "POST":
        try:
            data = json.loads(request.POST.get("plugins_json") or "{}")
        except json.JSONDecodeError:
            data = {}
        new_enabled = [n for n in available if (data.get(n) or {}).get("enabled")]
        Setting.objects.update_or_create(key="plugins_enabled", defaults={"value": new_enabled})
        audit(request, "plugins_save", ", ".join(new_enabled))
        for name, spec in available.items():
            values = clean_fields(spec.get("settings", []), (data.get(name) or {}).get("settings") or {})
            refused = []
            P.keep_secrets(spec, P.plugin_settings(name), values, refused)
            for f in refused:
                messages.error(request, f'{_t(request, "This is not a valid JSON file, so it was not saved:")} {_t(request, f["label"])}')
            Setting.objects.update_or_create(key=f"plugin:{name}", defaults={"value": values})
        P.load(force=True)
        publish_and_report(request, "Plugins")
        return redirect("cms:plugins")
    rows = [{"name": n, "spec": s, "enabled": n in enabled, "settings": P.browser_settings(s, P.plugin_settings(n))}
            for n, s in available.items()]
    return render(request, "cms/plugins.html", {"rows": rows, "rows_json": json.dumps(rows, ensure_ascii=False, default=str)})
