"""Public endpoints for forms on example.com (CORS, like the newsletter sign-up) and on personal links (/f/<token>/).

    GET  /api/forms/<slug>/?lang=ar   the form for the browser (no scores, no rules for results)
    POST /api/forms/<slug>/save       save a draft server-side; returns the draft's secret token
    POST /api/forms/<slug>/resume     answers of a draft, by its token
    POST /api/forms/<slug>/submit     check everything again, record it, then return the results
    POST /api/forms/<slug>/event      count a step view (only while the site-stats plugin is on; counts only)

Protection: the Origin must be the site or the dashboard host, request size is capped, saves and submits are limited
per IP address (the address is used only as a short-lived counter key, never stored), a hidden "website" field
catches bots, and the final submit passes Cloudflare Turnstile when Technting Shield has it on. Personal links skip
Turnstile: their unguessable token already proves the person was sent the link.
"""
import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import actions, engine
from .engine import tx
from .models import Form, FormEvent, RecipientLink, Submission

log = logging.getLogger(__name__)
MAX_BODY = 64_000
TEXT = {
    "en": {"invalid": "Please check the highlighted answers.", "required": "Please answer the highlighted questions.",
           "rate": "Please wait a little before trying again.", "check": "Please complete the security check and try again.",
           "origin": "This request could not be verified.", "closed": "This form is not open at the moment.",
           "link": "This link has expired or was withdrawn. Please ask us for a new one.",
           "done": "These answers were already sent. Thank you.", "big": "Your answers are too long. Please shorten them.",
           "saved": "Saved", "thanks": "Thank you. Your answers were received."},
    "ar": {"invalid": "يرجى مراجعة الإجابات المحددة.", "required": "يرجى الإجابة عن الأسئلة المحددة.",
           "rate": "يرجى الانتظار قليلاً قبل المحاولة مرة أخرى.", "check": "يرجى إكمال التحقق الأمني ثم المحاولة مرة أخرى.",
           "origin": "تعذّر التحقق من هذا الطلب.", "closed": "هذا النموذج غير متاح حالياً.",
           "link": "انتهت صلاحية هذا الرابط أو أُلغي. يرجى طلب رابط جديد منا.",
           "done": "أُرسلت هذه الإجابات من قبل. شكراً لكم.", "big": "الإجابات طويلة جداً، يرجى اختصارها.",
           "saved": "تم الحفظ", "thanks": "شكراً لكم. وصلتنا إجاباتكم."},
}


def _lang(value):
    return "ar" if value == "ar" else "en"


def _cors(resp, request):
    origin = request.headers.get("Origin")
    if origin == settings.TECHNTING_CMS_SITE_URL:
        resp["Access-Control-Allow-Origin"] = origin
        resp["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp["Access-Control-Allow-Headers"] = "Content-Type"
        resp["Access-Control-Max-Age"] = "600"
    resp["Vary"] = "Origin"
    resp["Cache-Control"] = "no-store"
    return resp


def _answer(request, data, status=200):
    return _cors(JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False}), request)


def _fail(request, lang, key, status=400, **extra):
    return _answer(request, {"ok": False, "message": TEXT[lang][key], **extra}, status)


def _origin_ok(request):
    return request.headers.get("Origin") in (settings.TECHNTING_CMS_SITE_URL, settings.TECHNTING_CMS_ADMIN_URL.rstrip("/"))


def _ip(request):
    from cms.forms_api import client_ip
    return client_ip(request)


def _limited(request, what, limit, seconds=3600):
    key = f"forms:{what}:{_ip(request)}"
    n = cache.get(key, 0)
    if n >= limit:
        return True
    cache.set(key, n + 1, seconds)
    return False


def _body(request):
    if len(request.body) > MAX_BODY:
        raise ValueError("big")
    data = json.loads(request.body or b"{}")
    if not isinstance(data, dict):
        raise ValueError("invalid")
    return data


def _link(form, token):
    """The personal link sent with a request, when it belongs to this form and can still be used."""
    if not token:
        return None
    link = RecipientLink.objects.filter(token=str(token)[:64], form=form).select_related("contact", "deal").first()
    return link if link and link.is_usable else False


def _staff(request):
    u = getattr(request, "user", None)
    return bool(u and u.is_authenticated and u.is_staff)


def open_form(request, slug, link_token=None):
    """The form, or None when this visitor may not use it. Draft forms open only for signed-in staff (preview)."""
    form = Form.objects.filter(slug=slug).first()
    if form is None:
        return None, None
    link = _link(form, link_token)
    if link is False:
        return form, False
    if link:
        return form, link
    if form.status == Form.LIVE and form.opt("public", True):
        return form, None
    if _staff(request) and form.status != Form.CLOSED:
        return form, None
    return None, None


@csrf_exempt
def definition(request, slug):
    if request.method == "OPTIONS":
        return _cors(HttpResponse(status=204), request)
    lang = _lang(request.GET.get("lang"))
    form, link = open_form(request, slug, request.GET.get("link"))
    if form is None:
        return _fail(request, lang, "closed", 404)
    if link is False:
        return _fail(request, lang, "link", 410)
    spec = engine.Spec(form, steps=link.steps if link else None)
    return _answer(request, {"ok": True, "form": spec.public(lang, link=link)})


def _guard(request, slug, data):
    """Common checks for POSTs. Returns (form, link, lang, error response or None)."""
    lang = _lang(data.get("lang"))
    if not _origin_ok(request):
        return None, None, lang, _fail(request, lang, "origin", 403)
    form, link = open_form(request, slug, data.get("link"))
    if form is None:
        return None, None, lang, _fail(request, lang, "closed", 404)
    if link is False:
        return None, None, lang, _fail(request, lang, "link", 410)
    if link:
        lang = _lang(data.get("lang") or link.language)
    return form, link, lang, None


def _draft(form, link, token):
    if link:
        return link.submissions.order_by("-updated_at").first()
    if token:
        return Submission.objects.filter(form=form, token=str(token)[:64]).first()
    return None


@csrf_exempt
def save(request, slug):
    if request.method == "OPTIONS":
        return _cors(HttpResponse(status=204), request)
    if request.method != "POST":
        raise Http404
    try:
        data = _body(request)
    except (ValueError, json.JSONDecodeError) as exc:
        return _fail(request, "en", "big" if str(exc) == "big" else "invalid", 413 if str(exc) == "big" else 400)
    form, link, lang, err = _guard(request, slug, data)
    if err:
        return err
    if data.get("preview") and _staff(request):
        return _answer(request, {"ok": True, "token": ""})
    if not link and _limited(request, "save", 240):
        return _fail(request, lang, "rate", 429)
    spec = engine.Spec(form, steps=link.steps if link else None)
    answers, _ = spec.clean(data.get("answers"))
    sub = _draft(form, link, data.get("token"))
    if sub and sub.status == Submission.COMPLETE:
        return _fail(request, lang, "done", 409, complete=True)
    if sub is None:
        if not answers:
            return _answer(request, {"ok": True, "token": ""})
        sub = Submission(form=form, form_version=form.version, link=link or None)
    step = str(data.get("step") or "")[:40]
    sub.answers, sub.language, sub.step = answers, lang, step if step in {s.key for s in spec.steps} else sub.step
    sub.save()
    return _answer(request, {"ok": True, "token": "" if link else sub.token, "message": TEXT[lang]["saved"]})


@csrf_exempt
def resume(request, slug):
    if request.method == "OPTIONS":
        return _cors(HttpResponse(status=204), request)
    if request.method != "POST":
        raise Http404
    try:
        data = _body(request)
    except (ValueError, json.JSONDecodeError):
        return _fail(request, "en", "invalid")
    form, link, lang, err = _guard(request, slug, data)
    if err:
        return err
    if not link and _limited(request, "resume", 120):
        return _fail(request, lang, "rate", 429)
    sub = _draft(form, link, data.get("token"))
    if sub is None:
        return _answer(request, {"ok": False, "missing": True})
    if sub.status == Submission.COMPLETE:
        return _answer(request, {"ok": False, "complete": True, "message": TEXT[lang]["done"]})
    return _answer(request, {"ok": True, "answers": sub.answers, "step": sub.step})


def respondent_lang(form, lang):
    langs = form.languages or ["en", "ar"]
    return lang if lang in langs else langs[0]


@csrf_exempt
def submit(request, slug):
    if request.method == "OPTIONS":
        return _cors(HttpResponse(status=204), request)
    if request.method != "POST":
        raise Http404
    try:
        data = _body(request)
    except (ValueError, json.JSONDecodeError) as exc:
        return _fail(request, "en", "big" if str(exc) == "big" else "invalid", 413 if str(exc) == "big" else 400)
    form, link, lang, err = _guard(request, slug, data)
    if err:
        return err
    if data.get("website"):  # honeypot: answer like a success so bots learn nothing
        return _answer(request, {"ok": True, "html": "", "thank_you": TEXT[lang]["thanks"]})
    if not link and _limited(request, "submit", 10):
        return _fail(request, lang, "rate", 429)
    # staff trying a form from the dashboard (or a draft form): results are shown, nothing is stored or sent
    preview = not link and _staff(request) and (form.status != Form.LIVE or bool(data.get("preview")))
    if not link and not preview and form.opt("turnstile", True):
        from shield.turnstile import check_form
        if not check_form(request, str(data.get("cf-turnstile-response") or "")[:2048], _ip(request), f"form:{form.slug}"):
            return _fail(request, lang, "check")
    spec = engine.Spec(form, steps=link.steps if link else None)
    answers, errors = spec.clean(data.get("answers"), final=True)
    if errors:
        code = "required" if all(v == "required" for v in errors.values()) else "invalid"
        return _fail(request, lang, code, errors=errors)
    sub = _draft(form, link, data.get("token"))
    if sub and sub.status == Submission.COMPLETE:
        return _fail(request, lang, "done", 409, complete=True)
    lang = respondent_lang(form, lang)
    calcs, calc_errors = spec.compute(answers, lang)
    if calc_errors:
        log.warning("form %s: calculation errors %s", form.slug, calc_errors)
    from cms import mail
    email = str(actions.mapped(form, answers, "email") or "")
    emailed = bool(form.opt("respondent_email", False) and email and mail.ready())
    results = spec.results(answers, calcs, lang, emailed=emailed) if form.opt("results", "show") == "show" else []
    if preview:
        return _answer(request, {"ok": True, "preview": True, "html": engine.to_html(results),
                                 "thank_you": engine.fill(tx(form.opt("thank_you", {}), lang), spec.env(answers)) or TEXT[lang]["thanks"]})
    consent_key = (form.opt("map") or {}).get("consent", "")
    consent_field = spec.by_key.get(consent_key)
    sub = sub or Submission(form=form, link=link or None)
    sub.form_version, sub.status, sub.language, sub.answers = form.version, Submission.COMPLETE, lang, answers
    sub.calcs, sub.results, sub.tags = calcs, results, spec.tags(answers, calcs)
    sub.name = str(actions.mapped(form, answers, "name") or (link.contact.name if link and link.contact else ""))[:150]
    sub.email = (email or (link.contact.email if link and link.contact else ""))[:254]
    sub.company = str(actions.mapped(form, answers, "company") or "")[:200]
    if consent_field is not None and answers.get(consent_key) is True:
        sub.consent_text = engine.to_text([{"t": "p", "html": engine.fill(tx(consent_field.label, lang), spec.env({}, lang=lang))}])
        sub.consent_at = timezone.now()
    page = str(data.get("page") or "")[:300]
    sub.page = page if page.startswith(("/", settings.TECHNTING_CMS_SITE_URL)) else ""
    sub.completed_at = timezone.now()
    sub.save()
    count_event(form, FormEvent.COMPLETE, lang)
    actions.complete(sub, spec)
    thanks = engine.fill(tx(form.opt("thank_you", {}), lang), spec.env(answers, lang=lang)) or TEXT[lang]["thanks"]
    return _answer(request, {"ok": True, "html": engine.to_html(results), "thank_you": thanks})


def count_event(form, kind, lang, step=0):
    row, _ = FormEvent.objects.get_or_create(form=form, day=timezone.localdate(), lang=lang, kind=kind, step=step)
    FormEvent.objects.filter(pk=row.pk).update(count=F("count") + 1)


@csrf_exempt
def event(request, slug):
    """Step counts for drop-off per page. Always 204, like the stats beacon."""
    if request.method == "OPTIONS":
        return _cors(HttpResponse(status=204), request)
    resp = _cors(HttpResponse(status=204), request)
    from cms import stats
    if request.method != "POST" or not stats.enabled() or not _origin_ok(request) or len(request.body) > 500 or _staff(request):
        return resp
    try:
        data = json.loads(request.body)
        kind, step = str(data.get("kind")), int(data.get("step") or 0)
    except (ValueError, TypeError, AttributeError):
        return resp
    form = Form.objects.filter(slug=slug, status=Form.LIVE).first()
    if form is None or kind not in (FormEvent.VIEW, FormEvent.START, FormEvent.STEP) or not 0 <= step <= 60 or _limited(request, "event", 400):
        return resp
    count_event(form, kind, _lang(data.get("lang")), step if kind == FormEvent.STEP else 0)
    return resp


# ---------------------------------------------------------------- personal links: /f/<token>/
def link_page(request, token):
    """The respondent's page for a personal link, on the dashboard host. No sign-in; the token is the secret."""
    link = RecipientLink.objects.filter(token=token[:64]).select_related("form", "contact", "deal").first()
    if link is None:
        raise Http404
    lang = _lang(request.GET.get("lang") or link.language)
    if not link.is_usable:
        return render(request, "formbuilder/link_page.html", {"lang": lang, "gone": TEXT[lang]["link"], "dir": "rtl" if lang == "ar" else "ltr"},
                      status=410)
    now = timezone.now()
    first = link.first_opened_at is None
    RecipientLink.objects.filter(pk=link.pk).update(last_opened_at=now, **({"first_opened_at": now} if first else {}))
    if first:
        from crm.models import Activity
        Activity.objects.create(kind=Activity.SYSTEM, deal=link.deal, contact=link.contact,
                                organization=link.deal.organization if link.deal_id else None,
                                subject=f"Questionnaire link opened: {link.label or link.form.name('en')}"[:200])
    resp = render(request, "formbuilder/link_page.html", {
        "lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "link": link, "form": link.form,
        "title": link.form.name(lang), "langs": link.form.languages or ["en", "ar"],
        "config": {"api": "/api/forms/", "slug": link.form.slug, "lang": lang, "link": link.token}})
    resp["Referrer-Policy"] = "same-origin"   # the token never leaks to other sites (not no-referrer: POSTs would send Origin: null)
    resp["X-Robots-Tag"] = "noindex, nofollow"
    return resp
