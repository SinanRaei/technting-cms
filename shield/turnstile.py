"""Optional "are you human" check with Cloudflare Turnstile (free, no puzzles for most people, no tracking cookies)
on the sign-in page and, unless switched off, on the website forms (enquiries and newsletter). Off until an
administrator enters the site key and secret key in Plugins → Technting Shield.
If Cloudflare cannot be reached the request goes ahead (logged): it must never lock the team out or lose a lead.
"""
import json
import logging
import urllib.parse
import urllib.request

from . import conf

log = logging.getLogger(__name__)
VERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js"


def active():
    return conf.enabled() and bool(conf.opt("turnstile_site_key") and conf.opt("turnstile_secret"))


def verify(token, ip=""):
    """True / False, or None when Cloudflare could not be asked."""
    if not token:
        return False
    body = urllib.parse.urlencode({"secret": conf.opt("turnstile_secret"), "response": token[:2048], "remoteip": ip}).encode()
    req = urllib.request.Request(VERIFY, data=body, headers={"User-Agent": conf.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return bool(json.loads(r.read(100_000)).get("success"))
    except Exception as exc:
        log.warning("Turnstile check failed: %s", type(exc).__name__)
        return None


def forms_active():
    """The website forms ask for the check (the page gets the site key, the server asks Cloudflare)."""
    return active() and bool(conf.opt("turnstile_forms"))


def site_key():
    return conf.opt("turnstile_site_key") if forms_active() else ""


def check_form(request, token, ip="", form="enquiry"):
    """True when a website form may go ahead: the check is off, it passed, or Cloudflare could not be reached."""
    if not forms_active():
        return True
    ok = verify(token, ip)
    if ok is False:
        from . import events
        events.record("turnstile", kind="form", severity="low", action="blocked", ip=ip, request=request, detail=form)
        return False
    return True


def widget():
    from django.utils.html import escape
    return (f'<div class="cf-turnstile" data-sitekey="{escape(conf.opt("turnstile_site_key"))}" data-theme="light" '
            f'style="margin:4px 0 12px"></div><script src="{SCRIPT}" async defer></script>')


def csp(policy):
    """The dashboard's Content-Security-Policy plus what Turnstile needs (its script and its frame)."""
    policy = policy.replace("script-src 'self'", "script-src 'self' https://challenges.cloudflare.com", 1)
    return policy.replace("frame-src ", "frame-src https://challenges.cloudflare.com ", 1)
