"""Technting CMS data model.

Pages hold layout (an ordered list of blocks per language); Entries hold structured,
reusable records (labs, services, founders...) whose fields are defined by the theme.
Every save writes a Revision so any change can be rolled back.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Language(models.Model):
    code = models.CharField(max_length=10, unique=True)            # "en", "ar"
    name = models.CharField(max_length=60)                         # "English"
    native_name = models.CharField(max_length=60)                  # "العربية"
    direction = models.CharField(max_length=3, choices=[("ltr", "Left to right"), ("rtl", "Right to left")], default="ltr")
    url_prefix = models.CharField(max_length=20, blank=True)       # "" for the default language, "ar" otherwise
    locale = models.CharField(max_length=20, default="en_GB")      # og:locale
    is_default = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class Media(models.Model):
    file = models.FileField(upload_to="%Y/%m/")
    title = models.CharField(max_length=200, blank=True)
    alt = models.JSONField(default=dict, blank=True)               # {"en": "...", "ar": "..."}
    mime = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    variants = models.JSONField(default=dict, blank=True)          # {"800w": "2026/10/x-800.webp", ...}
    uploaded_at = models.DateTimeField(default=timezone.now)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title or self.file.name

    @property
    def is_image(self):
        return self.mime.startswith("image/")


class Page(models.Model):
    """A page exists once; its content lives in one PageTranslation per language."""
    key = models.SlugField(max_length=80, unique=True, null=True, blank=True,
                           help_text="Stable internal name used by themes and importers (e.g. home, labs).")
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.PROTECT)
    template = models.CharField(max_length=60, default="default")
    data = models.JSONField(default=dict, blank=True)              # template fields shared by all languages
    order = models.IntegerField(default=0)
    in_sitemap = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        t = self.translations.order_by("language__order").first()
        return t.title if t else (self.key or f"Page {self.pk}")

    def translation(self, lang_code):
        return self.translations.filter(language__code=lang_code).first()


class PageTranslation(models.Model):
    DRAFT, PUBLISHED, SCHEDULED = "draft", "published", "scheduled"
    STATUS = [(DRAFT, "Draft"), (PUBLISHED, "Published"), (SCHEDULED, "Scheduled")]

    page = models.ForeignKey(Page, related_name="translations", on_delete=models.CASCADE)
    language = models.ForeignKey(Language, on_delete=models.PROTECT)
    title = models.CharField(max_length=250)
    slug = models.SlugField(max_length=120, blank=True, allow_unicode=True, help_text="Empty for the home page.")
    path = models.CharField(max_length=500, editable=False)       # "/labs/websites/" (without language prefix)
    blocks = models.JSONField(default=list, blank=True)           # [{"id": "...", "type": "hero", "data": {...}}]
    seo_title = models.CharField(max_length=250, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    og_image = models.ForeignKey(Media, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    noindex = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUS, default=DRAFT)
    publish_at = models.DateTimeField(null=True, blank=True)
    unpublish_at = models.DateTimeField(null=True, blank=True)      # hidden from the site from this moment
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        unique_together = [("page", "language"), ("language", "path")]
        ordering = ["page__order", "page_id", "language__order"]

    def __str__(self):
        return f"{self.title} ({self.language.code})"

    def compute_path(self):
        parts = []
        node = self.page
        own = self.slug
        while node is not None:
            if node.pk == self.page.pk:
                slug = own
            else:
                parent_t = node.translation(self.language.code)
                slug = parent_t.slug if parent_t else (node.key or "")
            if slug:
                parts.append(slug)
            node = node.parent
        return "/" + "/".join(reversed(parts)) + ("/" if parts else "")

    @property
    def url(self):
        prefix = f"/{self.language.url_prefix}" if self.language.url_prefix else ""
        return prefix + self.path

    @property
    def is_live(self):
        now = timezone.now()
        if self.unpublish_at and self.unpublish_at <= now:
            return False
        if self.status == self.PUBLISHED:
            return True
        return self.status == self.SCHEDULED and self.publish_at and self.publish_at <= now

    def save(self, *args, **kwargs):
        self.path = self.compute_path()
        super().save(*args, **kwargs)


class Entry(models.Model):
    """A record in a theme-defined collection (lab, service, founder...)."""
    collection = models.CharField(max_length=60, db_index=True)
    key = models.CharField(max_length=80)                          # "W1", "websites"
    data = models.JSONField(default=dict, blank=True)              # fields shared by all languages
    order = models.IntegerField(default=0)
    is_published = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    review_requested_at = models.DateTimeField(null=True, blank=True)   # an author submitted this draft for review
    publish_at = models.DateTimeField(null=True, blank=True)            # visible entries appear on the site from this moment
    unpublish_at = models.DateTimeField(null=True, blank=True)          # ...and disappear from this moment

    class Meta:
        unique_together = [("collection", "key")]
        ordering = ["collection", "order", "id"]

    def __str__(self):
        return f"{self.collection}:{self.key}"


class EntryTranslation(models.Model):
    entry = models.ForeignKey(Entry, related_name="translations", on_delete=models.CASCADE)
    language = models.ForeignKey(Language, on_delete=models.PROTECT)
    data = models.JSONField(default=dict, blank=True)              # translatable fields

    class Meta:
        unique_together = [("entry", "language")]


class Revision(models.Model):
    """Snapshot of a page translation or entry, written on every save."""
    object_type = models.CharField(max_length=20)                  # "page" | "entry"
    object_id = models.PositiveIntegerField()
    language = models.CharField(max_length=10, blank=True)
    snapshot = models.JSONField()
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["object_type", "object_id"])]


class Menu(models.Model):
    key = models.SlugField(max_length=60)                          # "header", "footer"
    language = models.ForeignKey(Language, on_delete=models.CASCADE)
    items = models.JSONField(default=list, blank=True)             # [{"label": "", "url": "", "page": id, "children": []}]

    class Meta:
        unique_together = [("key", "language")]


class Setting(models.Model):
    key = models.CharField(max_length=80, unique=True)
    value = models.JSONField(default=dict, blank=True)             # per-language values as {"en": ..., "ar": ...} when relevant

    def __str__(self):
        return self.key


class Redirect(models.Model):
    source = models.CharField(max_length=500, unique=True, help_text="Old path, e.g. /services/old/")
    target = models.CharField(max_length=500)
    permanent = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["source"]


class PublishLog(models.Model):
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    ok = models.BooleanField(default=False)
    pages = models.PositiveIntegerField(default=0)
    message = models.TextField(blank=True)
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-started_at"]


class FormSubmission(models.Model):
    NEW, READ, ARCHIVED = "new", "read", "archived"
    STATUS = [(NEW, "New"), (READ, "Read"), (ARCHIVED, "Archived")]
    SOURCES = [("service", "Service pages"), ("usecase", "Use case pages"), ("article", "Articles"), ("page", "Other pages"),
               ("dialog", "Header form")]

    form = models.CharField(max_length=40, default="contact")
    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=254)
    organisation = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    interest = models.CharField(max_length=40, blank=True)
    message = models.TextField(max_length=4000)
    language = models.CharField(max_length=10, blank=True)
    page = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default=NEW)
    note = models.TextField(blank=True)
    email_sent = models.BooleanField(default=False)
    email_error = models.CharField(max_length=200, blank=True)            # why the email copy failed (shown in the inbox)
    source = models.CharField(max_length=20, blank=True, choices=SOURCES)                 # where the form was: dialog, service, usecase, article, page
    service = models.CharField(max_length=20, blank=True)                  # catalogue code chosen or implied by the page, e.g. W1
    topic = models.CharField(max_length=200, blank=True)                   # title of the page or article the person was reading
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}>"


class UserSecurity(models.Model):
    """Two-step verification (TOTP) for a dashboard user."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="security")
    totp_secret = models.CharField(max_length=64, blank=True)
    enabled = models.BooleanField(default=False)
    last_step = models.BigIntegerField(default=0)            # last accepted time step, blocks code replay
    recovery_codes = models.JSONField(default=list, blank=True)  # salted hashes of unused one-time codes
    enabled_at = models.DateTimeField(null=True, blank=True)


class AuditEvent(models.Model):
    """Who did what in the dashboard (sign-ins, publishing, deletions, settings). Kept for a year."""
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    username = models.CharField(max_length=150, blank=True)   # kept even if the user is deleted, or for failed sign-ins
    action = models.CharField(max_length=40, db_index=True)
    target = models.CharField(max_length=300, blank=True)
    ip = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.username} {self.action} {self.target}"


class Hit(models.Model):
    """One page view on the public site, without cookies or IP addresses (see cms/stats.py)."""
    ts = models.DateTimeField(default=timezone.now, db_index=True)
    path = models.CharField(max_length=300)
    lang = models.CharField(max_length=8, blank=True)
    source = models.CharField(max_length=80, blank=True)       # Google, LinkedIn, ChatGPT, a domain, or a utm_source
    channel = models.CharField(max_length=12, blank=True)      # direct, search, ai, social, email, referral, campaign
    ref_host = models.CharField(max_length=120, blank=True)
    campaign = models.CharField(max_length=80, blank=True)     # utm_campaign
    medium = models.CharField(max_length=60, blank=True)       # utm_medium
    content = models.CharField(max_length=80, blank=True)      # utm_content (e.g. en | ar, or a post id)
    country = models.CharField(max_length=2, blank=True)
    device = models.CharField(max_length=8, blank=True)
    visitor = models.CharField(max_length=16)                  # daily-salted hash; cannot link days or recover the IP
    status = models.PositiveSmallIntegerField(default=200)

    class Meta:
        indexes = [models.Index(fields=["status", "ts"])]
