"""Newsletter sign-up with double opt-in (in the spirit of MC4WP / Mailchimp for WordPress).

The public form (newsletter plugin) posts to /api/subscribe on the dashboard host. We store the address as
"waiting for confirmation" and email a confirmation link; only a confirmed address counts and becomes a CRM contact
with marketing consent. Every email we send later must carry the unsubscribe link. Sending the newsletter itself is
done elsewhere (export the confirmed list as CSV).
"""
import csv
import logging
import re
import secrets

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from cms.views import crm_required

from .models import Activity, Contact, Subscriber

log = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}")
TEXT = {
    "en": {"ok": "Almost done: we sent you an email. Open it and confirm to start receiving our insights.",
           "email": "Please enter a valid email address.", "rate": "Please wait a little before trying again.",
           "check": "Please complete the security check and try again.",
           "fail": "We could not sign you up right now. Please try again later.",
           "subject": "Confirm your subscription to Technting insights",
           "body": "Hello,\n\nPlease confirm that you want to receive Technting insights by opening this link:\n{confirm}\n\n"
                   "If you did not ask for this, ignore this email and nothing will happen.\n\nTechnting\n{site}",
           "confirmed_title": "You are subscribed", "confirmed_text": "Thank you. You will receive our new insights by email. You can leave at any time from the link in each email.",
           "unsub_title": "Unsubscribe", "unsub_text": "Stop receiving Technting insights at {email}?", "unsub_button": "Unsubscribe",
           "unsubbed_title": "You are unsubscribed", "unsubbed_text": "We will not send you our insights any more.",
           "back": "Back to example.com"},
    "ar": {"ok": "خطوة أخيرة: أرسلنا إليكم رسالة بالبريد. افتحوها وأكّدوا الاشتراك لتصلكم مقالاتنا.",
           "email": "يرجى إدخال بريد إلكتروني صحيح.", "rate": "يرجى الانتظار قليلاً قبل المحاولة مرة أخرى.",
           "check": "يرجى إكمال التحقق الأمني ثم المحاولة مرة أخرى.",
           "fail": "تعذّر الاشتراك الآن. يرجى المحاولة لاحقاً.",
           "subject": "أكّدوا اشتراككم في مقالات Technting",
           "body": "مرحباً،\n\nيرجى تأكيد رغبتكم في استلام مقالات Technting بفتح هذا الرابط:\n{confirm}\n\n"
                   "إذا لم تطلبوا ذلك، تجاهلوا هذه الرسالة ولن يحدث شيء.\n\nTechnting\n{site}",
           "confirmed_title": "تم الاشتراك", "confirmed_text": "شكراً لكم. ستصلكم مقالاتنا الجديدة بالبريد، ويمكنكم إلغاء الاشتراك في أي وقت من الرابط في كل رسالة.",
           "unsub_title": "إلغاء الاشتراك", "unsub_text": "إيقاف إرسال مقالات Technting إلى {email}؟", "unsub_button": "إلغاء الاشتراك",
           "unsubbed_title": "تم إلغاء الاشتراك", "unsubbed_text": "لن نرسل إليكم مقالاتنا بعد الآن.",
           "back": "العودة إلى example.com"},
}


def _cors(resp):
    resp["Access-Control-Allow-Origin"] = settings.TECHNTING_CMS_SITE_URL
    resp["Vary"] = "Origin"
    resp["Cache-Control"] = "no-store"
    return resp


def links(sub):
    base = settings.TECHNTING_CMS_ADMIN_URL
    return f"{base}/newsletter/confirm/{sub.token}/", f"{base}/newsletter/unsubscribe/{sub.token}/"


@csrf_exempt
@require_http_methods(["POST"])
def api_subscribe(request):
    from cms import plugins
    from cms.forms_api import client_ip
    lang = "ar" if request.POST.get("lang") == "ar" else "en"
    t = TEXT[lang]

    def answer(ok, key, code=200):
        return _cors(JsonResponse({"ok": ok, "message": t[key]}, status=code))

    if request.headers.get("Origin") != settings.TECHNTING_CMS_SITE_URL or "newsletter" not in plugins.enabled_names():
        return answer(False, "fail", 403)
    if request.POST.get("website"):  # honeypot
        return answer(True, "ok")
    email = (request.POST.get("email") or "").strip().lower()[:254]
    if not EMAIL_RE.fullmatch(email):
        return answer(False, "email", 400)
    key = f"subscribe:{client_ip(request)}"
    if cache.get(key, 0) >= 5:
        return answer(False, "rate", 429)
    cache.set(key, cache.get(key, 0) + 1, 3600)
    from shield.turnstile import check_form
    if not check_form(request, request.POST.get("cf-turnstile-response", "")[:2048], client_ip(request), "newsletter"):
        return answer(False, "check", 400)
    sub = Subscriber.objects.filter(email=email).first()
    if sub and sub.status == Subscriber.CONFIRMED:
        return answer(True, "ok")  # say the same thing, so the form does not reveal who is subscribed
    if not sub:
        sub = Subscriber(email=email, token=secrets.token_urlsafe(32))
    sub.language, sub.status, sub.page = lang, Subscriber.PENDING, (request.POST.get("page") or "")[:300]
    sub.save()
    from cms import mail
    if not mail.ready():
        return answer(False, "fail", 503)
    confirm, _ = links(sub)
    try:
        mail.send(t["subject"], t["body"].format(confirm=confirm, site=settings.TECHNTING_CMS_SITE_URL), [email])
    except Exception as exc:
        log.warning("newsletter confirmation email failed: %s", type(exc).__name__)
        return answer(False, "fail", 503)
    return answer(True, "ok")


def _page(request, sub, title, text, form=False):
    lang = sub.language if sub.language in TEXT else "en"
    return render(request, "crm/newsletter_page.html", {"t": TEXT[lang], "lang": lang, "title": title, "text": text,
                                                         "form": form, "site_url": settings.TECHNTING_CMS_SITE_URL})


def confirm(request, token):
    sub = get_object_or_404(Subscriber, token=token)
    t = TEXT.get(sub.language, TEXT["en"])
    if sub.status != Subscriber.CONFIRMED:
        sub.status, sub.confirmed_at, sub.unsubscribed_at = Subscriber.CONFIRMED, timezone.now(), None
        contact = sub.contact or Contact.objects.filter(email__iexact=sub.email).first()
        if not contact:
            contact = Contact.objects.create(name=sub.email, email=sub.email, language=sub.language, source="website",
                                             lawful_basis="consent", marketing_opt_in=True)
        else:
            contact.marketing_opt_in = True
            contact.save(update_fields=["marketing_opt_in", "updated_at"])
        sub.contact = contact
        sub.save()
        Activity.objects.create(kind=Activity.SYSTEM, contact=contact, subject="Subscribed to the newsletter",
                                body=f"Confirmed from the email link. Signed up on {sub.page or 'the website'}.")
    return _page(request, sub, t["confirmed_title"], t["confirmed_text"])


NEWSLETTER_SUBJECTS = {"Subscribed to the newsletter", "Unsubscribed from the newsletter"}


def forget_contact(sub):
    """After unsubscribing we keep only the address (as a do-not-email record), as the privacy notice says.

    A contact that exists only because of the newsletter is deleted. A contact we also know from an enquiry, a deal or
    our own notes stays, without marketing consent.
    """
    c = sub.contact
    sub.contact = None
    if not c:
        return
    only_newsletter = (not c.deals.exists() and c.lawful_basis == "consent" and c.name == c.email
                       and not c.activities.exclude(kind=Activity.SYSTEM, subject__in=NEWSLETTER_SUBJECTS).exists())
    if only_newsletter:
        c.delete()
        return
    c.marketing_opt_in = False
    c.save(update_fields=["marketing_opt_in", "updated_at"])
    Activity.objects.create(kind=Activity.SYSTEM, contact=c, subject="Unsubscribed from the newsletter")


def prune_pending(days=30):
    """Addresses that never confirmed are deleted after 30 days."""
    from datetime import timedelta
    return Subscriber.objects.filter(status=Subscriber.PENDING, created_at__lt=timezone.now() - timedelta(days=days)).delete()[0]


@csrf_exempt  # the token in the address is the secret; mail apps send one-click POSTs without a CSRF cookie
@require_http_methods(["GET", "POST"])
def unsubscribe(request, token):
    """GET shows a button; POST unsubscribes (so email link scanners cannot unsubscribe people by opening the link)."""
    sub = get_object_or_404(Subscriber, token=token)
    t = TEXT.get(sub.language, TEXT["en"])
    if request.method == "POST":
        if sub.status != Subscriber.UNSUBSCRIBED:
            forget_contact(sub)
            sub.status, sub.unsubscribed_at, sub.page = Subscriber.UNSUBSCRIBED, timezone.now(), ""
            sub.save(update_fields=["status", "unsubscribed_at", "page", "contact"])
        return _page(request, sub, t["unsubbed_title"], t["unsubbed_text"])
    return _page(request, sub, t["unsub_title"], t["unsub_text"].format(email=sub.email), form=True)


@crm_required
def subscribers(request):
    status = request.GET.get("status", "confirmed")
    qs = Subscriber.objects.select_related("contact")
    counts = {s: qs.filter(status=s).count() for s, _ in Subscriber.STATUS}
    rows = qs.filter(status=status) if status in counts else qs
    if request.GET.get("export") == "csv":
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="subscribers.csv"'
        resp.write("﻿")
        w = csv.writer(resp)
        w.writerow(["email", "language", "confirmed_at", "unsubscribe_link"])
        for s in qs.filter(status=Subscriber.CONFIRMED):
            w.writerow([s.email, s.language, s.confirmed_at.isoformat() if s.confirmed_at else "", links(s)[1]])
        return resp
    return render(request, "crm/subscribers.html", {"rows": rows[:500], "counts": counts, "status": status})
