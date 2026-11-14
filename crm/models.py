"""Technting CRM: organisations, contacts, deals (the sales pipeline), activities and tasks.

Website enquiries land here automatically (crm.services.capture_enquiry): the sender becomes a contact, their
organisation is matched or created, and a new deal opens in the "New" stage with the enquiry on its timeline.
Every stage change, task and note is an Activity, so a deal's timeline is its full history.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

USER = settings.AUTH_USER_MODEL


class Stage:
    NEW, QUALIFYING, DISCOVERY, PROPOSAL, NEGOTIATION, WON, LOST = (
        "new", "qualifying", "discovery", "proposal", "negotiation", "won", "lost")
    CHOICES = [(NEW, "New"), (QUALIFYING, "Qualifying"), (DISCOVERY, "Discovery"), (PROPOSAL, "Proposal"),
               (NEGOTIATION, "Negotiation"), (WON, "Won"), (LOST, "Lost")]
    OPEN = [NEW, QUALIFYING, DISCOVERY, PROPOSAL, NEGOTIATION]
    PROBABILITY = {NEW: 5, QUALIFYING: 10, DISCOVERY: 25, PROPOSAL: 50, NEGOTIATION: 75, WON: 100, LOST: 0}
    LABEL = dict(CHOICES)


SOURCES = [("website", "Website enquiry"), ("referral", "Referral"), ("linkedin", "LinkedIn"), ("event", "Event"),
           ("partner", "Partner"), ("outbound", "Outbound"), ("existing", "Existing client"), ("other", "Other")]
CURRENCIES = ["USD", "SAR", "AED", "JOD", "QAR", "KWD", "BHD", "OMR", "EGP", "EUR"]
LAWFUL_BASIS = [("enquiry", "Responding to their enquiry"), ("contract", "Contract or pre-contract steps"),
                ("legitimate", "Legitimate interest (B2B)"), ("consent", "Consent")]
PRIORITIES = [("low", "Low"), ("normal", "Normal"), ("high", "High")]
LOST_REASONS = [("no_budget", "No budget"), ("no_response", "No response"), ("timing", "Timing"), ("competitor", "Chose another provider"),
                ("not_fit", "Not a fit for our services"), ("internal", "Did it in-house"), ("other", "Other")]


class Organization(models.Model):
    name = models.CharField(max_length=200)
    domain = models.CharField(max_length=120, blank=True, db_index=True)       # email/web domain used for matching
    website = models.CharField(max_length=300, blank=True)
    industry = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=80, blank=True)
    size = models.CharField(max_length=40, blank=True)                         # e.g. "51-200"
    notes = models.TextField(blank=True)
    owner = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Contact(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(max_length=254, blank=True, db_index=True)
    phone = models.CharField(max_length=40, blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL, related_name="contacts")
    language = models.CharField(max_length=10, blank=True)                    # en / ar: language to reply in
    source = models.CharField(max_length=20, choices=SOURCES, default="other")
    lawful_basis = models.CharField(max_length=20, choices=LAWFUL_BASIS, default="enquiry")
    marketing_opt_in = models.BooleanField(default=False)                     # only with explicit consent
    linkedin = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)
    owner = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def initials(self):
        parts = [p for p in self.name.split() if p]
        return ("".join(p[0] for p in parts[:2]) or "?").upper()


class Deal(models.Model):
    title = models.CharField(max_length=200)
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL, related_name="deals")
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="deals")
    stage = models.CharField(max_length=20, choices=Stage.CHOICES, default=Stage.NEW, db_index=True)
    value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="USD")
    probability = models.PositiveSmallIntegerField(default=5)                 # %, follows the stage unless edited
    expected_close = models.DateField(null=True, blank=True)
    owner = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="crm_deals")
    source = models.CharField(max_length=20, choices=SOURCES, default="other")
    priority = models.CharField(max_length=10, choices=PRIORITIES, default="normal")
    lab = models.CharField(max_length=40, blank=True)                          # practice area key (cms/areas.py: websites, content...)
    services = models.JSONField(default=list, blank=True)                      # catalogue codes, e.g. ["W1", "W4"]
    lost_reason = models.CharField(max_length=20, choices=LOST_REASONS, blank=True)
    lost_note = models.CharField(max_length=300, blank=True)
    enquiry = models.ForeignKey("cms.FormSubmission", null=True, blank=True, on_delete=models.SET_NULL, related_name="deals")
    stage_changed_at = models.DateTimeField(default=timezone.now)
    first_response_at = models.DateTimeField(null=True, blank=True)            # first call/email/meeting logged
    closed_at = models.DateTimeField(null=True, blank=True)
    position = models.IntegerField(default=0)                                  # order inside a pipeline column
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.stage in Stage.OPEN

    @property
    def weighted(self):
        return (self.value or 0) * Decimal(self.probability) / 100

    @property
    def days_in_stage(self):
        return max(0, (timezone.now() - self.stage_changed_at).days)


class Activity(models.Model):
    NOTE, CALL, EMAIL, MEETING, TASK, STAGE, ENQUIRY, SYSTEM = (
        "note", "call", "email", "meeting", "task", "stage", "enquiry", "system")
    KINDS = [(NOTE, "Note"), (CALL, "Call"), (EMAIL, "Email"), (MEETING, "Meeting"), (TASK, "Task"),
             (STAGE, "Stage change"), (ENQUIRY, "Website enquiry"), (SYSTEM, "System")]
    RESPONSE_KINDS = {CALL, EMAIL, MEETING}

    kind = models.CharField(max_length=10, choices=KINDS, default=NOTE)
    deal = models.ForeignKey(Deal, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)                       # tasks
    assigned_to = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="crm_tasks")
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind}: {self.subject}"

    @property
    def overdue(self):
        return self.kind == self.TASK and not self.done and self.due_at and self.due_at < timezone.now()


class Subscriber(models.Model):
    """Newsletter sign-up with double opt-in: counted only after the person confirms from the email we send."""
    PENDING, CONFIRMED, UNSUBSCRIBED = "pending", "confirmed", "unsubscribed"
    STATUS = [(PENDING, "Waiting for confirmation"), (CONFIRMED, "Subscribed"), (UNSUBSCRIBED, "Unsubscribed")]

    email = models.EmailField(max_length=254, unique=True)
    language = models.CharField(max_length=10, default="en")
    status = models.CharField(max_length=14, choices=STATUS, default=PENDING, db_index=True)
    token = models.CharField(max_length=64, unique=True)
    page = models.CharField(max_length=300, blank=True)                        # where they signed up
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="subscriptions")
    created_at = models.DateTimeField(default=timezone.now)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} ({self.status})"


class Prospect(models.Model):
    """A researched target company, kept apart from the pipeline. Nobody has contacted it yet; when someone decides to,
    "Move to leads" turns it into an organisation, a company contact and a deal in New (crm.services.promote_prospect).
    Only company-level contacts the company publishes itself are stored here, each with the page it came from."""
    OPEN, HOLD, DO_NOT_CONTACT, MOVED = "open", "hold", "dnc", "moved"
    STATUS = [(OPEN, "Not contacted yet"), (HOLD, "On hold"), (DO_NOT_CONTACT, "Do not contact"), (MOVED, "Moved to leads")]
    PRIORITY = [("A", "A"), ("B", "B"), ("C", "C")]

    name = models.CharField(max_length=200)
    name_ar = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=80, blank=True, db_index=True)
    city = models.CharField(max_length=80, blank=True)
    sector = models.CharField(max_length=80, blank=True, db_index=True)
    sub_sector = models.CharField(max_length=150, blank=True)
    size_band = models.CharField(max_length=200, blank=True)
    ownership = models.CharField(max_length=150, blank=True)
    listed_on = models.CharField(max_length=80, blank=True)
    website = models.CharField(max_length=300, blank=True)
    domain = models.CharField(max_length=120, blank=True, db_index=True)
    email = models.CharField(max_length=254, blank=True)                      # generic company address, as published
    email_source = models.CharField(max_length=500, blank=True)
    email_verified = models.BooleanField(default=False)
    phone = models.CharField(max_length=80, blank=True)
    phone_source = models.CharField(max_length=500, blank=True)
    phone_verified = models.BooleanField(default=False)
    contact_page = models.CharField(max_length=500, blank=True)
    linkedin = models.CharField(max_length=300, blank=True)
    officer = models.CharField(max_length=200, blank=True)                    # "Role: Name", only if on the company's own site
    # extra contacts not checked by us: [{"id", "type": person|company, "role", "name", "email", "phone", "source",
    # "source_kind", "note", "added"}]; only business details seen published, never guessed or from people-search sites
    unverified = models.JSONField(default=list, blank=True)
    checked_on = models.DateField(null=True, blank=True)
    fit_score = models.PositiveSmallIntegerField(default=3)
    fit_reason = models.TextField(blank=True)
    fit_source = models.CharField(max_length=500, blank=True)
    services = models.JSONField(default=list, blank=True)                      # catalogue codes, e.g. ["W4", "C1"]
    priority = models.CharField(max_length=1, choices=PRIORITY, default="B", db_index=True)
    status = models.CharField(max_length=10, choices=STATUS, default=OPEN, db_index=True)
    notes = models.TextField(blank=True)
    owner = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    deal = models.ForeignKey(Deal, null=True, blank=True, on_delete=models.SET_NULL, related_name="prospects")
    moved_at = models.DateTimeField(null=True, blank=True)
    moved_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "-fit_score", "name"]

    def __str__(self):
        return self.name
