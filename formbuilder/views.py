"""Dashboard pages for Technting Forms: build forms (editors), read submissions and send personal links (CRM roles).

Every text box comes in an English / Arabic pair side by side. Rules and calculations are checked when saved and the
problem is shown next to them; the form keeps working (a broken visibility rule shows the question).
"""
import csv
import json
import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from cms.audit import audit
from cms.roles import role_of
from cms.ui_i18n import tr, ui_lang
from cms.views import admin_required, crm_required, editor_required

from . import engine, expr
from .engine import LANGS, tx
from .models import Field, Form, FormEvent, Option, RecipientLink, Step, Submission

BLOCK_TYPES = [("heading", "Heading"), ("text", "Text"), ("lookup", "Text chosen by a value"), ("match", "First rule that matches"),
               ("scores", "Score bars"), ("verify", "List of questions to verify"), ("button", "Button")]
TEXT_STYLES = [("p", "Normal"), ("lead", "Large"), ("callout", "Highlighted"), ("note", "Small, grey"), ("small", "Small")]
OWNER_MODES = [("rotate", "Take turns (round-robin)"), ("default", "CRM default owner"), ("none", "Nobody (assign by hand)")]
CRM_MODES = [("deal", "Contact, organisation and a new deal"), ("contact", "Contact and organisation only"), ("none", "Nothing in the CRM")]
MAP_KEYS = [("name", "Full name"), ("email", "Email"), ("phone", "Phone"), ("company", "Company"), ("job_title", "Job title"),
            ("country", "Country"), ("size", "Company size"), ("industry", "Sector"), ("consent", "Consent tick box")]
NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,39}")
KEY_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")


def _t(request, text):
    return tr(text, ui_lang(request))


def pair(request, name):
    out = {}
    for lang in LANGS:
        v = (request.POST.get(f"{name}_{lang}") or "").replace("\r\n", "\n").strip()
        if v:
            out[lang] = v
    return out


def pairs(request, name):
    """Parallel English / Arabic lists (table rows)."""
    en, ar = request.POST.getlist(f"{name}_en"), request.POST.getlist(f"{name}_ar")
    n = max(len(en), len(ar))
    en, ar = en + [""] * (n - len(en)), ar + [""] * (n - len(ar))
    return [{k: v.replace("\r\n", "\n").strip() for k, v in (("en", e), ("ar", a)) if v.strip()} for e, a in zip(en, ar)]


def parse_values(text):
    """"score=1, extent=2" -> {"score": 1, "extent": 2}"""
    out = {}
    for part in re.split(r"[,;\n]", text or ""):
        if "=" in part:
            k, v = (x.strip() for x in part.split("=", 1))
            if NAME_RE.fullmatch(k):
                try:
                    n = float(v)
                    out[k] = int(n) if n.is_integer() else n
                except ValueError:
                    pass
    return out


def show_values(values):
    return ", ".join(f"{k}={v}" for k, v in (values or {}).items())


def bump(form):
    form.version += 1
    form.save(update_fields=["version", "updated_at"])


def _ctx(request, form, tab, **extra):
    extra.update({"form": form, "tab": tab, "langs": LANGS, "can_edit": role_of(request.user) in ("admin", "editor"),
                  "site_url": settings.TECHNTING_CMS_SITE_URL})
    return extra


def can_build(user):
    return role_of(user) in ("admin", "editor")


# ---------------------------------------------------------------- list, new, duplicate, delete
@crm_required
def forms_list(request):
    forms = Form.objects.annotate(
        done=Count("submissions", filter=Q(submissions__status=Submission.COMPLETE)),
        drafts=Count("submissions", filter=Q(submissions__status=Submission.DRAFT)),
        recent=Count("submissions", filter=Q(submissions__status=Submission.COMPLETE,
                                              submissions__completed_at__gte=timezone.now() - timedelta(days=30))))
    if request.method == "POST":
        if not can_build(request.user):
            return HttpResponseForbidden("Only editors and administrators can build forms.")
        title = (request.POST.get("title") or "").strip()[:150]
        slug = slugify(request.POST.get("slug") or title)[:80]
        if not title or not slug:
            messages.error(request, _t(request, "Give the form a name."))
        elif Form.objects.filter(slug=slug).exists():
            messages.error(request, _t(request, "This address is already used by another form."))
        else:
            f = Form.objects.create(slug=slug, title={"en": title}, languages=["en", "ar"], created_by=request.user,
                                    settings={"public": True, "results": "thank_you", "respondent_email": False,
                                              "crm": {"mode": "contact"}, "owner": {"mode": "default"},
                                              "retention_months": 24, "draft_days": 30, "turnstile": True})
            Step.objects.create(form=f, key="step-1", order=1, title={"en": "Step 1"})
            audit(request, "form_create", slug)
            return redirect("formbuilder:edit", form_id=f.pk)
    return render(request, "formbuilder/list.html", {"forms": forms, "can_edit": can_build(request.user)})


@editor_required
@require_POST
def form_duplicate(request, form_id):
    src = get_object_or_404(Form, pk=form_id)
    with transaction.atomic():
        base = f"{src.slug}-copy"[:76]
        slug, n = base, 2
        while Form.objects.filter(slug=slug).exists():
            slug, n = f"{base}-{n}", n + 1
        copy = Form.objects.create(slug=slug, title={k: f"{v} (copy)" if k == "en" else f"{v} (نسخة)" for k, v in (src.title or {}).items()},
                                   intro=src.intro, status=Form.DRAFT, languages=src.languages, settings=src.settings,
                                   calcs=src.calcs, results=src.results, created_by=request.user)
        for s in src.steps.prefetch_related("fields__options"):
            s2 = Step.objects.create(form=copy, key=s.key, order=s.order, title=s.title, intro=s.intro, visible_if=s.visible_if)
            for f in s.fields.all():
                f2 = Field.objects.create(step=s2, key=f.key, order=f.order, type=f.type, label=f.label, help=f.help, why=f.why,
                                          required=f.required, visible_if=f.visible_if, texts=f.texts, options_extra=f.options_extra)
                Option.objects.bulk_create([Option(field=f2, key=o.key, order=o.order, label=o.label, values=o.values,
                                                   is_unknown=o.is_unknown, visible_if=o.visible_if) for o in f.options.all()])
    audit(request, "form_duplicate", f"{src.slug} -> {slug}")
    messages.success(request, _t(request, "Copy made as a draft."))
    return redirect("formbuilder:edit", form_id=copy.pk)


@admin_required
@require_POST
def form_delete(request, form_id):
    form = get_object_or_404(Form, pk=form_id)
    if request.POST.get("confirm") != form.slug:
        messages.error(request, _t(request, "Type the form's address to confirm."))
        return redirect("formbuilder:edit", form_id=form.pk)
    audit(request, "form_delete", form.slug)
    form.delete()
    messages.success(request, _t(request, "Form deleted with its answers."))
    return redirect("formbuilder:list")


# ---------------------------------------------------------------- settings
@crm_required
def form_edit(request, form_id):
    form = get_object_or_404(Form, pk=form_id)
    if request.method == "POST":
        if not can_build(request.user):
            return HttpResponseForbidden("Only editors and administrators can change forms.")
        s = dict(form.settings or {})
        slug = slugify(request.POST.get("slug") or form.slug)[:80]
        if slug != form.slug and Form.objects.filter(slug=slug).exists():
            messages.error(request, _t(request, "This address is already used by another form."))
            return redirect("formbuilder:edit", form_id=form.pk)
        form.slug, form.title, form.intro = slug, pair(request, "title") or form.title, pair(request, "intro")
        status = request.POST.get("status")
        form.status = status if status in dict(Form.STATUS) else form.status
        form.languages = [l for l in LANGS if request.POST.get(f"lang_{l}")] or ["en"]
        num = lambda k, d, lo, hi: max(lo, min(hi, int(request.POST.get(k) or d))) if (request.POST.get(k) or str(d)).isdigit() else d
        s.update({
            "public": bool(request.POST.get("public")), "results": "show" if request.POST.get("results") == "show" else "thank_you",
            "thank_you": pair(request, "thank_you"), "booking_url": (request.POST.get("booking_url") or "").strip()[:500],
            "notify_email": (request.POST.get("notify_email") or "").strip()[:254],
            "privacy_email": (request.POST.get("privacy_email") or "").strip()[:254],
            "respondent_email": bool(request.POST.get("respondent_email")), "turnstile": bool(request.POST.get("turnstile")),
            "email": {"subject": pair(request, "email_subject"), "intro": pair(request, "email_intro"), "outro": pair(request, "email_outro")},
            "crm": {"mode": request.POST.get("crm_mode") if request.POST.get("crm_mode") in dict(CRM_MODES) else "contact",
                    "service": (request.POST.get("crm_service") or "").strip()[:20], "lab": (request.POST.get("crm_lab") or "").strip()[:40],
                    "task": {"subject": (request.POST.get("task_subject") or "").strip()[:200], "hours": num("task_hours", 24, 1, 720)}},
            "owner": {"mode": request.POST.get("owner_mode") if request.POST.get("owner_mode") in dict(OWNER_MODES) else "default",
                      "users": [int(u) for u in request.POST.getlist("owner_users") if u.isdigit()]},
            "map": {k: request.POST.get(f"map_{k}", "") for k, _ in MAP_KEYS if request.POST.get(f"map_{k}")},
            "retention_months": num("retention_months", 24, 1, 120), "draft_days": num("draft_days", 30, 1, 365),
        })
        tags = []
        for name, cond in zip(request.POST.getlist("tag_name"), request.POST.getlist("tag_if")):
            if name.strip() and cond.strip():
                tags.append({"name": name.strip()[:60], "if": cond.strip()[:1000]})
        s["tags"] = tags
        form.settings = s
        form.version += 1
        form.save()
        for t_ in tags:
            err = expr.check(t_["if"], names=[c.get("name") for c in form.calcs or []])
            if err:
                messages.error(request, f"{_t(request, 'Tag')} {t_['name']}: {err}")
        audit(request, "form_settings", form.slug)
        messages.success(request, _t(request, "Saved."))
        return redirect("formbuilder:edit", form_id=form.pk)
    U = get_user_model()
    users = U.objects.filter(is_active=True, is_staff=True).order_by("username")
    keys = [f.key for s in form.steps.prefetch_related("fields") for f in s.fields.all()]
    return render(request, "formbuilder/edit.html", _ctx(
        request, form, "settings", users=users, keys=keys, map_keys=MAP_KEYS, owner_modes=OWNER_MODES, crm_modes=CRM_MODES,
        tags=(form.opt("tags") or []) + [{"name": "", "if": ""}] * 2, statuses=Form.STATUS))


# ---------------------------------------------------------------- steps and questions
@crm_required
def form_questions(request, form_id):
    form = get_object_or_404(Form, pk=form_id)
    if request.method == "POST":
        if not can_build(request.user):
            return HttpResponseForbidden("Only editors and administrators can change forms.")
        action = request.POST.get("action", "")
        with transaction.atomic():
            if action == "add_step":
                n = form.steps.count() + 1
                key = slugify(request.POST.get("key") or f"step-{n}")[:40] or f"step-{n}"
                while form.steps.filter(key=key).exists():
                    key = f"{key}-{n}"
                Step.objects.create(form=form, key=key, order=n * 10, title=pair(request, "title") or {"en": f"Step {n}"})
            elif action in ("step_up", "step_down"):
                _move(list(form.steps.all()), int(request.POST.get("id") or 0), action.endswith("up"))
            elif action == "delete_step":
                s = get_object_or_404(Step, pk=request.POST.get("id"), form=form)
                if form.steps.count() > 1:
                    s.delete()
            elif action == "save_step":
                s = get_object_or_404(Step, pk=request.POST.get("id"), form=form)
                key = slugify(request.POST.get("key") or s.key)[:40]
                if key != s.key and not form.steps.filter(key=key).exists():
                    s.key = key
                s.title, s.intro = pair(request, "title"), pair(request, "intro")
                s.visible_if = (request.POST.get("visible_if") or "").strip()[:2000]
                s.save()
                err = expr.check(s.visible_if, client=True) if s.visible_if else ""
                if err:
                    messages.error(request, f"{s.key}: {err}")
            elif action == "add_field":
                s = get_object_or_404(Step, pk=request.POST.get("step"), form=form)
                ftype = request.POST.get("type") if request.POST.get("type") in dict(Field.TYPES) else Field.RADIO
                existing = {f.key for st in form.steps.all() for f in st.fields.all()}
                n, key = 1, f"q{len(existing) + 1}"
                while key in existing:
                    n += 1
                    key = f"q{len(existing) + n}"
                f = Field.objects.create(step=s, key=key, type=ftype, order=(s.fields.count() + 1) * 10, label={"en": "New question"})
                bump(form)
                return redirect("formbuilder:field", form_id=form.pk, field_id=f.pk)
            elif action in ("field_up", "field_down"):
                f = get_object_or_404(Field, pk=request.POST.get("id"), step__form=form)
                _move(list(f.step.fields.all()), f.pk, action.endswith("up"))
            elif action == "delete_field":
                get_object_or_404(Field, pk=request.POST.get("id"), step__form=form).delete()
            bump(form)
        return redirect("formbuilder:questions", form_id=form.pk)
    steps = list(form.steps.prefetch_related("fields__options"))
    for s in steps:
        s.rule_error = expr.check(s.visible_if, client=True) if s.visible_if else ""
        for f in s.fields.all():
            f.rule_error = expr.check(f.visible_if, client=True) if f.visible_if else ""
    return render(request, "formbuilder/questions.html", _ctx(request, form, "questions", steps=steps, types=Field.TYPES))


def _move(items, pk, up):
    ids = [i.pk for i in items]
    if pk not in ids:
        return
    i = ids.index(pk)
    j = i - 1 if up else i + 1
    if 0 <= j < len(items):
        items[i], items[j] = items[j], items[i]
    for n, item in enumerate(items):
        if item.order != (n + 1) * 10:
            item.order = (n + 1) * 10
            item.save(update_fields=["order"])


@crm_required
def field_edit(request, form_id, field_id):
    form = get_object_or_404(Form, pk=form_id)
    field = get_object_or_404(Field.objects.select_related("step"), pk=field_id, step__form=form)
    if request.method == "POST":
        if not can_build(request.user):
            return HttpResponseForbidden("Only editors and administrators can change forms.")
        key = (request.POST.get("key") or field.key).strip()
        taken = Field.objects.filter(step__form=form, key=key).exclude(pk=field.pk).exists()
        if not KEY_RE.fullmatch(key) or taken:
            messages.error(request, _t(request, "The question key must be unique and use only letters, numbers, - and _."))
            key = field.key
        field.key = key
        field.type = request.POST.get("type") if request.POST.get("type") in dict(Field.TYPES) else field.type
        field.label, field.help, field.why = pair(request, "label"), pair(request, "help"), pair(request, "why")
        field.required = bool(request.POST.get("required"))
        field.visible_if = (request.POST.get("visible_if") or "").strip()[:2000]
        step_id = request.POST.get("step")
        if step_id and step_id.isdigit() and form.steps.filter(pk=step_id).exists():
            field.step_id = int(step_id)
        extra = {}
        for k in ("min", "max", "step", "max_length"):
            v = (request.POST.get(f"x_{k}") or "").strip()
            if re.fullmatch(r"-?\d+(\.\d+)?", v):
                extra[k] = float(v) if "." in v else int(v)
        for k in ("group", "autocomplete"):
            v = (request.POST.get(f"x_{k}") or "").strip()[:40]
            if v:
                extra[k] = v
        for k in ("placeholder", "min_label", "max_label"):
            p = pair(request, f"x_{k}")
            if p:
                extra[k] = p
        field.options_extra = extra
        texts = []
        for cond, text in zip(request.POST.getlist("t_if"), pairs(request, "t_text")):
            if text:
                texts.append({"if": cond.strip()[:2000], "text": text})
        field.texts = texts
        field.save()
        if field.has_options:
            keep = []
            labels = pairs(request, "o_label")
            rows = zip(request.POST.getlist("o_id"), request.POST.getlist("o_key"), labels, request.POST.getlist("o_values"),
                       request.POST.getlist("o_unknown"), request.POST.getlist("o_if"), request.POST.getlist("o_delete"))
            seen = set()
            for n, (oid, okey, label, values, unknown, cond, delete) in enumerate(rows):
                okey = okey.strip()
                if not okey or delete == "1" or not KEY_RE.fullmatch(okey) or okey in seen:
                    continue
                seen.add(okey)
                o = Option.objects.filter(pk=oid, field=field).first() if oid.isdigit() else None
                o = o or Option(field=field)
                o.key, o.label, o.values, o.is_unknown = okey, label, parse_values(values), unknown == "1"
                o.visible_if, o.order = cond.strip()[:2000], (n + 1) * 10
                o.save()
                keep.append(o.pk)
            if request.POST.get("add_unknown") and not Option.objects.filter(pk__in=keep, is_unknown=True).exists():
                o = Option.objects.create(field=field, key="dk", order=(len(keep) + 1) * 10, is_unknown=True, values={"score": 0},
                                          label={"en": "I don't know / not sure", "ar": "لا أعرف / غير متأكد"})
                keep.append(o.pk)
            field.options.exclude(pk__in=keep).delete()
        bump(form)
        for where, src in [("visible", field.visible_if)] + [(f"text {i + 1}", t_["if"]) for i, t_ in enumerate(field.texts)] + \
                [(f"option {o.key}", o.visible_if) for o in field.options.all()]:
            err = expr.check(src, client=True) if src else ""
            if err:
                messages.error(request, f"{where}: {err}")
        audit(request, "form_field", f"{form.slug}/{field.key}")
        messages.success(request, _t(request, "Saved."))
        return redirect("formbuilder:field", form_id=form.pk, field_id=field.pk)
    options = list(field.options.all())
    for o in options:
        o.values_text = show_values(o.values)
    blank = [{"label": {}, "values_text": "", "key": "", "pk": "", "visible_if": "", "is_unknown": False}] * 3
    keys = [f.key for s in form.steps.prefetch_related("fields") for f in s.fields.all()]
    return render(request, "formbuilder/field.html", _ctx(
        request, form, "questions", field=field, options=options, blank=blank, types=Field.TYPES, steps=form.steps.all(),
        texts=(field.texts or []) + [{"if": "", "text": {}}] * 2, keys=keys, extra=field.options_extra or {}))


# ---------------------------------------------------------------- calculations and a test with answers
@crm_required
def form_calcs(request, form_id):
    form = get_object_or_404(Form, pk=form_id)
    test = None
    if request.method == "POST" and request.POST.get("action") == "test":
        try:
            raw = json.loads(request.POST.get("answers") or "{}")
        except json.JSONDecodeError as exc:
            raw, test = {}, {"error": str(exc)}
        if test is None:
            spec = engine.Spec(form)
            answers, errors = spec.clean(raw, final=True)
            lang = "ar" if request.POST.get("lang") == "ar" else "en"
            calcs, calc_errors = spec.compute(answers, lang)
            test = {"answers": json.dumps(raw, ensure_ascii=False, indent=1), "errors": errors, "calc_errors": calc_errors,
                    "calcs": [(c.get("name"), calcs.get(c.get("name")), c.get("internal")) for c in form.calcs or []],
                    "tags": spec.tags(answers, calcs), "html": engine.to_html(spec.results(answers, calcs, lang)), "lang": lang}
    elif request.method == "POST":
        if not can_build(request.user):
            return HttpResponseForbidden("Only editors and administrators can change forms.")
        calcs, names, problems = [], [], []
        rows = zip(request.POST.getlist("c_name"), request.POST.getlist("c_expr"), request.POST.getlist("c_label"),
                   request.POST.getlist("c_internal"), request.POST.getlist("c_delete"))
        for name, src, label, internal, delete in rows:
            name, src = name.strip(), src.replace("\r\n", "\n").strip()
            if not name or delete == "1":
                continue
            if not NAME_RE.fullmatch(name) or name in names or name == "this":
                problems.append(f"{name}: {_t(request, 'use a unique name made of letters, numbers and _')}")
                continue
            err = expr.check(src, names=names)
            if err:
                problems.append(f"{name}: {err}")
            calcs.append({"name": name, "expr": src[:4000], "label": label.strip()[:120], "internal": internal == "1"})
            names.append(name)
        form.calcs = calcs
        form.version += 1
        form.save()
        for p in problems:
            messages.error(request, p)
        audit(request, "form_calcs", form.slug)
        messages.success(request, _t(request, "Saved."))
        return redirect("formbuilder:calcs", form_id=form.pk)
    rows = list(form.calcs or []) + [{"name": "", "expr": "", "label": "", "internal": False}] * 3
    sample = {}
    for s in form.steps.prefetch_related("fields__options"):
        for f in s.fields.all():
            opts = list(f.options.all())
            if opts:
                sample[f.key] = opts[0].key
    return render(request, "formbuilder/calcs.html", _ctx(request, form, "calcs", rows=rows, test=test,
                                                           sample=json.dumps(sample, ensure_ascii=False)))


# ---------------------------------------------------------------- results
def _block_summary(b, lang):
    t = b.get("type")
    if t in ("heading", "text"):
        return tx(b.get("text"), lang)[:140]
    if t == "lookup":
        return f"{b.get('key', '')} → {len(b.get('texts') or {})}"
    if t == "match":
        return f"{len(b.get('cases') or [])}"
    if t == "scores":
        return ", ".join(tx(i.get("label"), lang) for i in b.get("items") or [])
    if t == "verify":
        return b.get("include") or "unknown(this) or score(this) == 0"
    if t == "button":
        return tx(b.get("label"), lang)
    return ""


@crm_required
def form_results(request, form_id):
    form = get_object_or_404(Form, pk=form_id)
    res = dict(form.results or {})
    blocks = list(res.get("blocks") or [])
    if request.method == "POST":
        if not can_build(request.user):
            return HttpResponseForbidden("Only editors and administrators can change forms.")
        action = request.POST.get("action", "")
        if action == "labels":
            labels = {}
            for key, text in zip(request.POST.getlist("l_key"), pairs(request, "l_text")):
                if key.strip() and text:
                    labels[key.strip()[:60]] = text
            res["labels"] = labels
        elif action == "add":
            t = request.POST.get("type")
            if t in dict(BLOCK_TYPES):
                blocks.append({"type": t})
                res["blocks"] = blocks
                form.results, form.version = res, form.version + 1
                form.save()
                return redirect("formbuilder:block", form_id=form.pk, n=len(blocks) - 1)
        elif action in ("up", "down", "delete"):
            n = int(request.POST.get("n") or -1)
            if 0 <= n < len(blocks):
                if action == "delete":
                    blocks.pop(n)
                else:
                    m = n - 1 if action == "up" else n + 1
                    if 0 <= m < len(blocks):
                        blocks[n], blocks[m] = blocks[m], blocks[n]
            res["blocks"] = blocks
        elif action == "json" and request.user.is_superuser:
            try:
                data = json.loads(request.POST.get("json") or "{}")
                if not isinstance(data, dict) or not isinstance(data.get("blocks", []), list):
                    raise ValueError("expected {\"labels\": {...}, \"blocks\": [...]}")
                res = {"labels": data.get("labels") or {}, "blocks": data.get("blocks") or []}
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("formbuilder:results", form_id=form.pk)
        form.results, form.version = res, form.version + 1
        form.save()
        audit(request, "form_results", form.slug)
        messages.success(request, _t(request, "Saved."))
        return redirect("formbuilder:results", form_id=form.pk)
    lang = ui_lang(request)
    rows = [{"n": i, "type": b.get("type"), "label": dict(BLOCK_TYPES).get(b.get("type"), b.get("type")), "if": b.get("if", ""),
             "summary": _block_summary(b, lang)} for i, b in enumerate(blocks)]
    labels = [{"key": k, "text": v} for k, v in (res.get("labels") or {}).items()] + [{"key": "", "text": {}}] * 3
    return render(request, "formbuilder/results.html", _ctx(request, form, "results", rows=rows, labels=labels, block_types=BLOCK_TYPES,
                                                             as_json=json.dumps(res, ensure_ascii=False, indent=1)))


@crm_required
def block_edit(request, form_id, n):
    form = get_object_or_404(Form, pk=form_id)
    res = dict(form.results or {})
    blocks = list(res.get("blocks") or [])
    if not 0 <= n < len(blocks):
        raise Http404
    b = dict(blocks[n])
    names = [c.get("name") for c in form.calcs or []]
    if request.method == "POST":
        if not can_build(request.user):
            return HttpResponseForbidden("Only editors and administrators can change forms.")
        t = b.get("type")
        b = {"type": t, "if": (request.POST.get("if") or "").strip()[:2000]}
        if t in ("heading", "text"):
            b["text"] = pair(request, "text")
            b["level" if t == "heading" else "style"] = (int(request.POST.get("level") or 2) if t == "heading"
                                                         else request.POST.get("style") if request.POST.get("style") in dict(TEXT_STYLES) else "p")
        elif t == "lookup":
            b.update({"key": (request.POST.get("key") or "").strip()[:2000], "title": pair(request, "title"),
                      "style": request.POST.get("style") if request.POST.get("style") in dict(TEXT_STYLES) else "p",
                      "texts": {k.strip(): v for k, v in zip(request.POST.getlist("lk_key"), pairs(request, "lk_text")) if k.strip() and v}})
        elif t == "match":
            cases = []
            for cond, title, text in zip(request.POST.getlist("m_if"), pairs(request, "m_title"), pairs(request, "m_text")):
                if title or text:
                    cases.append({"if": cond.strip()[:2000], "title": title, "text": text})
            b["cases"] = cases
        elif t == "scores":
            b["items"] = [{"label": label, "score": s.strip(), "band": bd.strip()}
                          for label, s, bd in zip(pairs(request, "s_label"), request.POST.getlist("s_score"), request.POST.getlist("s_band"))
                          if label and s.strip()]
        elif t == "verify":
            b.update({"intro": pair(request, "intro"), "empty": pair(request, "empty"),
                      "include": (request.POST.get("include") or "").strip()[:2000],
                      "fields": [k.strip() for k in re.split(r"[,\s]+", request.POST.get("fields") or "") if k.strip()]})
        elif t == "button":
            b.update({"label": pair(request, "label"), "url": pair(request, "url"), "note": pair(request, "note")})
        blocks[n] = b
        res["blocks"] = blocks
        form.results, form.version = res, form.version + 1
        form.save()
        check_names = names + ["this", "emailed"]
        sources = [b.get("if", ""), b.get("key", ""), b.get("include", "")] + [c.get("if", "") for c in b.get("cases", [])] + \
                  [x for i in b.get("items", []) for x in (i["score"], i["band"])]
        for src in sources:
            err = expr.check(src, names=check_names) if src else ""
            if err:
                messages.error(request, f"{src[:60]}: {err}")
        audit(request, "form_results", form.slug)
        messages.success(request, _t(request, "Saved."))
        return redirect("formbuilder:block", form_id=form.pk, n=n)
    ctx = {"b": b, "n": n, "type_label": dict(BLOCK_TYPES).get(b.get("type")), "styles": TEXT_STYLES, "names": names,
           "lookup_rows": [{"key": k, "text": v} for k, v in (b.get("texts") or {}).items()] + [{"key": "", "text": {}}] * 2,
           "cases": (b.get("cases") or []) + [{"if": "", "title": {}, "text": {}}] * 2,
           "items": (b.get("items") or []) + [{"label": {}, "score": "", "band": ""}] * 2,
           "fields_text": ", ".join(b.get("fields") or [])}
    return render(request, "formbuilder/block.html", _ctx(request, form, "results", **ctx))


# ---------------------------------------------------------------- preview
@crm_required
def form_preview(request, form_id):
    form = get_object_or_404(Form, pk=form_id)
    lang = "ar" if request.GET.get("lang") == "ar" else "en"
    return render(request, "formbuilder/link_page.html", {
        "lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "form": form, "title": form.name(lang), "preview": True,
        "langs": form.languages or ["en", "ar"],
        "config": {"api": "/api/forms/", "slug": form.slug, "lang": lang, "preview": "1"}})


# ---------------------------------------------------------------- submissions
@crm_required
def submissions(request, form_id):
    form = get_object_or_404(Form, pk=form_id)
    status = request.GET.get("status", "complete")
    qs = form.submissions.select_related("deal", "owner", "link").order_by("-completed_at", "-created_at")
    qs = qs.filter(status=status) if status in dict(Submission.STATUS) else qs
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(company__icontains=q))
    lab = form.results.get("labels", {}) if form.results else {}
    shown = [c for c in form.calcs or [] if c.get("label")][:6]
    lang = ui_lang(request)
    rows = []
    for s in qs[:500]:
        vals = []
        for c in shown:
            v = s.calcs.get(c["name"], "")
            vals.append(tx(lab.get(v), lang) if isinstance(v, str) and v in lab else v)
        rows.append((s, vals))
    events = funnel(form)
    return render(request, "formbuilder/submissions.html", _ctx(
        request, form, "submissions", rows=rows, shown=shown, status=status, q=q, events=events,
        counts={k: form.submissions.filter(status=k).count() for k, _ in Submission.STATUS}))


def funnel(form, days=90):
    """Opened, started, each step and completed over the last N days (counts only)."""
    since = timezone.localdate() - timedelta(days=days)
    rows = FormEvent.objects.filter(form=form, day__gte=since).values("kind", "step").annotate(n=Sum("count"))
    by = {(r["kind"], r["step"]): r["n"] for r in rows}
    steps = [(i, s, by.get((FormEvent.STEP, i), 0)) for i, s in enumerate(form.steps.all(), start=1)]
    return {"view": by.get((FormEvent.VIEW, 0), 0), "start": by.get((FormEvent.START, 0), 0), "steps": steps,
            "complete": by.get((FormEvent.COMPLETE, 0), 0), "days": days, "any": bool(by)}


def answer_rows(sub, lang):
    """Every question with the answer given, its option values and whether it was "I don't know"."""
    spec = engine.Spec(sub.form)
    out = []
    for s in spec.steps:
        items = []
        for f in s.fields.all():
            if f.type == Field.INFO:
                continue
            a = sub.answers.get(f.key)
            if a in (None, "", []) and f.key not in sub.answers:
                continue
            text, vals, unknown = a, {}, False
            if f.has_options:
                opts = {o.key: o for o in f.options.all()}
                chosen = [opts[k] for k in (a if isinstance(a, list) else [a]) if k in opts]
                text = "; ".join(tx(o.label, lang) for o in chosen)
                vals = {k: v for o in chosen for k, v in (o.values or {}).items()}
                unknown = any(o.is_unknown for o in chosen)
            elif a is True:
                text = "✓"
            items.append({"key": f.key, "label": engine.to_text([{"t": "p", "html": engine.fill(tx(f.label, lang), spec.env({}, lang=lang))}]),
                          "answer": text, "values": show_values(vals), "unknown": unknown})
        if items:
            out.append((tx(s.title, lang) or s.key, items))
    return out


@crm_required
def submission_detail(request, sub_id):
    sub = get_object_or_404(Submission.objects.select_related("form", "deal", "contact", "owner", "link"), pk=sub_id)
    form = sub.form
    if request.method == "POST":
        action = request.POST.get("action")
        spec = engine.Spec(form, steps=sub.link.steps if sub.link else None)
        from . import actions
        if action == "resend_team":
            ok = actions.notify_team(sub, spec)
            (messages.success if ok else messages.error)(request, _t(request, "Email sent.") if ok else sub.notify_error)
        elif action == "resend_results":
            ok = actions.email_respondent(sub, spec)
            (messages.success if ok else messages.error)(request, _t(request, "Email sent.") if ok else (sub.results_error or _t(request, "This form does not email results.")))
        elif action == "note":
            sub.note = (request.POST.get("note") or "")[:4000]
            sub.save(update_fields=["note"])
            messages.success(request, _t(request, "Saved."))
        elif action == "delete" and request.user.is_superuser:
            audit(request, "form_submission_delete", f"{form.slug} #{sub.pk}")
            sub.delete()
            messages.success(request, _t(request, "Answers deleted."))
            return redirect("formbuilder:submissions", form_id=form.pk)
        return redirect("formbuilder:submission", sub_id=sub.pk)
    lang = ui_lang(request)
    labels = (form.results or {}).get("labels", {})

    def show(v):
        return tx(labels.get(v), lang) if isinstance(v, str) and v in labels else v

    calcs = [{"name": c.get("name"), "label": c.get("label") or c.get("name"), "value": show(sub.calcs.get(c.get("name"))),
              "internal": c.get("internal")} for c in form.calcs or [] if c.get("name") in sub.calcs]
    return render(request, "formbuilder/submission.html", _ctx(
        request, form, "submissions", sub=sub, answers=answer_rows(sub, lang), calcs=calcs,
        internal=[c for c in calcs if c["internal"]], public=[c for c in calcs if not c["internal"] and c["label"] != c["name"]],
        results_html=engine.to_html(sub.results)))


@admin_required
def submissions_export(request, form_id):
    form = get_object_or_404(Form, pk=form_id)
    spec = engine.Spec(form)
    keys = [f.key for f in spec.fields if f.type != Field.INFO]
    calc_names = [c.get("name") for c in form.calcs or []]
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{form.slug}-answers.csv"'
    resp.write("﻿")
    w = csv.writer(resp)
    scored = [k for k in keys if spec.by_key[k].has_options]
    w.writerow(["id", "status", "completed", "language", "name", "email", "company", "tags", "owner", "deal", "link"]
               + keys + [f"{k}_values" for k in scored] + calc_names)
    for s in form.submissions.select_related("owner", "link").order_by("created_at"):
        vals = []
        for k in scored:
            f = spec.by_key[k]
            opts = {o.key: o for o in f.options.all()}
            a = s.answers.get(k)
            chosen = [opts[x] for x in (a if isinstance(a, list) else [a]) if x in opts]
            vals.append(show_values({kk: vv for o in chosen for kk, vv in (o.values or {}).items()}) + (" (unknown)" if any(o.is_unknown for o in chosen) else ""))
        row = [s.pk, s.status, timezone.localtime(s.completed_at).strftime("%Y-%m-%d %H:%M") if s.completed_at else "", s.language,
               s.name, s.email, s.company, " ".join(s.tags or []), s.owner.get_username() if s.owner else "",
               f"{settings.TECHNTING_CMS_ADMIN_URL.rstrip('/')}/crm/deals/{s.deal_id}/" if s.deal_id else "", s.link.label if s.link else ""]
        row += [";".join(s.answers.get(k)) if isinstance(s.answers.get(k), list) else s.answers.get(k, "") for k in keys]
        row += vals + [s.calcs.get(n, "") for n in calc_names]
        w.writerow([_csv_safe(x) for x in row])
    audit(request, "form_export", form.slug)
    return resp


def _csv_safe(v):
    """Stop spreadsheet formulas in answers (=, +, -, @ at the start) from running when the file is opened."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") and not re.fullmatch(r"-?\d+(\.\d+)?", s) else s


# ---------------------------------------------------------------- personal links
def link_progress(link, sub=None):
    """(answered, total) required questions for the person's steps, using their saved answers."""
    sub = sub if sub is not None else link.submissions.order_by("-updated_at").first()
    spec = engine.Spec(link.form, steps=link.steps or None)
    answers = sub.answers if sub else {}
    shown = [f for fields in spec.visible(answers).values() for f in fields if f.required and f.type not in (Field.INFO, Field.HIDDEN)]
    done = sum(1 for f in shown if answers.get(f.key) not in (None, "", [], False))
    return done, len(shown)


def annotate_links(links):
    for link in links:
        link.sub = link.submissions.order_by("-updated_at").first()
        link.done, link.total = link_progress(link, link.sub)
        link.pct = round(100 * link.done / link.total) if link.total else 0
        link.st = link.state
    return links


@crm_required
def form_links(request, form_id):
    form = get_object_or_404(Form, pk=form_id)
    from crm.models import Contact, Deal, Stage
    if request.method == "POST":
        contact = Contact.objects.filter(pk=request.POST.get("contact") or 0).first()
        deal = Deal.objects.filter(pk=request.POST.get("deal") or 0).first()
        steps = [k for k in request.POST.getlist("steps") if form.steps.filter(key=k).exists()]
        days = int(request.POST.get("days") or 30) if (request.POST.get("days") or "30").isdigit() else 30
        lang = "ar" if request.POST.get("language") == "ar" else "en"
        if contact is None and deal is not None:
            contact = deal.contact
        link = RecipientLink.objects.create(form=form, label=(request.POST.get("label") or "").strip()[:150], steps=steps, language=lang,
                                            contact=contact, deal=deal, created_by=request.user,
                                            expires_at=timezone.now() + timedelta(days=max(1, min(days, 365))))
        from crm.models import Activity
        Activity.objects.create(kind=Activity.SYSTEM, deal=deal, contact=contact, organization=deal.organization if deal else None,
                                created_by=request.user, subject=f"Questionnaire link created: {link.label or form.name('en')}"[:200],
                                body=f"Form: {form.name('en')}\nParts: {', '.join(steps) or 'all'}\nExpires: {timezone.localtime(link.expires_at):%Y-%m-%d}")
        audit(request, "form_link_create", f"{form.slug}: {link.label}")
        messages.success(request, _t(request, "Link created. Copy it or send it by email."))
        return redirect("formbuilder:link", link_id=link.pk)
    deal_id = request.GET.get("deal")
    links = annotate_links(list(form.links.select_related("contact", "deal")[:300]))
    return render(request, "formbuilder/links.html", _ctx(
        request, form, "links", links=links, steps=form.steps.all(),
        contacts=Contact.objects.order_by("-created_at")[:500], deals=Deal.objects.filter(stage__in=Stage.OPEN).order_by("-created_at")[:300],
        deal_id=int(deal_id) if deal_id and deal_id.isdigit() else None))


@crm_required
def link_detail(request, link_id):
    link = get_object_or_404(RecipientLink.objects.select_related("form", "contact", "deal"), pk=link_id)
    form = link.form
    from crm.models import Activity
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "revoke":
            link.revoked_at = timezone.now()
            link.save(update_fields=["revoked_at"])
            Activity.objects.create(kind=Activity.SYSTEM, deal=link.deal, contact=link.contact, created_by=request.user,
                                    subject=f"Questionnaire link withdrawn: {link.label or form.name('en')}"[:200])
            audit(request, "form_link_revoke", link.label)
            messages.success(request, _t(request, "Link withdrawn. It no longer opens."))
        elif action == "extend":
            base = max(link.expires_at or timezone.now(), timezone.now())
            link.expires_at, link.revoked_at = base + timedelta(days=30), None
            link.save(update_fields=["expires_at", "revoked_at"])
            messages.success(request, _t(request, "Link extended by 30 days."))
        elif action == "send":
            to = (request.POST.get("to") or "").strip()
            if not engine.EMAIL_RE.fullmatch(to):
                messages.error(request, _t(request, "Enter a valid email address."))
            elif not link.is_usable:
                messages.error(request, _t(request, "This link cannot be used any more."))
            else:
                ok, err = send_link(link, to, (request.POST.get("message") or "").strip()[:2000])
                if ok:
                    link.sent_at, link.sent_to = timezone.now(), to
                    link.save(update_fields=["sent_at", "sent_to"])
                    Activity.objects.create(kind=Activity.EMAIL, deal=link.deal, contact=link.contact, created_by=request.user,
                                            subject=f"Questionnaire link sent to {to}"[:200], body=link.label)
                    audit(request, "form_link_send", f"{link.label} -> {to}")
                    messages.success(request, _t(request, "Email sent."))
                else:
                    messages.error(request, err)
        return redirect("formbuilder:link", link_id=link.pk)
    annotate_links([link])
    lang = link.language
    return render(request, "formbuilder/link.html", _ctx(
        request, form, "links", link=link, sub=link.sub, answers=answer_rows(link.sub, ui_lang(request)) if link.sub else [],
        email_preview=link_email(link, "")[1], lang=lang,
        default_to=link.contact.email if link.contact else ""))


def link_email(link, message):
    lang = link.language
    name = link.contact.name if link.contact else ""
    title = link.form.name(lang)
    exp = timezone.localtime(link.expires_at).strftime("%Y-%m-%d") if link.expires_at else ""
    if lang == "ar":
        subject = f"{title}: رابطكم الخاص"
        text = (f"مرحباً {name}،\n\n" if name else "مرحباً،\n\n") + (message + "\n\n" if message else "") + \
               f"هذا رابطكم الخاص لتعبئة «{title}»{(' (' + link.label + ')') if link.label else ''}:\n{link.url()}\n\n" + \
               "يمكنكم الحفظ والعودة لاحقاً من الرابط نفسه. الرابط خاص بكم، فلا تشاركوه." + \
               (f" ينتهي في {exp}." if exp else "") + "\n\nمع التحية،\nفريق Technting"
    else:
        subject = f"{title}: your personal link"
        text = (f"Hello {name},\n\n" if name else "Hello,\n\n") + (message + "\n\n" if message else "") + \
               f"Here is your personal link to complete {title}{(' (' + link.label + ')') if link.label else ''}:\n{link.url()}\n\n" + \
               "Your answers are saved as you go, so you can come back with the same link. The link is for you only; please do not share it." + \
               (f" It expires on {exp}." if exp else "") + "\n\nKind regards,\nThe Technting team"
    return subject, text


def send_link(link, to, message):
    from cms import mail
    if not mail.ready():
        return False, "Email is not set up (Settings → Email)."
    subject, text = link_email(link, message)
    try:
        mail.send(subject, text, [to])
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:200]
    return True, ""


def deal_links(deal):
    """Questionnaire links on a deal, with progress (crm deal page)."""
    return annotate_links(list(RecipientLink.objects.filter(deal=deal).select_related("form", "contact")))
