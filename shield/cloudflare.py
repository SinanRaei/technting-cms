"""Optional: copy Technting Shield's blocks of single addresses to Cloudflare's edge (IP Access Rules), so they also cover
the public website, which nginx serves without Django. Off until an administrator enters an API token (permission:
Zone → Firewall Services → Edit) and the zone ID. The large threat lists stay on the server (Cloudflare's free plan
allows a limited number of rules); only addresses Technting Shield blocked itself are pushed. Rules are tagged in their
notes with "Technting Shield" and removed when the block ends.
"""
import json
import logging
import urllib.error
import urllib.request

from . import conf
from .netset import parse_net

log = logging.getLogger(__name__)
API = "https://api.cloudflare.com/client/v4"
NOTE = "Technting Shield"
MAX_PER_RUN = 50


def configured():
    return bool(conf.opt("cloudflare_token") and conf.opt("cloudflare_zone"))


def _call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + conf.opt("cloudflare_token"), "Content-Type": "application/json",
                                          "User-Agent": conf.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read(2_000_000))
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read(200_000))
        except ValueError:
            data = {}
        errors = "; ".join(str(e.get("message", "")) for e in data.get("errors") or []) or f"HTTP {exc.code}"
        raise RuntimeError(errors) from None


def test():
    """(ok, message) for the dashboard's "Test the connection" button."""
    if not configured():
        return False, "Enter the API token and zone ID in Plugins → Technting Shield first."
    try:
        zone = _call("GET", f"/zones/{conf.opt('cloudflare_zone')}")["result"]
        _call("GET", f"/zones/{conf.opt('cloudflare_zone')}/firewall/access_rules/rules?per_page=5")
        return True, zone.get("name", "")
    except Exception as exc:
        return False, str(exc)[:200]


def _target(network):
    n = parse_net(network)
    if n is None or n.num_addresses != 1:
        return None
    return ("ip" if n.version == 4 else "ip6"), str(n.network_address)


def sync():
    """Push new blocks, remove ended ones. While Technting Shield is off or in learning mode, every rule it pushed is
    taken back off the edge (blocks stay on the server). Returns a list of short status lines."""
    from django.db.models import Q
    from django.utils import timezone

    from .models import Block
    if not configured():
        return []
    zone, now, out = conf.opt("cloudflare_zone"), timezone.now(), []
    pushing = conf.enabled() and conf.protect()
    done = Block.objects.exclude(cf_rule_id="")
    if pushing:
        done = done.filter(expires_at__lte=now)
    for b in done[:MAX_PER_RUN]:
        try:
            _call("DELETE", f"/zones/{zone}/firewall/access_rules/rules/{b.cf_rule_id}", {"cascade": "none"})
        except RuntimeError as exc:
            if "not found" not in str(exc).lower():
                out.append(f"remove {b.network}: {exc}")
                continue
        if b.active(now):
            Block.objects.filter(pk=b.pk).update(cf_rule_id="")
        else:
            b.delete()
        out.append(f"removed {b.network} from Cloudflare")
    if not pushing:
        return out
    todo = Block.objects.filter(cf_rule_id="").filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))[:MAX_PER_RUN]
    for b in todo:
        target = _target(b.network)
        if not target:
            continue
        try:
            res = _call("POST", f"/zones/{zone}/firewall/access_rules/rules",
                        {"mode": "block", "configuration": {"target": target[0], "value": target[1]}, "notes": f"{NOTE}: {b.reason}"[:200]})
            b.cf_rule_id = res["result"]["id"]
            b.save(update_fields=["cf_rule_id"])
            out.append(f"pushed {b.network}")
        except Exception as exc:
            out.append(f"push {b.network}: {exc}")
            log.warning("cloudflare push failed: %s", exc)
            break
    return out


def remove(block):
    """Remove one block's rule now (when an administrator unblocks)."""
    if block.cf_rule_id and configured():
        try:
            _call("DELETE", f"/zones/{conf.opt('cloudflare_zone')}/firewall/access_rules/rules/{block.cf_rule_id}", {"cascade": "none"})
        except RuntimeError as exc:
            if "not found" not in str(exc).lower():
                raise
