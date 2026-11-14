"""Technting Forms. Run: manage.py test formbuilder

The tests run against the sample "Website check" form (formbuilder/sample.py): structure, scoring, rules, the public
API, personal links, the dashboard pages and rendering on a site page.
"""
import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail as djmail
from django.core.cache import cache
from django.core.mail.backends.locmem import EmailBackend
from django.test import TestCase, override_settings
from django.utils import timezone

from crm.models import Activity, Contact, Deal, Organization

from . import engine, expr, sample
from .models import Field, Form, FormEvent, RecipientLink, Submission
from .retention import prune

SITE, ADMIN = "https://example.com", "https://cms.example.com"
SLUG = sample.SLUG
PROFILE = {"P1": "Lina Haddad", "P2": "Acme Trading", "P3": "us", "P4": "lina@acme-trading.example", "P5": "+1 555 010 0100",
           "C1": True}


def answers(**over):
    """Profile + every question at option o2, then the overrides (key=option key)."""
    a = dict(PROFILE)
    a.update({k: "o2" for k in sample.ALL_Q})
    a.update(over)
    return a


def scored(spec, a, lang="en"):
    clean, errors = spec.clean(a, final=True)
    assert not errors, errors
    calcs, calc_errors = spec.compute(clean, lang)
    assert not calc_errors, calc_errors
    return clean, calcs


class Scoring(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.form = sample.build(site_url=SITE)

    def setUp(self):
        self.spec = engine.Spec(self.form)

    def verify_keys(self, clean, calcs):
        blocks = self.spec.results(clean, calcs, "en")
        v = [b for b in blocks if b["t"] == "verify"]
        return [i["key"] for i in v[0]["items"]] if v else []

    def test_defaults(self):
        clean, c = scored(self.spec, answers())
        self.assertEqual((c["A_raw"], c["A_score"], c["A_band"]), (6, 67, "good"))
        self.assertEqual((c["B_raw"], c["B_score"], c["B_band"]), (6, 67, "good"))
        self.assertEqual((c["avg"], c["weakest"], c["unknowns"]), (67, "content", 0))   # tie: first part
        self.assertEqual(self.verify_keys(clean, c), [])

    def test_all_threes(self):
        clean, c = scored(self.spec, answers(**{k: "o3" for k in sample.ALL_Q}))
        self.assertEqual((c["A_score"], c["B_score"]), (100, 100))
        self.assertEqual([c["A_band"], c["B_band"]], ["strong"] * 2)
        self.assertEqual((c["lead_total"], c["lead_band"]), (18, "hot"))

    def test_all_dont_know(self):
        clean, c = scored(self.spec, answers(**{k: "dk" for k in sample.ALL_Q}))
        self.assertEqual((c["A_score"], c["B_score"], c["A_band"]), (0, 0, "weak"))
        self.assertEqual(c["unknowns"], 6)
        self.assertEqual(self.verify_keys(clean, c), sample.ALL_Q)
        blocks = self.spec.results(clean, c, "en")
        self.assertTrue(any("rough guide" in b.get("html", "") for b in blocks))      # the >= 3 unknowns line

    def test_verify_lists_zero_and_unknown(self):
        clean, c = scored(self.spec, answers(A1="o0", A2="none", B2="dk"))
        self.assertEqual(self.verify_keys(clean, c), ["A1", "A2", "B2"])
        blocks = self.spec.results(clean, c, "en")
        self.assertTrue(any("a short post every month" in b.get("html", "") for b in blocks))

    def test_bands_at_thresholds(self):
        env = self.spec.env({})
        for score, band in ((0, "weak"), (25, "weak"), (26, "fair"), (50, "fair"), (51, "good"), (75, "good"),
                            (76, "strong"), (100, "strong")):
            self.assertEqual(expr.evaluate(f'band({score}, [25, 50, 75], {sample.BANDS!r})'.replace("'", '"'), env), band)

    def test_weakest_by_band_then_score(self):
        _, c = scored(self.spec, answers(A1="o0", A2="o0", A3="o1", B1="o3"))
        self.assertEqual((c["A_band"], c["weakest"]), ("weak", "content"))
        _, c = scored(self.spec, answers(B1="o1"))                   # same band, lower score wins
        self.assertEqual((c["A_score"], c["B_score"], c["weakest"]), (67, 56, "reach"))

    def test_internal_scores_never_reach_results(self):
        clean, c = scored(self.spec, answers(**{k: "o3" for k in sample.ALL_Q}))
        public = self.spec.public_calcs(c)
        self.assertFalse(any(k.startswith("lead_") for k in public))
        text = json.dumps(self.spec.results(clean, c, "en"))
        self.assertNotIn("lead_", text)
        self.assertNotIn("Lead score", text)

    def test_tags(self):
        a = answers(P4="lina@gmail.com", P3="other")
        _, c = scored(self.spec, a)
        self.assertEqual(self.spec.tags(a, c), ["personal-email", "country:other"])
        self.assertEqual(self.spec.tags(answers(), c), [])


class Rules(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.form = sample.build(site_url=SITE)

    def setUp(self):
        self.spec = engine.Spec(self.form)

    def test_option_shown_only_when_rule_matches(self):
        _, errors = self.spec.clean(answers(A1="o1", A2="none"), final=True)
        self.assertIn("A2", errors)
        _, errors = self.spec.clean(answers(A1="o0", A2="none"), final=True)
        self.assertEqual(errors, {})

    def test_required_and_types(self):
        a = answers()
        a.pop("A3")
        a["P4"] = "not-an-email"
        a["C1"] = False
        _, errors = self.spec.clean(a, final=True)
        self.assertEqual(errors.get("A3"), "required")
        self.assertEqual(errors.get("P4"), "invalid")
        self.assertEqual(errors.get("C1"), "required")
        clean, errors = self.spec.clean({"P1": 5, "nope": "x", "A1": "zzz"})
        self.assertNotIn("nope", clean)
        self.assertIn("P1", errors)
        self.assertIn("A1", errors)

    def test_conditional_text(self):
        a1 = self.spec.by_key["A1"]
        self.assertTrue(expr.truthy(a1.texts[0]["if"], self.spec.env({"P3": "other"}), default=False))
        self.assertFalse(expr.truthy(a1.texts[0]["if"], self.spec.env({"P3": "us"}), default=False))

    def test_public_definition_hides_scoring(self):
        data = json.dumps(self.spec.public("en"))
        for secret in ('"score"', "lead_", "calcs", "Lead score", "A_raw"):
            self.assertNotIn(secret, data)
        d = self.spec.public("ar")
        self.assertEqual(d["dir"], "rtl")
        a2 = next(f for s in d["steps"] for f in s["fields"] if f["key"] == "A2")
        none = next(o for o in a2["options"] if o["key"] == "none")
        self.assertEqual(none["if"], {"k": "cmp", "op": "==", "l": {"k": "answer", "v": "A1"}, "r": {"k": "c", "v": "o0"}})
        self.assertEqual(len(d["steps"]), 4)
        self.assertEqual([len(s["fields"]) for s in d["steps"]], [5, 3, 3, 1])


class Expressions(TestCase):
    def test_round_half_up_and_safe_division(self):
        env = expr.Env()
        self.assertEqual(expr.evaluate("round(2.5)", env), 3)
        self.assertEqual(expr.evaluate("round(10 * 100 / 18)", env), 56)
        self.assertEqual(expr.evaluate("5 / 0", env), 0)
        self.assertEqual(expr.evaluate('choose(3, [3, 2], [2, 1], 0) + choose(1, [3, 2], [2, 1], 0)', env), 2)
        self.assertEqual(expr.evaluate('argmin(["a", "b", "c"], [1, 0, 0], [5, 9, 9])', env), "b")

    def test_unsafe_code_is_refused(self):
        for src in ("__import__('os')", "().__class__", "open('x')", "lambda: 1", "[x for x in [1]]", "a.b", "x[0]", "f(**{})"):
            with self.assertRaises(expr.ExprError, msg=src):
                expr.parse(src)

    def test_check_and_client_rules(self):
        self.assertEqual(expr.check('answer("A1") == "o0"', client=True), "")
        self.assertIn("cannot be used here", expr.check('score("A1") > 1', client=True))
        self.assertIn("unknown name", expr.check("A_raw + 1", names=["B_raw"]))
        self.assertEqual(expr.check("A_raw + 1", names=["A_raw"]), "")

    def test_fill_escapes_answers(self):
        env = expr.Env(answers={"P2": "<b>Acme</b> **x**"})
        out = engine.fill('Results: {{ answer("P2") }} **bold** [privacy](https://example.com/privacy/)', env)
        self.assertIn("&lt;b&gt;Acme&lt;/b&gt; **x**", out)
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn('<a href="https://example.com/privacy/">privacy</a>', out)
        self.assertNotIn("<a", engine.fill("[x](javascript:alert(1))", env))


def mail_on():
    return mock.patch.multiple("cms.mail", ready=mock.DEFAULT, connection=mock.DEFAULT)


@override_settings(TECHNTING_CMS_SITE_URL=SITE, TECHNTING_CMS_ADMIN_URL=ADMIN, ALLOWED_HOSTS=["testserver", "cms.example.com"])
class Api(TestCase):
    def setUp(self):
        cache.clear()
        self.form = sample.build(site_url=SITE)
        self.form.status = Form.LIVE
        self.form.save()
        U = get_user_model()
        sales = Group.objects.get_or_create(name="sales")[0]
        self.s1 = U.objects.create_user("sam", "sam@example.com", "pass-word-123456", is_staff=True)
        self.s2 = U.objects.create_user("rana", "rana@example.com", "pass-word-123456", is_staff=True)
        for u in (self.s1, self.s2):
            u.groups.add(sales)
        p = mail_on()
        m = p.start()
        m["ready"].return_value = True
        m["connection"].side_effect = lambda: EmailBackend()
        self.addCleanup(p.stop)

    def post(self, what, body, origin=SITE, slug=SLUG):
        return self.client.post(f"/api/forms/{slug}/{what}", json.dumps(body), content_type="application/json", HTTP_ORIGIN=origin)

    def test_definition_and_cors(self):
        r = self.client.get(f"/api/forms/{SLUG}/?lang=ar", HTTP_ORIGIN=SITE)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Access-Control-Allow-Origin"], SITE)
        self.assertEqual(r.json()["form"]["dir"], "rtl")
        r = self.client.options(f"/api/forms/{SLUG}/submit", HTTP_ORIGIN=SITE)
        self.assertEqual(r.status_code, 204)
        self.assertIn("Content-Type", r["Access-Control-Allow-Headers"])
        self.form.status = Form.DRAFT
        self.form.save()
        self.assertEqual(self.client.get(f"/api/forms/{SLUG}/").status_code, 404)

    def test_draft_resume_then_submit_records_before_results(self):
        r = self.post("save", {"answers": {"P1": "Lina", "P4": "lina@acme-trading.example"}, "step": "content", "lang": "en"})
        token = r.json()["token"]
        self.assertTrue(token)
        sub = Submission.objects.get(token=token)
        self.assertEqual((sub.status, sub.step, sub.answers["P1"]), (Submission.DRAFT, "content", "Lina"))
        r = self.post("resume", {"token": token})
        self.assertEqual(r.json()["answers"]["P4"], "lina@acme-trading.example")
        # missing answers: refused, nothing recorded, no results
        r = self.post("submit", {"token": token, "answers": {"P1": "Lina"}, "lang": "en"})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("html", r.json())
        self.assertEqual(Submission.objects.filter(status=Submission.COMPLETE).count(), 0)
        r = self.post("submit", {"token": token, "answers": answers(), "lang": "en", "page": "/check/"})
        self.assertEqual(r.status_code, 200, r.content)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Submission.COMPLETE)
        self.assertIn("fr-scores", r.json()["html"])
        self.assertEqual(sub.calcs["A_score"], 67)
        self.assertTrue(sub.consent_at)
        self.assertIn("I agree", sub.consent_text)
        # cannot be sent twice
        self.assertEqual(self.post("submit", {"token": token, "answers": answers()}).status_code, 409)

    def test_crm_records_owner_rotation_task_and_emails(self):
        self.post("submit", {"answers": answers(), "lang": "en"})
        self.post("submit", {"answers": answers(P1="Omar Ali", P4="omar@other.example", P2="Other Co"), "lang": "ar"})
        s1, s2 = Submission.objects.order_by("pk")
        self.assertEqual({s1.owner, s2.owner}, {self.s1, self.s2})         # takes turns between sales users
        org = Organization.objects.get(name="Acme Trading")
        self.assertEqual((org.domain, org.country), ("acme-trading.example", "United States"))
        c = Contact.objects.get(email="lina@acme-trading.example")
        self.assertEqual((c.name, c.lawful_basis, c.organization), ("Lina Haddad", "consent", org))
        deal = Deal.objects.get(contact=c)
        self.assertEqual((deal.services, deal.owner, deal.source), (["S1"], s1.owner, "website"))
        self.assertTrue(Activity.objects.filter(deal=deal, kind=Activity.ENQUIRY, body__contains="Lead score").exists())
        task = Activity.objects.get(deal=deal, kind=Activity.TASK)
        self.assertIn("Call Lina Haddad about the results", task.subject)
        self.assertEqual(task.assigned_to, s1.owner)
        # two emails per submission: results to the person, a notice to the team (leads@ by default)
        self.assertEqual(len(djmail.outbox), 4)
        team = [m for m in djmail.outbox if m.to == ["leads@example.com"]]
        person = [m for m in djmail.outbox if m.to != ["leads@example.com"]]
        self.assertEqual(len(team), 2)
        self.assertNotIn("Lead score", team[0].body + team[0].alternatives[0][0])
        ar = next(m for m in person if m.to == ["omar@other.example"])
        html = ar.alternatives[0][0]
        self.assertIn('dir="rtl"', html)
        self.assertIn('lang="ar"', html)
        self.assertIn("نتيجة Other Co", html)
        s2.refresh_from_db()
        self.assertTrue(s2.results_emailed_at)

    def test_origin_honeypot_and_rate_limit(self):
        self.assertEqual(self.post("submit", {"answers": answers()}, origin="https://evil.example").status_code, 403)
        r = self.post("submit", {"answers": answers(), "website": "spam"})
        self.assertTrue(r.json()["ok"])
        self.assertEqual(Submission.objects.count(), 0)
        for _ in range(10):
            self.post("submit", {"answers": {"P1": "x"}})
        self.assertEqual(self.post("submit", {"answers": answers()}).status_code, 429)

    def test_turnstile_blocks_public_submit(self):
        with mock.patch("shield.turnstile.check_form", return_value=False) as check:
            r = self.post("submit", {"answers": answers(), "cf-turnstile-response": "bad"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(check.call_args[0][1], "bad")
        self.assertEqual(Submission.objects.count(), 0)
        with mock.patch("shield.turnstile.check_form", return_value=True):
            self.assertEqual(self.post("submit", {"answers": answers()}).status_code, 200)

    def test_staff_preview_records_nothing(self):
        self.client.force_login(self.s1)
        r = self.post("submit", {"answers": answers(), "preview": True}, origin=ADMIN)
        self.assertTrue(r.json()["preview"])
        self.assertEqual(Submission.objects.count(), 0)
        self.assertEqual(len(djmail.outbox), 0)

    def test_step_events_only_with_site_stats(self):
        with mock.patch("cms.stats.enabled", return_value=False):
            self.post("event", {"kind": "step", "step": 2})
        self.assertEqual(FormEvent.objects.count(), 0)
        with mock.patch("cms.stats.enabled", return_value=True):
            for _ in range(3):
                self.post("event", {"kind": "step", "step": 2, "lang": "ar"})
            self.post("event", {"kind": "start"})
        self.assertEqual(FormEvent.objects.get(kind="step", step=2, lang="ar").count, 3)
        self.assertEqual(FormEvent.objects.get(kind="start").count, 1)


@override_settings(TECHNTING_CMS_SITE_URL=SITE, TECHNTING_CMS_ADMIN_URL=ADMIN)
class Links(TestCase):
    def setUp(self):
        cache.clear()
        self.form = sample.build(site_url=SITE)
        self.form.settings = {**self.form.settings, "public": False, "results": "thank_you", "respondent_email": False}
        self.form.save()
        self.org = Organization.objects.create(name="Client Co")
        self.contact = Contact.objects.create(name="Part A person", email="a@client.example", organization=self.org)
        self.deal = Deal.objects.create(title="Client Co: S2", organization=self.org, contact=self.contact)
        self.link = RecipientLink.objects.create(form=self.form, label="Part A", steps=["content"], contact=self.contact, deal=self.deal,
                                                 expires_at=timezone.now() + timedelta(days=10))

    def post(self, what, body):
        return self.client.post(f"/api/forms/{SLUG}/{what}", json.dumps(body), content_type="application/json", HTTP_ORIGIN=ADMIN)

    def test_token_is_long_and_random(self):
        other = RecipientLink.objects.create(form=self.form)
        self.assertGreaterEqual(len(self.link.token), 40)
        self.assertNotEqual(self.link.token, other.token)

    def test_link_page_logs_first_open_and_limits_steps(self):
        r = self.client.get(f"/f/{self.link.token}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-link="' + self.link.token)
        self.assertEqual(r["X-Robots-Tag"], "noindex, nofollow")
        self.client.get(f"/f/{self.link.token}/?lang=ar")
        self.assertEqual(Activity.objects.filter(deal=self.deal, subject__startswith="Questionnaire link opened").count(), 1)
        d = self.client.get(f"/api/forms/{SLUG}/?link={self.link.token}").json()["form"]
        self.assertEqual([s["key"] for s in d["steps"]], ["content"])
        # without the link the form (not public) does not open
        self.assertEqual(self.client.get(f"/api/forms/{SLUG}/").status_code, 404)

    def test_link_submit_needs_no_turnstile_and_joins_the_deal(self):
        a = {k: "o3" for k in sample.QUESTIONS["A"]}
        self.assertEqual(self.post("save", {"link": self.link.token, "answers": {"A1": "o3"}}).json()["token"], "")
        with mock.patch("shield.turnstile.check_form", return_value=False):
            r = self.post("submit", {"link": self.link.token, "answers": a})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["html"], "")                          # this form shows a thank-you, not results
        sub = Submission.objects.get(link=self.link)
        self.assertEqual((sub.status, sub.deal, sub.contact), (Submission.COMPLETE, self.deal, self.contact))
        self.assertEqual(Deal.objects.count(), 1)
        self.assertEqual(self.link.state, "complete")

    def test_revoked_and_expired_links_close(self):
        self.link.revoked_at = timezone.now()
        self.link.save()
        self.assertEqual(self.client.get(f"/f/{self.link.token}/").status_code, 410)
        self.assertEqual(self.post("save", {"link": self.link.token, "answers": {"A1": "o3"}}).status_code, 410)
        self.link.revoked_at, self.link.expires_at = None, timezone.now() - timedelta(minutes=1)
        self.link.save()
        self.assertEqual(self.client.get(f"/f/{self.link.token}/").status_code, 410)
        self.assertEqual(self.client.get("/f/not-a-real-token/").status_code, 404)

    def test_progress(self):
        from .views import link_progress
        self.assertEqual(link_progress(self.link), (0, 3))
        self.post("save", {"link": self.link.token, "answers": {"A1": "o3", "A2": "dk"}})
        self.assertEqual(link_progress(self.link), (2, 3))


class Retention(TestCase):
    def test_old_answers_and_drafts_are_deleted(self):
        form = Form.objects.create(slug="f", settings={"retention_months": 24, "draft_days": 30})
        now = timezone.now()
        old = Submission.objects.create(form=form, status=Submission.COMPLETE, completed_at=now - timedelta(days=800))
        keep = Submission.objects.create(form=form, status=Submission.COMPLETE, completed_at=now - timedelta(days=600))
        draft = Submission.objects.create(form=form)
        Submission.objects.filter(pk=draft.pk).update(updated_at=now - timedelta(days=31))
        fresh = Submission.objects.create(form=form)
        self.assertEqual(prune(), (1, 1))
        self.assertEqual(set(Submission.objects.values_list("pk", flat=True)), {keep.pk, fresh.pk})
        self.assertFalse(Submission.objects.filter(pk=old.pk).exists())


@override_settings(TECHNTING_CMS_THEME="technting", TECHNTING_CMS_ADMIN_URL=ADMIN)
class Rendering(TestCase):
    def test_form_block_on_an_arabic_page(self):
        from cms.fields import clean_blocks
        from cms.models import Language, Page, PageTranslation
        from cms.render import RenderContext
        from cms.theme import load_theme
        theme = load_theme("technting")
        Language.objects.create(code="en", name="English", native_name="English", is_default=True)
        ar = Language.objects.create(code="ar", name="Arabic", native_name="العربية", direction="rtl", url_prefix="ar", order=1)
        p = Page.objects.create(key="check", template="default")
        t = PageTranslation.objects.create(page=p, language=ar, title="الفحص", slug="check", status=PageTranslation.PUBLISHED,
                                           blocks=clean_blocks(theme, [{"id": "f1", "type": "form_embed", "data": {"form": SLUG}}]))
        html = RenderContext(theme=theme).render(t)
        self.assertIn('dir="rtl"', html)
        self.assertIn(f'data-api="{ADMIN}/api/forms/"', html)
        self.assertIn(f'data-slug="{SLUG}" data-lang="ar"', html)
        self.assertIn("js/form-runner.js", html)
        self.assertIn("css/forms.css", html)

    def test_results_html_web_and_email(self):
        form = sample.build(site_url=SITE)
        spec = engine.Spec(form)
        clean, c = scored(spec, answers())
        blocks = spec.results(clean, c, "ar")
        web = engine.to_html(blocks)
        self.assertIn('class="fr-scores"', web)
        self.assertIn("المحتوى: جيد.", web)
        self.assertIn("/ar/contact/", web)                         # booking link placeholder until the real link is set
        mailhtml = engine.to_email_html(blocks, "ar")
        self.assertTrue(mailhtml.startswith('<!doctype html><html lang="ar" dir="rtl">'))
        self.assertNotIn("<style", mailhtml)
        form.settings["booking_url"] = "https://book.example/45"
        spec = engine.Spec(form)
        self.assertIn("https://book.example/45", engine.to_html(spec.results(clean, c, "en")))


@override_settings(TECHNTING_CMS_SITE_URL=SITE, TECHNTING_CMS_ADMIN_URL=ADMIN)
class Dashboard(TestCase):
    def setUp(self):
        U = get_user_model()
        self.admin = U.objects.create_superuser("boss", "boss@example.com", "pass-word-123456")
        self.sales = U.objects.create_user("sam", "sam@example.com", "pass-word-123456", is_staff=True)
        self.sales.groups.add(Group.objects.get_or_create(name="sales")[0])
        self.form = sample.build(site_url=SITE)
        self.sub = Submission.objects.create(form=self.form, status=Submission.COMPLETE, completed_at=timezone.now(),
                                             answers={**answers(), "P1": "=HYPERLINK(1)"}, calcs={"A_score": 67}, name="=HYPERLINK(1)")

    def test_pages_open(self):
        self.client.force_login(self.admin)
        f = self.form
        field = Field.objects.get(step__form=f, key="A2")
        last = len(f.results["blocks"]) - 1
        for url in ("/forms/", f"/forms/{f.pk}/", f"/forms/{f.pk}/questions/", f"/forms/{f.pk}/questions/{field.pk}/",
                    f"/forms/{f.pk}/calculations/", f"/forms/{f.pk}/results/", f"/forms/{f.pk}/results/0/", f"/forms/{f.pk}/results/{last}/",
                    f"/forms/{f.pk}/preview/?lang=ar", f"/forms/{f.pk}/submissions/", f"/forms/submissions/{self.sub.pk}/",
                    f"/forms/{f.pk}/links/", "/forms/?deal=1"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.sub.calcs = {"A_score": 67, "lead_total": 9}
        self.sub.save()
        self.assertContains(self.client.get(f"/forms/submissions/{self.sub.pk}/"), "Internal pre-score")

    def test_calc_test_tool(self):
        self.client.force_login(self.admin)
        r = self.client.post(f"/forms/{self.form.pk}/calculations/", {"action": "test", "answers": json.dumps(answers()), "lang": "en"})
        self.assertContains(r, "lead_total")
        self.assertContains(r, "fr-scores")

    def test_sales_reads_but_cannot_edit(self):
        self.client.force_login(self.sales)
        self.assertEqual(self.client.get(f"/forms/{self.form.pk}/submissions/").status_code, 200)
        r = self.client.post(f"/forms/{self.form.pk}/calculations/", {"c_name": ["x"], "c_expr": ["1"], "c_label": [""],
                                                                       "c_internal": ["0"], "c_delete": ["0"]})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get(f"/forms/{self.form.pk}/export.csv").status_code, 403)

    def test_edit_option_values_and_rules(self):
        self.client.force_login(self.admin)
        field = Field.objects.get(step__form=self.form, key="B3")
        opts = list(field.options.all())
        data = {"key": "B3", "type": "radio", "label_en": "Newsletter?", "label_ar": "النشرة؟", "required": "1", "visible_if": "score(\"A1\") > 1",
                "step": field.step_id, "o_id": [o.pk for o in opts] + [""], "o_key": [o.key for o in opts] + ["extra"],
                "o_label_en": ["a"] * len(opts) + ["New"], "o_label_ar": ["ب"] * len(opts) + ["جديد"],
                "o_values": ["score=0"] * len(opts) + ["score=2, extent=1"], "o_unknown": ["0"] * len(opts) + ["0"],
                "o_if": [""] * (len(opts) + 1), "o_delete": ["0"] * len(opts) + ["0"]}
        r = self.client.post(f"/forms/{self.form.pk}/questions/{field.pk}/", data, follow=True)
        self.assertContains(r, "cannot be used here")                       # a browser rule may not read scores
        field.refresh_from_db()
        self.assertEqual(field.label, {"en": "Newsletter?", "ar": "النشرة؟"})
        self.assertEqual(field.options.get(key="extra").values, {"score": 2, "extent": 1})
        v = self.form.version
        self.form.refresh_from_db()
        self.assertGreater(self.form.version, v)

    def test_duplicate_and_export(self):
        self.client.force_login(self.admin)
        self.client.post(f"/forms/{self.form.pk}/duplicate/")
        copy = Form.objects.get(slug=f"{SLUG}-copy")
        self.assertEqual((copy.status, Field.objects.filter(step__form=copy).count()), (Form.DRAFT, 12))
        self.assertEqual(copy.calcs, self.form.calcs)
        r = self.client.get(f"/forms/{self.form.pk}/export.csv")
        body = r.content.decode("utf-8-sig")
        self.assertIn("'=HYPERLINK(1)", body)                               # formulas in answers cannot run in a spreadsheet
        self.assertIn("A_score", body.splitlines()[0])

    def test_create_and_send_link(self):
        self.client.force_login(self.sales)
        org = Organization.objects.create(name="Client")
        c = Contact.objects.create(name="Huda", email="huda@client.example", organization=org)
        deal = Deal.objects.create(title="Client: S2", contact=c, organization=org)
        r = self.client.post(f"/forms/{self.form.pk}/links/", {"label": "Part B", "deal": deal.pk, "steps": ["reach"], "days": "14",
                                                                "language": "ar"})
        link = RecipientLink.objects.get(label="Part B")
        self.assertRedirects(r, f"/forms/links/{link.pk}/")
        self.assertEqual((link.contact, link.steps, link.language), (c, ["reach"], "ar"))
        self.assertTrue(Activity.objects.filter(deal=deal, subject__startswith="Questionnaire link created").exists())
        with mock.patch("cms.mail.ready", return_value=True), mock.patch("cms.mail.connection", side_effect=lambda: EmailBackend()):
            self.client.post(f"/forms/links/{link.pk}/", {"action": "send", "to": "huda@client.example", "message": ""})
        self.assertEqual(len(djmail.outbox), 1)
        self.assertIn(link.url(), djmail.outbox[0].body)
        self.assertIn("مرحباً Huda", djmail.outbox[0].body)
        link.refresh_from_db()
        self.assertEqual(link.sent_to, "huda@client.example")
        r = self.client.get(f"/crm/deals/{deal.pk}/")
        self.assertContains(r, "Part B")
        self.client.post(f"/forms/links/{link.pk}/", {"action": "revoke"})
        link.refresh_from_db()
        self.assertFalse(link.is_usable)
