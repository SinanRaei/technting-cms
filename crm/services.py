"""CRM logic shared by views, the enquiry form and commands."""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from cms.areas import AREA_OF_PREFIX, AREAS

from .models import Activity, Contact, Deal, Organization, Stage

FREE_MAIL = {"gmail.com", "googlemail.com", "hotmail.com", "outlook.com", "live.com", "yahoo.com", "icloud.com", "me.com",
             "aol.com", "proton.me", "protonmail.com", "msn.com", "gmx.com", "mail.com", "yandex.com", "zoho.com"}
INTEREST_LAB = {name: key for key, name in AREAS.items()}


def crm_settings():
    from cms.models import Setting
    v = Setting.objects.filter(key="crm").values_list("value", flat=True).first() or {}
    return {"default_owner": v.get("default_owner"), "currency": v.get("currency") or "USD",
            "response_hours": int(v.get("response_hours") or 24)}


def default_owner():
    from django.contrib.auth import get_user_model
    U = get_user_model()
    uid = crm_settings()["default_owner"]
    return U.objects.filter(pk=uid, is_active=True).first() if uid else None


def email_domain(email):
    d = (email or "").rsplit("@", 1)[-1].lower().strip()
    return "" if not d or d in FREE_MAIL else d


@transaction.atomic
def capture_enquiry(sub, lab=""):
    """Website form submission -> contact + organisation + deal in New, with the message on the timeline.
    The deal carries the lab and service of the page the form was on, so sales see what the person was reading."""
    if Deal.objects.filter(enquiry=sub).exists():
        return Deal.objects.filter(enquiry=sub).first()
    owner = default_owner()
    domain = email_domain(sub.email)
    org = None
    if sub.organisation:
        org = Organization.objects.filter(name__iexact=sub.organisation.strip()).first()
    if org is None and domain:
        org = Organization.objects.filter(domain=domain).first()
    if org is None and (sub.organisation or domain):
        org = Organization.objects.create(name=(sub.organisation or domain).strip()[:200], domain=domain,
                                          website=f"https://{domain}" if domain else "", owner=owner)
    elif org and domain and not org.domain:
        org.domain = domain
        org.save(update_fields=["domain"])
    contact = Contact.objects.filter(email__iexact=sub.email).first() if sub.email else None
    if contact is None:
        contact = Contact.objects.create(name=sub.name[:150], email=sub.email, phone=sub.phone, organization=org,
                                         language=sub.language or "", source="website", lawful_basis="enquiry", owner=owner)
    else:
        changed = []
        if sub.phone and not contact.phone:
            contact.phone, changed = sub.phone, changed + ["phone"]
        if org and not contact.organization_id:
            contact.organization, changed = org, changed + ["organization"]
        if changed:
            contact.save(update_fields=changed)
    what = sub.service or (sub.interest if sub.interest and sub.interest != "Not sure yet" else "")
    title = f"{org.name if org else contact.name}: {what or 'website enquiry'}"
    deal = Deal.objects.create(title=title[:200], organization=org, contact=contact, stage=Stage.NEW,
                               probability=Stage.PROBABILITY[Stage.NEW], currency=crm_settings()["currency"],
                               owner=owner, source="website", lab=lab or INTEREST_LAB.get(sub.interest, ""), enquiry=sub,
                               services=[sub.service] if sub.service else [],
                               created_at=sub.created_at, stage_changed_at=sub.created_at, position=-1)
    where = f"\n\nSent from: {sub.topic + ' · ' if sub.topic else ''}{sub.page}" if sub.page else ""
    Activity.objects.create(kind=Activity.ENQUIRY, deal=deal, contact=contact, organization=org,
                            subject=f"Website enquiry{(' · ' + (sub.service or sub.interest)) if (sub.service or sub.interest) else ''}"[:200],
                            body=sub.message + where, created_at=sub.created_at)
    hours = crm_settings()["response_hours"]
    Activity.objects.create(kind=Activity.TASK, deal=deal, contact=contact, organization=org, assigned_to=owner,
                            subject=f"Reply to {contact.name}", due_at=sub.created_at + timedelta(hours=hours))
    return deal


def move_stage(deal, stage, user=None, lost_reason="", lost_note=""):
    """Change a deal's stage, keep probability in step, close/reopen, and log it on the timeline."""
    if stage not in Stage.LABEL or stage == deal.stage:
        return False
    old = deal.stage
    auto_prob = deal.probability == Stage.PROBABILITY.get(old)
    deal.stage = stage
    deal.stage_changed_at = timezone.now()
    if auto_prob or stage in (Stage.WON, Stage.LOST):
        deal.probability = Stage.PROBABILITY[stage]
    if stage in (Stage.WON, Stage.LOST):
        deal.closed_at = timezone.now()
    else:
        deal.closed_at = None
    if stage == Stage.LOST:
        deal.lost_reason, deal.lost_note = lost_reason[:20], lost_note[:300]
    else:
        deal.lost_reason, deal.lost_note = "", ""
    deal.save()
    body = ""
    if stage == Stage.LOST and (lost_reason or lost_note):
        from .models import LOST_REASONS
        body = ": ".join(x for x in (dict(LOST_REASONS).get(lost_reason, ""), lost_note) if x)
    Activity.objects.create(kind=Activity.STAGE, deal=deal, contact=deal.contact, organization=deal.organization,
                            subject=f"{Stage.LABEL[old]} → {Stage.LABEL[stage]}", body=body, created_by=user)
    return True


def log_activity(deal=None, contact=None, organization=None, kind=Activity.NOTE, subject="", body="", user=None,
                 due_at=None, assigned_to=None):
    if deal:
        contact = contact or deal.contact
        organization = organization or deal.organization
    a = Activity.objects.create(kind=kind, deal=deal, contact=contact, organization=organization, subject=subject[:200],
                                body=body, created_by=user, due_at=due_at,
                                assigned_to=assigned_to if kind == Activity.TASK else None)
    if deal and kind in Activity.RESPONSE_KINDS and not deal.first_response_at:
        deal.first_response_at = a.created_at
        deal.save(update_fields=["first_response_at"])
    return a


def money(v):
    return f"{Decimal(v or 0):,.0f}"


def dashboard_numbers(user=None, days=30):
    now = timezone.now()
    since = now - timedelta(days=days)
    open_deals = Deal.objects.filter(stage__in=Stage.OPEN)
    pipeline = sum((d.value for d in open_deals), Decimal(0))
    weighted = sum((d.weighted for d in open_deals), Decimal(0))
    closed_90 = Deal.objects.filter(closed_at__gte=now - timedelta(days=90))
    won_90, lost_90 = closed_90.filter(stage=Stage.WON).count(), closed_90.filter(stage=Stage.LOST).count()
    responded = Deal.objects.filter(created_at__gte=now - timedelta(days=90), first_response_at__isnull=False)
    hours = sorted((d.first_response_at - d.created_at).total_seconds() / 3600 for d in responded)
    median_h = hours[len(hours) // 2] if hours else None
    tasks = Activity.objects.filter(kind=Activity.TASK, done=False)
    by_stage = {s: {"count": 0, "value": Decimal(0)} for s in Stage.OPEN}
    for d in open_deals:
        by_stage[d.stage]["count"] += 1
        by_stage[d.stage]["value"] += d.value or 0
    new_by_source = (Deal.objects.filter(created_at__gte=since).values("source").annotate(n=Count("id")).order_by("-n"))
    new_by_lab = (Deal.objects.filter(created_at__gte=since).exclude(lab="").values("lab").annotate(n=Count("id")).order_by("-n"))
    return {
        "new_leads": Deal.objects.filter(created_at__gte=since).count(),
        "new_web": Deal.objects.filter(created_at__gte=since, source="website").count(),
        "open_count": open_deals.count(), "pipeline": pipeline, "weighted": weighted,
        "win_rate": round(100 * won_90 / (won_90 + lost_90)) if (won_90 + lost_90) else None,
        "won_value_90": closed_90.filter(stage=Stage.WON).aggregate(v=Sum("value"))["v"] or Decimal(0),
        "median_response_h": median_h,
        "overdue": tasks.filter(due_at__lt=now).count(),
        "due_today": tasks.filter(due_at__gte=now.replace(hour=0, minute=0, second=0), due_at__lt=now.replace(hour=23, minute=59)).count(),
        "by_stage": by_stage, "by_source": list(new_by_source), "by_lab": list(new_by_lab),
        "unanswered": Deal.objects.filter(stage=Stage.NEW, first_response_at__isnull=True).count(),
    }


def search(q):
    q = (q or "").strip()
    if not q:
        return [], [], []
    deals = Deal.objects.filter(Q(title__icontains=q) | Q(organization__name__icontains=q) | Q(contact__name__icontains=q)
                                | Q(contact__email__icontains=q)).select_related("organization", "contact")[:30]
    contacts = Contact.objects.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q)).select_related("organization")[:30]
    orgs = Organization.objects.filter(Q(name__icontains=q) | Q(domain__icontains=q))[:30]
    return deals, contacts, orgs


# ---------------------------------------------------------------- prospects (researched companies, not contacted yet)
LAB_OF_PREFIX = AREA_OF_PREFIX
PRIORITY_OF = {"A": "high", "B": "normal", "C": "low"}


def web_domain(url):
    d = (url or "").lower().strip()
    d = d.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    return d[4:] if d.startswith("www.") else d


def _digits_tails(phone):
    """Last 8 digits of each number in '1234 / +44 20 500 7777' -> {'65007777'}; short codes are ignored."""
    import re
    out = set()
    for part in re.split(r"[/,;]|\bor\b", phone or ""):
        d = re.sub(r"\D", "", part)
        if len(d) >= 7:
            out.add(d[-8:])
    return out


LEGAL_WORDS = {"the", "plc", "psc", "pjsc", "pjs", "psjc", "ltd", "limited", "llc", "co", "company", "inc", "sa", "saog",
               "شركة", "ش", "م", "ع", "ذ"}


def _plain_name(name):
    """'The Sample Bank P.L.C. (Jordan)' -> 'sample bank': no brackets, punctuation or legal-form words."""
    import re
    n = re.sub(r"\(.*?\)", " ", (name or "").lower()).replace("p.l.c", "plc").replace("p.s.c", "psc")
    words = [w for w in re.sub(r"[^\w\s]", " ", n).split() if w not in LEGAL_WORDS]
    return " ".join(words)


def prospect_matches(p):
    """What the CRM already has for this company: organisations (same domain or name), contacts (same email, same phone,
    or an address at the company's domain) and every deal attached to them. Each item carries the reason it matched."""
    domains = {d for d in (p.domain, web_domain(p.website), email_domain(p.email)) if d}
    names = {n for n in (_plain_name(p.name), _plain_name(p.name_ar)) if n}
    orgs = {}
    for o in Organization.objects.all():
        why = []
        if o.domain and o.domain in domains or o.website and web_domain(o.website) in domains:
            why.append("same website domain")
        if _plain_name(o.name) in names:
            why.append("same name")
        if why:
            orgs[o.pk] = (o, why)
    contacts = {}
    tails = _digits_tails(p.phone)
    email = (p.email or "").strip().lower()
    for c in Contact.objects.select_related("organization").filter(Q(email__gt="") | Q(phone__gt="")):
        why = []
        if email and c.email.lower() == email:
            why.append("same email")
        elif c.email and email_domain(c.email) in domains:
            why.append("email at the company's domain")
        if tails and tails & _digits_tails(c.phone):
            why.append("same phone")
        if why:
            contacts[c.pk] = (c, why)
    deals = (Deal.objects.filter(Q(organization_id__in=orgs) | Q(contact_id__in=contacts))
             .select_related("organization", "contact", "owner").order_by("-created_at").distinct())
    deals = list(deals)
    return {"orgs": list(orgs.values()), "contacts": list(contacts.values()), "deals": deals,
            "first_open": next((d for d in deals if d.is_open), None)}


def has_matches(m):
    return bool(m["orgs"] or m["contacts"] or m["deals"])


# fallback names for service codes that have no "service" entry in the CMS (fill in for your own catalogue)
CATALOGUE = {}


def service_names(codes, lang="en"):
    from cms.models import Entry
    found = {e.key: e for e in Entry.objects.filter(collection="service", key__in=codes or []).prefetch_related("translations__language")}
    out = []
    for code in codes or []:
        e = found.get(code)
        tr_ = {t.language.code: t.data for t in e.translations.all()} if e else {}
        out.append((code, (tr_.get(lang) or tr_.get("en") or {}).get("name", "") or CATALOGUE.get(code, "")))
    return out


UNVERIFIED_KINDS = ["company site", "annual report", "exchange filing", "press release", "government directory", "event page",
                    "business directory", "other"]


def clean_unverified(item):
    """One 'unverified info' entry, trimmed; None when it holds no contact detail or name worth keeping."""
    import secrets
    s = {k: str(item.get(k) or "").strip() for k in ("type", "role", "name", "email", "phone", "source", "source_kind", "note")}
    s["type"] = "person" if s["type"] == "person" or s["name"] else "company"
    if s["email"] and ("@" not in s["email"] or " " in s["email"]):
        s["email"] = ""
    if s["source_kind"] not in UNVERIFIED_KINDS:
        s["source_kind"] = "other" if s["source_kind"] else ""
    # keep: any email or phone; a named person with a role; or a company link such as a tenders or supplier page
    if not (s["email"] or s["phone"] or (s["type"] == "person" and s["name"] and s["role"])
            or (s["type"] == "company" and s["role"] and s["source"].startswith("http"))):
        return None
    limits = {"role": 150, "name": 150, "email": 254, "phone": 80, "source": 500, "source_kind": 40, "note": 500}
    s = {k: v[:limits.get(k, 20)] for k, v in s.items()}
    s["id"] = str(item.get("id") or secrets.token_hex(4))[:16]
    s["added"] = str(item.get("added") or timezone.localdate().isoformat())[:10]
    return s


def merge_unverified(p, items):
    """Add new entries to p.unverified, skipping ones already there (same name, role, email and phone). Returns how many were added."""
    def key(e):
        return (e.get("name", "").lower(), e.get("role", "").lower(), e.get("email", "").lower(), e.get("phone", "").replace(" ", ""))
    have = {key(e) for e in p.unverified or []}
    added = 0
    for raw in items or []:
        e = clean_unverified(raw)
        if e and key(e) not in have:
            p.unverified = list(p.unverified or []) + [e]
            have.add(key(e))
            added += 1
    return added


def prospect_summary(p):
    """The research, written onto the deal's timeline so sales see why and how to approach the company."""
    lines = [f"Why they fit ({p.fit_score}/5, priority {p.priority}): {p.fit_reason}"]
    if p.fit_source:
        lines.append(f"Source: {p.fit_source}")
    if p.services:
        lines.append("Suggested services: " + ", ".join(f"{c} {n}".strip() for c, n in service_names(p.services)))
    facts = [x for x in (p.sector, p.sub_sector, p.country, p.city, p.ownership, p.listed_on and f"listed on {p.listed_on}", p.size_band) if x]
    if facts:
        lines.append(" · ".join(facts))
    for label, value, src, ok in (("Email", p.email, p.email_source, p.email_verified), ("Phone", p.phone, p.phone_source, p.phone_verified)):
        if value:
            lines.append(f"{label}: {value} ({'checked on the company site' if ok else 'not verified'}{', ' + src if src else ''})")
    if p.contact_page:
        lines.append(f"Contact page: {p.contact_page}")
    if p.officer:
        lines.append(f"Named on their site: {p.officer}")
    if p.notes:
        lines.append(f"Notes: {p.notes}")
    if p.unverified:
        lines.append("Unverified info (check before use):")
        for e in p.unverified:
            who = " - ".join(x for x in (e.get("role"), e.get("name")) if x) or "Company channel"
            how = ", ".join(x for x in (e.get("email"), e.get("phone")) if x)
            lines.append(f"  · {who}{': ' + how if how else ''}{' (' + e['source'] + ')' if e.get('source') else ''}")
    lines.append("Company-level contact only. B2B outreach: say who we are, keep it relevant, include an opt-out and honour it.")
    return "\n".join(lines)


@transaction.atomic
def promote_prospect(p, user=None, link_deal=None):
    """Move a prospect to the leads. With link_deal, the research joins that existing deal; otherwise a new deal opens in New,
    reusing a matching organisation and contact instead of creating duplicates. Returns the deal."""
    from .models import Prospect
    if p.status == Prospect.MOVED and p.deal_id:
        return p.deal
    m = prospect_matches(p)
    if link_deal is not None:
        deal = link_deal
        log_activity(deal=deal, kind=Activity.NOTE, subject="Research from the prospect list", body=prospect_summary(p), user=user)
    else:
        org = m["orgs"][0][0] if m["orgs"] else None
        domain = p.domain or web_domain(p.website)
        if org is None:
            org = Organization.objects.create(name=p.name[:200], domain=domain, website=p.website, industry=p.sector[:120],
                                              country=p.country, size=p.size_band[:40], owner=user,
                                              notes="\n".join(x for x in (p.name_ar, p.ownership, p.linkedin) if x))
        else:
            changed = []
            for f, v in (("domain", domain), ("website", p.website), ("industry", p.sector[:120]), ("country", p.country)):
                if v and not getattr(org, f):  # fill gaps only, never overwrite what sales typed
                    setattr(org, f, v)
                    changed.append(f)
            if changed:
                org.save(update_fields=changed)
        contact = None
        email = (p.email or "").strip()
        if email:
            contact = next((c for c, why in m["contacts"] if "same email" in why), None)
        if contact is None and (email or p.phone):
            contact = Contact.objects.create(name=f"{p.name} (general contact)"[:150], email=email[:254], phone=p.phone[:40],
                                             organization=org, source="outbound", lawful_basis="legitimate", owner=user,
                                             notes="Company-level address published by the company"
                                                   + (f": {p.email_source or p.phone_source}" if (p.email_source or p.phone_source) else "."))
        first = service_names(p.services[:1])
        what = f"{first[0][0]} {first[0][1]}".strip() if first else "outbound"
        deal = Deal.objects.create(title=f"{p.name}: {what}"[:200], organization=org, contact=contact, stage=Stage.NEW,
                                   probability=Stage.PROBABILITY[Stage.NEW], currency=crm_settings()["currency"], owner=user,
                                   source="outbound", priority=PRIORITY_OF.get(p.priority, "normal"),
                                   lab=LAB_OF_PREFIX.get((p.services or [" "])[0][:1], ""), services=list(p.services or [])[:12],
                                   position=-1)
        log_activity(deal=deal, kind=Activity.SYSTEM, subject="Moved from the prospect list", body=prospect_summary(p), user=user)
        log_activity(deal=deal, kind=Activity.TASK, subject=f"First contact with {p.name}"[:200], user=user,
                     due_at=timezone.now() + timedelta(days=3), assigned_to=user)
    p.status, p.deal, p.moved_at, p.moved_by = Prospect.MOVED, deal, timezone.now(), user
    p.save(update_fields=["status", "deal", "moved_at", "moved_by", "updated_at"])
    return deal
