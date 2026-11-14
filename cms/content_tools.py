"""Automatic redirects when a page moves, duplicate pages and records, and revision compare.

The WordPress counterparts: Redirection's "monitor permalink changes", Yoast Duplicate Post, and the revisions
screen's compare view.
"""
import difflib
import html
import re

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from .audit import audit
from .models import Entry, EntryTranslation, Page, PageTranslation, Redirect, Revision
from .views import _t, editor_required, snapshot_translation, write_revision


# ---------------------------------------------------------------- redirects when a page moves
def subtree(page):
    """The page and all pages below it."""
    out, todo = [], [page]
    while todo:
        p = todo.pop()
        out.append(p)
        todo.extend(Page.objects.filter(parent=p))
    return out


def live_urls(page, language):
    """{translation pk: public URL} for live translations of the page and its descendants, from the saved state."""
    pages = subtree(page)
    return {t.pk: t.url for t in PageTranslation.objects.filter(page__in=pages, language=language).select_related("language")
            if t.is_live}


def add_redirect(source, target):
    """301 from source to target, without loops or chains. Returns True when a redirect was added or changed."""
    from .publish import valid_redirect
    if not valid_redirect(source, target):
        return False
    Redirect.objects.filter(source=target).delete()                 # the page lives at target now
    Redirect.objects.filter(target=source).update(target=target)    # old redirects skip straight to the new address
    Redirect.objects.filter(source=source, target=source).delete()
    Redirect.objects.update_or_create(source=source, defaults={"target": target, "permanent": True})
    return True


def follow_moves(page, language, before):
    """After a page was saved: refresh the stored paths below it and redirect every live address that changed."""
    for p in subtree(page):
        for t in PageTranslation.objects.filter(page=p, language=language).select_related("language"):
            if p.pk != page.pk and t.compute_path() != t.path:
                t.save(update_fields=["path"])
    after = live_urls(page, language)
    moved = []
    for pk, old in before.items():
        new = after.get(pk)
        if new and new != old and add_redirect(old, new):
            moved.append((old, new))
    return moved


# ---------------------------------------------------------------- duplicate
def _free_slug(language, parent, slug):
    base, n = f"{slug}-copy" if slug else "copy", 2
    candidate = base
    while PageTranslation.objects.filter(language=language, slug=candidate, page__parent=parent).exists():
        candidate, n = f"{base}-{n}", n + 1
    return candidate


@editor_required
@require_POST
def page_duplicate(request, page_id):
    src = get_object_or_404(Page, pk=page_id)
    with transaction.atomic():
        copy = Page.objects.create(key=None, parent=src.parent, template=src.template, data=src.data, order=src.order + 1,
                                   in_sitemap=src.in_sitemap)
        for t in src.translations.select_related("language"):
            n = PageTranslation(page=copy, language=t.language, title=f"{t.title} ({_t(request, 'copy')})",
                                slug=_free_slug(t.language, src.parent, t.slug), blocks=t.blocks, seo_title="",
                                seo_description=t.seo_description, og_image=t.og_image, noindex=t.noindex,
                                status=PageTranslation.DRAFT, updated_by=request.user)
            n.save()
            write_revision("page", n.pk, t.language.code, snapshot_translation(n), request.user, f"copy of page #{src.pk}")
    audit(request, "page_duplicate", f"{src} → #{copy.pk}")
    messages.success(request, _t(request, "Copy created as a draft. Change its title and address before publishing."))
    first = copy.translations.select_related("language").first()
    return redirect("cms:page_edit", page_id=copy.pk, lang=first.language.code if first else "en")


@editor_required
@require_POST
def entry_duplicate(request, collection, entry_id):
    from .theme import load_theme
    src = get_object_or_404(Entry, pk=entry_id, collection=collection)
    spec = load_theme().collections.get(collection, {})
    title_field = spec.get("title_field", "name")
    base, n = f"{src.key}-copy", 2
    key = base
    while Entry.objects.filter(collection=collection, key=key).exists():
        key, n = f"{base}-{n}", n + 1
    with transaction.atomic():
        copy = Entry.objects.create(collection=collection, key=key[:80], data=src.data, order=src.order + 1, is_published=False,
                                    publish_at=None, updated_by=request.user, created_by=request.user)
        for t in src.translations.select_related("language"):
            data = dict(t.data or {})
            if data.get(title_field):
                data[title_field] = f"{data[title_field]} ({_t(request, 'copy')})"
            EntryTranslation.objects.create(entry=copy, language=t.language, data=data)
        write_revision("entry", copy.pk, "", {"data": copy.data, "translations": {
            t.language.code: t.data for t in copy.translations.select_related("language")}}, request.user, f"copy of {src.key}")
    audit(request, "entry_duplicate", f"{collection}:{src.key} → {key}")
    messages.success(request, _t(request, "Copy created as a draft. Change its title and address before publishing."))
    lang = request.POST.get("lang") or "en"
    return redirect("cms:entry_edit", collection=collection, entry_id=copy.pk, lang=lang)


# ---------------------------------------------------------------- revision compare
TAG = re.compile(r"<[^>]+>")
BLOCK_END = re.compile(r"</(p|h[1-6]|li|tr|div|blockquote)>|<br\s*/?>", re.I)
SKIP = {"id", "type", "cover", "photo", "image", "og_image", "media", "video", "poster"}


def _text(v):
    if isinstance(v, str):
        if "<" in v:
            v = html.unescape(TAG.sub("", BLOCK_END.sub("\n", v)))
        return "\n".join(line.strip() for line in v.splitlines() if line.strip())
    if isinstance(v, bool) or v is None:
        return "" if v is None else str(v)
    return str(v)


def flatten(value, prefix=""):
    """{"Hero › title": "text", ...} from a snapshot, for a readable comparison."""
    out = {}
    if isinstance(value, dict):
        for k, v in value.items():
            if k in SKIP:
                continue
            label = f"{prefix} › {k}" if prefix else k
            out.update(flatten(v, label))
    elif isinstance(value, list):
        for i, v in enumerate(value, 1):
            label = f"{prefix} {i}" if prefix else str(i)
            if isinstance(v, dict) and v.get("type"):
                label = f"{prefix} {i} ({v['type']})" if prefix else f"{i} ({v['type']})"
            out.update(flatten(v.get("data", v) if isinstance(v, dict) and "data" in v else v, label))
    else:
        t = _text(value)
        if t:
            out[prefix] = t
    return out


def word_diff(a, b):
    """HTML with removed words in <del> and added words in <ins>."""
    wa, wb = re.findall(r"\S+|\s+", a), re.findall(r"\S+|\s+", b)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, wa, wb, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(escape("".join(wa[i1:i2])))
        if op in ("delete", "replace"):
            out.append("<del>" + escape("".join(wa[i1:i2])) + "</del>")
        if op in ("insert", "replace"):
            out.append("<ins>" + escape("".join(wb[j1:j2])) + "</ins>")
    return mark_safe("".join(out).replace("\n", "<br>"))


def _current_snapshot(rev):
    if rev.object_type == "page":
        t = PageTranslation.objects.filter(pk=rev.object_id).select_related("page", "language").first()
        return t, (snapshot_translation(t) if t else None)
    e = Entry.objects.filter(pk=rev.object_id).first()
    if not e:
        return None, None
    return e, {"data": e.data, "translations": {t.language.code: t.data for t in e.translations.select_related("language")}}


@editor_required
def revision_compare(request, revision_id):
    rev = get_object_or_404(Revision, pk=revision_id)
    obj, current = _current_snapshot(rev)
    if current is None:
        messages.error(request, _t(request, "This item no longer exists."))
        return redirect("cms:dashboard")
    old, new = rev.snapshot, current
    if rev.object_type == "entry" and rev.language:  # compare the shared fields and the revision's language only
        old = {"data": old.get("data", {}), rev.language: old.get("translations", {}).get(rev.language, {})}
        new = {"data": new.get("data", {}), rev.language: new.get("translations", {}).get(rev.language, {})}
    if rev.object_type == "page":
        old, new = {k: v for k, v in old.items() if k != "page"}, {k: v for k, v in new.items() if k != "page"}
    fo, fn = flatten(old), flatten(new)
    changes = []
    for k in list(dict.fromkeys(list(fo) + list(fn))):
        a, b = fo.get(k, ""), fn.get(k, "")
        if a != b:
            changes.append({"field": k, "kind": "added" if not a else "removed" if not b else "changed", "html": word_diff(a, b)})
    from django.urls import reverse
    if rev.object_type == "page":
        back, title = reverse("cms:page_edit", args=[obj.page_id, obj.language.code]), obj.title
    else:
        back, title = reverse("cms:entry_edit", args=[obj.collection, obj.pk, rev.language or "en"]), obj.key
    return render(request, "cms/revision_compare.html", {"rev": rev, "changes": changes, "title": title, "back": back})


# ---------------------------------------------------------------- translations overview
@editor_required
def translations_view(request):
    """Which pages and records miss a language, or were changed in the default language after the translation
    (in the spirit of WPML's translation dashboard)."""
    from django.db.models import Max
    from django.urls import reverse
    from .models import Language
    from .theme import load_theme
    langs = list(Language.objects.order_by("order"))
    default = next((l for l in langs if l.is_default), langs[0])
    others = [l for l in langs if l.pk != default.pk]
    theme = load_theme()
    rows = []
    for page in Page.objects.prefetch_related("translations__language").order_by("order", "id"):
        trs = {t.language.code: t for t in page.translations.all()}
        base = trs.get(default.code)
        title = base.title if base else next((t.title for t in trs.values()), page.key or f"#{page.pk}")
        states = []
        for l in others:
            t = trs.get(l.code)
            if not t:
                states.append({"lang": l.code, "state": "missing"})
            elif base and base.updated_at > t.updated_at and (base.updated_at - t.updated_at).total_seconds() > 3600:
                states.append({"lang": l.code, "state": "outdated", "days": (base.updated_at - t.updated_at).days})
            else:
                states.append({"lang": l.code, "state": "ok"})
        rows.append({"kind": "Page", "title": title, "states": states, "live": bool(base and base.is_live),
                     "url": reverse("cms:page_edit", args=[page.pk, default.code]),
                     "edit": {s["lang"]: reverse("cms:page_edit", args=[page.pk, s["lang"]]) for s in states}})
    last = {(r["object_id"], r["language"]): r["t"] for r in Revision.objects.filter(object_type="entry")
            .values("object_id", "language").annotate(t=Max("created_at"))}
    for e in Entry.objects.prefetch_related("translations__language").order_by("collection", "order", "key"):
        spec = theme.collections.get(e.collection, {})
        trs = {t.language.code: t.data for t in e.translations.all()}
        title_field = spec.get("title_field", "name")
        title = (trs.get(default.code) or {}).get(title_field) or e.key
        states = []
        base_t = last.get((e.pk, default.code))
        for l in others:
            if l.code not in trs or not trs[l.code]:
                states.append({"lang": l.code, "state": "missing"})
                continue
            t = last.get((e.pk, l.code))
            if base_t and t and base_t > t and (base_t - t).total_seconds() > 3600:
                states.append({"lang": l.code, "state": "outdated", "days": (base_t - t).days})
            else:
                states.append({"lang": l.code, "state": "ok"})
        rows.append({"kind": spec.get("label", e.collection), "title": title, "states": states, "live": e.is_published,
                     "url": reverse("cms:entry_edit", args=[e.collection, e.pk, default.code]),
                     "edit": {s["lang"]: reverse("cms:entry_edit", args=[e.collection, e.pk, s["lang"]]) for s in states}})
    show = request.GET.get("show", "attention")
    attention = [r for r in rows if any(s["state"] != "ok" for s in r["states"])]
    counts = {"all": len(rows), "attention": len(attention),
              "missing": sum(1 for r in rows if any(s["state"] == "missing" for s in r["states"])),
              "outdated": sum(1 for r in rows if any(s["state"] == "outdated" for s in r["states"]))}
    if show == "attention":
        rows = attention
    elif show in ("missing", "outdated"):
        rows = [r for r in rows if any(s["state"] == show for s in r["states"])]
    return render(request, "cms/translations.html", {"rows": rows, "counts": counts, "show": show, "default": default,
                                                      "others": others})


# ---------------------------------------------------------------- edit lock (WordPress post lock)
LOCK_TTL = 90  # seconds; the editor sends a heartbeat every 30 seconds


def _lock_key(kind, pk, lang):
    return f"editlock:{kind}:{int(pk)}:{lang}"


def lock_holder(request, kind, pk, lang):
    """The other person editing this item right now, or None."""
    from django.core.cache import cache
    v = cache.get(_lock_key(kind, pk, lang))
    return v if v and v.get("user") != request.user.pk else None


@require_POST
def edit_lock(request):
    """Heartbeat from an open editor: {kind, id, lang, action: beat|take|release}."""
    import json as _json
    from django.core.cache import cache
    from django.http import JsonResponse
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"ok": False}, status=403)
    try:
        d = _json.loads(request.body)
        kind, pk, lang, action = d["kind"], int(d["id"]), str(d["lang"])[:8], d.get("action", "beat")
        assert kind in ("page", "entry")
    except (ValueError, KeyError, TypeError, AssertionError):
        return JsonResponse({"ok": False}, status=400)
    key = _lock_key(kind, pk, lang)
    other = lock_holder(request, kind, pk, lang)
    if action == "release":
        if not other:
            cache.delete(key)
        return JsonResponse({"ok": True})
    if other and action != "take":
        return JsonResponse({"ok": True, "locked_by": other["name"]})
    name = request.user.get_full_name() or request.user.get_username()
    cache.set(key, {"user": request.user.pk, "name": name}, LOCK_TTL)
    return JsonResponse({"ok": True, "locked_by": None})


# ---------------------------------------------------------------- quick search (Ctrl+K)
def find_view(request):
    """Search everything the person may open: pages, records, media, CRM and dashboard sections."""
    from django.db.models import Q
    from django.http import JsonResponse
    from django.urls import reverse
    from .models import Media
    from .roles import AUTHOR_COLLECTIONS, role_of
    from .theme import load_theme
    from .ui_i18n import tr, ui_lang
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"items": []}, status=403)
    role = role_of(request.user)
    lang = ui_lang(request)
    q = (request.GET.get("q") or "").strip()[:80]
    items = []

    def add(group, label, url, hint=""):
        items.append({"group": tr(group, lang), "label": label, "url": url, "hint": hint})
    sections = [("Stats", "cms:stats"), ("SEO", "cms:seo"), ("Calendar", "cms:calendar"), ("Translations", "cms:translations"), ("Site health", "cms:health"),
                ("Media", "cms:media"), ("Menus", "cms:menus"), ("Inbox", "cms:inbox"), ("Settings", "cms:settings"), ("Users", "cms:users"),
                ("Plugins", "cms:plugins"), ("Security", "cms:site_security"), ("Backups", "cms:backups"), ("Updates", "cms:updates"),
                ("Find and replace", "cms:replace"),
                ("Activity", "cms:activity"), ("My account", "cms:account")]
    allowed = {"admin": None, "editor": {"Stats", "SEO", "Calendar", "Translations", "Site health", "Media", "Menus", "Inbox", "My account"},
               "sales": {"Stats", "Inbox", "My account"}, "author": {"Media", "My account"}}.get(role, set())
    ql = q.lower()
    for name, urlname in sections:
        if (allowed is None or name in allowed) and (not q or ql in name.lower() or ql in tr(name, lang).lower()):
            add("Dashboard", tr(name, lang), reverse(urlname))
    if len(q) >= 2:
        theme = load_theme()
        if role in ("admin", "editor"):
            for t in PageTranslation.objects.filter(Q(title__icontains=q) | Q(path__icontains=q)).select_related("language")[:8]:
                add("Pages", t.title, reverse("cms:page_edit", args=[t.page_id, t.language.code]), t.url)
        if role in ("admin", "editor", "author"):
            # JSON is stored with escaped Arabic, so match in Python (a few hundred rows)
            ets = EntryTranslation.objects.select_related("entry", "language")
            if role == "author":
                ets = ets.filter(entry__collection__in=AUTHOR_COLLECTIONS, entry__created_by=request.user)
            import json as _json
            seen = set()
            for t in (t for t in ets if ql in t.entry.key.lower() or ql in _json.dumps(t.data, ensure_ascii=False).lower()):
                e = t.entry
                if e.pk in seen:
                    continue
                seen.add(e.pk)
                spec = theme.collections.get(e.collection, {})
                title = (t.data or {}).get(spec.get("title_field", "name")) or e.key
                label = spec.get("label", e.collection)
                group = theme.admin_strings.get("ar", {}).get(label, label) if lang == "ar" else label
                items.append({"group": group, "label": str(title), "url": reverse("cms:entry_edit", args=[e.collection, e.pk, t.language.code]),
                              "hint": e.key})
                if len(seen) >= 10:
                    break
            for m in Media.objects.filter(Q(title__icontains=q) | Q(file__icontains=q))[:5]:
                add("Media", m.title or m.file.name, reverse("cms:media") + f"?q={m.title or ''}")
        if role in ("admin", "editor", "sales"):
            from crm.models import Contact, Deal, Organization
            for c in Contact.objects.filter(Q(name__icontains=q) | Q(email__icontains=q))[:5]:
                add("Contacts", c.name, reverse("crm:contact", args=[c.pk]), c.email)
            for o in Organization.objects.filter(name__icontains=q)[:4]:
                add("Organisations", o.name, reverse("crm:organization", args=[o.pk]))
            for d in Deal.objects.filter(title__icontains=q)[:5]:
                add("Deals", d.title, reverse("crm:deal", args=[d.pk]))
    return JsonResponse({"items": items[:30]})
