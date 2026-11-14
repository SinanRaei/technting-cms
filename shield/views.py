"""Technting Shield dashboard pages (administrators), plus two forms every signed-in user may use from My account:
security alert emails and "sign out my other sessions"."""
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from cms.audit import audit
from cms.views import _t, admin_required

from . import conf, events, sessions
from .models import Block, Event

TABS = ("overview", "log", "blocks", "lists", "scans", "domain", "sessions")
SEVERITY = ("high", "medium", "low", "info")


def _need_on(view):
    def wrapper(request, *args, **kwargs):
        if not conf.enabled():
            if request.method == "POST":
                raise Http404
            return render(request, "shield/off.html")
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _log_rows(qs, lang):
    from cms.ui_i18n import tr
    return [{"id": e.pk, "at": timezone.localtime(e.last_at).strftime("%Y-%m-%d %H:%M:%S"), "count": e.count, "kind": e.kind,
             "rule": e.rule, "label": tr(events.label(e.rule), lang), "severity": e.severity, "action": e.action,
             "action_label": tr({"blocked": "Blocked", "logged": "Logged", "alert": "Alert"}.get(e.action, e.action), lang),
             "ip": e.ip, "country": e.country, "method": e.method, "path": e.path, "ua": e.user_agent[:120], "user": e.username,
             "detail": e.detail} for e in qs]


def _filtered(request):
    qs = Event.objects.all()
    f = {k: request.GET.get(k, "").strip() for k in ("kind", "severity", "action", "ip", "q")}
    if f["kind"] in ("firewall", "login", "scan"):
        qs = qs.filter(kind=f["kind"])
    if f["severity"] in SEVERITY:
        qs = qs.filter(severity=f["severity"])
    if f["action"] in ("blocked", "logged", "alert"):
        qs = qs.filter(action=f["action"])
    if f["ip"]:
        qs = qs.filter(ip=f["ip"])
    if f["q"]:
        from django.db.models import Q
        qs = qs.filter(Q(path__icontains=f["q"]) | Q(username__icontains=f["q"]) | Q(detail__icontains=f["q"]) | Q(user_agent__icontains=f["q"]))
    return qs, f


@admin_required
@_need_on
def home(request):
    from cms.ui_i18n import ui_lang

    from . import cloudflare, ct, feeds, integrity, jobs, osv, report
    tab = request.GET.get("tab", "overview")
    tab = tab if tab in TABS else "overview"
    lang = ui_lang(request)
    ctx = {"tab": tab, "tabs": TABS, "protect": conf.protect(), "cloudflare": cloudflare.configured(),
           "reputation_on": bool(conf.opt("abuseipdb_key"))}
    if tab == "overview":
        ctx.update(c7=report.counts(7), c1=report.counts(1), findings=report.findings(), feeds=feeds.status(),
                   osv=osv.load(), integrity=integrity.load(), ct=ct.load(), blocks_active=sum(1 for b in Block.objects.all() if b.active()))
        for r in ctx["c7"]["top_rules"]:
            r["label"] = events.label(r["rule"])
    elif tab == "log":
        qs, f = _filtered(request)
        ctx.update(rows=_log_rows(qs[:200], lang), f=f, severities=SEVERITY)
    elif tab == "blocks":
        now = timezone.now()
        ctx.update(blocks=[b for b in Block.objects.select_related("created_by")[:500] if b.active(now)],
                   allow=conf.opt("allow_ips"))
    elif tab == "lists":
        ctx.update(feeds=feeds.status(), last=jobs.last_run("feeds"), check=request.session.pop("shield_check", None))
    elif tab == "scans":
        from . import mediascan, public
        o, i, c = osv.load(), integrity.load(), ct.load()
        m = mediascan.load()
        ctx.update(osv=o, integrity=i, ct=c, certs=ct.recent(c), domain=conf.site_domain(), public=public.load(),
                   media=m, media_problems=sorted((m or {}).get("problems", {}).items()))
    elif tab == "domain":
        from . import domain, lookalike
        lk = lookalike.load()
        ctx.update(dom=domain.load(), lookalikes=lookalike.rows(lk), lk=lk, domain=conf.site_domain())
    elif tab == "sessions":
        rows = sessions.active()
        for r in rows:
            r["browser"] = sessions.browser(r["ua"])
            r["current"] = r["key"] == request.session.session_key
        from .models import KnownDevice
        ctx.update(sessions=rows, devices=KnownDevice.objects.select_related("user")[:100])
    return render(request, "shield/shield.html", ctx)


@admin_required
@_need_on
def log_json(request):
    from cms.ui_i18n import ui_lang
    qs, _ = _filtered(request)
    try:
        after = request.GET.get("after", "")
        if after:
            qs = qs.filter(last_at__gt=datetime.fromisoformat(after))
    except ValueError:
        pass
    rows = _log_rows(qs[:100], ui_lang(request))
    return JsonResponse({"rows": rows, "now": timezone.now().isoformat()}, headers={"Cache-Control": "no-store"})


@admin_required
@_need_on
@require_POST
def block_add(request):
    from . import feeds
    from .netset import parse_net
    network = request.POST.get("network", "").strip()
    n = parse_net(network)
    try:
        hours = int(request.POST.get("hours") or 0)
    except ValueError:
        hours = 0
    if n is None:
        messages.error(request, _t(request, "Enter an address such as 203.0.113.7 or a network such as 203.0.113.0/24."))
    elif n.prefixlen < (16 if n.version == 4 else 32):
        messages.error(request, _t(request, "That network is too large to block safely."))
    elif events.allowed(str(n.network_address)) or _covers_me(request, n):
        messages.error(request, _t(request, "That address is on the allow list, or it is your own address."))
    elif feeds.is_cloudflare(str(n.network_address)):
        messages.error(request, _t(request, "That is a Cloudflare server: blocking it would block many visitors."))
    else:
        reason = request.POST.get("reason", "").strip()[:200] or "Blocked by an administrator"
        Block.objects.create(network=str(n) if n.num_addresses > 1 else str(n.network_address), reason=reason, source=Block.MANUAL,
                             created_by=request.user, expires_at=timezone.now() + timedelta(hours=hours) if hours > 0 else None)
        events.forget_blocks()
        audit(request, "shield_block", str(n))
        messages.success(request, _t(request, "Blocked."))
    return redirect(_tab("blocks"))


def _covers_me(request, network):
    from .netset import parse_ip
    me = parse_ip(getattr(request, "shield_ip", "") or "")
    return me is not None and me.version == network.version and me in network


def _tab(name):
    return reverse("shield:home") + f"?tab={name}"


@admin_required
@_need_on
@require_POST
def block_remove(request, block_id):
    b = get_object_or_404(Block, pk=block_id)
    audit(request, "shield_unblock", b.network)
    err = events.unblock(b)
    if err:
        messages.warning(request, _t(request, "Removed here, but Cloudflare did not confirm:") + f" {err}")
    else:
        messages.success(request, _t(request, "Unblocked."))
    return redirect(_tab("blocks"))


@admin_required
@_need_on
@require_POST
def run_now(request, job):
    from . import cloudflare, feeds, jobs
    if job == "cloudflare":
        ok, msg = cloudflare.test()
        (messages.success if ok else messages.error)(request, (_t(request, "Cloudflare connection works:") if ok else _t(request, "Cloudflare connection failed:")) + f" {msg}")
        if ok:
            cloudflare.sync()
        return redirect(_tab("blocks"))
    if job not in jobs.HOURS:
        raise Http404
    lines = feeds.refresh_due(force=True) if job == "feeds" else jobs.run_job(job)
    audit(request, "shield_run", job)
    messages.success(request, _t(request, "Done.") + " " + " · ".join(lines))
    return redirect(_tab({"feeds": "lists", "domain": "domain", "lookalike": "domain"}.get(job, "scans")))


@admin_required
@_need_on
@require_POST
def integrity_accept(request):
    from . import integrity
    n = integrity.accept()
    integrity.run()
    audit(request, "shield_accept_files", str(n))
    messages.success(request, _t(request, "The current files are now the reference."))
    return redirect(_tab("scans"))


@admin_required
@_need_on
@require_POST
def public_accept(request):
    from . import public
    n = public.accept()
    audit(request, "shield_accept_public_files", str(n))
    messages.success(request, _t(request, "The current files are now the reference."))
    return redirect(_tab("scans"))


@admin_required
@_need_on
@require_POST
def ip_check(request):
    from . import feeds, reputation
    from .netset import is_public, parse_ip
    ip = request.POST.get("ip", "").strip()
    if not parse_ip(ip):
        messages.error(request, _t(request, "Enter an address such as 203.0.113.7."))
        return redirect(_tab("lists"))
    request.session["shield_check"] = {"ip": ip, "public": is_public(ip), "lists": feeds.lookup(ip), "cloudflare": feeds.is_cloudflare(ip),
                                       "blocked": events.blocked(ip) or "", "allowed": events.allowed(ip),
                                       "reputation": reputation.check(ip), "events": Event.objects.filter(ip=ip).count()}
    return redirect(_tab("lists"))


@admin_required
@_need_on
@require_POST
def session_end(request, ref_id):
    user = sessions.end(ref_id)
    if user:
        audit(request, "shield_session_end", user.get_username())
        messages.success(request, _t(request, "Signed out."))
    return redirect(_tab("sessions"))


@login_required
@_need_on
@require_POST
def sessions_others(request):
    n = sessions.end_others(request.user, request.session.session_key)
    events.record("sessions_ended", kind="login", severity="info", ip=getattr(request, "shield_ip", ""), request=request,
                  username=request.user.get_username(), detail=str(n))
    audit(request, "shield_sessions_others", str(n))
    messages.success(request, _t(request, "Other sessions signed out:") + f" {n}")
    from cms.views import safe_next
    return redirect(safe_next(request.POST.get("next")) or "cms:account")


@login_required
@_need_on
@require_POST
def alerts_pref(request):
    from . import alerts
    if not request.user.is_superuser:
        raise Http404
    on = request.POST.get("alerts") == "on"
    alerts.set_pref(request.user, on, request.POST.get("lang", "en"))
    audit(request, "shield_alerts_on" if on else "shield_alerts_off")
    messages.success(request, _t(request, "Saved."))
    return redirect("cms:account")
