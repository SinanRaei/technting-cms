"""Prospect list: researched companies kept apart from the leads until someone decides to contact them.

"Move to leads" first checks what the CRM already has (same domain, name, email or phone, and their deals). If anything
matches, a popup lists it and the user chooses per company: add the research to an existing deal, open a new lead anyway
(reusing the organisation and contact), or skip. Companies marked "Do not contact" never move."""
from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from cms.audit import audit
from cms.ui_i18n import ui_lang
from cms.views import admin_required, crm_required

from . import prospect_io, services
from .forms import ProspectForm
from .models import Deal, Prospect
from .views import _ctx, _t

PER_PAGE = [25, 50, 100, 200]
STATUS_FILTERS = {"todo": [Prospect.OPEN, Prospect.HOLD], **{k: [k] for k, _ in Prospect.STATUS}}
SERVICE_URL = "/services/{code}/"   # joined to the site URL


def service_links(codes, lang):
    return [{"code": c, "name": n, "url": settings.TECHNTING_CMS_SITE_URL + SERVICE_URL.format(code=c.lower())}
            for c, n in services.service_names(codes, lang)]


def _filtered(request):
    f = {k: request.GET.get(k, "").strip() for k in ("q", "country", "sector", "priority", "status", "owner")}
    f["status"] = f["status"] or "todo"
    qs = Prospect.objects.select_related("owner", "deal")
    if f["q"]:
        qs = qs.filter(Q(name__icontains=f["q"]) | Q(name_ar__icontains=f["q"]) | Q(domain__icontains=f["q"])
                       | Q(fit_reason__icontains=f["q"]) | Q(sub_sector__icontains=f["q"]) | Q(city__icontains=f["q"]))
    for key in ("country", "sector", "priority"):
        if f[key]:
            qs = qs.filter(**{key: f[key]})
    if f["status"] in STATUS_FILTERS:
        qs = qs.filter(status__in=STATUS_FILTERS[f["status"]])
    if f["owner"] == "me":
        qs = qs.filter(owner=request.user)
    return qs, f


@crm_required
def prospects(request):
    qs, f = _filtered(request)
    base = Prospect.objects.all()
    counts = {"A": base.filter(priority="A", status__in=STATUS_FILTERS["todo"]).count(),
              "B": base.filter(priority="B", status__in=STATUS_FILTERS["todo"]).count(),
              "C": base.filter(priority="C", status__in=STATUS_FILTERS["todo"]).count(),
              "moved": base.filter(status=Prospect.MOVED).count()}
    per = request.GET.get("per", "")
    if per.isdigit() and int(per) in PER_PAGE:
        request.session["prospects_per"] = int(per)  # remembered for this person until they change it
    per = request.session.get("prospects_per", 50)
    page = Paginator(qs, per).get_page(request.GET.get("page"))
    keep = request.GET.copy()
    keep.pop("page", None)
    return render(request, "crm/prospects.html", _ctx(
        request, rows=page.object_list, page=page, pages=_page_numbers(page), per=per, per_choices=PER_PAGE,
        keep=keep.urlencode(), f=f, total=page.paginator.count, counts=counts,
        countries=base.exclude(country="").values_list("country", flat=True).distinct().order_by("country"),
        sectors=base.exclude(sector="").values("sector").annotate(n=Count("id")).order_by("sector"),
        statuses=Prospect.STATUS, back=request.get_full_path()))


def _page_numbers(page, around=2):
    """[1, None, 4, 5, 6, 7, 8, None, 20]: first, last and the pages near the current one; None is a gap."""
    last, cur = page.paginator.num_pages, page.number
    keep = {1, last} | set(range(max(1, cur - around), min(last, cur + around) + 1))
    out, prev = [], 0
    for n in sorted(keep):
        if n - prev > 1:
            out.append(None)
        out.append(n)
        prev = n
    return out


@crm_required
def prospect_detail(request, prospect_id):
    p = get_object_or_404(Prospect.objects.select_related("owner", "deal", "moved_by"), pk=prospect_id)
    lang = ui_lang(request)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "unv_add":
            if services.merge_unverified(p, [request.POST]):
                p.save(update_fields=["unverified", "updated_at"])
                audit(request, "crm_prospect_unverified", f"{p.name}: added")
                messages.success(request, _t(request, "Added to the unverified info."))
            else:
                messages.error(request, _t(request, "Add an email, a phone, a name with a role, or a link with a description."))
        elif action == "unv_delete":
            before = len(p.unverified or [])
            p.unverified = [e for e in p.unverified or [] if e.get("id") != request.POST.get("item")]
            if len(p.unverified) < before:  # also how we honour a person's request to remove their details
                p.save(update_fields=["unverified", "updated_at"])
                audit(request, "crm_prospect_unverified", f"{p.name}: removed one")
                messages.success(request, _t(request, "Removed."))
        return redirect(f"{reverse('crm:prospect', args=[p.pk])}#unverified")
    m = services.prospect_matches(p) if p.status != Prospect.MOVED else None
    return render(request, "crm/prospect.html", _ctx(request, p=p, svc=service_links(p.services, lang), matches=m,
                                                     statuses=Prospect.STATUS, back=request.get_full_path(),
                                                     unv_kinds=services.UNVERIFIED_KINDS))


@crm_required
def prospect_edit(request, prospect_id=None):
    p = get_object_or_404(Prospect, pk=prospect_id) if prospect_id else None
    form = ProspectForm(request.POST or None, instance=p, initial={"owner": request.user.pk} if not p else None, lang=ui_lang(request))
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        p.domain = services.web_domain(p.website)
        p.save()
        audit(request, "crm_prospect_save", p.name)
        messages.success(request, _t(request, "Saved."))
        return redirect("crm:prospect", prospect_id=p.pk)
    return render(request, "crm/form.html", _ctx(request, form=form, kind="prospect", obj=p,
                                                 title=p.name if p else _t(request, "New company")))


def _next(request, fallback):
    nxt = request.POST.get("next", "")
    return nxt if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}) else fallback


def _ids(request):
    one = request.POST.get("one", "")  # a row's own button wins over the ticked boxes
    if one.isdigit():
        return [int(one)]
    return [int(x) for x in request.POST.getlist("ids") if x.isdigit()][:600]


@crm_required
@require_POST
def prospect_move(request):
    """Move one or more prospects to the leads. Without decisions, companies the CRM already knows are shown in a popup."""
    fetch = request.headers.get("x-requested-with") == "fetch"
    back = _next(request, reverse("crm:prospects"))
    chosen = Prospect.objects.filter(pk__in=_ids(request))
    blocked = [p.name for p in chosen if p.status == Prospect.DO_NOT_CONTACT]
    todo = [p for p in chosen if p.status not in (Prospect.MOVED, Prospect.DO_NOT_CONTACT)]
    if request.POST.get("decided") != "1":
        found = [(p, m) for p in todo for m in [services.prospect_matches(p)] if services.has_matches(m)]
        if found:
            dupe_ids = {p.pk for p, _ in found}
            ctx = {"found": found, "ids": [p.pk for p in todo], "clean_ids": [p.pk for p in todo if p.pk not in dupe_ids],
                   "clean": len(todo) - len(found), "next": back, "blocked": blocked}
            if fetch:
                return JsonResponse({"dupes": True, "html": render_to_string("crm/_prospect_dupes.html", ctx, request=request)})
            return render(request, "crm/prospect_move.html", _ctx(request, **ctx))
        decisions = {p.pk: "new" for p in todo}
    else:
        decisions = {p.pk: request.POST.get(f"dec_{p.pk}", "skip") for p in todo}
    moved, linked, deal = 0, 0, None
    for p in todo:
        d = decisions.get(p.pk, "skip")
        if d == "new":
            deal = services.promote_prospect(p, request.user)
            moved += 1
        elif d.startswith("link:") and d[5:].isdigit():
            target = Deal.objects.filter(pk=int(d[5:])).first()
            if target:
                deal = services.promote_prospect(p, request.user, link_deal=target)
                linked += 1
        else:
            continue
        audit(request, "crm_prospect_move", f"{p.name} -> {deal.title}")
    if blocked:
        messages.error(request, _t(request, "Not moved, marked “Do not contact”:") + " " + ", ".join(blocked))
    if moved or linked:
        msg = []
        if moved:
            msg.append(f"{_t(request, 'New leads')}: {moved}")
        if linked:
            msg.append(f"{_t(request, 'Added to existing deals')}: {linked}")
        messages.success(request, " · ".join(msg))
    elif not blocked:
        messages.info(request, _t(request, "Nothing was moved."))
    url = reverse("crm:deal", args=[deal.pk]) if deal and moved + linked == 1 and len(todo) == 1 else back
    return JsonResponse({"ok": True, "redirect": url}) if fetch else redirect(url)


@crm_required
@require_POST
def prospect_status(request):
    """Bulk or single status change: not contacted yet, on hold, do not contact; administrators can also delete."""
    status = request.POST.get("status", "")
    qs = Prospect.objects.filter(pk__in=_ids(request)).exclude(status=Prospect.MOVED)
    back = _next(request, reverse("crm:prospects"))
    if status == "delete" and request.user.is_superuser:
        n = qs.count()
        qs.delete()
        audit(request, "crm_prospect_delete", f"{n} prospects")
        messages.success(request, f"{_t(request, 'Deleted')}: {n}")
        return redirect("crm:prospects")
    if status in {Prospect.OPEN, Prospect.HOLD, Prospect.DO_NOT_CONTACT}:
        n = qs.update(status=status)
        audit(request, "crm_prospect_status", f"{n} -> {status}")
        messages.success(request, _t(request, "Saved."))
    return redirect(back)


# ---------------------------------------------------------------- export and import (administrators: the files hold contacts)
IMPORT_MAX_BYTES = 10 * 1024 * 1024
IMPORT_MODES = [("update", "Add new companies and update the ones already in the list"),
                ("add", "Only add new companies; leave existing ones as they are"),
                ("unverified", "Only add unverified info to companies already in the list")]


@admin_required
def prospects_export(request):
    """The list as it is filtered on screen (all pages), as Excel or CSV."""
    qs, f = _filtered(request)
    qs = qs.select_related("owner", "deal")
    fmt = "csv" if request.GET.get("format") == "csv" else "xlsx"
    stamp = timezone.localdate().isoformat()
    if fmt == "csv":
        resp = HttpResponse(prospect_io.export_csv(qs), content_type="text/csv; charset=utf-8")
    else:
        resp = HttpResponse(prospect_io.export_xlsx(qs),
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="prospects-{stamp}.{fmt}"'
    audit(request, "crm_prospect_export", f"{qs.count()} companies ({fmt})")
    return resp


@admin_required
def prospects_import(request):
    """Upload -> preview (nothing saved) -> confirm. The parsed rows wait in the cache for 30 minutes."""
    ctx = {"modes": IMPORT_MODES, "mode": request.POST.get("mode", "update"), "max_mb": IMPORT_MAX_BYTES // (1024 * 1024)}
    if request.method == "POST" and request.POST.get("token"):
        key = f"prospect-import:{request.user.pk}:{request.POST['token'][:40]}"
        saved = cache.get(key)
        if not saved:
            messages.error(request, _t(request, "This preview has expired. Upload the file again."))
            return redirect("crm:prospects_import")
        res = prospect_io.apply_rows(saved["rows"], mode=saved["mode"])
        cache.delete(key)
        audit(request, "crm_prospect_import", f"{saved['filename']}: {res.line()}")
        messages.success(request, f"{_t(request, 'Import finished')}: {_t(request, 'added')} {res.added} · "
                                  f"{_t(request, 'updated')} {res.updated} · {_t(request, 'skipped')} {res.skipped}"
                                  + (f" · {_t(request, 'unverified entries added')} {res.entries}" if res.entries else ""))
        return redirect(f"{reverse('crm:prospects')}?status=all")
    if request.method == "POST":
        upload = request.FILES.get("file")
        mode = ctx["mode"] if ctx["mode"] in dict(IMPORT_MODES) else "update"
        if not upload:
            messages.error(request, _t(request, "Choose a file to import."))
        elif upload.size > IMPORT_MAX_BYTES:
            messages.error(request, _t(request, "The file is too large."))
        else:
            try:
                rows = prospect_io.read_rows(upload.read(), upload.name)
            except prospect_io.ProspectFileError as e:
                messages.error(request, str(e))
            else:
                import secrets
                token = secrets.token_urlsafe(16)
                cache.set(f"prospect-import:{request.user.pk}:{token}", {"rows": rows, "mode": mode, "filename": upload.name[:120]},
                          30 * 60)
                ctx.update(preview=prospect_io.apply_rows(rows, mode=mode, dry_run=True), token=token, filename=upload.name,
                           total=len(rows), mode=mode, mode_label=dict(IMPORT_MODES)[mode])
    return render(request, "crm/prospect_import.html", _ctx(request, **ctx))
