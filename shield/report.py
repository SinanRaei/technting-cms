"""Technting Shield summaries for the dashboard, the Security page and the weekly summary email."""
from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from . import conf


def counts(days=7):
    from .models import Event
    since = timezone.now() - timedelta(days=days)
    qs = Event.objects.filter(kind="firewall", last_at__gte=since)
    blocked = qs.filter(action="blocked").aggregate(n=Sum("count"))["n"] or 0
    logged = qs.filter(action="logged").aggregate(n=Sum("count"))["n"] or 0
    top_rules = list(qs.values("rule").annotate(n=Sum("count")).order_by("-n")[:6])
    top_ips = list(qs.values("ip", "country").annotate(n=Sum("count"), rules=Count("rule", distinct=True)).order_by("-n")[:8])
    fails = Event.objects.filter(rule="login_failed", last_at__gte=since).aggregate(n=Sum("count"))["n"] or 0
    return {"blocked": blocked, "logged": logged, "top_rules": top_rules, "top_ips": top_ips, "login_failed": fails}


def findings():
    """[{level, text, detail}] for the Security page and the weekly email (only when Technting Shield is on)."""
    if not conf.enabled():
        return []
    from cms.models import Setting

    from . import ct, domain, feeds, integrity, lookalike, mediascan, osv, public
    out = []
    if not conf.protect():
        out.append({"level": "low", "text": "Technting Shield is in learning mode: attacks are logged, not blocked", "detail": ""})
    for row in feeds.status():
        if row["kind"] == "block" and row["stale"]:
            out.append({"level": "medium", "text": "A threat list is out of date", "detail": row["label"]})
    o = osv.load()
    if o:
        bad = [f for f in o.get("findings", []) if f["severity"] in ("CRITICAL", "HIGH")]
        if bad:
            out.append({"level": "high", "text": "Packages with serious security problems", "detail": ", ".join(sorted({f["package"] for f in bad}))})
        elif o.get("findings"):
            out.append({"level": "medium", "text": "Packages with known security problems", "detail": ", ".join(sorted({f["package"] for f in o["findings"]}))})
    i = integrity.load()
    if i and (i.get("changed") or i.get("added")):
        out.append({"level": "high", "text": "Code files differ from the committed version", "detail": str(len(i["changed"]) + len(i["added"]))})
    if i and i.get("web_root"):
        out.append({"level": "high", "text": "Unexpected files in the public website folder", "detail": ", ".join(i["web_root"][:3])})
    pub = public.load()
    if pub and (pub.get("changed") or pub.get("missing")):
        out.append({"level": "high", "text": "Public website files changed outside the CMS", "detail": str(len(pub["changed"]) + len(pub["missing"]))})
    if pub and pub.get("new_extra"):
        out.append({"level": "medium", "text": "New files on the public website that the CMS did not make", "detail": ", ".join(pub["new_extra"][:3])})
    m = mediascan.load()
    if m and m.get("problems"):
        out.append({"level": "high", "text": "Suspicious files in the media library", "detail": ", ".join(list(m["problems"])[:3])})
    d = domain.load()
    for item in (d or {}).get("items", []):
        if item["level"] in ("high", "medium"):
            out.append(item)
    lk = lookalike.load()
    if lk and lk.get("found"):
        week = timezone.now().timestamp() - 7 * 86400
        since = max(week, lk.get("first_checked", 0) + 60)
        fresh = [n for n, v in lk["found"].items() if v.get("first_seen", 0) > since]
        if fresh:
            out.append({"level": "high", "text": "Lookalike domains registered this week", "detail": ", ".join(fresh[:5])})
    c = ct.load()
    if c:
        week = timezone.now().timestamp() - 7 * 86400
        since = max(week, c.get("first_checked", 0) + 60)  # the first check only learns what already exists
        fresh = [x for x in c.get("certs", {}).values() if x.get("seen", 0) > since]
        if fresh:
            out.append({"level": "low", "text": "New certificates for our domain this week", "detail": str(len(fresh))})
    breached = Setting.objects.filter(key="shield:breached").values_list("value", flat=True).first() or {}
    if breached:
        from django.contrib.auth import get_user_model
        names = get_user_model().objects.filter(pk__in=[int(k) for k in breached]).values_list("username", flat=True)
        out.append({"level": "high", "text": "Accounts using a password found in data breaches", "detail": ", ".join(names)})
    return out


def digest_lines():
    """(text, detail) lines for the weekly summary's "Needs attention" part."""
    if not conf.enabled():
        return []
    c = counts(7)
    lines = [("Technting Shield: requests blocked this week", str(c["blocked"]))] if c["blocked"] else []
    lines += [(f["text"], f["detail"]) for f in findings() if f["level"] in ("high", "medium")]
    return lines
