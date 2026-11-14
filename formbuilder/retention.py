"""Retention (settings per form): complete answers are deleted after retention_months (default 24), unfinished drafts
after draft_days (default 30), and step counts after 400 days like the site stats. Runs with publish_due every few
minutes; each run only deletes what is past its date. CRM records made from an answer stay (they follow the CRM's own
rules); the answers, scores and results themselves go."""
from datetime import timedelta

from django.utils import timezone

from .models import Form, FormEvent, Submission

DEFAULT_MONTHS, DEFAULT_DRAFT_DAYS = 24, 30


def prune(now=None):
    now = now or timezone.now()
    done = drafts = 0
    for form in Form.objects.all():
        months = int(form.opt("retention_months") or DEFAULT_MONTHS)
        days = int(form.opt("draft_days") or DEFAULT_DRAFT_DAYS)
        done += Submission.objects.filter(form=form, status=Submission.COMPLETE,
                                          completed_at__lt=now - timedelta(days=round(months * 30.44))).delete()[0]
        drafts += Submission.objects.filter(form=form, status=Submission.DRAFT, updated_at__lt=now - timedelta(days=days)).delete()[0]
    FormEvent.objects.filter(day__lt=(now - timedelta(days=400)).date()).delete()
    return done, drafts
