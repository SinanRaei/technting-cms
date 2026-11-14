"""The free Technting CMS licence (cms/licence.py): the check with the licence server, the 30-day grace period, the
twice-daily job, Settings, Licence, the warning for administrators and Updates turned off without a valid licence.
No network: urlopen is replaced. Run: manage.py test cms.test_licence"""
import io
import json
import time
import urllib.error
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from cms import licence
from cms.models import Setting

User = get_user_model()
PASSWORD = "quiet-harbour-lantern-42"
KEY = "TAI1.eyJwcm9kdWN0IjoiY21zIn0.c2lnbmF0dXJlLWZvci10ZXN0cw"
URL = "https://licenses.example.test/api/v1/plugins/cms/check"


class Answer(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def answer(code, body):
    if code == 200:
        return Answer(json.dumps(body).encode())
    return urllib.error.HTTPError(URL, code, "x", {}, io.BytesIO(json.dumps(body).encode()))


@override_settings(TECHNTING_CMS_LICENCE_URL=URL, TECHNTING_CMS_SITE_URL="https://www.harbour.example/", TECHNTING_CMS_DEMO_MODE=False)
class LicenceTests(TestCase):
    def setUp(self):
        self.reply = answer(200, {"status": "active", "license": {"lid": "x", "customer": "y"}, "update": None, "grace_days": 30})
        self.sent = []

        def urlopen(req, timeout=None):
            self.sent.append((req.full_url, req.get_method(), json.loads(req.data.decode())))
            if isinstance(self.reply, Exception):
                raise self.reply
            r = self.reply
            if isinstance(r, Answer):
                r.seek(0)
            return r
        p = mock.patch("urllib.request.urlopen", side_effect=urlopen)
        p.start()
        self.addCleanup(p.stop)

    # ------------------------------------------------------------ the check
    def test_what_is_sent(self):
        r = licence.ask(" " + KEY[:10] + "\n" + KEY[10:] + " ")
        self.assertEqual(r, {"status": "active", "reached": True, "grace_days": 30, "error": ""})
        url, method, body = self.sent[0]
        self.assertEqual((url, method), (URL, "POST"))
        self.assertEqual(set(body), {"license", "installation_id", "domain", "current_version"})
        self.assertEqual(body["license"], KEY)
        self.assertEqual(body["domain"], "www.harbour.example")
        from technting_cms import __version__
        self.assertEqual(body["current_version"], __version__)
        licence.ask(KEY)
        self.assertEqual(self.sent[1][2]["installation_id"], body["installation_id"], "one id per installation")
        self.assertEqual(len(body["installation_id"]), 36)

    def test_answers(self):
        # the server's own answers (licence server docs/CMS_LICENSE.md): the code is in "status"
        for reply, status in ((answer(200, {"status": "inactive_installation", "active_domain_hint": "ag***.test", "message": "x"}), "inactive_installation"),
                              (answer(403, {"status": "revoked"}), "revoked"),
                              (answer(401, {"status": "no_license"}), "no_license"),
                              (answer(401, {"status": "invalid_license"}), "invalid_license"),
                              (answer(401, {"error": "no_license"}), "no_license"),          # "error" read as a fallback
                              (answer(401, {"status": "something"}), "invalid_license")):
            self.reply = reply
            r = licence.ask(KEY)
            self.assertEqual((r["status"], r["reached"]), (status, True))
        for reply in (urllib.error.URLError("down"), answer(500, {}), answer(200, {"status": "surprise"}), answer(429, {}),
                      answer(404, {"status": "unknown_product"}), answer(422, {"status": "invalid_request"})):
            self.reply = reply
            self.assertEqual(licence.ask(KEY)["status"], "unreachable")

    def test_state_and_grace(self):
        self.assertEqual(licence.state()["status"], "no_key")
        self.assertFalse(licence.allows_updates())
        now = time.time()
        licence.record(KEY, licence.ask(KEY), now=now)
        self.assertTrue(licence.state(now)["ok"])
        down = {"status": "unreachable", "reached": False, "grace_days": None, "error": "URLError"}
        licence.record(KEY, down, now=now + 86400)
        st = licence.state(now + 86400)
        self.assertTrue(st["ok"] and st["offline"])
        self.assertEqual(st["grace_left"], 29)
        self.assertEqual(licence.stored()["status"], "active", "an unreachable server keeps the last answer")
        licence.record(KEY, down, now=now + 31 * 86400)
        self.assertEqual(licence.state(now + 31 * 86400)["status"], "grace_over")
        self.assertFalse(licence.state(now + 31 * 86400)["ok"])
        licence.record(KEY, {"status": "revoked", "reached": True, "grace_days": 30, "error": ""}, now=now + 32 * 86400)
        self.assertEqual(licence.state(now + 32 * 86400)["status"], "revoked")
        self.assertFalse(licence.state(now + 32 * 86400)["ok"])

    def test_a_new_key_the_server_could_not_check_counts_for_the_grace_period(self):
        now = time.time()
        licence.record(KEY, {"status": "unreachable", "reached": False, "grace_days": None, "error": "URLError"}, now=now)
        self.assertEqual(licence.state(now)["status"], "unchecked")
        self.assertTrue(licence.state(now + 29 * 86400)["ok"])
        self.assertFalse(licence.state(now + 31 * 86400)["ok"])

    def test_demo_needs_no_licence(self):
        with override_settings(TECHNTING_CMS_DEMO_MODE=True):
            self.assertTrue(licence.allows_updates())
            self.assertEqual(licence.run_due(), [])
        self.assertEqual(self.sent, [])

    def test_checked_twice_a_day(self):
        self.assertEqual(licence.run_due(), [], "no key: nothing is sent")
        self.assertEqual(self.sent, [])
        licence.record(KEY, licence.ask(KEY))
        self.assertEqual(licence.run_due(), [], "checked just now")
        v = licence.stored()
        v["checked_at"] = time.time() - 13 * 3600
        Setting.objects.update_or_create(key="licence", defaults={"value": v})
        self.reply = answer(403, {"status": "revoked"})
        self.assertEqual(licence.run_due(), ["licence: revoked (updates are off)"])
        self.assertEqual(len(self.sent), 2)
        out = io.StringIO()
        v = licence.stored()
        v["checked_at"] = 0
        Setting.objects.update_or_create(key="licence", defaults={"value": v})
        call_command("publish_due", stdout=out)
        self.assertIn("licence: revoked", out.getvalue())

    # ------------------------------------------------------------ the dashboard
    def admin(self):
        user = User.objects.create_superuser("owner", "owner@example.org", PASSWORD)
        self.client.force_login(user)
        return user

    def test_warning_for_administrators_only(self):
        self.admin()
        r = self.client.get("/settings/licence/")
        self.assertContains(r, "Add your Technting CMS licence key. Updates are off until then.", count=2)
        editor = User.objects.create_user("ed", "ed@example.org", PASSWORD, is_staff=True)
        self.client.force_login(editor)
        self.assertNotContains(self.client.get("/"), "licence key")
        self.admin_with_key()
        self.assertNotContains(self.client.get("/settings/licence/"), "Updates are off until then")

    def admin_with_key(self):
        self.client.force_login(User.objects.get(username="owner"))
        licence.record(KEY, licence.ask(KEY))

    def test_settings_saves_a_good_key_and_refuses_a_bad_one(self):
        self.admin()
        self.reply = answer(200, {"status": "inactive_installation"})
        r = self.client.post("/settings/licence/", {"action": "save", "licence_key": KEY}, follow=True)
        self.assertContains(r, "already runs on another website")
        self.assertFalse(licence.stored())
        r = self.client.post("/settings/licence/", {"action": "save", "licence_key": "nonsense"}, follow=True)
        self.assertContains(r, "It starts with TAI1.")
        self.reply = answer(200, {"status": "active", "license": {"lid": "x", "customer": "y"}, "update": None, "grace_days": 30})
        r = self.client.post("/settings/licence/", {"action": "save", "licence_key": KEY}, follow=True)
        self.assertContains(r, "The licence key is saved and active.")
        self.assertEqual(licence.stored()["key"], KEY)
        self.assertContains(r, KEY[:10] + "…")
        self.assertNotContains(r, KEY, msg_prefix="the full key is not shown again")
        self.reply = answer(403, {"status": "revoked"})
        self.client.post("/settings/licence/", {"action": "check"})
        self.assertEqual(licence.stored()["status"], "revoked")

    def test_updates_are_off_without_a_licence(self):
        self.admin()
        with mock.patch("cms.updater.fetch") as fetch, mock.patch("cms.updater.start_in_background") as start:
            r = self.client.post("/settings/updates/", {"action": "check"}, follow=True)
            self.assertContains(r, "Updates are off until then")
            self.client.post("/settings/updates/", {"action": "update"})
            fetch.assert_not_called()
            start.assert_not_called()
            licence.record(KEY, licence.ask(KEY))
            self.client.post("/settings/updates/", {"action": "check"})
            fetch.assert_called_once()
        Setting.objects.filter(key="licence").delete()
        err = io.StringIO()
        with mock.patch("cms.updater.run_update") as run:
            call_command("update_site", stdout=io.StringIO(), stderr=err)
        run.assert_not_called()
        self.assertIn("Updates are off", err.getvalue())

    def test_arabic_warning(self):
        user = self.admin()
        session = self.client.session
        session["ui_lang"] = "ar"
        session.save()
        r = self.client.get("/settings/licence/")
        self.assertContains(r, "أضيفوا مفتاح رخصة Technting CMS")
        self.assertTrue(user.is_superuser)
