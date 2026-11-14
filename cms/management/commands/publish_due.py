from django.core.management.base import BaseCommand
from django.utils import timezone

from cms.models import Entry, PageTranslation, PublishLog
from cms.publish import publish_site


class Command(BaseCommand):
    help = "Publish the site only if a scheduled page or entry is due (run every few minutes by a systemd timer)."

    def handle(self, *args, **opts):
        now = timezone.now()
        due = PageTranslation.objects.filter(status=PageTranslation.SCHEDULED, publish_at__lte=now).exists()
        if not due:
            # entries whose publish time passed since the last successful build
            last = PublishLog.objects.filter(ok=True).order_by("-started_at").values_list("started_at", flat=True).first()
            entries = Entry.objects.filter(is_published=True, publish_at__lte=now)
            due = (entries.filter(publish_at__gt=last) if last else entries).exists()
        if not due:
            # something reached its hide-on date since the last successful build
            last = PublishLog.objects.filter(ok=True).order_by("-started_at").values_list("started_at", flat=True).first()
            ended = dict(unpublish_at__lte=now, **({"unpublish_at__gt": last} if last else {}))
            due = Entry.objects.filter(is_published=True, **ended).exists() or PageTranslation.objects.filter(**ended).exists()
        if due:
            log = publish_site()
            self.stdout.write(("OK " if log.ok else "FAILED ") + log.message)
        from cms import stats
        removed = stats.prune()
        if removed:
            self.stdout.write(f"stats: removed {removed} page views older than {stats.KEEP_DAYS} days")
        # Technting SEO: Google search daily, index status and Bing weekly, PageSpeed monthly; never stops the rest
        try:
            from cms import seo_pro
            for line in seo_pro.run_due():
                self.stdout.write("seo " + line)
        except Exception as exc:
            self.stdout.write(f"seo: skipped ({exc.__class__.__name__})")
        from cms.digest import send_all
        n = send_all()
        if n:
            self.stdout.write(f"weekly summary: {n} email(s) sent")
        from crm.newsletter import prune_pending
        dropped = prune_pending()
        if dropped:
            self.stdout.write(f"newsletter: removed {dropped} unconfirmed sign-ups older than 30 days")
        # Technting Forms: answers past their retention period, unfinished drafts
        from formbuilder.retention import prune as prune_forms
        done, drafts = prune_forms()
        if done or drafts:
            self.stdout.write(f"forms: removed {done} answers past retention and {drafts} old drafts")
        # the free licence: checked with licenses.technting.com every 12 hours (cms/licence.py); never stops the rest
        try:
            from cms import licence
            for line in licence.run_due():
                self.stdout.write(line)
        except Exception as exc:
            self.stdout.write(f"licence: check skipped ({exc.__class__.__name__})")
        # Technting Shield: threat lists, package / file / certificate checks, ended blocks (only when the plugin is on)
        from shield.jobs import run_due
        for line in run_due():
            self.stdout.write("shield: " + line)
        # plugins with periodic work (Technting Backup uploads, checks and alerts)
        from cms.plugins import do_action
        do_action("scheduled", log=self.stdout.write)
        # monthly check of the external sources our pages cite
        from cms import linkcheck
        if linkcheck.due():
            data = linkcheck.run()
            if data:
                bad = sum(1 for i in data["items"] if i["verdict"] in ("not_found", "error"))
                self.stdout.write(f"external links: {data['count']} checked, {bad} broken")
