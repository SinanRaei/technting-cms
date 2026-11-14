"""Public demo mode (TECHNTING_CMS_DEMO_MODE=1).

A demo server lets anyone sign in with a shared account and try the dashboard until `manage.py demo_reset` rebuilds
it (every 2 hours; see docs/INSTALL.md, "Running a public demo"). The account is an administrator, so most pages can
be tried, but everything that reaches outside the server or could lock other visitors out is refused here:

  DemoModeMiddleware   refuses the dashboard actions in BLOCKED with a message (EN/AR) and adds X-Robots-Tag
  NetworkGuard         urllib refuses outbound HTTP(S) except to this site's own addresses (plugins, Shield, Technting SEO,
                       IndexNow, webhooks, link checks, Google Drive and S3 all use urllib)
  cms.mail             email goes to the console backend; nothing is sent
  cms.media            uploads limited to JPEG, PNG, WebP, GIF and PDF up to 5 MB, by signature and extension
"""
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

MESSAGE = "This is turned off in the public demo, so the demo stays safe for everyone."
BANNER = "This is a public demo. Everything resets every 2 hours. Do not enter real personal data."

# url name -> "post" (opening the page works, changes are refused) or "all" (the page itself is refused too)
BLOCKED = {
    "cms:updates": "post",                 # self-update
    "cms:licence": "post",                 # the demo needs no licence
    "cms:backups": "post",                 # making backups (disk space)
    "cms:backup_download": "all",
    "cms:offsite_settings": "post",
    "cms:offsite_run": "post",             # offsite copy and restore test
    "cms:offsite_download": "all",
    "cms:email_settings": "post",          # SMTP account and test email
    "cms:social_settings": "post",
    "cms:site_security": "post",
    "cms:users": "post",                   # creating users
    "cms:user_toggle": "post",
    "cms:user_invite": "post",
    "cms:user_role": "post",
    "cms:security": "post",                # two-step sign-in would lock the shared account
    "cms:set_password": "post",
    "cms:accept_invite": "post",
    "cms:plugins": "post",
    "cms:seo_refresh": "post",             # Google, PageSpeed and Bing APIs
    "cms:health_links": "post",            # external link check
    "crm:prospects_import": "post",        # spreadsheet uploads
}
BLOCKED_APPS = {"shield": "post"}          # IP blocks, feeds, Cloudflare, ending sessions of other visitors


def on():
    return bool(getattr(settings, "TECHNTING_CMS_DEMO_MODE", False))


def blocked(request, match):
    """True when this request is an action the demo refuses."""
    if not on() or match is None:
        return False
    mode = BLOCKED.get(match.view_name) or BLOCKED_APPS.get(match.app_name)
    if match.view_name == "cms:account":   # the shared account's password; the weekly email setting stays
        mode = "post" if request.method == "POST" and request.POST.get("form") != "digest" else None
    return mode == "all" or (mode == "post" and request.method not in ("GET", "HEAD", "OPTIONS"))


def message(request):
    from .ui_i18n import tr, ui_lang
    return tr(MESSAGE, ui_lang(request))


def has_code_field(spec):
    """Blocks with a raw HTML ("code") field are not offered and not published in the demo."""
    def walk(fields):
        return any(f.get("type") == "code" or walk(f.get("fields", [])) for f in fields or [])
    return walk((spec or {}).get("fields", []))


def code_blocks(theme, blocks):
    """Types of the incoming blocks that carry raw HTML."""
    out = set()
    for b in blocks if isinstance(blocks, list) else []:
        spec = theme.blocks.get(b.get("type")) if isinstance(b, dict) else None
        data = b.get("data") if spec else None
        if isinstance(data, dict) and any(f.get("type") == "code" and str(data.get(f.get("name")) or "").strip()
                                          for f in spec.get("fields", [])):
            out.add(b["type"])
    return out


# ---------------------------------------------------------------- outbound connections
def allowed_hosts():
    """This site's own addresses (the security page checks them); everything else is refused in the demo."""
    hosts = set()
    for url in (settings.TECHNTING_CMS_SITE_URL, settings.TECHNTING_CMS_ADMIN_URL):
        host = urllib.parse.urlsplit(url).hostname
        if host:
            hosts.add(host.lower())
    return hosts


class NetworkGuard(urllib.request.BaseHandler):
    """Runs before urllib's own HTTP handlers. Outside the demo it does nothing."""
    handler_order = 50

    def _check(self, req):
        if on():
            host = (urllib.parse.urlsplit(req.full_url).hostname or "").lower()
            if host not in allowed_hosts():
                raise urllib.error.URLError("outbound connections are turned off in the public demo")
        return None

    http_open = https_open = _check


def install_network_guard():
    urllib.request.install_opener(urllib.request.build_opener(NetworkGuard()))
