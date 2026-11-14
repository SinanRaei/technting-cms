"""Create the blog index page (EN + AR) as a draft if it does not exist. Never overwrites edits."""
import uuid

from django.core.management.base import BaseCommand

from cms.models import Language, Page, PageTranslation

TEXT = {
    "en": ("Insights", "Insights", "Notes, news and practical articles from our team.",
           "Our first articles are on the way."),
    "ar": ("المقالات", "المقالات", "ملاحظات وأخبار ومقالات عملية من فريقنا.",
           "مقالاتنا الأولى قيد الإعداد."),
}


class Command(BaseCommand):
    help = "Create the blog index page as a draft (key 'blog', address /blog/)."

    def handle(self, *args, **opts):
        page, created = Page.objects.get_or_create(key="blog", defaults={"template": "default", "order": Page.objects.count()})
        for lang in Language.objects.all():
            if PageTranslation.objects.filter(page=page, language=lang).exists():
                continue
            title, eyebrow, lead, empty = TEXT.get(lang.code, TEXT["en"])
            PageTranslation.objects.create(page=page, language=lang, title=title, slug="blog", status=PageTranslation.DRAFT,
                                           seo_title=title, seo_description=lead, blocks=[
                {"id": uuid.uuid4().hex[:8], "type": "page_hero", "data": {"eyebrow": "Technting", "title": eyebrow, "lead": lead, "text": ""}},
                {"id": uuid.uuid4().hex[:8], "type": "posts_list", "data": {"limit": 0, "empty_text": empty}},
            ])
        self.stdout.write(self.style.SUCCESS(f"Blog page {'created' if created else 'present'} (draft until you publish it)."))
