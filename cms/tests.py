"""Block display settings: a hidden block stays in the editor but never reaches the site; "devices" limits the screen
sizes a block shows on. Run: manage.py test cms"""
from django.test import TestCase, override_settings

from cms.fields import clean_blocks
from cms.models import Language, Page, PageTranslation
from cms.render import RenderContext
from cms.theme import load_theme


@override_settings(TECHNTING_CMS_THEME="technting")
class BlockVisibilityTests(TestCase):
    def setUp(self):
        self.theme = load_theme()
        self.en = Language.objects.create(code="en", name="English", native_name="English", is_default=True)

    def test_clean_keeps_only_valid_settings(self):
        b = clean_blocks(self.theme, [
            {"id": "a", "type": "page_hero", "data": {}, "hidden": True, "devices": ["desktop", "phone", "bogus"]},
            {"id": "b", "type": "page_hero", "data": {}, "hidden": "yes", "devices": ["phone", "tablet", "desktop"]},
            {"id": "c", "type": "page_hero", "data": {}, "devices": []},
            {"id": "d", "type": "page_hero", "data": {}, "devices": "phone"},
        ])
        self.assertIs(b[0]["hidden"], True)
        self.assertEqual(b[0]["devices"], ["phone", "desktop"])  # unknown dropped, fixed order
        self.assertNotIn("hidden", b[1])                         # only a real true hides
        self.assertNotIn("devices", b[1])                        # all three = default, not stored
        self.assertNotIn("devices", b[2])
        self.assertNotIn("devices", b[3])

    def page(self, blocks):
        p = Page.objects.create(key="t", template="default")
        return PageTranslation.objects.create(page=p, language=self.en, title="T", slug="t", status=PageTranslation.PUBLISHED,
                                              blocks=clean_blocks(self.theme, blocks))

    def test_hidden_block_is_not_rendered(self):
        t = self.page([{"id": "h1", "type": "rich_text", "data": {"body": "<p>Visible title</p>"}},
                       {"id": "h2", "type": "rich_text", "data": {"body": "<p>Secret draft text</p>"}, "hidden": True}])
        for preview in (False, True):  # the preview shows what visitors will see
            html = RenderContext(preview=preview).render(t)
            self.assertIn("Visible title", html)
            self.assertNotIn("Secret draft text", html)

    def test_devices_wrap_block_with_hide_classes(self):
        t = self.page([{"id": "h1", "type": "rich_text", "data": {"body": "<p>Phone text</p>"}, "devices": ["phone"]},
                       {"id": "h2", "type": "rich_text", "data": {"body": "<p>Everywhere text</p>"}}])
        html = RenderContext().render(t)
        self.assertRegex(html, r'<div class="vis vis-hide-tablet vis-hide-desktop">.*Phone text')
        self.assertEqual(html.count('class="vis '), 1)


@override_settings(TECHNTING_CMS_THEME="technting")
class StarterThemeTests(TestCase):
    """The starter theme: every block renders, the demo content builds an EN and an AR home page, seed_demo is idempotent."""

    def test_seed_demo_builds_bilingual_home(self):
        import io
        from django.core.management import call_command
        from cms.models import Entry
        call_command("seed_demo", stdout=io.StringIO())
        counts = (Page.objects.count(), PageTranslation.objects.count(), Entry.objects.count())
        call_command("seed_demo", stdout=io.StringIO())
        self.assertEqual(counts, (Page.objects.count(), PageTranslation.objects.count(), Entry.objects.count()))
        ctx = RenderContext()
        homes = {t.language.code: ctx.render(t) for t in ctx.translations if t.page.key == "home"}
        self.assertIn('dir="rtl"', homes["ar"])
        for html in homes.values():
            for css in ("hero hero-dark", "features", "class=\"steps\"", "class=\"faq\"", "class=\"plans\"", "section cta"):
                self.assertIn(css, html)
            self.assertIn('"@type": "FAQPage"', html)
        for coll, e_, lang, url in ctx.entry_routes:  # service and post pages
            self.assertIn("<h1", ctx.render_entry(coll, e_, lang, url))

    def test_every_block_renders_empty(self):
        theme = load_theme()
        t = PageTranslation.objects.create(page=Page.objects.create(key="all", template="default"), language=self.en_lang(),
                                           title="All", slug="all", status=PageTranslation.PUBLISHED,
                                           blocks=clean_blocks(theme, [{"id": k, "type": k, "data": {}} for k in theme.blocks]))
        RenderContext().render(t)  # no block may fail on empty data

    def en_lang(self):
        return Language.objects.create(code="en", name="English", native_name="English", is_default=True)
