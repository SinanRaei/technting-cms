"""Technting Shield firewall for the dashboard host and the public APIs it serves (/api/contact, /api/subscribe, /api/hit).

The public website itself is static files served by nginx, so requests for it never reach Django; blocks can be
pushed to Cloudflare's edge (cloudflare.py) to cover it too. In learning mode (the default) every rule only writes
the log. Any error inside the firewall lets the request through: a bug here must never take the dashboard down.
"""
import contextvars
import logging
import re
from urllib.parse import unquote_plus

from django.conf import settings
from django.core.cache import caches
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.html import escape

from . import conf, events, feeds
from .netset import is_public, parse_ip

log = logging.getLogger(__name__)
ui_lang = contextvars.ContextVar("shield_ui_lang", default="en")

PUBLIC_PREFIXES = ("/api/contact", "/api/subscribe", "/api/hit", "/newsletter/", "/assets/", "/uploads/", "/static/")
SKIP_PREFIXES = ("/static/", "/assets/", "/uploads/")
DEVICE_COOKIE = "technting_cms_device"

# Paths that do not exist on Technting CMS and are only asked for by scanners (WordPress, PHP, leaked config, admin tools).
SCANNER = re.compile(r"""(?ix)
    \.(php\d?|phtml|asp|aspx|jsp|cgi|env|ini|sql|bak|old|swp|git|svn|htaccess|htpasswd|ds_store|yml|yaml|config|log)(\?|$|/)
  | ^/(wp-|wordpress|xmlrpc|phpmyadmin|pma|myadmin|adminer|cgi-bin|vendor/|\.git|\.svn|\.aws|\.ssh|\.vscode|\.idea|actuator
      |server-status|boaform|hnap1|owa/|autodiscover|remote/login|sdk|telescope|_profiler|solr/|console/|manager/html
      |jenkins|druid|geoserver|cgi/|shell|webshell|backup|dump|setup\.cgi|global-protect|dana-na|\.well-known/(?!acme-challenge|security\.txt))
""")
BAD_AGENTS = re.compile(r"(?i)sqlmap|nikto|nmap|masscan|zgrab|nuclei|wpscan|acunetix|dirbuster|gobuster|feroxbuster|ffuf|wfuzz|"
                        r"hydra|jorgee|zmeu|netsparker|openvas|w3af|havij|commix|fimap|morfeus|libwww-perl|python-httpx/0\.0")
ATTACKS = [
    ("attack:sqli", re.compile(r"(?i)\bunion\b[\s(]+(all\s+)?select\b|\bselect\b.+\bfrom\b.+\b(information_schema|sysobjects|pg_catalog)\b|"
                               r"'\s*or\s+'?\d+'?\s*=\s*'?\d|\b(sleep|benchmark|pg_sleep)\s*\(\s*\d|;\s*(drop|truncate|alter)\s+table\b|"
                               r"\bload_file\s*\(|\binto\s+(out|dump)file\b|\bwaitfor\s+delay\b|\bextractvalue\s*\(|\bupdatexml\s*\(")),
    ("attack:xss", re.compile(r"(?i)<\s*script\b|javascript\s*:|\bon(error|load|mouseover|focus|toggle|begin)\s*=|<\s*(svg|img|iframe|body)"
                              r"\b[^>]*\bon\w+\s*=|document\.(cookie|domain)|\balert\s*\(|<\s*iframe\b")),
    ("attack:traversal", re.compile(r"(?i)\.\./|\.\.\\|/etc/(passwd|shadow|hosts)|\bwin\.ini\b|/proc/self/|\bboot\.ini\b|"
                                    r"(php|file|expect|zip|phar|data)://")),
    ("attack:rce", re.compile(r"(?i)\$\{jndi:|\$\{\$\{|;\s*(wget|curl|nc|bash|chmod)\s+(-|https?:|/)|\|\s*(nc|bash|sh)\b|"
                              r"\$\((wget|curl|id|whoami|cat)\b|<\?php|\bbase64_decode\s*\(|\beval\s*\(|\bsystem\s*\(|\bpassthru\s*\(")),
]


def client_ip(request):
    return peer_info(request)[0]


def peer_info(request):
    """(visitor address, came through Cloudflare?). CF-Connecting-IP and CF-IPCountry are trusted only when the
    request really came through Cloudflare (nginx passes the connecting address as X-Real-IP), so they cannot be
    forged by connecting to the server directly. A private or missing X-Real-IP means a local proxy hop."""
    peer = request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR", "")
    cf = request.META.get("HTTP_CF_CONNECTING_IP", "").strip()
    if cf and parse_ip(cf) and (not is_public(peer) or feeds.is_cloudflare(peer)):
        return cf, True
    return peer, False


def country(request):
    """Cloudflare's country code for the visitor, or "" when the request did not come through Cloudflare."""
    return request.META.get("HTTP_CF_IPCOUNTRY", "").upper()[:2] if getattr(request, "shield_via_cf", False) else ""


def _texts(request, body):
    """Decoded path, query and (for public forms) the form fields, the places attacks hide. Passwords are never
    inspected: a strong password may contain anything."""
    out = [unquote_plus(unquote_plus(request.path)), unquote_plus(unquote_plus(request.META.get("QUERY_STRING", "")))]
    if body:
        out += [v[:5000] for k, values in request.POST.lists() if k not in ("password", "csrfmiddlewaretoken") for v in values]
    return out


def inspect(request, ip, authed):
    """(rule, severity, block?) for the first rule that matches, or None. Order matters: cheap checks first.
    Signed-in staff passed the password (and two-step) check: threat lists and automatic blocks only log them
    (a shared mobile address may be on a list), and their editing never trips a pattern. Blocks an administrator
    made, and country rules, apply to everyone."""
    path = request.path
    public = path.startswith(PUBLIC_PREFIXES)
    hit = events.blocked(ip)
    if hit:
        return hit, "high", not (authed and hit == "auto")
    for name in feeds.lookup(ip):
        if name == "tor-exits":
            if conf.opt("block_tor"):
                return "feed:tor-exits", "medium", not authed
            continue
        if conf.opt("block_feeds"):
            return f"feed:{name}", "high", not authed
    code = country(request)
    if code and code in conf.countries("blocked_countries"):
        return "country", "medium", True
    allowed = conf.countries("dashboard_countries")
    if allowed and not public and code not in allowed:  # unknown country (or not via Cloudflare) is refused too
        return "dashboard_country", "medium", True
    if authed:
        return None
    if BAD_AGENTS.search(request.META.get("HTTP_USER_AGENT", "")):
        return "bad_agent", "high", True
    if SCANNER.search(path):
        return "scanner", "medium", True
    # only url-encoded forms: reading a multipart body here would stop the view from reading it again
    body = (request.method == "POST" and (public or path.startswith("/login")) and not path.startswith("/api/hit")
            and request.content_type == "application/x-www-form-urlencoded")
    for text in _texts(request, body):
        for rule, rx in ATTACKS:
            if rx.search(text):
                return rule, "high", True
    return _rate(ip, path)


def _rate(ip, path):
    """Requests per minute per address, counted in this process's memory (cache "shield"), so a busy page never
    writes to disk. With several workers the real limit is a little higher; it is meant for floods."""
    hot = caches["shield"]
    per_minute = conf.number("requests_per_minute") * (4 if path.startswith("/api/hit") else 1)
    key = f"shield-rl:{events.bucket(ip)}:{int(timezone.now().timestamp() // 60)}"
    if hot.add(key, 1, 90):
        return None
    try:
        n = hot.incr(key)
    except ValueError:
        return None
    if n > per_minute:
        return "rate", "medium", True
    return None


def blocked_response(request, rule, status=403):
    if request.path.startswith("/api/") or "json" in request.headers.get("Accept", ""):
        return JsonResponse({"ok": False, "error": "blocked" if status == 403 else "too_many_requests"}, status=status)
    ref = timezone.now().strftime("%Y%m%d%H%M%S")
    html = (f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Access blocked</title><body style="font-family:system-ui,sans-serif;max-width:560px;margin:12vh auto;padding:0 16px;'
            f'line-height:1.6;color:#123"><h1 style="font-size:22px">Access blocked</h1><p>This request was stopped by the site\'s '
            f'security filter. If you think this is a mistake, email us and quote the reference below.</p>'
            f'<h2 dir="rtl" lang="ar" style="font-size:22px">تم إيقاف الطلب</h2><p dir="rtl" lang="ar">أوقف نظام حماية الموقع هذا الطلب. '
            f'إذا كان ذلك خطأً، راسلونا واذكروا الرقم المرجعي أدناه.</p><p><code>{escape(rule)} · {ref}</code></p></body></html>')
    return HttpResponse(html, status=status, headers={"Cache-Control": "no-store"})


class ShieldMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not conf.enabled():
            return self.get_response(request)
        try:
            from cms.ui_i18n import ui_lang as session_lang
            ui_lang.set(session_lang(request))
            response = self._check(request)
        except Exception:
            log.exception("shield firewall error (request allowed)")
            response = None
        if response is not None:
            return response
        response = self.get_response(request)
        try:
            self._after(request, response)
        except Exception:
            log.exception("shield after-response error")
        return response

    def _check(self, request):
        ip, request.shield_via_cf = peer_info(request)
        request.shield_ip = ip
        if request.path.startswith(SKIP_PREFIXES) or not is_public(ip) or events.allowed(ip) or feeds.is_cloudflare(ip):
            return None
        peer = request.META.get("HTTP_X_REAL_IP")
        if peer and is_public(peer) and not feeds.is_cloudflare(peer):
            events.record("direct", severity="low", ip=ip, request=request)
        user = getattr(request, "user", None)
        authed = bool(user is not None and user.is_authenticated and user.is_staff)
        request._shield_was_anonymous = not (user is not None and user.is_authenticated)
        verdict = inspect(request, ip, authed)
        if not verdict:
            return self._turnstile(request, ip)
        rule, severity, block = verdict
        block = block and conf.protect()
        events.record(rule, severity=severity, action="blocked" if block else "logged", ip=ip, request=request,
                      username=user.get_username() if authed else "")
        if rule in ("scanner", "bad_agent") or rule.startswith("attack:"):
            events.strike(ip, rule, request)
        if rule == "rate" and block:
            events.strike(ip, rule, request, limit=5)
            return blocked_response(request, rule, 429)
        if block:
            return blocked_response(request, rule)
        return self._turnstile(request, ip)

    def _turnstile(self, request, ip):
        """The optional Turnstile check of a sign-in (see turnstile.py)."""
        if request.method != "POST" or request.path != "/login/" or not getattr(request, "_shield_was_anonymous", False):
            return None
        from . import turnstile
        if not turnstile.active():
            return None
        if turnstile.verify(request.POST.get("cf-turnstile-response", ""), ip) is not False:
            return None  # passed, or Cloudflare could not be asked
        from django.shortcuts import render

        from cms.ui_i18n import tr
        events.record("turnstile", kind="login", severity="low", action="blocked", ip=ip, request=request,
                      username=request.POST.get("username", "")[:150])
        response = render(request, "cms/login.html", {"error": tr("Please confirm that you are not a robot, then sign in again.", ui_lang.get())},
                          status=400)
        self._turnstile_csp(request, response)
        return response

    @staticmethod
    def _turnstile_csp(request, response):
        from . import turnstile
        if request.path == "/login/" and turnstile.active():
            from cms.middleware import DASHBOARD_CSP
            response.headers["Content-Security-Policy"] = turnstile.csp(DASHBOARD_CSP)

    def _after(self, request, response):
        self._turnstile_csp(request, response)
        token = getattr(request, "_shield_device_token", None)
        if token:
            response.set_cookie(DEVICE_COOKIE, token, max_age=2 * 365 * 86400, httponly=True, samesite="Lax",
                                secure=not settings.DEBUG)
        # a password sign-in that worked (the sign-in page answers with a redirect); not someone already signed in
        if (request.method == "POST" and request.path == "/login/" and response.status_code == 302
                and getattr(request, "_shield_was_anonymous", False)):
            from .pwned import check_after_login
            check_after_login(request)
