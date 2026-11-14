"""Import blog posts from JSON files (one article per file, all languages inside).

    python manage.py import_posts DIR [--publish] [--author KEY]

Each DIR/<key>.json holds {"key", "area", "services", "date", "publish_at" (optional ISO time, local), "<lang code>": {...}};
an image DIR/<key>.png (or .jpg / .webp) becomes the cover. Fields are cleaned with the theme's own field specs,
so rich text goes through the same sanitiser as the editor. Existing posts with the same key are updated (a
revision is written), their cover is replaced only when a new image is given. Without --publish, posts are
imported as drafts.
"""
import json
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cms.fields import clean_fields
from cms.media import save_upload
from cms.models import Entry, EntryTranslation, Language, Media
from cms.theme import load_theme

COLLECTION = "post"


class Command(BaseCommand):
    help = "Import blog posts from a folder of JSON files (and optional cover images)."

    def add_arguments(self, parser):
        parser.add_argument("folder")
        parser.add_argument("--publish", action="store_true", help="make the posts visible and publish the site")
        parser.add_argument("--author", default="", help="team member key to set as author (default: none, shown as the site name)")

    def handle(self, *args, **o):
        folder = Path(o["folder"])
        files = sorted(p for p in folder.glob("*.json") if not p.name.startswith("_"))
        if not files:
            raise CommandError(f"No .json files in {folder}")
        theme = load_theme()
        if COLLECTION not in theme.collections:
            raise CommandError("The active theme has no 'post' collection.")
        shared_fields = theme.collection_fields(COLLECTION, translatable=False)
        tr_fields = theme.collection_fields(COLLECTION, translatable=True)
        langs = {l.code: l for l in Language.objects.all()}
        from cms.views import write_revision
        done = []
        for path in files:
            art = json.loads(path.read_text(encoding="utf-8"))
            key = art.get("key") or path.stem
            if not all(c.isalnum() or c in "-_" for c in key):
                raise CommandError(f"{path.name}: key '{key}' must use letters, numbers and dashes")
            with transaction.atomic():
                entry, created = Entry.objects.get_or_create(collection=COLLECTION, key=key[:80], defaults={
                    "order": Entry.objects.filter(collection=COLLECTION).count(), "is_published": False})
                cover_id = entry.data.get("cover")
                for ext in (".png", ".jpg", ".jpeg", ".webp"):
                    img = folder / f"{key}{ext}"
                    if img.exists():
                        up = SimpleUploadedFile(img.name, img.read_bytes())
                        m = save_upload(up)
                        alt = {c: (art.get(c) or {}).get("cover_alt") or (art.get(c) or {}).get("title", "") for c in langs}
                        m.title, m.alt = (art.get("en") or {}).get("title", key)[:200], alt
                        m.save()
                        old = Media.objects.filter(pk=cover_id).first() if str(cover_id or "").isdigit() else None
                        cover_id = m.pk
                        if old and old.pk != m.pk:
                            from cms.media import delete_media
                            delete_media(old)
                        break
                shared = {"date": art.get("date"), "updated": art.get("updated", ""), "cover": cover_id,
                          "author": o["author"] or entry.data.get("author", ""),
                          "area": art.get("area", art.get("lab", "")), "lab": art.get("lab", ""),
                          "services": art.get("services", [])}
                entry.data = clean_fields(shared_fields, shared)
                if art.get("publish_at"):
                    from django.utils import timezone
                    when = timezone.datetime.fromisoformat(art["publish_at"])
                    entry.publish_at = when if timezone.is_aware(when) else timezone.make_aware(when)
                    entry.data["date"] = timezone.localtime(entry.publish_at).date().isoformat()
                if o["publish"]:
                    entry.is_published = True
                entry.save()
                for code, lang in langs.items():
                    if isinstance(art.get(code), dict):
                        EntryTranslation.objects.update_or_create(entry=entry, language=lang,
                                                                  defaults={"data": clean_fields(tr_fields, art[code])})
                snap = {"data": entry.data, "translations": {t.language.code: t.data for t in entry.translations.select_related("language")}}
                write_revision("entry", entry.pk, "en", snap, type("System", (), {"is_authenticated": False})(), "imported")
            done.append(key)
            self.stdout.write(f"{'created' if created else 'updated'} {key}")
        if o["publish"]:
            from cms.publish import publish_site
            log = publish_site(None)
            self.stdout.write(log.message)
        self.stdout.write(self.style.SUCCESS(f"{len(done)} posts imported"))
