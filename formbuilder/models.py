"""Technting Forms: multi-step forms built in the dashboard (see formbuilder/sample.py).

A Form has Steps (pages), each Step has Fields (questions), and choice fields have Options. Every piece of text is
bilingual: {"en": "...", "ar": "..."}. Options carry named numbers ("values"), e.g. {"score": 2, "extent": 1}, which
the form's calculations add up. Visibility rules and calculations are short expressions (formbuilder/expr.py), e.g.
answer("G1") == "no_ai" or round(G_raw * 100 / 18).

A Submission is one person's answers. It starts as a draft (saved server-side, resumed by its secret token) and
becomes complete when submitted: answers are checked again on the server, calculations run, results are rendered,
and only then are results shown (spec: results only after the submission is recorded).
A RecipientLink is a personal, expiring link for one person at a client (for example Parts A-D to different
people); it needs no sign-in, and its token is the secret.
"""
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

USER = settings.AUTH_USER_MODEL


def new_token():
    return secrets.token_urlsafe(32)


class Form(models.Model):
    DRAFT, LIVE, CLOSED = "draft", "live", "closed"
    STATUS = [(DRAFT, "Draft"), (LIVE, "Live"), (CLOSED, "Closed")]

    slug = models.SlugField(max_length=80, unique=True)
    title = models.JSONField(default=dict, blank=True)           # {"en": "", "ar": ""}
    intro = models.JSONField(default=dict, blank=True)           # shown before the first step; short markdown
    status = models.CharField(max_length=10, choices=STATUS, default=DRAFT, db_index=True)
    languages = models.JSONField(default=list, blank=True)       # ["en", "ar"]
    # options: public, results ("show" | "thank_you"), thank_you, booking_url, notify_email, respondent_email,
    # email {subject, intro, outro}, privacy_email, crm {mode, service, lab, task, task_hours, title}, owner {mode, users},
    # map {name, email, phone, company, job_title, country, size, industry, consent}, tags [{name, if}],
    # retention_months, draft_days, turnstile
    settings = models.JSONField(default=dict, blank=True)
    calcs = models.JSONField(default=list, blank=True)           # [{"name", "expr", "internal": bool, "label"}] in order
    results = models.JSONField(default=dict, blank=True)         # {"labels": {key: {en, ar}}, "blocks": [...]}
    version = models.PositiveIntegerField(default=1)             # +1 on every save, kept on submissions
    created_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self):
        return self.title.get("en") or self.slug

    def opt(self, key, default=None):
        return (self.settings or {}).get(key, default)

    def name(self, lang="en"):
        return (self.title or {}).get(lang) or (self.title or {}).get("en") or self.slug


class Step(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="steps")
    key = models.SlugField(max_length=40)                        # stable id, e.g. "profile", "govern", "part_a"
    order = models.IntegerField(default=0)
    title = models.JSONField(default=dict, blank=True)
    intro = models.JSONField(default=dict, blank=True)
    visible_if = models.TextField(blank=True)                    # expression; empty = always shown

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("form", "key")]

    def __str__(self):
        return f"{self.form.slug}/{self.key}"


class Field(models.Model):
    TEXT, EMAIL, PHONE, TEXTAREA, SELECT, RADIO, CHECKBOX, CONSENT, SCALE, HIDDEN, INFO = (
        "text", "email", "phone", "textarea", "select", "radio", "checkbox", "consent", "scale", "hidden", "info")
    TYPES = [(TEXT, "Short text"), (EMAIL, "Email"), (PHONE, "Phone"), (TEXTAREA, "Long text"), (SELECT, "Dropdown"),
             (RADIO, "Single choice (scored options)"), (CHECKBOX, "Several choices"), (CONSENT, "Agreement tick box"),
             (SCALE, "Scale (number)"), (HIDDEN, "Hidden value"), (INFO, "Text only (no answer)")]
    CHOICE_TYPES = {SELECT, RADIO, CHECKBOX}

    step = models.ForeignKey(Step, on_delete=models.CASCADE, related_name="fields")
    key = models.CharField(max_length=40)                        # stable id used in expressions, e.g. "G1", "P7"
    order = models.IntegerField(default=0)
    type = models.CharField(max_length=10, choices=TYPES, default=RADIO)
    label = models.JSONField(default=dict, blank=True)
    help = models.JSONField(default=dict, blank=True)            # shown under the question
    why = models.JSONField(default=dict, blank=True)             # "why it matters": shown only in results, never in the form
    required = models.BooleanField(default=True)
    visible_if = models.TextField(blank=True)
    # conditional text under the question: [{"if": expr, "text": {en, ar}}], e.g. sector examples keyed on P6
    texts = models.JSONField(default=list, blank=True)
    # min / max / step / min_label / max_label (scale), max_length, group (e.g. pillar "G"), placeholder {en, ar}
    options_extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.key

    @property
    def form(self):
        return self.step.form

    @property
    def has_options(self):
        return self.type in self.CHOICE_TYPES


class Option(models.Model):
    field = models.ForeignKey(Field, on_delete=models.CASCADE, related_name="options")
    key = models.CharField(max_length=40)                        # stable id, e.g. "o0", "no_ai", "dk"
    order = models.IntegerField(default=0)
    label = models.JSONField(default=dict, blank=True)
    values = models.JSONField(default=dict, blank=True)          # {"score": 1, "extent": 2}
    is_unknown = models.BooleanField(default=False)              # "I don't know / not sure": scores 0, counted as unknown
    visible_if = models.TextField(blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.key


class RecipientLink(models.Model):
    """A personal link to one form for one person at a client; no sign-in, the token is the secret."""
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="links")
    token = models.CharField(max_length=64, unique=True, default=new_token)
    label = models.CharField(max_length=150, blank=True)         # e.g. "Part A: CEO"
    steps = models.JSONField(default=list, blank=True)           # step keys this person answers; empty = all
    language = models.CharField(max_length=5, default="en")
    contact = models.ForeignKey("crm.Contact", null=True, blank=True, on_delete=models.SET_NULL, related_name="form_links")
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="form_links")
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    first_opened_at = models.DateTimeField(null=True, blank=True)
    last_opened_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_to = models.CharField(max_length=254, blank=True)
    created_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.label or f"Link {self.pk}"

    @property
    def is_usable(self):
        return (self.revoked_at is None and (self.expires_at is None or self.expires_at > timezone.now())
                and self.form.status != Form.CLOSED)

    @property
    def state(self):
        sub = self.submissions.order_by("-updated_at").first()
        if sub and sub.status == Submission.COMPLETE:
            return "complete"
        if self.revoked_at:
            return "revoked"
        if self.expires_at and self.expires_at <= timezone.now():
            return "expired"
        if sub:
            return "in_progress"
        return "opened" if self.first_opened_at else ("sent" if self.sent_at else "new")

    def url(self):
        return f"{settings.TECHNTING_CMS_ADMIN_URL.rstrip('/')}/f/{self.token}/"


class Submission(models.Model):
    DRAFT, COMPLETE = "draft", "complete"
    STATUS = [(DRAFT, "In progress"), (COMPLETE, "Complete")]

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="submissions")
    form_version = models.PositiveIntegerField(default=1)
    token = models.CharField(max_length=64, unique=True, default=new_token)   # resume + results; the browser keeps it
    status = models.CharField(max_length=10, choices=STATUS, default=DRAFT, db_index=True)
    language = models.CharField(max_length=5, default="en")
    answers = models.JSONField(default=dict, blank=True)
    step = models.CharField(max_length=40, blank=True)           # last step reached (drafts)
    calcs = models.JSONField(default=dict, blank=True)           # every calculated value, internal ones included
    results = models.JSONField(default=list, blank=True)         # rendered result blocks as the respondent saw them
    tags = models.JSONField(default=list, blank=True)
    name = models.CharField(max_length=150, blank=True)
    email = models.CharField(max_length=254, blank=True)
    company = models.CharField(max_length=200, blank=True)
    consent_text = models.TextField(blank=True)                  # the exact wording they agreed to
    consent_at = models.DateTimeField(null=True, blank=True)
    page = models.CharField(max_length=300, blank=True)
    link = models.ForeignKey(RecipientLink, null=True, blank=True, on_delete=models.SET_NULL, related_name="submissions")
    contact = models.ForeignKey("crm.Contact", null=True, blank=True, on_delete=models.SET_NULL, related_name="form_submissions")
    deal = models.ForeignKey("crm.Deal", null=True, blank=True, on_delete=models.SET_NULL, related_name="form_submissions")
    owner = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notify_error = models.CharField(max_length=200, blank=True)  # team email
    results_error = models.CharField(max_length=200, blank=True) # respondent email
    results_emailed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.form.slug} #{self.pk}"


class FormEvent(models.Model):
    """Counts only (no visitor id, no cookie): how many people saw each step, started and finished, per day."""
    VIEW, START, STEP, COMPLETE = "view", "start", "step", "complete"
    KINDS = [(VIEW, "Opened"), (START, "Started"), (STEP, "Reached step"), (COMPLETE, "Completed")]

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="events")
    day = models.DateField(default=timezone.localdate)
    lang = models.CharField(max_length=5, blank=True)
    kind = models.CharField(max_length=10, choices=KINDS)
    step = models.PositiveSmallIntegerField(default=0)           # 1-based step number for "step"
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("form", "day", "lang", "kind", "step")]
