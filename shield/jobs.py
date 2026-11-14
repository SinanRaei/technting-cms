"""Periodic Technting Shield work, run by publish_due every 5 minutes (systemd timer). Each job has its own interval and
never raises: a failing source is noted in the log and on the dashboard, and the rest still runs."""
import logging
import time

from . import conf

log = logging.getLogger(__name__)
# feeds: each list has its own interval too; "integrity" covers the code and the public website files
HOURS = {"feeds": 1, "osv": 24, "integrity": 1, "ct": 12, "domain": 6, "lookalike": 24, "media": 6, "prune": 24}


def _state():
    from cms.models import Setting
    return Setting.objects.filter(key="shield:jobs").values_list("value", flat=True).first() or {}


def _mark(name):
    from cms.models import Setting
    s = _state()
    s[name] = time.time()
    Setting.objects.update_or_create(key="shield:jobs", defaults={"value": s})


def last_run(name):
    return _state().get(name)


def run_job(name):
    """Run one job now. Returns status lines."""
    from . import alerts, events
    out = []
    if name == "feeds":
        from django.core.cache import cache

        from . import feeds
        out += feeds.refresh_due()
        for row in feeds.status():
            if row["stale"] and row["kind"] == "block" and row["updated"] is not None and cache.add(f"shield-stale:{row['name']}", 1, 86400):
                events.record("feed_failed", kind="scan", severity="medium", action="alert", detail=row["label"])
                alerts.send_admins("feed_failed", row["label"])
    elif name == "osv":
        from . import osv
        result, new = osv.run()
        out.append(f"osv: {result.get('packages', 0)} packages, {len(result.get('findings', []))} known problems"
                   + (f" ({result['error']})" if result.get("error") else ""))
        for f in new:
            sev = "high" if f["severity"] in ("CRITICAL", "HIGH") else "medium"
            events.record("vuln", kind="scan", severity=sev, action="alert", detail=f"{f['package']} {f['version']}: {f['id']}")
        if any(f["severity"] in ("CRITICAL", "HIGH") for f in new):
            alerts.send_admins("vuln", ", ".join(sorted({f["package"] for f in new})))
    elif name == "integrity":
        from . import integrity
        result, new, new_web = integrity.run()
        out.append(f"integrity: {result['files']} files vs {result['source']}, {len(result['changed'])} changed, {len(result['added'])} added")
        alarming = [f for f in new if f in result["changed"] or f in result["added"]]
        if alarming:
            events.record("integrity", kind="scan", severity="high", action="alert", detail=", ".join(alarming[:8]))
            alerts.send_admins("integrity", ", ".join(alarming[:8]))
        if new_web:
            events.record("web_root", kind="scan", severity="high", action="alert", detail=", ".join(new_web[:8]))
            alerts.send_admins("web_root", ", ".join(new_web[:8]))
        from . import public
        res, problems = public.run()
        if res is None:
            out.append("public site: skipped (publishing, or nothing published yet)")
        else:
            out.append(f"public site: {res['files']} files, {len(res['changed'])} changed, {len(res['missing'])} missing, "
                       f"{len(res['new_extra'])} new unknown")
            changed = [f for k, f in problems if k in ("changed", "missing")]
            extra = [f for k, f in problems if k == "extra"]
            if changed:
                events.record("public_changed", kind="scan", severity="high", action="alert", detail=", ".join(changed[:8]))
                alerts.send_admins("public_changed", ", ".join(changed[:8]))
            if extra:
                events.record("public_extra", kind="scan", severity="medium", action="alert", detail=", ".join(extra[:8]))
    elif name == "ct":
        from . import ct
        state, new = ct.run()
        out.append(f"ct: {len(state.get('certs', {}))} certificates" + (f" ({state['error']})" if state.get("error") else ""))
        for cid, c, level in new:
            events.record("ct_new", kind="scan", severity=level, action="alert" if level == "high" else "logged",
                          detail=f"{', '.join(c['names'][:4])} · {c['issuer']} · {c['not_before']}")
        if any(level == "high" for *_, level in new):
            alerts.send_admins("ct_new", "; ".join(", ".join(c["names"][:3]) for _, c, level in new if level == "high")[:300])
    elif name == "domain":
        from . import domain
        res, changes = domain.run()
        out.append(f"domain: {len([i for i in res['items'] if i['level'] != 'ok'])} notes"
                   + (f", not checked: {', '.join(res['failed'])}" if res["failed"] else ""))
        for key, before, now in changes:
            events.record("domain_dns", kind="scan", severity="high", action="alert",
                          detail=f"{key}: {', '.join(before) or '-'} → {', '.join(now) or '-'}")
        if changes:
            alerts.send_admins("domain_dns", "; ".join(f"{k}: {', '.join(n) or '-'}" for k, _, n in changes)[:300])
    elif name == "lookalike":
        from . import lookalike
        state, new = lookalike.run()
        out.append(f"lookalike: {state['checked']} names checked, {len(state['found'])} registered, {len(new)} new")
        for n in new:
            info = state["found"][n]
            events.record("lookalike", kind="scan", severity="high" if info.get("mail") or info.get("web") else "medium",
                          action="alert", detail=n + (" · email" if info.get("mail") else "") + (" · website" if info.get("web") else ""))
        if new:
            alerts.send_admins("lookalike", ", ".join(new[:10]))
    elif name == "media":
        from . import mediascan
        state, new = mediascan.run()
        out.append(f"media: {state['count']} files, {len(state['problems'])} suspicious")
        for rel in new:
            level = max((lvl for lvl, _ in state["problems"][rel]), key=["low", "medium", "high"].index)
            events.record("media", kind="scan", severity=level, action="alert" if level == "high" else "logged",
                          detail=f"{rel}: {'; '.join(t for _, t in state['problems'][rel])}")
        if any(lvl == "high" for rel in new for lvl, _ in state["problems"][rel]):
            alerts.send_admins("media", ", ".join(new[:8]))
    elif name == "prune":
        n = events.prune()
        if n:
            out.append(f"log: removed {n} old lines")
    return out


def run_due(force=False):
    """Called by publish_due. Returns status lines for its output."""
    from . import cloudflare, events
    if not conf.enabled():
        try:
            from .models import Block
            return cloudflare.sync() if Block.objects.exclude(cf_rule_id="").exists() else []
        except Exception:
            log.exception("shield: Cloudflare clean-up failed")
            return []
    out = []
    state = _state()
    for name, hours in HOURS.items():
        if force or time.time() - state.get(name, 0) >= hours * 3600:
            try:
                _mark(name)  # mark first, so a job that keeps failing does not run every 5 minutes
                out += run_job(name)
            except Exception as exc:
                log.exception("shield job %s failed", name)
                out.append(f"{name}: failed ({type(exc).__name__})")
    try:
        out += cloudflare.sync()
        n = events.expired(cloudflare.configured())
        if n:
            out.append(f"blocks: {n} ended")
    except Exception as exc:
        log.exception("shield block sync failed")
        out.append(f"blocks: failed ({type(exc).__name__})")
    return out
