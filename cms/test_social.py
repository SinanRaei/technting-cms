"""Social profiles, phone/WhatsApp, /links/ page and UTM capture. Run: manage.py test cms"""
import json
import re
import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from cms import social, stats
from cms.models import Hit, Language, Page, PageTranslation, Setting
from cms.render import RenderContext

LINKEDIN = "https://www.linkedin.com/company/example/"
X_URL = "https://x.com/example"
YT_URL = "https://www.youtube.com/@example"
GH_URL = "https://github.com/example"


def org_ld(html):
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        data = json.loads(block.replace("<\\/", "</"))
        if data.get("@type") == "Organization":
            return data
    return None


@override_settings(TECHNTING_CMS_THEME="technting", TECHNTING_CMS_SITE_URL="https://example.com")
class SocialSiteTests(TestCase):
    def setUp(self):
        self.en = Language.objects.create(code="en", name="English", native_name="English", is_default=True)
        self.ar = Language.objects.create(code="ar", name="Arabic", native_name="العربية", direction="rtl", url_prefix="ar")
        # the migration prefills these; the test database starts from migrations, so set them explicitly
        Setting.objects.update_or_create(key="contact_phone", defaults={"value": "+1 555 010 0199"})
        Setting.objects.update_or_create(key="whatsapp", defaults={"value": "+1 555 010 0199"})
        Setting.objects.update_or_create(key="contact_email", defaults={"value": "leads@example.com"})
        self.set_rows([
            {"platform": "linkedin", "url": LINKEDIN, "enabled": True, "footer": True},
            {"platform": "x", "url": X_URL, "enabled": True, "footer": True},
            {"platform": "youtube", "url": YT_URL, "enabled": False, "footer": True},     # off: nowhere
            {"platform": "github", "url": GH_URL, "enabled": True, "footer": False},      # on, not in footer
            {"platform": "instagram", "url": "javascript:alert(1)", "enabled": True},     # invalid: ignored
        ])
        self.home = Page.objects.create(key="home", template="home")
        self.home_en = self.tr(self.home, self.en, "Home", "")
        self.home_ar = self.tr(self.home, self.ar, "الرئيسية", "")
        contact = Page.objects.create(key="contact", template="default")
        blocks = [{"id": "e1", "type": "enquiry", "data": {}}]
        self.contact_en = self.tr(contact, self.en, "Contact us", "contact", blocks)
        self.contact_ar = self.tr(contact, self.ar, "تواصلوا معنا", "contact", blocks)

    def tr(self, page, lang, title, slug, blocks=None):
        return PageTranslation.objects.create(page=page, language=lang, title=title, slug=slug, blocks=blocks or [],
                                              status=PageTranslation.PUBLISHED)

    def set_rows(self, rows):
        Setting.objects.update_or_create(key="social_profiles", defaults={"value": {"rows": rows}})

    def render(self, t):
        return RenderContext().render(t)

    def footer(self, html):
        return html[html.index('<footer class="site-footer">'):html.index("</footer>")]

    def test_footer_shows_only_enabled_footer_profiles_same_on_en_and_ar(self):
        for t in (self.home_en, self.home_ar):
            f = self.footer(self.render(t))
            self.assertIn(f'href="{LINKEDIN}"', f)
            self.assertIn(f'href="{X_URL}"', f)
            self.assertNotIn(YT_URL, f)       # off
            self.assertNotIn(GH_URL, f)       # on, but not in the footer
            self.assertNotIn("javascript:", f)
            self.assertIn('rel="noopener me"', f)
            self.assertIn('aria-label="LinkedIn"', f)
            self.assertIn("<svg", f)
            self.assertNotRegex(f, r'<(img|script)[^>]+src="https?://')  # icons are inline, no external hosts

    def test_footer_without_profiles_has_no_icon_list(self):
        self.set_rows([])
        f = self.footer(self.render(self.home_en))
        self.assertNotIn("footer-social", f)

    def test_same_as_lists_enabled_urls_once(self):
        self.set_rows([{"platform": "linkedin", "url": LINKEDIN, "enabled": True},
                       {"platform": "other", "label": "LinkedIn again", "url": LINKEDIN, "enabled": True},
                       {"platform": "x", "url": X_URL, "enabled": False}])
        ld = org_ld(self.render(self.home_en))
        self.assertEqual(ld["sameAs"], [LINKEDIN])

    def test_same_as_includes_enabled_non_footer_and_skips_disabled(self):
        ld = org_ld(self.render(self.home_ar))
        self.assertEqual(ld["sameAs"], [LINKEDIN, X_URL, GH_URL])

    def test_no_same_as_key_when_nothing_enabled(self):
        self.set_rows([{"platform": "x", "url": X_URL, "enabled": False}])
        ld = org_ld(self.render(self.home_en))
        self.assertNotIn("sameAs", ld)

    def test_telephone_in_organization_json_ld(self):
        ld = org_ld(self.render(self.home_en))
        self.assertEqual(ld["telephone"], "+1 555 010 0199")
        self.assertEqual(ld["contactPoint"]["telephone"], "+1 555 010 0199")
        self.assertEqual(ld["email"], "leads@example.com")

    def test_phone_markup_footer_ltr_in_arabic(self):
        f = self.footer(self.render(self.home_ar))
        self.assertIn('<a href="tel:+15550100199">', f)
        self.assertIn('<bdi dir="ltr">+1 555 010 0199</bdi>', f)
        self.assertIn('href="https://wa.me/15550100199"', f)
        self.assertIn("واتساب", f)

    def test_contact_page_shows_phone_and_whatsapp(self):
        for t in (self.contact_en, self.contact_ar):
            html = self.render(t)
            direct = html[html.index('class="enquiry-direct"'):]
            direct = direct[:direct.index("</div>")]
            self.assertIn('href="tel:+15550100199"', direct)
            self.assertIn('<bdi dir="ltr">+1 555 010 0199</bdi>', direct)
            self.assertIn('href="https://wa.me/15550100199"', direct)

    def test_empty_phone_hides_phone_markup(self):
        Setting.objects.filter(key__in=["contact_phone", "whatsapp"]).update(value="")
        html = self.render(self.contact_en)
        self.assertNotIn("tel:", html)
        self.assertNotIn("wa.me", html)
        self.assertNotIn("telephone", json.dumps(org_ld(self.render(self.home_en))))

    def test_links_page_published_indexable_and_in_sitemap(self):
        from pathlib import Path

        from cms.publish import build
        with tempfile.TemporaryDirectory() as out:
            build(Path(out))
            en = (Path(out) / "links" / "index.html").read_text(encoding="utf-8")
            ar = (Path(out) / "ar" / "links" / "index.html").read_text(encoding="utf-8")
            sitemap = (Path(out) / "sitemap.xml").read_text(encoding="utf-8")
        self.assertNotIn('name="robots"', en)
        self.assertIn('hreflang="ar" href="https://example.com/ar/links/"', en)
        self.assertIn('href="/contact/"', en)
        self.assertIn('href="/ar/contact/"', ar)
        self.assertIn('href="https://wa.me/15550100199"', ar)
        self.assertNotIn("links_scan", en)
        self.assertIn("<loc>https://example.com/links/</loc>", sitemap)
        self.assertIn("<loc>https://example.com/ar/links/</loc>", sitemap)

    def test_links_page_scan_line_only_when_set(self):
        ctx = RenderContext()
        page = next(p for o, l, r, p in ctx.output_pages() if p and p["key"] == "links" and l.code == "en")
        html = ctx.render_named("special/links.html", self.en, page=page)
        self.assertNotIn("Our latest highlight", html)
        Setting.objects.update_or_create(key="links_scan_url", defaults={"value": "/scan/"})
        ctx = RenderContext()
        html = ctx.render_named("special/links.html", self.en, page=page)
        self.assertIn('href="/scan/"', html)
        self.assertIn("Our latest highlight", html)


class SocialHelpersTests(TestCase):
    def test_phone_digits_and_contact(self):
        self.assertEqual(social.phone_digits("+1 555 010 0199"), "+15550100199")
        c = social.contact({"contact_phone": "+1 555 010 0199", "whatsapp": "+1 (555) 010-0199"})
        self.assertEqual(c["wa_url"], "https://wa.me/15550100199")
        self.assertEqual(social.contact({})["wa_url"], "")

    def test_valid_url(self):
        self.assertTrue(social.valid_url(LINKEDIN))
        for bad in ("http://x.com/a", "javascript:alert(1)", "https://x.com/a b", 'https://x.com/"><script>', ""):
            self.assertFalse(social.valid_url(bad), bad)


@override_settings(TECHNTING_CMS_THEME="technting", TECHNTING_CMS_SITE_URL="https://example.com")
class SocialSettingsPageTests(TestCase):
    def setUp(self):
        Language.objects.create(code="en", name="English", native_name="English", is_default=True)
        self.admin = User.objects.create_superuser("boss", "b@example.com", "pw-123-long-enough")
        self.client.force_login(self.admin)
        self.out = tempfile.TemporaryDirectory()
        self.addCleanup(self.out.cleanup)

    def post(self, **extra):
        data = {"rows": 2, "platform_0": "linkedin", "url_0": LINKEDIN, "enabled_0": "on", "footer_0": "on",
                "platform_1": "x", "url_1": "", "contact_phone": "+1 555 010 0199", "whatsapp": "+1 555 010 0199",
                "links_scan_url": ""}
        data.update(extra)
        with override_settings(TECHNTING_CMS_OUTPUT_DIR=self.out.name):
            return self.client.post(reverse("cms:social_settings"), data)

    def test_page_loads(self):
        r = self.client.get(reverse("cms:social_settings"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'name="lang_0"')  # one account per platform, no language split

    def test_save_rows_drops_empty(self):
        self.post(url_1=X_URL)
        rows = Setting.objects.get(key="social_profiles").value["rows"]
        self.assertEqual([(r["platform"], r["url"], r["enabled"]) for r in rows], [("linkedin", LINKEDIN, True), ("x", X_URL, False)])
        self.post()
        self.assertEqual(len(Setting.objects.get(key="social_profiles").value["rows"]), 1)

    def test_invalid_values_save_nothing(self):
        Setting.objects.update_or_create(key="contact_phone", defaults={"value": "+1 555 010 0199"})
        before = list(Setting.objects.filter(key="social_profiles").values_list("value", flat=True))
        r = self.post(url_1="http://insecure.example.com/", contact_phone="call me")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(list(Setting.objects.filter(key="social_profiles").values_list("value", flat=True)), before)
        self.assertEqual(Setting.objects.get(key="contact_phone").value, "+1 555 010 0199")

    def test_non_admin_cannot_open(self):
        self.client.logout()
        u = User.objects.create_user("ed", "e@example.com", "pw-123-long-enough", is_staff=True)
        self.client.force_login(u)
        r = self.client.get(reverse("cms:social_settings"))
        self.assertNotEqual(r.status_code, 200)


@override_settings(TECHNTING_CMS_SITE_URL="https://example.com")
class UtmCaptureTests(TestCase):
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

    def hit(self, **data):
        body = {"p": "/", "r": "", "l": "en", "w": 1400, "s": 200}
        body.update(data)
        with mock.patch.object(stats, "enabled", return_value=True):
            r = self.client.post("/api/hit", json.dumps(body), content_type="text/plain", HTTP_ORIGIN="https://example.com",
                                 HTTP_USER_AGENT=self.UA, REMOTE_ADDR="203.0.113.7")
        self.assertEqual(r.status_code, 204)

    def test_records_all_four_utm_values(self):
        self.hit(u="LinkedIn", m="social", c="posts_ar", n="GB1-post-07")
        h = Hit.objects.get()
        self.assertEqual((h.source, h.channel, h.medium, h.campaign, h.content), ("linkedin", "campaign", "social", "posts_ar", "gb1-post-07"))
        self.assertNotIn("203.0.113.7", json.dumps(list(Hit.objects.values()), default=str))

    def test_free_text_is_reduced_to_a_code(self):
        self.hit(u="x", c="profile", n="someone@example.com <b>")
        self.assertEqual(Hit.objects.get().content, "someone_example.com_b")
        self.assertEqual(stats.utm("A" * 200, 80), "a" * 80)

    def test_untagged_visit_has_empty_utm(self):
        self.hit()
        h = Hit.objects.get()
        self.assertEqual((h.medium, h.campaign, h.content), ("", "", ""))

    def test_beacon_sends_medium_and_content(self):
        js = stats.beacon_script()
        for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content"):
            self.assertIn(key, js)

    def test_campaign_table_and_filters(self):
        def add(visitor, campaign, content, source="linkedin", n=1):
            for _ in range(n):
                Hit.objects.create(path="/", visitor=visitor, source=source, channel="campaign", medium="social",
                                   campaign=campaign, content=content)
        add("v1", "profile", "en", n=3)
        add("v2", "profile", "ar")
        add("v3", "profile", "ar")
        add("v4", "posts_en", "p12", source="x")
        Hit.objects.create(path="/", visitor="v5", channel="direct")  # not a campaign visit
        t = stats.report(30)["campaign_table"]
        self.assertEqual(t["campaigns"], ["posts_en", "profile"])
        rows = {(r["campaign"], r["content"]): (r["visits"], r["views"]) for r in t["rows"]}
        self.assertEqual(rows, {("profile", "en"): (1, 3), ("profile", "ar"): (2, 2), ("posts_en", "p12"): (1, 1)})
        t = stats.report(30, campaign="profile")["campaign_table"]
        self.assertEqual({r["content"] for r in t["rows"]}, {"en", "ar"})
        self.assertEqual(t["contents"], ["ar", "en"])
        t = stats.report(30, campaign="profile", content="ar")["campaign_table"]
        self.assertEqual([(r["content"], r["visits"]) for r in t["rows"]], [("ar", 2)])

    def test_stats_page_shows_campaigns_table(self):
        Hit.objects.create(path="/", visitor="v1", source="linkedin", channel="campaign", campaign="profile", content="ar")
        admin = User.objects.create_superuser("boss", "b@example.com", "pw-123-long-enough")
        self.client.force_login(admin)
        r = self.client.get(reverse("cms:stats") + "?campaign=profile&content=ar")
        self.assertContains(r, 'id="campaigns"')
        self.assertContains(r, "<code>profile</code>", html=False)
        self.assertContains(r, '<option value="ar" selected>')
