from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = ("Technting Shield from the server's command line. status | run [feeds|osv|integrity|ct|prune] | unblock <address> | "
            "learning (stop blocking, e.g. if the team is locked out) | manifest (write code-manifest.json from Git) | accept-files")

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["status", "run", "unblock", "learning", "manifest", "accept-files"])
        parser.add_argument("arg", nargs="?", default="")

    def handle(self, action, arg, **opts):
        from shield import conf, events, feeds, integrity, jobs
        from shield.models import Block
        if action == "status":
            self.stdout.write(f"enabled: {conf.enabled()}  protect: {conf.protect()}")
            for f in feeds.status():
                self.stdout.write(f"  {f['label']}: {f['count']} entries, updated {f['updated'] or 'never'}{' (out of date)' if f['stale'] else ''}")
            active = [b for b in Block.objects.all() if b.active()]
            self.stdout.write(f"blocked now: {len(active)}")
        elif action == "run":
            names = [arg] if arg else list(jobs.HOURS)
            for name in names:
                if name not in jobs.HOURS:
                    raise CommandError(f"unknown job {name}")
                for line in (feeds.refresh_due(force=True) if name == "feeds" else jobs.run_job(name)):
                    self.stdout.write(line)
        elif action == "unblock":
            rows = list(Block.objects.filter(network=arg))
            for b in rows:
                err = events.unblock(b)
                if err:
                    self.stdout.write(f"Cloudflare did not confirm ({err}); the next run of publish_due retries")
            self.stdout.write(f"removed {len(rows)} block(s) for {arg}")
        elif action == "learning":
            from cms.models import Setting
            s, _ = Setting.objects.get_or_create(key=f"plugin:{conf.PLUGIN}", defaults={"value": {}})
            s.value = dict(s.value or {}, protect=False)
            s.save()
            conf.reset()
            from shield import cloudflare
            for line in cloudflare.sync():  # takes our rules back off Cloudflare's edge
                self.stdout.write(line)
            self.stdout.write("Technting Shield is in learning mode: it logs but blocks nothing.")
        elif action == "manifest":
            commit, n = integrity.write_manifest(arg or "HEAD")
            self.stdout.write(f"code-manifest.json: {n} files from {commit[:10]}")
        elif action == "accept-files":
            self.stdout.write(f"reference saved: {integrity.accept()} files")
