"""Bring website enquiries received before the CRM existed into the CRM (idempotent).

    python manage.py crm_import_enquiries

Archived enquiries are imported as Lost (reason: other, note "archived in inbox"); others as New.
Enquiries already linked to a deal are skipped.
"""
from django.core.management.base import BaseCommand

from cms.models import FormSubmission
from crm.models import Activity, Deal, Stage
from crm.services import capture_enquiry, move_stage


class Command(BaseCommand):
    help = "Import existing website enquiries into the CRM."

    def handle(self, *args, **o):
        done = 0
        for sub in FormSubmission.objects.order_by("created_at"):
            if Deal.objects.filter(enquiry=sub).exists():
                continue
            deal = capture_enquiry(sub)
            if sub.note:
                Activity.objects.create(kind=Activity.NOTE, deal=deal, contact=deal.contact, organization=deal.organization,
                                        subject="Inbox note", body=sub.note, created_at=sub.created_at)
            if sub.status == FormSubmission.ARCHIVED:
                move_stage(deal, Stage.LOST, None, "other", "archived in inbox")
                deal.activities.filter(kind=Activity.TASK).update(done=True)
            done += 1
        self.stdout.write(self.style.SUCCESS(f"{done} enquiries imported"))
