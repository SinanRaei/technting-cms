"""Relative times in the interface language, and form labels passed through the interface strings."""
from datetime import timedelta

from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone


def render(minutes, lang):
    request = RequestFactory().get("/")
    request.session = {"ui_lang": lang}
    t = Template("{% load cms_i18n %}{% ago when %}")
    return t.render(Context({"when": timezone.now() - timedelta(minutes=minutes), "request": request}))


class AgoTests(SimpleTestCase):
    def test_english(self):
        self.assertEqual(render(25, "en"), "25\xa0minutes ago")
        self.assertEqual(render(0, "en"), "just now")

    def test_arabic(self):
        self.assertEqual(render(25, "ar"), "منذ 25\xa0دقيقة")
        self.assertEqual(render(5, "ar"), "منذ 5\xa0دقائق")
        self.assertEqual(render(2, "ar"), "منذ دقيقتين")
        self.assertEqual(render(1, "ar"), "منذ دقيقة")
        self.assertEqual(render(0, "ar"), "الآن")
        self.assertNotIn("minutes", render(90, "ar"))

    def test_known_form_label_in_arabic(self):
        request = RequestFactory().get("/")
        request.session = {"ui_lang": "ar"}
        out = Template("{% load cms_i18n %}{% tr label %}").render(Context({"label": "Content score", "request": request}))
        self.assertEqual(out, "درجة المحتوى")
        out = Template("{% load cms_i18n %}{% tr label %}").render(Context({"label": "My own label", "request": request}))
        self.assertEqual(out, "My own label")
