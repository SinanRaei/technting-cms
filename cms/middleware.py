"""Send signed-in users to the two-step verification setup when the site requires it."""
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class SetupMiddleware:
    """Until the first administrator exists, every dashboard URL opens the setup wizard (cms/setup_wizard.py).
    The public endpoints (contact form, forms, beacon, newsletter) and static files keep working."""
    OPEN = ("/setup/", "/static/", "/assets/", "/uploads/", "/api/", "/f/", "/newsletter/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(self.OPEN):
            from .setup_wizard import is_complete
            if not is_complete():
                return redirect("cms:setup")
        return self.get_response(request)


class DemoModeMiddleware:
    """Public demo (cms/demo.py): refuses the actions in demo.BLOCKED with a message, and keeps the dashboard out of
    search engines. Does nothing unless TECHNTING_CMS_DEMO_MODE is on."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.TECHNTING_CMS_DEMO_MODE:
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        from . import demo
        if not demo.blocked(request, getattr(request, "resolver_match", None)):
            return None
        text = demo.message(request)
        wants_json = (request.path.startswith("/api/") or "application/json" in request.headers.get("Accept", "")
                      or "application/json" in request.headers.get("Content-Type", "")
                      or request.headers.get("X-Requested-With") == "XMLHttpRequest")
        if wants_json:
            from django.http import JsonResponse
            return JsonResponse({"ok": False, "error": text, "message": text}, status=403)
        from django.contrib import messages
        from django.utils.http import url_has_allowed_host_and_scheme
        messages.error(request, text)
        back = request.headers.get("Referer", "")
        if not (back and url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure())):
            back = reverse("cms:dashboard")
        return redirect(back)


class Require2FAMiddleware:
    ALLOWED = ("cms:security", "cms:logout", "cms:ui_language")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        # staff only: accounts without dashboard access have no two-step setup page
        if user is not None and user.is_authenticated and (user.is_staff or user.is_superuser) and not request.path.startswith(("/static/", "/assets/", "/uploads/", "/api/")):
            from .models import Setting, UserSecurity
            if Setting.objects.filter(key="require_2fa", value=True).exists():
                enabled = UserSecurity.objects.filter(user=user, enabled=True).exists()
                if not enabled and request.path not in {reverse(n) for n in self.ALLOWED}:
                    return redirect("cms:security")
        return self.get_response(request)


DASHBOARD_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com; "
                 "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; "
                 "img-src 'self' data: blob: " + settings.TECHNTING_CMS_SITE_URL + "; media-src 'self' blob:; connect-src 'self' https://cloudflareinsights.com; "
                 "frame-src https://www.youtube-nocookie.com https://player.vimeo.com; "
                 "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
PERMISSIONS = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()"


class SecurityHeadersMiddleware:
    """Content-Security-Policy and Permissions-Policy for the dashboard (the public site gets its own from nginx)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", DASHBOARD_CSP)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS)
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response
