from django.conf import settings
from django.db import models
from django.utils import timezone


class Event(models.Model):
    """One line of the security log: a blocked or logged request, a sign-in event, a scan result."""
    HIGH, MEDIUM, LOW, INFO = "high", "medium", "low", "info"
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_at = models.DateTimeField(default=timezone.now, db_index=True)  # repeats within a few minutes are counted, not stored again
    count = models.PositiveIntegerField(default=1)
    kind = models.CharField(max_length=20, db_index=True)        # firewall | login | scan
    rule = models.CharField(max_length=40)                       # scanner, attack:sqli, feed:spamhaus-drop, rate, lockout, ...
    severity = models.CharField(max_length=8, default=LOW)
    action = models.CharField(max_length=10, default="logged")   # blocked | logged | alert
    ip = models.CharField(max_length=64, blank=True, db_index=True)
    country = models.CharField(max_length=2, blank=True)
    method = models.CharField(max_length=8, blank=True)
    path = models.CharField(max_length=300, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    username = models.CharField(max_length=150, blank=True)
    detail = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-last_at"]


class Block(models.Model):
    """An address or network that may not reach the dashboard or its public APIs."""
    MANUAL, AUTO = "manual", "auto"
    network = models.CharField(max_length=64)                    # 1.2.3.4 or 1.2.3.0/24
    reason = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=10, default=MANUAL)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)     # empty = until removed
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    hits = models.PositiveIntegerField(default=0)
    cf_rule_id = models.CharField(max_length=64, blank=True)     # Cloudflare IP Access Rule, when pushed to the edge

    class Meta:
        ordering = ["-created_at"]

    def active(self, now=None):
        return self.expires_at is None or self.expires_at > (now or timezone.now())


class KnownDevice(models.Model):
    """Browsers and countries a user has signed in from, for new-device and new-country alerts."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    device = models.CharField(max_length=64)                     # SHA-256 of the device cookie
    country = models.CharField(max_length=2, blank=True)
    ip = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    first_seen = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_seen"]
