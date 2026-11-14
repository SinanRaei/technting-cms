"""What happens when a submission is complete: CRM records, the owner, the call task, and the two emails.

Order matters (spec §8): the submission is stored first, so results exist only once it is recorded; CRM and emails
come after and never undo it. Each step that fails is logged on the submission and the rest still runs.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

from . import engine
from .engine import tx

log = logging.getLogger(__name__)
DEFAULT_MAP = {"name": "name", "email": "email", "phone": "phone", "company": "company", "job_title": "job_title",
               "country": "country", "size": "size", "industry": "industry", "consent": "consent"}


def mapped(form, answers, what, spec=None, lang="en"):
    """The answer behind a CRM field (settings "map": {"email": "P7", ...}); option keys become their English labels."""
    key = (form.opt("map") or {}).get(what) or ""
    v = answers.get(key) if key else None
    if v in (None, "") or spec is None:
        return v if v is not None else ""
    f = spec.by_key.get(key) or next((fl for s in spec.all_steps for fl in s.fields.all() if fl.key == key), None)
    if f is not None and f.has_options:
        labels = {o.key: tx(o.label, lang) for o in f.options.all()}
        return ", ".join(labels.get(x, x) for x in v) if isinstance(v, list) else labels.get(v, v)
    return v


# ---------------------------------------------------------------- owner
def sales_users():
    U = get_user_model()
    return list(U.objects.filter(is_active=True, is_staff=True, groups__name="sales").order_by("pk"))


def pick_owner(form):
    """Owner of a new lead (spec §11 #5: rotating, whoever is free). owner.mode: "rotate" (round-robin over
    owner.users, or every active sales user when that list is empty), "default" (CRM default owner) or "none"."""
    from cms.models import Setting
    from crm.services import default_owner
    o = form.opt("owner") or {}
    mode = o.get("mode", "rotate")
    if mode == "none":
        return None
    if mode == "rotate":
        U = get_user_model()
        ids = [int(i) for i in o.get("users") or [] if str(i).isdigit()]
        pool = list(U.objects.filter(pk__in=ids, is_active=True).order_by("pk")) if ids else sales_users()
        if pool:
            with transaction.atomic():
                s, _ = Setting.objects.select_for_update().get_or_create(key="forms_rotation", defaults={"value": {}})
                last = (s.value or {}).get(str(form.pk))
                ids_ = [u.pk for u in pool]
                nxt = pool[(ids_.index(last) + 1) % len(pool)] if last in ids_ else pool[0]
                s.value = {**(s.value or {}), str(form.pk): nxt.pk}
                s.save(update_fields=["value"])
            return nxt
    return default_owner()


# ---------------------------------------------------------------- CRM
def summary_lines(sub, spec):
    """Answers and scores for the CRM timeline (internal: includes the internal pre-score)."""
    lines = []
    for c in sub.form.calcs or []:
        if c.get("label") and c.get("name") in sub.calcs:
            v = sub.calcs[c["name"]]
            lines.append(f"{c['label']}: {spec.env({}).call('label', [v]) if isinstance(v, str) else v}"
                         + ("  (internal)" if c.get("internal") else ""))
    if sub.tags:
        lines.append("Tags: " + ", ".join(sub.tags))
    return lines


@transaction.atomic
def to_crm(sub, spec):
    """Match or create the organisation and contact, then add the scan to an existing deal (personal links) or open a
    new deal (settings crm.mode "deal"), with the call task for the owner. Returns the deal or None."""
    from crm.models import Activity, Contact, Deal, Organization, Stage
    from crm.services import crm_settings, email_domain
    form = sub.form
    crm = form.opt("crm") or {}
    mode = crm.get("mode", "deal")
    if mode == "none" and not sub.link_id:
        return None
    a, lang = sub.answers, "en"
    email = (mapped(form, a, "email") or (sub.link.contact.email if sub.link and sub.link.contact else "")).strip()
    company = str(mapped(form, a, "company") or "").strip()
    link = sub.link
    contact = link.contact if link and link.contact_id else None
    org = (link.deal.organization if link and link.deal_id and link.deal.organization_id else None) or (contact.organization if contact else None)
    owner = (link.deal.owner if link and link.deal_id else None) or pick_owner(form)
    domain = email_domain(email)
    if org is None and company:
        org = Organization.objects.filter(name__iexact=company).first()
    if org is None and domain:
        org = Organization.objects.filter(domain=domain).first()
    if org is None and (company or domain):
        org = Organization.objects.create(name=(company or domain)[:200], domain=domain, website=f"https://{domain}" if domain else "",
                                          owner=owner)
    if org is not None:
        changed = []
        for f_, what in (("country", "country"), ("size", "size"), ("industry", "industry")):
            v = str(mapped(form, a, what, spec, lang) or "")[: 40 if f_ == "size" else 80 if f_ == "country" else 120]
            if v and not getattr(org, f_):
                setattr(org, f_, v)
                changed.append(f_)
        if domain and not org.domain:
            org.domain, changed = domain, changed + ["domain"]
        if changed:
            org.save(update_fields=changed)
    if contact is None and email:
        contact = Contact.objects.filter(email__iexact=email).first()
    name = str(mapped(form, a, "name") or "").strip() or email
    if contact is None and (email or name):
        contact = Contact.objects.create(name=name[:150], email=email[:254], phone=str(mapped(form, a, "phone") or "")[:40],
                                         job_title=str(mapped(form, a, "job_title") or "")[:150], organization=org,
                                         language=sub.language, source="website",
                                         lawful_basis="consent" if a.get((form.opt("map") or {}).get("consent", "")) else "enquiry",
                                         owner=owner)
    elif contact is not None:
        changed = []
        for f_, what in (("phone", "phone"), ("job_title", "job_title")):
            v = str(mapped(form, a, what) or "")
            if v and not getattr(contact, f_):
                setattr(contact, f_, v[: 40 if f_ == "phone" else 150])
                changed.append(f_)
        if org and not contact.organization_id:
            contact.organization, changed = org, changed + ["organization"]
        if changed:
            contact.save(update_fields=changed)
    deal = link.deal if link and link.deal_id else None
    title = tx(form.title, "en")
    if deal is None and mode == "deal":
        service = crm.get("service", "")
        deal = Deal.objects.create(title=f"{org.name if org else name}: {service + ' ' if service else ''}{title}"[:200],
                                   organization=org, contact=contact, stage=Stage.NEW, probability=Stage.PROBABILITY[Stage.NEW],
                                   currency=crm_settings()["currency"], owner=owner, source="website", lab=crm.get("lab", ""),
                                   services=[service] if service else [], position=-1)
    admin = settings.TECHNTING_CMS_ADMIN_URL.rstrip("/")
    body = "\n".join(summary_lines(sub, spec) + [f"Answers and results: {admin}/forms/submissions/{sub.pk}/"])
    Activity.objects.create(kind=Activity.ENQUIRY, deal=deal, contact=contact, organization=org,
                            subject=f"{title} completed{' · ' + link.label if link and link.label else ''}"[:200], body=body)
    task = crm.get("task") or {}
    if deal is not None and task.get("subject") and not (link and link.deal_id):
        Activity.objects.create(kind=Activity.TASK, deal=deal, contact=contact, organization=org, assigned_to=owner,
                                subject=str(task["subject"]).replace("{name}", contact.name if contact else name)[:200],
                                due_at=timezone.now() + timedelta(hours=int(task.get("hours") or 24)))
    sub.contact, sub.deal, sub.owner = contact, deal, owner
    sub.save(update_fields=["contact", "deal", "owner"])
    return deal


# ---------------------------------------------------------------- emails
def notify_email(form):
    from cms.forms_api import EMAIL_RE, leads_email
    v = (form.opt("notify_email") or "").strip()
    return v if v and EMAIL_RE.fullmatch(v) else leads_email()


def notify_team(sub, spec):
    """Short email to the team inbox (settings notify_email, default the leads email). No internal pre-score:
    it is shown only in the dashboard."""
    from cms import mail
    if not mail.ready():
        sub.notify_error = "Email is not set up (Settings → Email)."
        sub.save(update_fields=["notify_error"])
        return False
    form = sub.form
    admin = settings.TECHNTING_CMS_ADMIN_URL.rstrip("/")
    internal = {c.get("name") for c in form.calcs or [] if c.get("internal")}
    rows = [("Form", tx(form.title, "en")), ("Name", sub.name), ("Email", sub.email), ("Company", sub.company),
            ("Language", "Arabic" if sub.language == "ar" else "English")]
    if sub.link_id:
        rows.append(("Personal link", sub.link.label or f"#{sub.link_id}"))
    for c in form.calcs or []:
        if c.get("label") and c.get("name") in sub.calcs and c.get("name") not in internal:
            v = sub.calcs[c["name"]]
            rows.append((c["label"], spec.env({}).call("label", [v]) if isinstance(v, str) else str(v)))
    if sub.tags:
        rows.append(("Tags", ", ".join(sub.tags)))
    if sub.owner:
        rows.append(("Owner", sub.owner.get_username()))
    link = f"{admin}/forms/submissions/{sub.pk}/"
    deal = f"{admin}/crm/deals/{sub.deal_id}/" if sub.deal_id else ""
    text = "\n".join(f"{a}: {b}" for a, b in rows) + f"\n\nOpen in Technting CMS: {link}" + (f"\nDeal: {deal}" if deal else "")
    html = ("<div style='font-family:Arial,sans-serif;max-width:640px'><h2 style='color:#0b1320'>"
            + escape(tx(form.title, "en")) + " completed</h2><table>"
            + "".join(f"<tr><th align='left' valign='top' style='padding:4px 12px 4px 0;color:#607185'>{escape(a)}</th>"
                      f"<td dir='auto'>{escape(b)}</td></tr>" for a, b in rows)
            + f"</table><p><a href='{escape(link)}' style='display:inline-block;background:#0b1320;color:#fff;padding:10px 16px;"
              f"border-radius:8px;text-decoration:none;font-weight:bold'>Open the answers</a></p></div>")
    subject = " ".join(f"{tx(form.title, 'en')}: {sub.company or sub.name or sub.email}".split())[:200]
    try:
        mail.send(subject, text, [notify_email(form)], html=html, reply_to=[sub.email] if sub.email else None)
        sub.notify_error = ""
    except Exception as exc:
        log.warning("form notification failed: %s", type(exc).__name__)
        sub.notify_error = f"{type(exc).__name__}: {exc}"[:200]
    sub.save(update_fields=["notify_error"])
    return not sub.notify_error


def email_respondent(sub, spec):
    """The respondent's results by email: the same blocks as the results page (settings respondent_email)."""
    from cms import mail
    form = sub.form
    if not form.opt("respondent_email", False) or not sub.email or form.opt("results", "show") != "show":
        return False
    if not mail.ready():
        sub.results_error = "Email is not set up (Settings → Email)."
        sub.save(update_fields=["results_error"])
        return False
    lang = sub.language
    env = spec.env(sub.answers, spec.public_calcs(sub.calcs), lang)
    e = form.opt("email") or {}
    subject = engine.fill(tx(e.get("subject"), lang), env, markdown=False) or engine.escape(form.name(lang))
    subject = engine.to_text([{"t": "p", "html": subject}])
    intro = engine.fill(tx(e.get("intro"), lang), env)
    outro = engine.fill(tx(e.get("outro"), lang), env)
    p = "margin:0 0 14px;line-height:1.6;font-size:15px;color:#0B1320"
    html = engine.to_email_html(sub.results, lang, before=f'<p style="{p}">{intro}</p>' if intro else "",
                                after=f'<p style="{p};margin-top:22px">{outro}</p>' if outro else "")
    text = "\n\n".join(x for x in (engine.to_text([{"t": "p", "html": intro}]), engine.to_text(sub.results),
                                   engine.to_text([{"t": "p", "html": outro}])) if x)
    try:
        mail.send(subject[:200], text, [sub.email], html=html, reply_to=[notify_email(form)])
        sub.results_error, sub.results_emailed_at = "", timezone.now()
    except Exception as exc:
        log.warning("results email failed: %s", type(exc).__name__)
        sub.results_error = f"{type(exc).__name__}: {exc}"[:200]
    sub.save(update_fields=["results_error", "results_emailed_at"])
    return not sub.results_error


def complete(sub, spec):
    """Everything after a submission is recorded. Never raises."""
    try:
        to_crm(sub, spec)
    except Exception:
        log.exception("form CRM capture failed")
    email_respondent(sub, spec)
    notify_team(sub, spec)
