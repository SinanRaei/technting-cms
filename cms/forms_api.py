"""Public enquiry endpoint used by the site's enquiry forms (/api/contact on example.com).

Two kinds of form post here: the header dialog ("Start a conversation") and the inline form on every service page,
use case page and article. Every valid enquiry is stored first (dashboard inbox + CRM deal), then a copy is emailed
to the leads mailbox (Settings → "Leads email", default leads@example.com). If the email fails, the enquiry is
kept and the inbox shows "email not sent" with a button to send it again.
"""
import json
import logging
import re

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .areas import AREAS, INTEREST_CHOICES
from .models import Entry, FormSubmission, Setting

log = logging.getLogger(__name__)
DEFAULT_LEADS_EMAIL = settings.TECHNTING_CMS_LEADS_EMAIL
INTERESTS = set(INTEREST_CHOICES)
LAB_INTEREST = AREAS
SOURCES = {"", "dialog", "service", "usecase", "article", "page"}
EMAIL_RE = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+")
PHONE_RE = re.compile(r"[+()0-9 .-]{4,40}")
KEY_RE = re.compile(r"[A-Za-z0-9_-]{0,80}")
PATH_RE = re.compile(r"/[A-Za-z0-9/_.~%-]{0,299}")
MESSAGES = {
    "en": {"invalid": "Please check the information you entered.", "name": "Please enter your full name.",
           "email": "Please enter a valid email address.", "phone": "Please check the phone number.",
           "message": "Please tell us a little more about your enquiry.", "rate": "Please wait before sending another enquiry.",
           "origin": "This request could not be verified.", "big": "Your enquiry is too long. Please shorten it.",
           "organisation": "Please enter your organisation.", "phone_required": "Please enter your phone number.",
           "interest": "Please choose an area of interest.", "check": "Please complete the security check and try again."},
    "ar": {"invalid": "يرجى التحقق من البيانات المدخلة.", "name": "يرجى إدخال الاسم الكامل.",
           "email": "يرجى إدخال بريد إلكتروني صحيح.", "phone": "يرجى التحقق من رقم الهاتف.",
           "message": "يرجى توضيح استفساركم بتفاصيل أكثر.", "rate": "يرجى الانتظار قليلاً قبل إرسال استفسار آخر.",
           "origin": "تعذّر التحقق من هذا الطلب.", "big": "الاستفسار طويل جداً، يرجى اختصاره.",
           "organisation": "يرجى إدخال اسم المؤسسة.", "phone_required": "يرجى إدخال رقم الهاتف.",
           "interest": "يرجى اختيار مجال الاهتمام.", "check": "يرجى إكمال التحقق الأمني ثم المحاولة مرة أخرى."},
}


def smtp_ready():
    from . import mail
    return mail.ready()


def leads_email():
    """Where every enquiry is emailed (Settings → Leads email)."""
    v = Setting.objects.filter(key="leads_email").values_list("value", flat=True).first()
    return v if isinstance(v, str) and EMAIL_RE.fullmatch(v) else DEFAULT_LEADS_EMAIL


def client_ip(request):
    # Technting Shield sets shield_ip after checking that the request really came through Cloudflare
    return getattr(request, "shield_ip", None) or request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR", "")


def clean(value, limit):
    if not isinstance(value, str):
        raise ValueError("invalid")
    value = value.strip()
    if len(value) > limit or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError("invalid")
    return value


def _entry(collection, key):
    if not key:
        return None
    return Entry.objects.filter(collection=collection, key=key, is_published=True).prefetch_related("translations__language").first()


def _text(entry, field, lang):
    """A translated field of a catalogue entry, in the page language, falling back to English."""
    by_lang = {t.language.code: t.data for t in entry.translations.all()}
    for code in (lang, "en"):
        if (by_lang.get(code) or {}).get(field):
            return str(by_lang[code][field])
    return str(entry.data.get(field) or "")


def page_context(source, ref, service, lang):
    """Service code, area and topic for an enquiry, checked against the catalogue: the page only says where the form
    was (source + key) and which service was picked; names and areas come from the database, not from the browser.
    Collections a theme does not have ("lab", "challenge") simply match nothing."""
    lab, topic = "", ""
    if source == "service":
        e = _entry("lab", ref)
        if e:
            lab, topic = e.key, _text(e, "name", lang)
        else:  # a page for one service (starter theme): the page itself names the service
            e = _entry("service", ref)
            if e:
                service, topic = service or e.key, _text(e, "name", lang)
    elif source == "usecase":
        e = _entry("challenge", ref)
        if e:
            topic = _text(e, "title", lang)
            service = service or str(e.data.get("service") or "")
    elif source == "article":
        e = _entry("post", ref)
        if e:
            lab, topic = str(e.data.get("area") or e.data.get("lab") or ""), _text(e, "title", lang)
    elif source == "page" and ref:
        from .models import PageTranslation
        t = (PageTranslation.objects.filter(page__key=ref, language__code=lang).first()
             or PageTranslation.objects.filter(page__key=ref).first())
        topic = t.title if t else ""
    svc = _entry("service", service)
    if svc:
        lab = str(svc.data.get("area") or svc.data.get("lab") or "") or lab
    return (svc.key if svc else ""), lab, topic


@require_http_methods(["GET"])
def status(request):
    # The inbox always accepts enquiries; email is an extra copy.
    return JsonResponse({"available": True}, headers={"Cache-Control": "no-store"})


@csrf_exempt
@require_http_methods(["POST"])
def submit(request):
    referer = request.META.get("HTTP_REFERER") or ""
    lang = "ar" if "/ar/" in referer else "en"
    msg = MESSAGES[lang]

    def fail(key, code=400):
        return JsonResponse({"ok": False, "message": msg[key]}, status=code, headers={"Cache-Control": "no-store"})

    allowed = settings.TECHNTING_CMS_SITE_URL.rstrip("/")
    if request.headers.get("Origin") != allowed or request.headers.get("Sec-Fetch-Site", "same-origin") not in {"same-origin", "none"}:
        return fail("origin", 403)
    if request.content_type != "application/json":
        return fail("invalid", 415)
    if len(request.body) > 12_000:
        return fail("big", 413)
    try:
        data = json.loads(request.body)
        token = clean(data.get("cf-turnstile-response", ""), 2048)
        v = {k: clean(data.get(k, ""), n) for k, n in
             [("name", 100), ("email", 254), ("organisation", 120), ("phone", 40), ("interest", 40), ("message", 4000), ("website", 200),
              ("source", 20), ("ref", 80), ("service", 20), ("page", 300), ("lang", 5)]}
    except (ValueError, json.JSONDecodeError, AttributeError):
        return fail("invalid")
    if v["lang"] in MESSAGES:
        lang = v["lang"]
        msg = MESSAGES[lang]
    if v["website"]:  # honeypot: pretend success so bots learn nothing
        return JsonResponse({"ok": True})
    if len(v["name"]) < 2 or "\n" in v["name"]:
        return fail("name")
    if any("\n" in v[k] or "\t" in v[k] for k in ("email", "organisation", "phone", "page", "service", "ref")):
        return fail("invalid")
    if not EMAIL_RE.fullmatch(v["email"]):
        return fail("email")
    # every field is required (2026-10-19): organisation, phone, and on the header form the area of interest
    if len(v["organisation"]) < 2:
        return fail("organisation")
    if not v["phone"]:
        return fail("phone_required")
    if not PHONE_RE.fullmatch(v["phone"]) or sum(c.isdigit() for c in v["phone"]) < 6:
        return fail("phone")
    if v["service"] == "none":  # "Not sure yet" in the service list
        v["service"] = ""
    if v["source"] in ("", "dialog") and not v["interest"]:
        return fail("interest")
    if (v["interest"] not in INTERESTS or v["source"] not in SOURCES or not KEY_RE.fullmatch(v["ref"])
            or not KEY_RE.fullmatch(v["service"]) or (v["page"] and not PATH_RE.fullmatch(v["page"]))):
        return fail("invalid")
    if len(v["message"]) < 15:
        return fail("message")
    key = f"enquiry:{client_ip(request)}"
    if cache.get(key, 0) >= 5:
        return fail("rate", 429)
    cache.set(key, cache.get(key, 0) + 1, 900)
    from shield.turnstile import check_form
    if not check_form(request, token, client_ip(request), "enquiry"):
        return fail("check")

    service, lab, topic = page_context(v["source"], v["ref"], v["service"], lang)
    interest = v["interest"] or (LAB_INTEREST.get(lab, "") if lab else "")
    page = (allowed + v["page"]) if v["page"] else referer
    sub = FormSubmission.objects.create(
        name=v["name"], email=v["email"], organisation=v["organisation"], phone=v["phone"], interest=interest,
        message=v["message"], language=lang, page=page[:300], source=v["source"] or "dialog", service=service, topic=topic[:200])
    deal = None
    try:
        from crm.services import capture_enquiry
        deal = capture_enquiry(sub, lab=lab)
    except Exception:
        log.exception("CRM capture failed")
    from .plugins import do_action
    do_action("form_submitted", submission=sub)
    send_copy(sub, deal)
    return JsonResponse({"ok": True}, headers={"Cache-Control": "no-store"})


def send_copy(sub, deal=None):
    """Email the enquiry to the leads mailbox. Never raises: the enquiry is already stored, and the outcome is kept on
    it (email_sent / email_error) so the inbox can show "email not sent" with a retry. Returns True when sent."""
    if not smtp_ready():
        error = "Email is not set up (Settings → Email)."
    else:
        try:
            notify(sub, deal if deal is not None else sub.deals.first())
            error = ""
        except Exception as exc:
            log.warning("enquiry email failed: %s", type(exc).__name__)
            error = f"{type(exc).__name__}: {exc}"[:200]
    sub.email_sent, sub.email_error = not error, error
    sub.save(update_fields=["email_sent", "email_error"])
    return not error


def service_label(code):
    e = _entry("service", code)
    return f"{code} {_text(e, 'name', 'en')}".strip() if e else code


SOURCE_LABEL = dict(FormSubmission.SOURCES)


def notify(sub, deal=None):
    to = leads_email()
    about = service_label(sub.service) if sub.service else (sub.interest if sub.interest and sub.interest != "Not sure yet" else "General")
    who = sub.organisation or sub.name
    came = SOURCE_LABEL.get(sub.source, "Website") + (f": {sub.topic}" if sub.topic else "")
    rows = [("Name", sub.name), ("Email", sub.email), ("Organisation", sub.organisation or "Not provided"),
            ("Phone", sub.phone or "Not provided"), ("Service", service_label(sub.service) if sub.service else "Not chosen"),
            ("Area of interest", sub.interest or "Not specified"), ("Came from", came), ("Page", sub.page or "-"),
            ("Language", "Arabic" if sub.language == "ar" else "English")]
    crm_link = f"{settings.TECHNTING_CMS_ADMIN_URL.rstrip('/')}/crm/deals/{deal.pk}/" if deal else ""
    inbox_link = f"{settings.TECHNTING_CMS_ADMIN_URL.rstrip('/')}/inbox/{sub.pk}/"
    text = ("Technting: new website enquiry\n\n" + "\n".join(f"{a}: {b}" for a, b in rows) + "\n\nMessage\n-------\n" + sub.message
            + (f"\n\nOpen the deal in Technting CRM: {crm_link}" if crm_link else "") + f"\nInbox: {inbox_link}"
            + "\n\nReply to this email to answer the sender directly.")
    html = ("<div style='font-family:Arial,sans-serif;max-width:640px'><h2 style='color:#0b1320'>New website enquiry</h2><table>"
            + "".join(f"<tr><th align='left' valign='top' style='padding:4px 12px 4px 0;color:#607185'>{escape(a)}</th><td dir='auto'>{escape(b)}</td></tr>" for a, b in rows)
            + f"</table><p dir='auto' style='white-space:pre-wrap;border-left:3px solid #00a99a;padding:10px 14px;background:#f4f8f9'>{escape(sub.message)}</p>"
            + (f"<p><a href='{escape(crm_link)}' style='display:inline-block;background:#0b1320;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:bold'>Open the deal in Technting CRM</a></p>" if crm_link else "")
            + "<p style='color:#607185;font-size:12px'>Reply to this email to answer the sender directly. Also saved in the Technting CMS inbox and the CRM.</p></div>")
    from . import mail
    mail.send(" ".join(f"New enquiry: {about}, {who}".split())[:200], text, [to], html=html, reply_to=[sub.email])
