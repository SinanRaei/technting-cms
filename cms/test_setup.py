"""First-run setup wizard: redirects while no administrator exists, step validation, what the finish stores,
and that /setup/ is gone afterwards. Run: manage.py test cms.test_setup"""
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from cms import mail, setup_wizard
from cms.models import Language, PageTranslation, Setting
from cms.theme import reload_theme

User = get_user_model()
PASSWORD = "quiet-harbour-lantern-42"
KEY = "TAI1.eyJwcm9kdWN0IjoiY21zIn0.c2lnbmF0dXJlLWZvci10ZXN0cw"
ACTIVE = {"status": "active", "reached": True, "grace_days": 30, "error": ""}


class SetupTestCase(TestCase):
    def setUp(self):
        setup_wizard.reset_cache()
        cache.clear()
        self.tmp = Path(tempfile.mkdtemp())
        self.env_file = self.tmp / "site.env"
        self.ask = mock.patch("cms.licence.ask", return_value=dict(ACTIVE))
        patches = [self.ask, mock.patch.object(setup_wizard, "env_target", return_value=self.env_file),
                   mock.patch.dict(os.environ, {}),
                   override_settings(TECHNTING_CMS_OUTPUT_DIR=self.tmp / "public", TECHNTING_CMS_SITE_NAME="Technting",
                                     TECHNTING_CMS_SITE_URL="https://example.com", TECHNTING_CMS_THEME="technting",
                                     TECHNTING_CMS_SETUP_TOKEN="", TECHNTING_CMS_ENV_FROM_PROCESS=frozenset())]
        for p in patches:
            p.start() if hasattr(p, "start") else p.enable()
            self.addCleanup(p.stop if hasattr(p, "stop") else p.disable)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(setup_wizard.reset_cache)
        self.addCleanup(reload_theme)

    def walk(self, languages="both", default="en", email=None):
        c = self.client
        c.post("/setup/site/", {"site_name": "Harbour Studio", "site_url": "https://example.org/"})
        c.post("/setup/languages/", {"languages": languages, "default": default})
        c.post("/setup/admin/", {"username": "owner", "email": "owner@example.org", "password": PASSWORD, "password2": PASSWORD})
        c.post("/setup/theme/", {"theme": "technting"})
        c.post("/setup/email/", email or {"action": "skip"})
        c.post("/setup/licence/", {"licence_key": KEY})


class RedirectTests(SetupTestCase):
    def test_dashboard_urls_redirect_to_setup(self):
        for url in ("/", "/login/", "/pages/", "/crm/", "/settings/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertEqual(r["Location"], "/setup/", url)

    def test_public_endpoints_keep_working(self):
        r = self.client.get("/api/contact/status")
        self.assertEqual(r.status_code, 200)

    def test_setup_opens_first_step(self):
        r = self.client.get("/setup/")
        self.assertRedirects(r, "/setup/site/")
        r = self.client.get("/setup/site/")
        self.assertContains(r, 'name="site_name"')
        self.assertContains(r, "csrfmiddlewaretoken")

    def test_later_steps_wait_for_earlier_ones(self):
        r = self.client.get("/setup/admin/")
        self.assertRedirects(r, "/setup/site/")

    def test_existing_install_is_not_sent_to_setup(self):
        User.objects.create_user("editor", password=PASSWORD, is_staff=True)
        r = self.client.get("/login/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/setup/").status_code, 404)

    def test_csrf_is_enforced(self):
        c = self.client_class(enforce_csrf_checks=True)
        r = c.post("/setup/site/", {"site_name": "X", "site_url": "https://example.org"})
        self.assertEqual(r.status_code, 403)

    def test_arabic_interface(self):
        r = self.client.get("/setup/site/?ui=ar")
        self.assertContains(r, 'dir="rtl"')
        self.assertContains(r, "إعداد Technting CMS")


class StepTests(SetupTestCase):
    def test_site_url_is_validated(self):
        r = self.client.post("/setup/site/", {"site_name": "Harbour", "site_url": "example"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Enter the full address")

    def test_password_validators_apply(self):
        self.client.post("/setup/site/", {"site_name": "Harbour", "site_url": "https://example.org"})
        self.client.post("/setup/languages/", {"languages": "en"})
        r = self.client.post("/setup/admin/", {"username": "owner", "email": "owner@example.org", "password": "short", "password2": "short"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "too short")
        r = self.client.post("/setup/admin/", {"username": "owner", "email": "owner@example.org", "password": PASSWORD, "password2": PASSWORD + "x"})
        self.assertContains(r, "do not match")

    def test_session_keeps_only_a_password_hash(self):
        self.walk()
        stored = self.client.session[setup_wizard.SESSION_KEY]["admin"]["password"]
        self.assertNotIn(PASSWORD, str(self.client.session.items()))
        self.assertTrue(stored.startswith(("pbkdf2_", "argon2", "bcrypt", "scrypt")))

    def test_test_email_uses_the_typed_account(self):
        self.client.post("/setup/site/", {"site_name": "Harbour", "site_url": "https://example.org"})
        self.client.post("/setup/languages/", {"languages": "en"})
        self.client.post("/setup/admin/", {"username": "owner", "email": "owner@example.org", "password": PASSWORD, "password2": PASSWORD})
        self.client.post("/setup/theme/", {"theme": "technting"})
        with mock.patch.object(setup_wizard, "send_test") as send:
            r = self.client.post("/setup/email/", {"action": "test", "host": "smtp.example.org", "port": "587", "security": "starttls",
                                                   "username": "site@example.org", "password": "app-secret", "test_to": "owner@example.org"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(send.call_args[0][0]["host"], "smtp.example.org")
        self.assertEqual(send.call_args[0][1], "owner@example.org")
        self.assertContains(r, "Test email sent to")

    def test_test_email_is_rate_limited(self):
        self.walk()
        with mock.patch.object(setup_wizard, "send_test"):
            for _ in range(setup_wizard.MAIL_LIMIT + 1):
                r = self.client.post("/setup/email/", {"action": "test", "host": "smtp.example.org", "port": "465", "security": "ssl",
                                                       "username": "site@example.org", "password": "x", "test_to": "a@example.org"})
        self.assertContains(r, "Too many test emails")

    def test_posts_are_rate_limited(self):
        with mock.patch.object(setup_wizard, "POST_LIMIT", 3):
            for _ in range(4):
                r = self.client.post("/setup/site/", {"site_name": "", "site_url": ""}, follow=True)
        self.assertContains(r, "Too many attempts")


class FinishTests(SetupTestCase):
    def test_finish_creates_admin_settings_and_publishes(self):
        self.walk(email={"action": "save", "host": "smtp.example.org", "port": "465", "security": "ssl",
                         "username": "site@example.org", "password": "app-secret", "from_name": "Harbour"})
        r = self.client.post("/setup/finish/", {"demo": "on"})
        self.assertRedirects(r, "/", fetch_redirect_response=False)
        user = User.objects.get(username="owner")
        self.assertTrue(user.is_superuser and user.is_staff and user.check_password(PASSWORD))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)        # signed in
        self.assertTrue(Setting.objects.filter(key=setup_wizard.FLAG).exists())
        smtp = Setting.objects.get(key="smtp").value
        self.assertEqual(smtp["host"], "smtp.example.org")
        self.assertNotEqual(smtp["password"], "app-secret")
        self.assertEqual(mail.decrypt(smtp["password"]), "app-secret")             # read back like Settings, Email
        self.assertEqual(mail.config()["source"], "dashboard")
        self.assertEqual(sorted(Language.objects.values_list("code", flat=True)), ["ar", "en"])
        self.assertEqual(Language.objects.get(is_default=True).code, "en")
        self.assertEqual(Language.objects.get(code="ar").url_prefix, "ar")
        self.assertTrue(PageTranslation.objects.filter(page__key="home").exists())   # demo content
        env = self.env_file.read_text(encoding="utf-8")
        self.assertIn("TECHNTING_CMS_SITE_NAME=Harbour Studio", env)
        self.assertIn("TECHNTING_CMS_SITE_URL=https://example.org", env)
        self.assertIn("TECHNTING_CMS_THEME=technting", env)
        self.assertEqual(settings.TECHNTING_CMS_SITE_NAME, "Harbour Studio")
        self.assertTrue((self.tmp / "public" / "index.html").exists())               # published once
        self.assertEqual(self.client.get("/setup/").status_code, 404)
        self.assertEqual(self.client.get("/setup/site/").status_code, 404)
        lic = Setting.objects.get(key="licence").value                               # the licence step
        self.assertEqual((lic["key"], lic["status"]), (KEY, "active"))

    def test_arabic_only_site_drops_english_demo(self):
        self.walk(languages="ar")
        self.client.post("/setup/finish/", {"demo": "on"})
        self.assertEqual(list(Language.objects.values_list("code", "is_default", "url_prefix")), [("ar", True, "")])
        self.assertFalse(Setting.objects.filter(key="smtp").exists())
        self.assertFalse(PageTranslation.objects.exclude(language__code="ar").exists())

    def test_arabic_default_with_both(self):
        self.walk(languages="both", default="ar")
        self.client.post("/setup/finish/")
        self.assertEqual(Language.objects.get(is_default=True).code, "ar")
        self.assertEqual(Language.objects.get(code="en").url_prefix, "en")
        self.assertFalse(PageTranslation.objects.exists())

    def test_finish_needs_every_step(self):
        self.client.post("/setup/site/", {"site_name": "Harbour", "site_url": "https://example.org"})
        r = self.client.post("/setup/finish/")
        self.assertRedirects(r, "/setup/languages/")
        self.assertFalse(User.objects.exists())

    def test_locked_values_are_not_written(self):
        with override_settings(TECHNTING_CMS_ENV_FROM_PROCESS=frozenset({"TECHNTING_CMS_SITE_URL"})):
            self.walk()
            self.client.post("/setup/finish/")
        env = self.env_file.read_text(encoding="utf-8")
        self.assertNotIn("TECHNTING_CMS_SITE_URL", env)
        self.assertIn("TECHNTING_CMS_SITE_NAME=Harbour Studio", env)


class LicenceStepTests(SetupTestCase):
    def walk_to_licence(self):
        c = self.client
        c.post("/setup/site/", {"site_name": "Harbour Studio", "site_url": "https://example.org/"})
        c.post("/setup/languages/", {"languages": "en"})
        c.post("/setup/admin/", {"username": "owner", "email": "owner@example.org", "password": PASSWORD, "password2": PASSWORD})
        c.post("/setup/theme/", {"theme": "technting"})
        c.post("/setup/email/", {"action": "skip"})

    def test_the_key_is_required(self):
        self.walk_to_licence()
        self.assertRedirects(self.client.post("/setup/finish/"), "/setup/licence/")
        r = self.client.post("/setup/licence/", {"licence_key": ""})
        self.assertContains(r, "It starts with TAI1.")
        r = self.client.post("/setup/licence/", {"licence_key": "not-a-key"})
        self.assertContains(r, "It starts with TAI1.")
        self.assertFalse(User.objects.exists())

    def test_the_key_is_checked_for_the_site_address(self):
        self.walk_to_licence()
        with mock.patch("cms.licence.ask", return_value=dict(ACTIVE)) as ask:
            r = self.client.post("/setup/licence/", {"licence_key": KEY[:20] + "\n " + KEY[20:]})   # wrapped by an e-mail client
        self.assertRedirects(r, "/setup/finish/")
        ask.assert_called_once_with(KEY, "https://example.org")

    def test_a_refused_key_is_not_accepted(self):
        self.walk_to_licence()
        for status, words in (("inactive_installation", "already runs on another website"), ("revoked", "was cancelled"),
                              ("invalid_license", "is not valid")):
            with mock.patch("cms.licence.ask", return_value={**ACTIVE, "status": status}):
                r = self.client.post("/setup/licence/", {"licence_key": KEY})
            self.assertContains(r, words)
        self.assertRedirects(self.client.post("/setup/finish/"), "/setup/licence/")

    def test_an_unreachable_server_does_not_stop_the_setup(self):
        self.walk_to_licence()
        with mock.patch("cms.licence.ask", return_value={"status": "unreachable", "reached": False, "grace_days": None, "error": "URLError"}):
            r = self.client.post("/setup/licence/", {"licence_key": KEY}, follow=True)
        self.assertContains(r, "checked again later")
        self.client.post("/setup/finish/")
        lic = Setting.objects.get(key="licence").value
        self.assertEqual((lic["key"], lic["status"], lic["last_error"]), (KEY, "unchecked", "URLError"))

    def test_arabic_step(self):
        self.walk_to_licence()
        r = self.client.get("/setup/licence/?ui=ar")
        self.assertContains(r, "مفتاح الرخصة")


class TokenTests(SetupTestCase):
    def test_setup_key_is_asked_once(self):
        with override_settings(TECHNTING_CMS_SETUP_TOKEN="k3y-from-installer"):
            r = self.client.get("/setup/site/")
            self.assertContains(r, 'name="setup_token"')
            r = self.client.post("/setup/site/", {"setup_token": "wrong"})
            self.assertEqual(r.status_code, 403)
            r = self.client.get("/setup/site/?token=مفتاح")       # non-ASCII guesses must not crash
            self.assertEqual(r.status_code, 403)
            r = self.client.post("/setup/site/", {"setup_token": "k3y-from-installer"})
            self.assertRedirects(r, "/setup/site/")
            r = self.client.get("/setup/site/")
            self.assertContains(r, 'name="site_name"')


class EnvFileTests(TestCase):
    def test_update_keeps_other_lines(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        f = tmp / ".env"
        f.write_text("# comment\nTECHNTING_CMS_DEBUG=0\nTECHNTING_CMS_SITE_NAME=Old\n", encoding="utf-8")
        setup_wizard.update_env_file(f, {"TECHNTING_CMS_SITE_NAME": "New name", "TECHNTING_CMS_THEME": "technting"})
        self.assertEqual(f.read_text(encoding="utf-8"),
                         "# comment\nTECHNTING_CMS_DEBUG=0\nTECHNTING_CMS_SITE_NAME=New name\nTECHNTING_CMS_THEME=technting\n")
