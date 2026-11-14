"""Technting CRM dashboard views (editors and administrators; authors have no access)."""
import csv
import json
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cms.areas import AREAS

from cms.audit import audit
from cms.models import FormSubmission
from cms.ui_i18n import tr, ui_lang
from cms.views import admin_required, crm_required

from . import services
from .forms import ContactForm, DealForm, OrganizationForm
from .models import LOST_REASONS, SOURCES, Activity, Contact, Deal, Organization, Stage

U = get_user_model()
LAB_NAMES = AREAS


def _t(request, text):
    return tr(text, ui_lang(request))


def _users():
    return U.objects.filter(is_active=True, is_staff=True).order_by("first_name", "username")


def _ctx(request, **kw):
    kw.setdefault("stages", Stage.CHOICES)
    kw.setdefault("open_stages", Stage.OPEN)
    kw["crm_unanswered"] = Deal.objects.filter(stage=Stage.NEW, first_response_at__isnull=True).count()
    kw["crm_overdue"] = Activity.objects.filter(kind=Activity.TASK, done=False, due_at__lt=timezone.now()).count()
    return kw


# ---------------------------------------------------------------- overview
@crm_required
def home(request):
    n = services.dashboard_numbers()
    maxv = max([v["count"] for v in n["by_stage"].values()] + [1])
    funnel = [{"key": s, "label": Stage.LABEL[s], "count": n["by_stage"][s]["count"], "value": n["by_stage"][s]["value"],
               "pct": round(100 * n["by_stage"][s]["count"] / maxv)} for s in Stage.OPEN]
    src_max = max([r["n"] for r in n["by_source"]] + [1])
    sources = [{"label": dict(SOURCES).get(r["source"], r["source"]), "n": r["n"], "pct": round(100 * r["n"] / src_max)} for r in n["by_source"]]
    lab_max = max([r["n"] for r in n["by_lab"]] + [1])
    labs = [{"label": LAB_NAMES.get(r["lab"], r["lab"].capitalize()), "n": r["n"], "pct": round(100 * r["n"] / lab_max)} for r in n["by_lab"]]
    my_tasks = (Activity.objects.filter(kind=Activity.TASK, done=False).filter(Q(assigned_to=request.user) | Q(assigned_to__isnull=True))
                .select_related("deal", "contact").order_by("due_at")[:8])
    recent = Deal.objects.select_related("organization", "contact", "owner").order_by("-created_at")[:8]
    return render(request, "crm/home.html", _ctx(request, n=n, funnel=funnel, sources=sources, labs=labs, my_tasks=my_tasks,
                                                 recent=recent, currency=services.crm_settings()["currency"]))


# ---------------------------------------------------------------- pipeline (kanban)
@crm_required
def pipeline(request):
    owner = request.GET.get("owner", "")
    qs = Deal.objects.filter(stage__in=Stage.OPEN).select_related("organization", "contact", "owner")
    if owner == "me":
        qs = qs.filter(owner=request.user)
    elif owner.isdigit():
        qs = qs.filter(owner_id=int(owner))
    tasks = Activity.objects.filter(kind=Activity.TASK, done=False).order_by("due_at")
    qs = qs.prefetch_related(Prefetch("activities", queryset=tasks, to_attr="open_tasks"))
    columns = []
    for key in Stage.OPEN:
        deals = [d for d in qs if d.stage == key]
        columns.append({"key": key, "label": Stage.LABEL[key], "deals": deals, "total": sum(d.value for d in deals),
                        "prob": Stage.PROBABILITY[key]})
    closed = Deal.objects.filter(stage__in=[Stage.WON, Stage.LOST], closed_at__gte=timezone.now() - timedelta(days=30))
    return render(request, "crm/pipeline.html", _ctx(request, columns=columns, owner=owner, users=_users(),
                                                     won=closed.filter(stage=Stage.WON).count(), lost=closed.filter(stage=Stage.LOST).count(),
                                                     lost_reasons=LOST_REASONS))


@crm_required
@require_POST
def api_move(request, deal_id):
    deal = get_object_or_404(Deal, pk=deal_id)
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"error": "invalid"}, status=400)
    stage = data.get("stage")
    if stage not in Stage.LABEL:
        return JsonResponse({"error": "stage"}, status=400)
    if stage == Stage.LOST and not data.get("lost_reason"):
        return JsonResponse({"error": "lost_reason"}, status=400)
    old = deal.stage
    services.move_stage(deal, stage, request.user, data.get("lost_reason", ""), data.get("lost_note", ""))
    order = [int(x) for x in data.get("order", []) if str(x).isdigit()][:500]
    for i, pk in enumerate(order):
        Deal.objects.filter(pk=pk, stage=stage).update(position=i)
    if old != stage:
        audit(request, "crm_stage", f"{deal.title}: {old} -> {stage}")
    return JsonResponse({"ok": True, "stage": deal.stage, "probability": deal.probability})


# ---------------------------------------------------------------- deals
def _deal_filters(request):
    qs = Deal.objects.select_related("organization", "contact", "owner")
    f = {k: request.GET.get(k, "").strip() for k in ("q", "stage", "owner", "source", "lab", "status", "form")}
    if f["q"]:
        qs = qs.filter(Q(title__icontains=f["q"]) | Q(organization__name__icontains=f["q"]) | Q(contact__name__icontains=f["q"])
                       | Q(contact__email__icontains=f["q"]))
    if f["stage"] in Stage.LABEL:
        qs = qs.filter(stage=f["stage"])
    if f["status"] == "open":
        qs = qs.filter(stage__in=Stage.OPEN)
    elif f["status"] == "closed":
        qs = qs.filter(stage__in=[Stage.WON, Stage.LOST])
    if f["owner"] == "me":
        qs = qs.filter(owner=request.user)
    elif f["owner"].isdigit():
        qs = qs.filter(owner_id=int(f["owner"]))
    if f["source"]:
        qs = qs.filter(source=f["source"])
    if f["lab"]:
        qs = qs.filter(lab=f["lab"])
    if f["form"] in dict(FormSubmission.SOURCES):  # which website form the enquiry came from (service pages, articles...)
        qs = qs.filter(enquiry__source=f["form"])
    sort = request.GET.get("sort", "-created_at")
    if sort.lstrip("-") in {"created_at", "value", "expected_close", "title", "stage_changed_at"}:
        qs = qs.order_by(sort)
    return qs, f, sort


@crm_required
def deals(request):
    qs, f, sort = _deal_filters(request)
    if request.GET.get("export") == "csv":
        if not request.user.is_superuser:
            raise Http404
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="deals-{timezone.localdate()}.csv"'
        resp.write("﻿")
        w = csv.writer(resp)
        w.writerow(["created", "deal", "stage", "value", "currency", "probability", "expected_close", "organisation", "contact",
                    "email", "owner", "source", "lab", "services", "first_response", "closed", "lost_reason"])
        for d in qs:
            w.writerow([timezone.localtime(d.created_at).strftime("%Y-%m-%d"), d.title, d.stage, d.value, d.currency, d.probability,
                        d.expected_close or "", d.organization.name if d.organization else "", d.contact.name if d.contact else "",
                        d.contact.email if d.contact else "", d.owner.get_username() if d.owner else "", d.source, d.lab,
                        " ".join(d.services or []), d.first_response_at and timezone.localtime(d.first_response_at).strftime("%Y-%m-%d %H:%M") or "",
                        d.closed_at and timezone.localtime(d.closed_at).strftime("%Y-%m-%d") or "", d.lost_reason])
        audit(request, "crm_export", f"{qs.count()} deals")
        return resp
    return render(request, "crm/deals.html", _ctx(request, deals=qs[:500], f=f, sort=sort, users=_users(), sources=SOURCES,
                                                  forms=FormSubmission.SOURCES, total=qs.count()))


@crm_required
def deal_new(request):
    lang = ui_lang(request)
    initial = {"owner": request.user.pk, "currency": services.crm_settings()["currency"], "probability": Stage.PROBABILITY[Stage.NEW]}
    if request.GET.get("contact", "").isdigit():
        c = Contact.objects.filter(pk=request.GET["contact"]).first()
        if c:
            initial.update(contact=c.pk, organization=c.organization_id, title=f"{c.organization.name if c.organization else c.name}: ")
    if request.GET.get("organization", "").isdigit():
        initial["organization"] = int(request.GET["organization"])
    form = DealForm(request.POST or None, initial=initial, lang=lang)
    if request.method == "POST" and form.is_valid():
        deal = form.save(commit=False)
        deal.stage = request.POST.get("stage") if request.POST.get("stage") in Stage.OPEN else Stage.NEW
        deal.save()
        services.log_activity(deal=deal, kind=Activity.SYSTEM, subject="Deal created", user=request.user)
        audit(request, "crm_deal_create", deal.title)
        messages.success(request, _t(request, "Deal created."))
        return redirect("crm:deal", deal_id=deal.pk)
    return render(request, "crm/form.html", _ctx(request, form=form, kind="deal", title=_t(request, "New deal")))


@crm_required
def deal_detail(request, deal_id):
    deal = get_object_or_404(Deal.objects.select_related("organization", "contact", "owner", "enquiry"), pk=deal_id)
    lang = ui_lang(request)
    form = DealForm(instance=deal, lang=lang)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update":
            form = DealForm(request.POST, instance=deal, lang=lang)
            if form.is_valid():
                form.save()
                audit(request, "crm_deal_update", deal.title)
                messages.success(request, _t(request, "Saved."))
                return redirect("crm:deal", deal_id=deal.pk)
        elif action == "stage":
            stage = request.POST.get("stage")
            if stage == Stage.LOST and not request.POST.get("lost_reason"):
                messages.error(request, _t(request, "Choose why the deal was lost."))
            elif services.move_stage(deal, stage, request.user, request.POST.get("lost_reason", ""), request.POST.get("lost_note", "")):
                audit(request, "crm_stage", f"{deal.title}: {stage}")
            return redirect("crm:deal", deal_id=deal.pk)
        elif action == "log":
            kind = request.POST.get("kind")
            if kind in {Activity.NOTE, Activity.CALL, Activity.EMAIL, Activity.MEETING, Activity.TASK}:
                due = _parse_dt(request.POST.get("due_at")) if kind == Activity.TASK else None
                body = request.POST.get("body", "").strip()[:20000]
                subject = request.POST.get("subject", "").strip()[:200]
                if body or subject:
                    assignee = U.objects.filter(pk=request.POST.get("assigned_to") or 0).first() or request.user
                    services.log_activity(deal=deal, kind=kind, subject=subject, body=body, user=request.user, due_at=due,
                                          assigned_to=assignee)
                    messages.success(request, _t(request, "Added to the timeline."))
            return redirect("crm:deal", deal_id=deal.pk)
        elif action == "delete" and request.user.is_superuser:
            title = deal.title
            deal.delete()
            audit(request, "crm_deal_delete", title)
            messages.success(request, _t(request, "Deal deleted."))
            return redirect("crm:pipeline")
    timeline = deal.activities.exclude(kind=Activity.TASK).select_related("created_by")
    tasks = deal.activities.filter(kind=Activity.TASK).select_related("assigned_to").order_by("done", "due_at")
    idx = Stage.OPEN.index(deal.stage) if deal.stage in Stage.OPEN else len(Stage.OPEN)
    from cms.models import Entry
    svc = {e.key: e for e in Entry.objects.filter(collection="service", key__in=deal.services or []).prefetch_related("translations__language")}
    svc_names = []
    for code in deal.services or []:
        e = svc.get(code)
        tr_ = {t.language.code: t.data for t in e.translations.all()} if e else {}
        svc_names.append((code, (tr_.get(lang) or tr_.get("en") or {}).get("name", "")))
    return render(request, "crm/deal.html", _ctx(request, deal=deal, form=form, timeline=timeline, tasks=tasks, stage_index=idx,
                                                 users=_users(), lost_reasons=LOST_REASONS, svc_names=svc_names,
                                                 lab_name=LAB_NAMES.get(deal.lab, deal.lab.capitalize()),
                                                 now=timezone.now(), form_links=_form_links(deal),
                                                 scans=deal.form_submissions.filter(status="complete").select_related("form")[:5]))


def _form_links(deal):
    from formbuilder.views import deal_links
    return deal_links(deal)


def _parse_dt(value):
    try:
        return timezone.make_aware(datetime.fromisoformat(value)) if value else None
    except ValueError:
        return None


@crm_required
@require_POST
def task_toggle(request, activity_id):
    a = get_object_or_404(Activity, pk=activity_id, kind=Activity.TASK)
    a.done = not a.done
    a.done_at = timezone.now() if a.done else None
    a.save(update_fields=["done", "done_at"])
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"ok": True, "done": a.done})
    return redirect(request.POST.get("next") or "crm:tasks")


# ---------------------------------------------------------------- contacts
@crm_required
def contacts(request):
    q = request.GET.get("q", "").strip()
    qs = Contact.objects.select_related("organization", "owner").annotate(n_deals=Count("deals"))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q) | Q(organization__name__icontains=q))
    return render(request, "crm/contacts.html", _ctx(request, contacts=qs[:500], q=q, total=qs.count()))


@crm_required
def contact_edit(request, contact_id=None):
    contact = get_object_or_404(Contact, pk=contact_id) if contact_id else None
    initial = {"owner": request.user.pk}
    if request.GET.get("organization", "").isdigit():
        initial["organization"] = int(request.GET["organization"])
    form = ContactForm(request.POST or None, instance=contact, initial=initial if not contact else None, lang=ui_lang(request))
    if request.method == "POST" and form.is_valid():
        c = form.save()
        audit(request, "crm_contact_save", c.name)
        messages.success(request, _t(request, "Saved."))
        return redirect("crm:contact", contact_id=c.pk)
    return render(request, "crm/form.html", _ctx(request, form=form, kind="contact", obj=contact,
                                                 title=contact.name if contact else _t(request, "New contact")))


@crm_required
def contact_detail(request, contact_id):
    c = get_object_or_404(Contact.objects.select_related("organization", "owner"), pk=contact_id)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "log":
            kind = request.POST.get("kind")
            if kind in {Activity.NOTE, Activity.CALL, Activity.EMAIL, Activity.MEETING} and request.POST.get("body", "").strip():
                services.log_activity(contact=c, organization=c.organization, kind=kind, subject=request.POST.get("subject", ""),
                                      body=request.POST["body"].strip()[:20000], user=request.user)
            return redirect("crm:contact", contact_id=c.pk)
        if action == "erase" and request.user.is_superuser:
            # data subject request: remove the person's details and their timeline; deals stay for business records
            name = c.name
            c.activities.all().delete()
            c.deals.update(contact=None)
            c.delete()
            audit(request, "crm_contact_erase", name)
            messages.success(request, _t(request, "Personal data erased."))
            return redirect("crm:contacts")
    return render(request, "crm/contact.html", _ctx(request, c=c, deals=c.deals.select_related("organization").order_by("-created_at"),
                                                    timeline=c.activities.select_related("created_by", "deal")[:200]))


# ---------------------------------------------------------------- organisations
@crm_required
def organizations(request):
    q = request.GET.get("q", "").strip()
    qs = Organization.objects.annotate(n_contacts=Count("contacts", distinct=True), n_deals=Count("deals", distinct=True))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(domain__icontains=q) | Q(industry__icontains=q) | Q(country__icontains=q))
    return render(request, "crm/organizations.html", _ctx(request, orgs=qs[:500], q=q, total=qs.count()))


@crm_required
def organization_edit(request, org_id=None):
    org = get_object_or_404(Organization, pk=org_id) if org_id else None
    form = OrganizationForm(request.POST or None, instance=org, initial={"owner": request.user.pk} if not org else None,
                            lang=ui_lang(request))
    if request.method == "POST" and form.is_valid():
        o = form.save()
        audit(request, "crm_org_save", o.name)
        messages.success(request, _t(request, "Saved."))
        return redirect("crm:organization", org_id=o.pk)
    return render(request, "crm/form.html", _ctx(request, form=form, kind="organization", obj=org,
                                                 title=org.name if org else _t(request, "New organisation")))


@crm_required
def organization_detail(request, org_id):
    o = get_object_or_404(Organization, pk=org_id)
    deals = o.deals.select_related("contact", "owner").order_by("-created_at")
    won = sum(d.value for d in deals if d.stage == Stage.WON)
    return render(request, "crm/organization.html", _ctx(request, o=o, deals=deals, contacts=o.contacts.all(), won=won,
                                                         timeline=o.activities.select_related("created_by", "deal")[:100]))


# ---------------------------------------------------------------- tasks
@crm_required
def tasks(request):
    who = request.GET.get("who", "me")
    qs = Activity.objects.filter(kind=Activity.TASK).select_related("deal", "contact", "assigned_to")
    if who == "me":
        qs = qs.filter(Q(assigned_to=request.user) | Q(assigned_to__isnull=True))
    show_done = request.GET.get("done") == "1"
    qs = qs if show_done else qs.filter(done=False)
    now = timezone.now()
    end_today = timezone.localtime(now).replace(hour=23, minute=59, second=59)
    groups = [("Overdue", [t for t in qs.order_by("due_at") if not t.done and t.due_at and t.due_at < now]),
              ("Today", [t for t in qs.order_by("due_at") if not t.done and t.due_at and now <= t.due_at <= end_today]),
              ("Upcoming", [t for t in qs.order_by("due_at") if not t.done and (not t.due_at or t.due_at > end_today)])]
    if show_done:
        groups.append(("Done", list(qs.filter(done=True).order_by("-done_at")[:100])))
    return render(request, "crm/tasks.html", _ctx(request, groups=groups, who=who, show_done=show_done))


# ---------------------------------------------------------------- search and settings
@crm_required
def search(request):
    q = request.GET.get("q", "")
    d, c, o = services.search(q)
    return render(request, "crm/search.html", _ctx(request, q=q, deals=d, contacts=c, orgs=o))


@admin_required
def settings_page(request):
    from cms.models import Setting
    from .models import CURRENCIES
    cur = services.crm_settings()
    if request.method == "POST":
        owner = request.POST.get("default_owner", "")
        Setting.objects.update_or_create(key="crm", defaults={"value": {
            "default_owner": int(owner) if owner.isdigit() else None,
            "currency": request.POST.get("currency") if request.POST.get("currency") in CURRENCIES else "USD",
            "response_hours": max(1, min(168, int(request.POST.get("response_hours") or 24)))}})
        audit(request, "crm_settings_save")
        messages.success(request, _t(request, "Saved."))
        return redirect("crm:settings")
    return render(request, "crm/settings.html", _ctx(request, cur=cur, users=_users(), currencies=CURRENCIES))
