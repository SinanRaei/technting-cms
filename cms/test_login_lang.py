"""Sign-in page language: one interface language at a time, and the demo account shown cleanly in it."""
from django.test import TestCase, override_settings

DEMO = {"TECHNTING_CMS_DEMO_MODE": True, "TECHNTING_CMS_DEMO_USER": "visitor", "TECHNTING_CMS_DEMO_PASSWORD": "shared-demo-key-9921"}


@override_settings(**DEMO)
class LoginLanguageTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from django.core.cache import cache

        from cms import setup_wizard
        cache.clear()
        setup_wizard.reset_cache()
        User.objects.create_superuser("owner", "owner@example.org", "a-long-test-password-77")   # setup counts as done

    def test_english_by_default(self):
        r = self.client.get("/login/")
        self.assertContains(r, '<html lang="en" dir="ltr">')
        self.assertContains(r, "Everything resets every 2 hours")
        self.assertNotContains(r, "يُعاد ضبط كل شيء")
        self.assertContains(r, 'Username: <bdi dir="ltr"><code>visitor</code></bdi>')
        self.assertContains(r, 'Password: <bdi dir="ltr"><code>shared-demo-key-9921</code></bdi>')

    def test_arabic_from_the_switch_only_arabic(self):
        r = self.client.get("/login/?ui=ar&next=/pages/")
        self.assertContains(r, '<html lang="ar" dir="rtl">')
        self.assertContains(r, "يُعاد ضبط كل شيء كل ساعتين")
        self.assertNotContains(r, "Everything resets every 2 hours")
        self.assertNotContains(r, "Demo sign-in")
        self.assertContains(r, 'اسم المستخدم: <bdi dir="ltr"><code>visitor</code></bdi>')
        self.assertContains(r, 'href="?ui=en&amp;next=%2Fpages%2F"')
        self.assertEqual(self.client.session["ui_lang"], "ar")
        # the choice stays for the next visit
        self.assertContains(self.client.get("/login/"), '<html lang="ar" dir="rtl">')

    def test_arabic_browser_gets_arabic(self):
        r = self.client.get("/login/", HTTP_ACCEPT_LANGUAGE="ar-JO,ar;q=0.9,en;q=0.8")
        self.assertContains(r, '<html lang="ar" dir="rtl">')

    def test_unsafe_next_is_dropped_from_the_switch(self):
        r = self.client.get("/login/?next=https://evil.example/")
        self.assertContains(r, 'href="?ui=ar"')
        self.assertNotContains(r, "evil.example")

    def test_wrong_password_message_in_arabic(self):
        self.client.get("/login/?ui=ar")
        r = self.client.post("/login/", {"username": "nobody", "password": "wrong-password-1"})
        self.assertContains(r, "اسم المستخدم أو كلمة المرور غير صحيحة.")

    @override_settings(TECHNTING_CMS_DEMO_MODE=False)
    def test_no_demo_note_outside_demo_mode(self):
        r = self.client.get("/login/")
        self.assertNotContains(r, 'class="msg warning demo-note"')
        self.assertNotContains(r, "shared-demo-key-9921")
