"""Stats, search and replace, and backups (the dashboard's answers to Jetpack Stats, Better Search Replace and
UpdraftPlus)."""
import datetime
import io
import json
import re
import tarfile
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.management import call_command
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import stats
from .audit import audit
from .models import EntryTranslation, Menu, PageTranslation
from .views import _t, admin_required, crm_required, editor_required, write_revision, snapshot_translation


# ---------------------------------------------------------------- stats
@csrf_exempt
def api_hit(request):
    """Beacon from public pages. Always answers 204 so it never shows an error on the site."""
    if (request.method == "POST" and len(request.body) <= 2000 and stats.enabled()
            and request.headers.get("Origin") == settings.TECHNTING_CMS_SITE_URL):
        try:
            data = json.loads(request.body)
            if isinstance(data, dict):
                stats.record(request, data)
        except ValueError:
            pass
    return HttpResponse(status=204, headers={"Cache-Control": "no-store"})


@crm_required
def stats_view(request):
    from .ui_i18n import ui_lang
    try:
        days = int(request.GET.get("days", 30))
    except ValueError:
        days = 30
    days = days if days in (7, 30, 90, 365) else 30
    report = stats.report(days, ui_lang(request), request.GET.get("campaign", ""), request.GET.get("content", ""))
    return render(request, "cms/stats.html", {"r": report, "enabled": stats.enabled(),
                                              "site_url": settings.TECHNTING_CMS_SITE_URL, "periods": (7, 30, 90, 365)})


# ---------------------------------------------------------------- search and replace
SKIP_KEYS = {"url", "href", "id", "type", "photo", "cover", "key", "image", "media", "lab", "services", "author", "video",
             "poster", "logo", "source", "collection", "icon", "anchor"}
TAG = re.compile(r"(<[^>]+>)")


def _pattern(find, case):
    return re.compile(re.escape(find), 0 if case else re.IGNORECASE)


def _walk(value, fn, links):
    """Apply fn to every text string; without links, skip link/id fields and the inside of HTML tags."""
    if isinstance(value, str):
        if links:
            return fn(value)
        return "".join(part if TAG.fullmatch(part) else fn(part) for part in TAG.split(value))
    if isinstance(value, list):
        return [_walk(v, fn, links) for v in value]
    if isinstance(value, dict):
        return {k: (v if not links and k in SKIP_KEYS else _walk(v, fn, links)) for k, v in value.items()}
    return value


def _records(scope, lang):
    """(kind, obj, label, edit_url, data) for every text record in scope."""
    from django.urls import reverse
    from .theme import load_theme
    labels = {k: c.get("label", k) for k, c in load_theme().collections.items()}
    if "pages" in scope:
        for t in PageTranslation.objects.select_related("page", "language").order_by("page__key", "language__code"):
            if lang in ("all", t.language.code):
                yield ("page", t, t.title or t.page.key, t.language.code,
                       reverse("cms:page_edit", args=[t.page_id, t.language.code]),
                       {"title": t.title, "seo_title": t.seo_title, "seo_description": t.seo_description, "blocks": t.blocks})
    if "entries" in scope:
        for t in EntryTranslation.objects.select_related("entry", "language").order_by("entry__collection", "entry__key"):
            if lang in ("all", t.language.code):
                e = t.entry
                title = (t.data or {}).get("title") or (t.data or {}).get("name") or e.key
                yield ("entry", t, f"{labels.get(e.collection, e.collection)}: {title}", t.language.code,
                       reverse("cms:entry_edit", args=[e.collection, e.pk, t.language.code]), t.data)
    if "menus" in scope:
        for m in Menu.objects.select_related("language").order_by("key"):
            if lang in ("all", m.language.code):
                yield ("menu", m, f"Menu: {m.key}", m.language.code, reverse("cms:menus"), {"items": m.items})


def _snippets(text_parts, rx, limit=3):
    out = []
    for s in text_parts:
        for m in rx.finditer(s):
            a, b = max(0, m.start() - 50), min(len(s), m.end() + 50)
            out.append(mark_safe(("…" if a else "") + escape(s[a:m.start()]) + "<mark>" + escape(m.group(0)) + "</mark>"
                                 + escape(s[m.end():b]) + ("…" if b < len(s) else "")))
            if len(out) >= limit:
                return out
    return out


def _search(find, scope, lang, case, links):
    rx = _pattern(find, case)
    found = []
    for kind, obj, label, code, url, data in _records(scope, lang):
        hits, texts = [0], []

        def look(s):
            n = len(rx.findall(s))
            if n:
                hits[0] += n
                texts.append(re.sub(r"<[^>]+>", " ", s) if not links else s)
            return s
        _walk(data, look, links)
        if hits[0]:
            found.append({"kind": kind, "obj": obj, "label": label, "lang": code, "url": url, "count": hits[0],
                          "snippets": _snippets(texts, rx), "data": data})
    return found


@admin_required
def replace_view(request):
    src = request.POST if request.method == "POST" else request.GET
    find, repl_with = src.get("find", ""), src.get("replace", "")
    scope = src.getlist("scope") or ["pages", "entries", "menus"]
    lang = src.get("lang", "all")
    case = src.get("case", "1" if not find else "") == "1"
    links = src.get("links") == "1"
    found = _search(find, scope, lang, case, links) if len(find) >= 2 else []
    from .demo import on as demo_on
    if request.method == "POST" and src.get("confirm") == "1" and demo_on() and re.search(r"[<>]", repl_with):
        # rich text is cleaned when it is saved, and a replacement must not add markup behind that check
        messages.error(request, _t(request, "In the public demo, the replacement text cannot contain < or >."))
        return redirect("cms:replace")
    if request.method == "POST" and src.get("confirm") == "1" and found:
        from .publish import publish_site
        rx = _pattern(find, case)
        total = 0
        note = f"replace: {find[:60]} → {repl_with[:60]}"
        for f in found:
            new = _walk(f["data"], lambda s: rx.sub(lambda m: repl_with, s), links)
            obj = f["obj"]
            if f["kind"] == "page":
                obj.title, obj.seo_title, obj.seo_description, obj.blocks = new["title"], new["seo_title"], new["seo_description"], new["blocks"]
                obj.save()
                write_revision("page", obj.pk, f["lang"], snapshot_translation(obj), request.user, note)
            elif f["kind"] == "entry":
                obj.data = new
                obj.save()
                e = obj.entry
                write_revision("entry", e.pk, f["lang"], {"data": e.data, "translations": {
                    x.language.code: x.data for x in e.translations.select_related("language")}}, request.user, note)
            else:
                obj.items = new["items"]
                obj.save()
            total += f["count"]
        audit(request, "replace", f"{note} ({total} in {len(found)})")
        log = publish_site()
        from .ui_i18n import count, ui_lang
        code = ui_lang(request)
        msg = _t(request, "Replaced {n} in {r}.").format(n=count(total, "matches", code), r=count(len(found), "records", code))
        (messages.success if log.ok else messages.warning)(
            request, msg + " " + _t(request, "Site published." if log.ok else "Publishing failed:"))
        return redirect("cms:replace")
    return render(request, "cms/replace.html", {
        "find": find, "replace": repl_with, "scope": scope, "lang": lang, "case": case, "links": links,
        "found": found[:200], "total": sum(f["count"] for f in found), "records": len(found), "searched": len(find) >= 2})


# ---------------------------------------------------------------- backups
def _backup_root():
    return Path(settings.VAR_DIR).parent / "backups" / "technting-cms"


def _snapshots():
    root = _backup_root()
    out = []
    for d in sorted(root.glob("technting-cms-*"), reverse=True) if root.exists() else []:
        if not d.is_dir():
            continue
        size = sum(f.stat().st_size for f in d.iterdir() if f.is_file())
        try:
            manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}
        out.append({"name": d.name, "size": size, "manifest": manifest,
                     "when": re.sub(r"technting-cms-(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)\d\d", r"\1-\2-\3 \4:\5", d.name)})
    return out


@admin_required
def backups_view(request):
    if request.method == "POST":
        out = io.StringIO()
        try:
            call_command("backup", stdout=out)
            audit(request, "backup")
            messages.success(request, _t(request, "Backup created."))
        except Exception as exc:  # shown to the admin; nothing secret in the message
            messages.error(request, _t(request, "Backup failed:") + f" {type(exc).__name__}")
        return redirect("cms:backups")
    from . import offsite
    return render(request, "cms/backups.html", {"snapshots": _snapshots(), "offsite": offsite.status(),
                                                "alerts_on": offsite.wants_alerts(request.user)})


@admin_required
def backup_download(request, name):
    if not re.fullmatch(r"technting-cms-\d{8}-\d{6}", name):
        raise Http404
    d = _backup_root() / name
    if not d.is_dir():
        raise Http404
    buf = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)  # media can be large; spill to disk
    with tarfile.open(fileobj=buf, mode="w") as tar:  # files inside are already compressed
        for f in sorted(d.iterdir()):
            if f.is_file():
                tar.add(f, arcname=f"{name}/{f.name}")
    buf.seek(0)
    audit(request, "backup_download", name)
    return FileResponse(buf, as_attachment=True, filename=f"{name}.tar", content_type="application/x-tar")


# ---------------------------------------------------------------- editorial calendar
def _local_date(dt):
    from django.utils import timezone
    return timezone.localtime(dt).date()


def _calendar_items(first, last, lang="en"):
    """Dated records between first and last (inclusive): scheduled and published entries and scheduled pages."""
    from datetime import date as Date
    from django.urls import reverse
    from django.utils import timezone
    from .models import Entry
    from .theme import load_theme
    now = timezone.now()
    labels = {k: c.get("label", k) for k, c in load_theme().collections.items()}
    items, undated = [], []
    for e in Entry.objects.prefetch_related("translations__language").order_by("collection", "key"):
        tr = {t.language.code: t.data or {} for t in e.translations.all()}
        en = tr.get("en") or next(iter(tr.values()), {})
        own = tr.get(lang) or en
        title = own.get("title") or own.get("name") or en.get("title") or en.get("name") or e.key
        when = _local_date(e.publish_at) if e.publish_at else None
        if not when:
            try:
                when = Date.fromisoformat(str((e.data or {}).get("date") or en.get("date") or "")[:10])
            except ValueError:
                when = None
        if not e.is_published:
            state = "review" if e.review_requested_at else "draft"
        elif e.publish_at and e.publish_at > now:
            state = "scheduled"
        else:
            state = "published"
        item = {"kind": "entry", "id": e.pk, "title": title, "collection": labels.get(e.collection, e.collection),
                "state": state, "date": when, "langs": sorted(tr), "movable": state in ("scheduled", "draft", "review"),
                "url": reverse("cms:entry_edit", args=[e.collection, e.pk, lang if lang in tr else "en"])}
        if when and first <= when <= last:
            items.append(item)
        elif not when and state in ("draft", "review"):
            undated.append(item)
    from .models import PageTranslation
    for t in PageTranslation.objects.filter(status=PageTranslation.SCHEDULED, publish_at__isnull=False).select_related("page", "language"):
        when = _local_date(t.publish_at)
        if first <= when <= last:
            items.append({"kind": "page", "id": t.pk, "title": t.title, "collection": "Page", "state": "scheduled", "date": when,
                          "langs": [t.language.code], "movable": True,
                          "url": reverse("cms:page_edit", args=[t.page_id, t.language.code])})
    return items, undated


@editor_required
def calendar_view(request):
    import calendar as cal
    from datetime import date as Date, timedelta
    from django.utils import timezone
    today = timezone.localdate()
    try:
        y, m = (int(x) for x in request.GET.get("month", "").split("-"))
        month = Date(y, m, 1)
    except (ValueError, TypeError):
        month = today.replace(day=1)
    weeks = cal.Calendar(firstweekday=6).monthdatescalendar(month.year, month.month)  # weeks start on Sunday
    from .ui_i18n import ui_lang
    items, undated = _calendar_items(weeks[0][0], weeks[-1][-1], ui_lang(request))
    by_day = {}
    for i in items:
        by_day.setdefault(i["date"], []).append(i)
    prev_m = (month - timedelta(days=1)).replace(day=1)
    next_m = (month + timedelta(days=32)).replace(day=1)
    upcoming = sorted((i for i in items if i["state"] == "scheduled" and i["date"] >= today), key=lambda i: i["date"])
    return render(request, "cms/calendar.html", {
        "month": month, "prev": prev_m.strftime("%Y-%m"), "next": next_m.strftime("%Y-%m"), "today": today,
        "weeks": [[{"date": d, "in_month": d.month == month.month, "items": by_day.get(d, [])} for d in w] for w in weeks],
        "undated": undated, "upcoming": upcoming[:12],
        "weekdays": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]})


@editor_required
@require_POST
def calendar_move(request):
    """Drag and drop: move a scheduled or draft record to another day (keeps 09:00 local time)."""
    from datetime import date as Date, datetime, time
    from django.http import JsonResponse
    from django.utils import timezone
    from .models import Entry
    try:
        data = json.loads(request.body)
        day = Date.fromisoformat(data["date"])
        pk = int(data["id"])
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"ok": False, "message": _t(request, "Something went wrong.")}, status=400)
    when = timezone.make_aware(datetime.combine(day, time(9, 0)))
    if when <= timezone.now():
        return JsonResponse({"ok": False, "message": _t(request, "Choose a day in the future.")}, status=400)
    if data.get("kind") == "page":
        t = PageTranslation.objects.filter(pk=pk, status=PageTranslation.SCHEDULED).first()
        if not t:
            return JsonResponse({"ok": False, "message": _t(request, "Only scheduled items can be moved.")}, status=400)
        t.publish_at = when
        t.save(update_fields=["publish_at", "updated_at"])
        target = f"page {t.page.key or t.page_id} ({t.language.code})"
    else:
        e = Entry.objects.filter(pk=pk).first()
        if not e or (e.is_published and not (e.publish_at and e.publish_at > timezone.now())):
            return JsonResponse({"ok": False, "message": _t(request, "Only scheduled items can be moved.")}, status=400)
        e.publish_at = when
        if "date" in (e.data or {}):
            e.data["date"] = day.isoformat()
        e.save(update_fields=["publish_at", "data", "updated_at"])
        target = f"{e.collection} {e.key}"
    audit(request, "reschedule", f"{target} → {day.isoformat()}")
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------- security
@admin_required
def security_view(request):
    from . import security_check as sc
    if request.method == "POST":
        sc.public_checks(force=True)
        audit(request, "security_check")
        return redirect("cms:site_security")
    rows, required = sc.accounts()
    public = sc.public_checks()
    logins = sc.sign_ins()
    backup_hours = sc.backup_age_hours()
    items = sc.findings(rows, required, public, logins, backup_hours)
    from shield.report import findings as shield_findings
    extra = shield_findings()  # empty unless the Technting Shield plugin is on
    if extra:
        items = [i for i in items if i["level"] != "ok"] + extra
    score = max(0, 100 - sum({"high": 25, "medium": 10, "low": 3}.get(i["level"], 0) for i in items))
    from . import offsite
    return render(request, "cms/site_security.html", {"rows": rows, "required": required, "public": public, "logins": logins,
                                                 "backup_hours": backup_hours, "items": items, "score": score,
                                                 "offsite": offsite.summary()})


# ---------------------------------------------------------------- social profiles, phone and WhatsApp
SOCIAL_EXTRA_ROWS = 4


@admin_required
def social_settings(request):
    """Profile URLs per platform and language for the footer icons and the Organization sameAs; phone and WhatsApp."""
    from . import social
    from .models import Setting
    from .views import publish_and_report
    values = {s.key: s.value for s in Setting.objects.filter(key__in=["social_profiles", "contact_phone", "whatsapp",
                                                                      "links_scan_url"])}
    if request.method == "POST":
        rows, errors = [], []
        for i in range(int(request.POST.get("rows", 0) or 0)):
            row = social.clean_row({"platform": request.POST.get(f"platform_{i}"),
                                    "url": request.POST.get(f"url_{i}", ""), "label": request.POST.get(f"label_{i}", ""),
                                    "enabled": request.POST.get(f"enabled_{i}") == "on",
                                    "footer": request.POST.get(f"footer_{i}") == "on"})
            if row is None:
                continue  # an empty address removes the row
            if not social.valid_url(row["url"]):
                errors.append(row["url"])
                continue
            rows.append(row)
        phone = request.POST.get("contact_phone", "").strip()[:40]
        wa = request.POST.get("whatsapp", "").strip()[:40]
        scan = request.POST.get("links_scan_url", "").strip()[:300]
        for label, value in (("Phone", phone), ("WhatsApp", wa)):
            if value and not social.PHONE_RE.fullmatch(value):
                errors.append(f"{_t(request, label)}: {value}")
        if scan and not (social.valid_url(scan) or re.fullmatch(r"/[A-Za-z0-9/_.~%-]*", scan)):
            errors.append(scan)
        if errors:
            messages.error(request, _t(request, "Nothing was saved. Check these values (profile addresses must start with https://):")
                           + " " + ", ".join(errors))
            values = {"social_profiles": {"rows": rows}, "contact_phone": phone, "whatsapp": wa, "links_scan_url": scan}
        else:
            Setting.objects.update_or_create(key="social_profiles", defaults={"value": {"rows": rows}})
            Setting.objects.update_or_create(key="contact_phone", defaults={"value": phone})
            Setting.objects.update_or_create(key="whatsapp", defaults={"value": wa})
            Setting.objects.update_or_create(key="links_scan_url", defaults={"value": scan})
            audit(request, "settings_save", f"social profiles ({sum(r['enabled'] for r in rows)} on), phone, WhatsApp")
            publish_and_report(request, "Settings")
            return redirect("cms:social_settings")
    stored = values.get("social_profiles")
    rows = [r for r in (social.clean_row(x) for x in (stored.get("rows", []) if isinstance(stored, dict) else [])) if r]
    blank = {"platform": "x", "url": "", "label": "", "enabled": True, "footer": True}
    rows = rows + [dict(blank) for _ in range(SOCIAL_EXTRA_ROWS)]
    return render(request, "cms/social_settings.html", {
        "rows": rows, "platforms": [(c, label) for c, label, _ in social.PLATFORMS],
        "phone": values.get("contact_phone", ""), "whatsapp": values.get("whatsapp", ""),
        "scan_url": values.get("links_scan_url", ""), "same_as": social.same_as(values),
        "contact": social.contact(values), "site_url": settings.TECHNTING_CMS_SITE_URL})


# ---------------------------------------------------------------- licence (cms/licence.py)
@admin_required
def licence_view(request):
    from . import licence
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save":
            key = licence.clean(request.POST.get("licence_key", ""))
            if not licence.looks_valid(key):
                messages.error(request, _t(request, "Paste the licence key from your download e-mail. It starts with TAI1."))
                return redirect("cms:licence")
            result = licence.ask(key)
            if result["reached"] and result["status"] != licence.GOOD:
                messages.error(request, _t(request, licence.MESSAGES.get(result["status"], licence.MESSAGES["invalid_license"])))
                audit(request, "licence_refused", result["status"])
                return redirect("cms:licence")
            licence.record(key, result)
            audit(request, "licence_saved", result["status"])
            if result["reached"]:
                messages.success(request, _t(request, "The licence key is saved and active."))
            else:
                messages.warning(request, _t(request, "The licence server could not be reached. The key is kept and checked again later."))
        elif action == "check":
            st = licence.check_now()
            audit(request, "licence_check", st["status"])
        return redirect("cms:licence")
    st = licence.state()
    return render(request, "cms/licence.html", {"lic": st, "lic_message": licence.MESSAGES.get(st["status"], ""),
                                                "installation": licence.installation_id() if not licence.demo() else "",
                                                "lic_domain": licence.domain(),
                                                "lic_checked": datetime.datetime.fromtimestamp(st["checked_at"], datetime.timezone.utc) if st.get("checked_at") else None})


# ---------------------------------------------------------------- updates from GitHub
@admin_required
def updates_view(request):
    from . import licence, updater
    if request.method == "POST" and not licence.allows_updates():
        messages.error(request, _t(request, licence.MESSAGES.get(licence.state()["status"], licence.MESSAGES["no_key"])))
        return redirect("cms:updates")
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "check":
            try:
                updater.fetch()
                audit(request, "update_check")
            except Exception as exc:
                label = "Could not reach the update server:" if updater.mode() == "release" else "Could not reach the repository:"
                messages.error(request, _t(request, label) + f" {str(exc)[:200]}")
        elif action == "update" and not updater.state().get("running"):
            audit(request, "update_start", (updater.latest() or {}).get("short", ""))
            updater.start_in_background(request.user.get_username())
            messages.info(request, _t(request, "Update started. This page shows each step; it takes one to three minutes."))
            from django.urls import reverse
            return redirect(reverse("cms:updates") + "?started=1")
        return redirect("cms:updates")
    from .dbdump import describe
    return render(request, "cms/updates.html", {"installed": updater.installed(), "latest": updater.latest(),
                                                "pending": updater.pending(), "state": updater.state(), "release": updater.mode() == "release",
                                                "database": describe()})


@admin_required
def updates_status(request):
    from django.http import JsonResponse
    from . import updater
    return JsonResponse(updater.state(), headers={"Cache-Control": "no-store"})
