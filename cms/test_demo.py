"""Public demo mode (TECHNTING_CMS_DEMO_MODE): upload rules, refused actions, no outbound email or HTTP, no raw HTML,
the banner and demo sign-in, noindex, and `manage.py demo_reset`. Run: manage.py test cms.test_demo"""
import io
import json
import shutil
import struct
import tempfile
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core import mail as django_mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from PIL import Image

from cms import demo, mail, setup_wizard
from cms.fields import clean_rich
from cms.media import MediaError, check_upload, save_upload
from cms.models import FormSubmission, Language, Media, Page, PageTranslation, Setting, UserSecurity

User = get_user_model()
PASSWORD = "quiet-harbour-lantern-42"
DEMO = {"TECHNTING_CMS_DEMO_MODE": True, "TECHNTING_CMS_DEMO_USER": "visitor", "TECHNTING_CMS_DEMO_PASSWORD": "shared-demo-key-9921"}


def png_bytes():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    raw = b"".join(b"\x00" + b"\x10\x80\xf0" * 4 for _ in range(4))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def image_bytes(fmt):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (20, 120, 200)).save(buf, fmt)
    return buf.getvalue()


PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"


def upload(name, data, ctype="application/octet-stream"):
    return SimpleUploadedFile(name, data, content_type=ctype)


class MediaTempMixin:
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp())
        p = override_settings(MEDIA_ROOT=self.tmp / "media", VAR_DIR=self.tmp / "var", TECHNTING_CMS_OUTPUT_DIR=self.tmp / "public")
        p.enable()
        self.addCleanup(p.disable)
        (self.tmp / "var").mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        cache.clear()


# ---------------------------------------------------------------- uploads
@override_settings(**DEMO)
class DemoUploadTests(MediaTempMixin, TestCase):
    def refused(self, name, data, text=""):
        with self.assertRaises(MediaError) as cm:
            check_upload(upload(name, data))
        self.assertIn(text, str(cm.exception))

    def test_allowed_types_pass(self):
        for name, data in (("photo.png", png_bytes()), ("photo.jpg", image_bytes("JPEG")), ("photo.jpeg", image_bytes("JPEG")),
                           ("photo.webp", image_bytes("WEBP")), ("photo.gif", image_bytes("GIF")), ("brochure.pdf", PDF)):
            self.assertTrue(check_upload(upload(name, data)), name)

    def test_real_png_is_saved(self):
        m = save_upload(upload("photo.png", png_bytes(), "image/png"))
        self.assertEqual(m.mime, "image/png")
        self.assertTrue(Path(m.file.path).is_file())

    def test_svg_html_scripts_archives_and_office_files_are_refused(self):
        self.refused("drawing.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
        self.refused("page.html", b"<html><script>alert(1)</script></html>")
        self.refused("run.sh", b"#!/bin/sh\nrm -rf /\n")
        self.refused("tool.exe", b"MZ\x90\x00\x03\x00\x00\x00")
        self.refused("files.zip", b"PK\x03\x04" + b"\x00" * 30)
        self.refused("sheet.xlsx", b"PK\x03\x04" + b"\x00" * 30)
        self.refused("letter.docx", b"PK\x03\x04" + b"\x00" * 30)
        self.refused("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16, "public demo")

    def test_php_renamed_to_png_is_refused(self):
        self.refused("shell.png", b"<?php system($_GET['c']); ?>", "public demo")

    def test_extension_must_match_the_content(self):
        self.refused("photo.jpg", png_bytes(), "does not match")
        self.refused("photo.pdf", png_bytes(), "does not match")

    def test_five_mb_limit(self):
        self.refused("big.png", png_bytes() + b"\x00" * (5 * 1024 * 1024), "5 MB")

    def test_pdf_with_javascript_is_refused(self):
        self.refused("form.pdf", PDF.replace(b"/Type /Catalog", b"/Type /Catalog /OpenAction << /S /JavaScript /JS (app.alert(1)) >>"),
                     "scripts")

    def test_upload_view_reports_demo_rule_in_arabic(self):
        admin = User.objects.create_superuser("owner", "owner@example.org", PASSWORD)
        self.client.force_login(admin)
        s = self.client.session
        s["ui_lang"] = "ar"
        s.save()
        r = self.client.post("/media/upload/", {"files": [upload("shell.png", b"<?php echo 1; ?>", "image/png")]})
        self.assertEqual(r.status_code, 400)
        self.assertIn("النسخة التجريبية", r.json()["errors"][0])
        self.assertFalse(Media.objects.exists())

    def test_library_has_a_ceiling(self):
        Media.objects.create(title="old", mime="image/png", size=300 * 1024 * 1024, file="2026/01/old.png")
        with self.assertRaises(MediaError):
            save_upload(upload("photo.png", png_bytes()))


class AlwaysOnUploadTests(MediaTempMixin, TestCase):
    """Outside the demo the content check stays as it was (images, PDF, MP4, WebM up to 20 / 95 MB), and executable
    file names are refused even when the content is an image."""

    def test_executable_names_are_refused(self):
        for name in ("shell.php", "shell.php.png", "run.py", "run.sh", "tool.exe", "app.js", "page.html", "drawing.svg"):
            with self.assertRaises(MediaError, msg=name):
                check_upload(upload(name, png_bytes()))

    def test_content_check_refuses_scripts_with_image_names(self):
        with self.assertRaises(MediaError):
            check_upload(upload("shell.png", b"<?php echo 1; ?>"))

    def test_video_still_allowed_and_dots_in_names_are_flattened(self):
        self.assertEqual(check_upload(upload("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16)), "video/mp4")
        m = save_upload(upload("team.photo.v2.png", png_bytes()))
        self.assertTrue(m.file.name.endswith("team-photo-v2.png"), m.file.name)


# ---------------------------------------------------------------- refused actions
class AdminClientMixin:
    def setUp(self):
        super().setUp()
        cache.clear()
        setup_wizard.reset_cache()
        self.admin = User.objects.create_superuser("owner", "owner@example.org", PASSWORD)
        self.client.force_login(self.admin)

    def follow_message(self, r):
        return " ".join(str(m) for m in r.context["messages"]) if r.context else ""


@override_settings(**DEMO)
class DemoRefusedActionTests(AdminClientMixin, MediaTempMixin, TestCase):
    def assertRefused(self, method, url, data=None, **extra):
        r = getattr(self.client, method)(url, data or {}, HTTP_REFERER="http://testserver/", follow=True, **extra)
        self.assertIn(demo.MESSAGE, self.follow_message(r), url)
        return r

    def test_users_cannot_be_created_invited_or_changed(self):
        self.assertRefused("post", "/users/", {"username": "intruder", "password": PASSWORD, "role": "admin"})
        self.assertFalse(User.objects.filter(username="intruder").exists())
        other = User.objects.create_user("editor1", password=PASSWORD, is_staff=True)
        self.assertRefused("post", f"/users/{other.pk}/role/", {"role": "admin"})
        self.assertRefused("post", f"/users/{other.pk}/toggle/")
        self.assertRefused("post", f"/users/{other.pk}/invite/")
        other.refresh_from_db()
        self.assertTrue(other.is_active)
        self.assertFalse(other.is_superuser)

    def test_password_and_two_step_cannot_be_changed(self):
        self.assertRefused("post", "/account/", {"current": PASSWORD, "new": "another-long-passphrase-7"})
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(PASSWORD))
        self.assertRefused("post", "/account/security/", {"action": "confirm", "code": "123456"})
        self.assertFalse(UserSecurity.objects.filter(user=self.admin, enabled=True).exists())

    def test_weekly_email_setting_still_saves(self):
        r = self.client.post("/account/", {"form": "digest", "digest": "on", "digest_lang": "en"}, follow=True)
        self.assertNotIn(demo.MESSAGE, self.follow_message(r))

    def test_settings_pages_refuse_changes_but_open(self):
        for url in ("/settings/email/", "/settings/social/", "/settings/backups/offsite/", "/plugins/", "/settings/backups/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertRefused("post", "/settings/email/", {"username": "me@example.org", "password": "abcd efgh ijkl mnop"})
        self.assertFalse(Setting.objects.filter(key="smtp").exists())
        self.assertRefused("post", "/settings/social/", {"rows": "1", "platform_0": "x", "url_0": "https://x.com/someone"})
        self.assertFalse(Setting.objects.filter(key="social_profiles").exists())
        self.assertRefused("post", "/plugins/", {"plugins_json": json.dumps({"webhook-notify": {"enabled": True}})})
        self.assertFalse(Setting.objects.filter(key="plugins_enabled").exists())
        self.assertRefused("post", "/settings/backups/offsite/", {"provider": "r2"})
        self.assertRefused("post", "/settings/backups/offsite/run/", {"action": "upload"})
        self.assertRefused("post", "/settings/backups/")
        self.assertRefused("post", "/site-security/")

    def test_self_update_is_refused(self):
        with mock.patch("cms.updater.start_in_background") as start, mock.patch("cms.updater.fetch") as fetch:
            self.assertRefused("post", "/settings/updates/", {"action": "update"})
            self.assertRefused("post", "/settings/updates/", {"action": "check"})
        start.assert_not_called()
        fetch.assert_not_called()
        from cms import updater
        with self.assertRaises(RuntimeError):
            updater.start_in_background("someone")

    def test_backup_downloads_are_refused(self):
        self.assertRefused("get", "/settings/backups/technting-cms-20260101-020000/download/")
        self.assertRefused("post", "/settings/backups/offsite/technting-cms-20260101-020000/download/")

    def test_external_services_are_refused(self):
        self.assertRefused("post", "/seo/refresh/")
        self.assertRefused("post", "/health/links/")
        self.assertRefused("post", "/shield/blocks/add/", {"network": "203.0.113.0/24"})
        self.assertRefused("post", "/shield/sessions/others/")
        self.assertRefused("post", "/crm/prospects/import/", {"file": upload("list.csv", b"name\nAcme\n")})

    def test_json_callers_get_json(self):
        r = self.client.post("/plugins/", {}, HTTP_ACCEPT="application/json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"], demo.MESSAGE)

    def test_message_in_arabic(self):
        s = self.client.session
        s["ui_lang"] = "ar"
        s.save()
        r = self.client.post("/users/", {"username": "x"}, follow=True)
        self.assertIn("النسخة التجريبية العامة", self.follow_message(r))

    def test_require_two_step_cannot_be_turned_on(self):
        UserSecurity.objects.create(user=self.admin, enabled=True, totp_secret="JBSWY3DPEHPK3PXP")
        self.client.post("/settings/", {"require_2fa": "on", "contact_email": "", "leads_email": ""})
        self.assertFalse(Setting.objects.filter(key="require_2fa", value=True).exists())

    def test_replace_cannot_add_markup(self):
        r = self.client.post("/tools/replace/", {"find": "Hello", "replace": "<script>alert(1)</script>", "confirm": "1"}, follow=True)
        self.assertIn("cannot contain", self.follow_message(r))


class OutsideDemoTests(AdminClientMixin, TestCase):
    def test_actions_work_as_before(self):
        r = self.client.post("/users/", {"username": "editor2", "email": "", "password": PASSWORD, "role": "editor"}, follow=True)
        self.assertNotIn(demo.MESSAGE, self.follow_message(r))
        self.assertTrue(User.objects.filter(username="editor2").exists())

    def test_no_banner_no_demo_login_no_robots_header(self):
        r = self.client.get("/")
        self.assertNotContains(r, demo.BANNER)
        self.assertNotIn("X-Robots-Tag", r.headers)
        self.client.logout()
        with override_settings(TECHNTING_CMS_DEMO_USER="visitor", TECHNTING_CMS_DEMO_PASSWORD="shared-demo-key-9921"):
            self.assertNotContains(self.client.get("/login/"), "shared-demo-key-9921")

    def test_network_guard_does_nothing(self):
        req = urllib.request.Request("https://example.org/")
        self.assertIsNone(demo.NetworkGuard().https_open(req))


# ---------------------------------------------------------------- banner, login, noindex
@override_settings(**DEMO)
class DemoPagesTests(AdminClientMixin, TestCase):
    def test_banner_in_both_languages(self):
        r = self.client.get("/")
        self.assertContains(r, demo.BANNER)
        self.assertEqual(r.headers["X-Robots-Tag"], "noindex, nofollow")
        s = self.client.session
        s["ui_lang"] = "ar"
        s.save()
        self.assertContains(self.client.get("/"), "يُعاد ضبط كل شيء كل ساعتين")

    def test_login_page_shows_the_demo_account(self):
        self.client.logout()
        r = self.client.get("/login/")
        self.assertContains(r, "visitor")
        self.assertContains(r, "shared-demo-key-9921")
        self.assertContains(r, "Everything resets every 2 hours")
        self.assertEqual(r.headers["X-Robots-Tag"], "noindex, nofollow")

    @override_settings(TECHNTING_CMS_DEMO_USER="", TECHNTING_CMS_DEMO_PASSWORD="")
    def test_no_account_box_without_settings(self):
        self.client.logout()
        self.assertNotContains(self.client.get("/login/"), "Demo sign-in")


# ---------------------------------------------------------------- email and outbound HTTP
@override_settings(**DEMO)
class DemoNetworkTests(TestCase):
    def test_outbound_http_is_refused(self):
        for url in ("https://api.indexnow.org/indexnow", "http://127.0.0.1:8000/", "https://hooks.example.net/x"):
            with self.assertRaises(urllib.error.URLError) as cm:
                urllib.request.urlopen(url, timeout=2)
            self.assertIn("public demo", str(cm.exception.reason), url)

    @override_settings(TECHNTING_CMS_SITE_URL="https://demo.example.org", TECHNTING_CMS_ADMIN_URL="https://cms.demo.example.org")
    def test_own_site_stays_reachable_for_the_security_page(self):
        self.assertIsNone(demo.NetworkGuard().https_open(urllib.request.Request("https://demo.example.org/robots.txt")))

    def test_email_never_leaves_and_enquiries_still_save(self):
        Setting.objects.create(key="smtp", value={"host": "smtp.example.org", "port": 465, "security": "ssl",
                                                  "username": "me@example.org", "password": mail.encrypt("secret")})
        conn = mail.connection()
        self.assertNotIn("smtp", type(conn).__module__)
        with self.assertRaises(RuntimeError):
            mail.test_login("smtp.example.org", 465, "ssl", "me@example.org", "secret")
        from cms.forms_api import send_copy
        sub = FormSubmission.objects.create(name="Test", email="test@example.org", message="Hello")
        send_copy(sub)   # the test runner's locmem backend stands in for the console backend of a demo server
        self.assertTrue(FormSubmission.objects.filter(pk=sub.pk).exists())
        self.assertEqual(len(django_mail.outbox), 1)


# ---------------------------------------------------------------- raw HTML and rich text
@override_settings(**DEMO, TECHNTING_CMS_THEME="technting")
class DemoHtmlTests(AdminClientMixin, MediaTempMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.en = Language.objects.create(code="en", name="English", native_name="English", is_default=True)
        self.page = Page.objects.create(key="about", template="default")

    def test_html_block_is_not_offered(self):
        r = self.client.get(f"/pages/{self.page.pk}/en/edit/")
        theme_data = json.loads(r.context["theme_json"])
        self.assertNotIn("html", theme_data["blocks"])
        self.assertIn("rich_text", theme_data["blocks"])

    def test_html_block_is_refused_on_save(self):
        blocks = [{"id": "a1", "type": "html", "data": {"code": "<script>alert(1)</script>"}}]
        r = self.client.post(f"/pages/{self.page.pk}/en/edit/", {"title": "About", "blocks_json": json.dumps(blocks),
                                                                  "page_data_json": "{}", "action": "save"}, follow=True)
        self.assertIn("Custom HTML blocks are turned off", self.follow_message(r))
        self.assertFalse(PageTranslation.objects.filter(page=self.page).exists())

    def test_html_block_is_never_published(self):
        from cms.publish import publish_site
        PageTranslation.objects.create(page=self.page, language=self.en, title="About", slug="about", status=PageTranslation.PUBLISHED,
                                       blocks=[{"id": "a1", "type": "html", "data": {"code": "<p id='raw-html-marker'>x</p>"}}])
        log = publish_site()
        self.assertTrue(log.ok, log.message)
        html = (self.tmp / "public" / "about" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("raw-html-marker", html)
        self.assertEqual((self.tmp / "public" / "robots.txt").read_text(encoding="utf-8"), "User-agent: *\nDisallow: /\n")
        self.assertEqual(html.count('name="robots"'), 1)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', html)

    def test_rich_text_is_sanitised(self):
        dirty = ('<p onclick="x()">Hi<script>alert(1)</script><iframe src="https://evil.example"></iframe>'
                 '<img src="x" onerror="alert(1)"><a href="javascript:alert(1)">link</a></p>')
        clean = clean_rich(dirty)
        for bad in ("<script", "<iframe", "onclick", "onerror", "javascript:"):
            self.assertNotIn(bad, clean)
        blocks = [{"id": "r1", "type": "rich_text", "data": {"body": dirty}}]
        self.client.post(f"/pages/{self.page.pk}/en/edit/", {"title": "About", "blocks_json": json.dumps(blocks),
                                                              "page_data_json": "{}", "action": "save"})
        stored = PageTranslation.objects.get(page=self.page).blocks[0]["data"]["body"]
        self.assertNotIn("<script", stored)
        self.assertNotIn("onerror", stored)


class RobotsOutsideDemoTests(MediaTempMixin, TestCase):
    @override_settings(TECHNTING_CMS_THEME="technting")
    def test_theme_robots_is_kept(self):
        from cms.publish import publish_site
        Language.objects.create(code="en", name="English", native_name="English", is_default=True)
        self.assertTrue(publish_site().ok)
        robots = (self.tmp / "public" / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Allow: /", robots)
        self.assertNotIn("Disallow", robots)

    def test_noindex_html_replaces_the_theme_tag(self):
        from cms.publish import noindex_html
        f = self.tmp / "page.html"
        f.write_text('<html><HEAD lang="en"><meta name="robots" content="index"><title>x</title></head></html>', encoding="utf-8")
        noindex_html(self.tmp)
        self.assertEqual(f.read_text(encoding="utf-8"),
                         '<html><HEAD lang="en"><meta name="robots" content="noindex, nofollow"><title>x</title></head></html>')


# ---------------------------------------------------------------- demo_reset
class DemoResetRefusalTests(TestCase):
    @override_settings(TECHNTING_CMS_DEMO_MODE=False)
    def test_refuses_outside_demo_mode(self):
        with self.assertRaisesMessage(CommandError, "TECHNTING_CMS_DEMO_MODE is off"):
            call_command("demo_reset", stdout=io.StringIO())

    @override_settings(TECHNTING_CMS_DEMO_MODE=True, TECHNTING_CMS_DEMO_USER="", TECHNTING_CMS_DEMO_PASSWORD="")
    def test_needs_the_demo_account(self):
        with self.assertRaisesMessage(CommandError, "TECHNTING_CMS_DEMO_USER"):
            call_command("demo_reset", stdout=io.StringIO())

    @override_settings(**DEMO)
    def test_refuses_other_databases(self):
        with mock.patch("cms.dbdump.engine", return_value="mysql"),                 self.assertRaisesMessage(CommandError, "works only with the SQLite database"):
            call_command("demo_reset", stdout=io.StringIO())


@skipUnless(connection.vendor == "sqlite", "demo_reset is SQLite only (the public demo keeps SQLite)")
class DemoResetTests(TransactionTestCase):
    """End to end: a child process builds the demo, then it replaces this test database, media and the site."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        var = self.tmp / "var"
        (var / "media" / "2026").mkdir(parents=True)
        (var / "media" / "2026" / "visitor.png").write_bytes(png_bytes())
        (self.tmp / "public").mkdir()
        (self.tmp / "public" / "keep-me.txt").write_text("not made by the CMS")
        p = override_settings(**DEMO, VAR_DIR=var, MEDIA_ROOT=var / "media", TECHNTING_CMS_OUTPUT_DIR=self.tmp / "public",
                              TECHNTING_CMS_THEME="technting", TECHNTING_CMS_SITE_URL="https://demo.example.org")
        p.enable()
        self.addCleanup(p.disable)
        self.addCleanup(setup_wizard.reset_cache)

    def test_reset_rebuilds_everything_and_ends_sessions(self):
        visitor = User.objects.create_superuser("leftover", "x@example.org", PASSWORD)
        self.client.force_login(visitor)
        old_key = self.client.session.session_key
        self.assertTrue(Session.objects.filter(session_key=old_key).exists())
        out = io.StringIO()
        call_command("demo_reset", stdout=out)
        self.assertIn("Demo reset", out.getvalue())
        self.assertFalse(Session.objects.filter(session_key=old_key).exists())
        self.assertFalse(User.objects.filter(username="leftover").exists())
        demo_user = User.objects.get(username="visitor")
        self.assertTrue(demo_user.is_superuser and demo_user.check_password("shared-demo-key-9921"))
        self.assertTrue(Setting.objects.filter(key=setup_wizard.FLAG).exists())
        self.assertTrue(PageTranslation.objects.filter(page__key="home").exists())
        self.assertFalse((self.tmp / "var" / "media" / "2026" / "visitor.png").exists())
        site = self.tmp / "public"
        self.assertTrue((site / "index.html").is_file())
        self.assertIn("Disallow: /", (site / "robots.txt").read_text(encoding="utf-8"))
        self.assertTrue((site / "keep-me.txt").is_file())   # files the CMS did not make are left alone
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name.startswith(".var-demo-")], [])
        self.assertFalse((self.tmp / "var" / "demo_reset.lock").exists())
        r = self.client.get("/")
        self.assertEqual(r.status_code, 302)   # the old session cookie no longer signs anyone in
