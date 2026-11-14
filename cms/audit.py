"""Activity log helper: audit(request, "page_publish", "/labs/ (en)")."""
import logging
from datetime import timedelta

from django.utils import timezone

log = logging.getLogger(__name__)
KEEP_DAYS = 365


def audit(request, action, target="", username=None):
    from .models import AuditEvent
    from .views import client_ip
    try:
        user = request.user if getattr(request, "user", None) is not None and request.user.is_authenticated else None
        ev = AuditEvent.objects.create(user=user, username=(username or (user.get_username() if user else ""))[:150],
                                       action=action[:40], target=str(target)[:300], ip=client_ip(request)[:64])
        if ev.pk % 200 == 0:  # prune now and then
            AuditEvent.objects.filter(created_at__lt=timezone.now() - timedelta(days=KEEP_DAYS)).delete()
    except Exception:  # the log must never break the action being logged
        log.exception("audit failed")
