"""Prospect list: import, move to leads, and the "already in the CRM" check. Run: manage.py test crm"""
import json
import tempfile

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from crm.models import Activity, Contact, Deal, Organization, Prospect, Stage

ROW = {"name": "Sample Bank", "name_ar": "البنك النموذجي", "country": "Exampleland", "city": "Exampleville", "sector": "Banking",
       "website": "https://www.samplebank.example/", "email": "info@samplebank-mail.example", "email_source": "https://www.samplebank.example/contact",
       "email_verified": True, "phone": "+44 20 560 0000", "phone_verified": True, "fit_score": 5, "priority": "A",
       "fit_reason": "Runs a startup programme", "services": ["W4", "C1"], "checked_on": "2026-10-22", "notes": "test"}


def prospect(**kw):
    data = {"name": "Sample Bank", "country": "Exampleland", "sector": "Banking", "website": "https://www.samplebank.example/",
            "domain": "samplebank.example", "email": "info@samplebank-mail.example", "phone": "+44 20 560 0000", "fit_score": 5,
            "priority": "A", "services": ["W4", "C1"], "fit_reason": "Runs a startup programme"}
    data.update(kw)
    return Prospect.objects.create(**data)


class ImportTests(TestCase):
    def run_import(self, rows):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(rows, f)
        call_command("crm_import_prospects", f.name, stdout=open(tempfile.mktemp(), "w"))

    def test_import_then_reimport_updates_and_keeps_dashboard_fields(self):
        self.run_import([ROW, {**ROW, "name": "No site", "website": "", "contact_page": ""}])
        self.assertEqual(Prospect.objects.count(), 1)                      # row without site or contact page skipped
        p = Prospect.objects.get()
        self.assertEqual((p.domain, p.priority, p.services, str(p.checked_on)), ("samplebank.example", "A", ["W4", "C1"], "2026-10-22"))
        p.status, p.notes = Prospect.HOLD, "called reception"
        p.save()
        self.run_import([{**ROW, "fit_score": 4}])
        p.refresh_from_db()
        self.assertEqual(Prospect.objects.count(), 1)
        self.assertEqual((p.fit_score, p.status, p.notes), (4, Prospect.HOLD, "called reception"))
        self.assertEqual(Deal.objects.count(), 0)                           # importing never creates leads


class MoveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("owner", "owner@example.com", "x")
        self.client.force_login(self.user)
        self.url = reverse("crm:prospect_move")

    def move(self, ids, fetch=True, **extra):
        headers = {"HTTP_X_REQUESTED_WITH": "fetch"} if fetch else {}
        return self.client.post(self.url, {"ids": ids, "next": reverse("crm:prospects"), **extra}, **headers)

    def test_new_company_becomes_a_lead_with_research(self):
        p = prospect()
        r = self.move([p.pk])
        deal = Deal.objects.get()
        self.assertEqual(r.json()["redirect"], reverse("crm:deal", args=[deal.pk]))
        self.assertEqual((deal.stage, deal.source, deal.priority, deal.lab, deal.services, deal.owner),
                         (Stage.NEW, "outbound", "high", "websites", ["W4", "C1"], self.user))
        self.assertEqual(deal.organization.domain, "samplebank.example")
        self.assertEqual((deal.contact.email, deal.contact.lawful_basis, deal.contact.marketing_opt_in),
                         ("info@samplebank-mail.example", "legitimate", False))
        self.assertIn("Runs a startup programme", deal.activities.get(kind=Activity.SYSTEM).body)
        self.assertTrue(deal.activities.filter(kind=Activity.TASK, assigned_to=self.user).exists())
        p.refresh_from_db()
        self.assertEqual((p.status, p.deal), (Prospect.MOVED, deal))
        self.move([p.pk])                                                    # moving twice does nothing
        self.assertEqual(Deal.objects.count(), 1)

    def test_existing_organisation_opens_popup_and_creates_nothing(self):
        org = Organization.objects.create(name="Sample Bank PLC", domain="samplebank.example")
        old = Deal.objects.create(title="Sample Bank: workshop", organization=org, stage=Stage.DISCOVERY)
        p = prospect()
        r = self.move([p.pk])
        data = r.json()
        self.assertTrue(data["dupes"])
        self.assertIn("Sample Bank PLC", data["html"])
        self.assertIn(f'value="link:{old.pk}"', data["html"])
        self.assertEqual(Deal.objects.count(), 1)
        p.refresh_from_db()
        self.assertEqual(p.status, Prospect.OPEN)

    def test_without_javascript_the_popup_is_a_page(self):
        Organization.objects.create(name="The Sample Bank P.L.C.", domain="")  # matched by name, legal words ignored
        p = prospect()
        r = self.move([p.pk], fetch=False)
        self.assertContains(r, "already in the CRM")

    def test_link_to_existing_deal_adds_research_only(self):
        org = Organization.objects.create(name="Sample Bank PLC", domain="samplebank.example")
        old = Deal.objects.create(title="Sample Bank: workshop", organization=org, stage=Stage.DISCOVERY)
        p = prospect()
        self.move([p.pk], decided="1", **{f"dec_{p.pk}": f"link:{old.pk}"})
        self.assertEqual(Deal.objects.count(), 1)
        self.assertIn("Runs a startup programme", old.activities.get(kind=Activity.NOTE).body)
        p.refresh_from_db()
        self.assertEqual((p.status, p.deal), (Prospect.MOVED, old))

    def test_new_lead_anyway_reuses_organisation_and_contact(self):
        org = Organization.objects.create(name="Sample Bank PLC", domain="samplebank.example")
        c = Contact.objects.create(name="Sample Bank inbox", email="INFO@samplebank-mail.example", organization=org)
        p = prospect()
        self.move([p.pk], decided="1", **{f"dec_{p.pk}": "new"})
        deal = Deal.objects.get()
        self.assertEqual((deal.organization, deal.contact), (org, c))
        self.assertEqual((Organization.objects.count(), Contact.objects.count()), (1, 1))

    def test_same_phone_in_another_format_is_found(self):
        Contact.objects.create(name="Switchboard", phone="020 5600000")
        p = prospect(website="", domain="", email="")
        data = self.move([p.pk]).json()
        self.assertTrue(data["dupes"])
        self.assertIn("Switchboard", data["html"])

    def test_skip_and_do_not_contact(self):
        Organization.objects.create(name="Sample Bank", domain="samplebank.example")
        dupe = prospect()
        clean = prospect(name="Citrus Telecom", website="https://www.citrus.example", domain="citrus.example", email="info@citrus.example", phone="")
        blocked = prospect(name="Zinc Telecom", website="https://zinc.example", domain="zinc.example", email="", phone="",
                           status=Prospect.DO_NOT_CONTACT)
        data = self.move([dupe.pk, clean.pk, blocked.pk]).json()
        self.assertIn(f'name="dec_{clean.pk}" value="new"', data["html"])  # clean ones still move after the popup
        self.assertIn("Zinc Telecom", data["html"])
        self.move([dupe.pk, clean.pk, blocked.pk], decided="1", **{f"dec_{dupe.pk}": "skip", f"dec_{clean.pk}": "new"})
        self.assertEqual(list(Deal.objects.values_list("organization__name", flat=True)), ["Citrus Telecom"])
        self.assertEqual(Prospect.objects.get(pk=blocked.pk).status, Prospect.DO_NOT_CONTACT)
        self.assertEqual(Prospect.objects.get(pk=dupe.pk).status, Prospect.OPEN)

    def test_status_change_and_admin_delete(self):
        a, b = prospect(), prospect(name="Citrus Telecom", domain="citrus.example")
        self.client.post(reverse("crm:prospect_status"), {"ids": [a.pk, b.pk], "status": "dnc"})
        self.assertEqual(set(Prospect.objects.values_list("status", flat=True)), {Prospect.DO_NOT_CONTACT})
        self.client.post(reverse("crm:prospect_status"), {"ids": [a.pk], "status": "delete"})
        self.assertEqual(Prospect.objects.count(), 1)

    def test_pages_render_in_english_and_arabic(self):
        p = prospect(name_ar="البنك النموذجي")
        for lang in ("en", "ar"):
            s = self.client.session
            s["ui_lang"] = lang
            s.save()
            for url in (reverse("crm:prospects"), reverse("crm:prospect", args=[p.pk]), reverse("crm:prospect_edit", args=[p.pk]),
                        reverse("crm:prospect_new"), reverse("crm:prospects") + "?status=all&priority=A&country=Exampleland"):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200, url)
        self.assertContains(self.client.get(reverse("crm:prospects")), "شركات مستهدفة")

    def test_sales_role_can_move_but_not_delete(self):
        sales = User.objects.create_user("rep", password="x", is_staff=True)
        sales.groups.add(Group.objects.get_or_create(name="sales")[0])
        self.client.force_login(sales)
        p = prospect()
        self.client.post(reverse("crm:prospect_status"), {"ids": [p.pk], "status": "delete"})
        self.assertEqual(Prospect.objects.count(), 1)
        self.move([p.pk])
        self.assertEqual(Deal.objects.get().owner, sales)


class PageTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("owner", "owner@example.com", "x"))
        Prospect.objects.bulk_create([Prospect(name=f"Company {i:03d}", country="Qatar", priority="B") for i in range(60)])
        self.url = reverse("crm:prospects")

    def names(self, r):
        return [p.name for p in r.context["rows"]]

    def test_fifty_per_page_by_default_and_a_second_page(self):
        r = self.client.get(self.url)
        self.assertEqual(len(self.names(r)), 50)
        self.assertContains(r, "page=2")
        r2 = self.client.get(self.url + "?page=2")
        self.assertEqual(len(self.names(r2)), 10)
        self.assertFalse(set(self.names(r)) & set(self.names(r2)))

    def test_page_size_is_chosen_and_remembered(self):
        r = self.client.get(self.url + "?per=25&country=Qatar")
        self.assertEqual((len(self.names(r)), r.context["page"].paginator.num_pages), (25, 3))
        self.assertIn("country=Qatar", r.context["keep"])                     # filters stay when changing page
        self.assertEqual(len(self.names(self.client.get(self.url))), 25)       # remembered without ?per
        self.assertEqual(len(self.names(self.client.get(self.url + "?per=7"))), 25)  # only the offered sizes

    def test_out_of_range_page_shows_the_last_page(self):
        r = self.client.get(self.url + "?per=25&page=99")
        self.assertEqual(r.context["page"].number, 3)

    def test_page_numbers_collapse_with_gaps(self):
        from django.core.paginator import Paginator
        from crm.prospects import _page_numbers
        page = Paginator(range(400), 20).get_page(10)
        self.assertEqual(_page_numbers(page), [1, None, 8, 9, 10, 11, 12, None, 20])


class UnverifiedTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("owner", "owner@example.com", "x"))
        self.p = prospect()

    def test_add_and_delete_an_entry_on_the_company_page(self):
        url = reverse("crm:prospect", args=[self.p.pk])
        self.client.post(url, {"action": "unv_add", "role": "Chief Digital Officer", "name": "Rana Haddad", "email": "cdo@samplebank.example",
                               "source": "https://www.samplebank.example/annual-report.pdf", "source_kind": "annual report"})
        self.client.post(url, {"action": "unv_add", "role": "", "name": "", "email": "", "phone": ""})   # empty: refused
        self.p.refresh_from_db()
        self.assertEqual(len(self.p.unverified), 1)
        e = self.p.unverified[0]
        self.assertEqual((e["type"], e["source_kind"]), ("person", "annual report"))
        r = self.client.get(url)
        self.assertContains(r, "cdo@samplebank.example")
        self.client.post(url, {"action": "unv_delete", "item": e["id"]})
        self.p.refresh_from_db()
        self.assertEqual(self.p.unverified, [])

    def test_import_merges_entries_without_touching_other_fields(self):
        self.p.status, self.p.fit_score = Prospect.HOLD, 5
        self.p.save()
        rows = [{"country": "Exampleland", "name": "Sample Bank", "website": "https://www.samplebank.example/", "fit_score": 1,
                 "unverified": [{"type": "company", "role": "Procurement", "email": "tenders@samplebank.example", "source": "https://x"},
                                {"type": "company", "role": "Procurement", "email": "tenders@samplebank.example"},   # same again
                                {"type": "person", "name": "", "email": "not-an-email"},                    # nothing usable
                                {"type": "company", "role": "Supplier registration", "source": "https://www.samplebank.example/suppliers"},
                                {"type": "company", "role": "Tenders", "source": "not a link"}]}]           # no link: dropped
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(rows, f)
        for _ in range(2):  # running twice adds nothing new
            call_command("crm_import_prospects", f.name, "--unverified-only", stdout=open(tempfile.mktemp(), "w"))
        self.p.refresh_from_db()
        self.assertEqual([(e["email"], e["role"]) for e in self.p.unverified],
                         [("tenders@samplebank.example", "Procurement"), ("", "Supplier registration")])
        self.assertEqual((self.p.status, self.p.fit_score), (Prospect.HOLD, 5))

    def test_entries_travel_to_the_deal_timeline_as_unverified(self):
        services_merge = __import__("crm.services", fromlist=["merge_unverified"]).merge_unverified
        services_merge(self.p, [{"role": "CISO", "name": "Sam Example", "phone": "+44 20 000 0000"}])
        self.p.save()
        self.client.post(reverse("crm:prospect_move"), {"ids": [self.p.pk]}, HTTP_X_REQUESTED_WITH="fetch")
        body = Deal.objects.get().activities.get(kind=Activity.SYSTEM).body
        self.assertIn("Unverified info (check before use):", body)
        self.assertIn("CISO - Sam Example: +44 20 000 0000", body)


class ImportExportTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("owner", "owner@example.com", "x")
        self.client.force_login(self.admin)

    def upload(self, name, data, mode="update"):
        from django.core.files.uploadedfile import SimpleUploadedFile
        r = self.client.post(reverse("crm:prospects_import"), {"file": SimpleUploadedFile(name, data), "mode": mode})
        self.assertEqual(r.status_code, 200)
        return r

    def confirm(self, r):
        return self.client.post(reverse("crm:prospects_import"), {"token": r.context["token"]})

    def test_export_then_import_round_trip_changes_nothing(self):
        from crm.services import merge_unverified
        p = prospect(name_ar="البنك النموذجي", fit_reason="=HYPERLINK(\"x\")", status=Prospect.HOLD, notes="called")
        merge_unverified(p, [{"type": "person", "role": "CIO", "name": "Rana", "email": "cio@samplebank.example", "source": "https://x"},
                             {"type": "company", "role": "Switchboard", "phone": "+44 20 560 0001"}])
        p.save()
        for fmt in ("xlsx", "csv"):
            r = self.client.get(reverse("crm:prospects_export") + f"?status=all&format={fmt}")
            self.assertEqual(r.status_code, 200)
            data = r.content
            if fmt == "csv":
                self.assertIn("'=HYPERLINK", data.decode("utf-8"))       # formulas never run when the file is opened
            prev = self.upload(f"export.{fmt}", data)
            res = prev.context["preview"]
            self.assertEqual((res.added, res.updated, res.skipped, res.entries), (0, 1, 0, 0), fmt)   # no duplicates
            self.confirm(prev)
            p.refresh_from_db()
            self.assertEqual((p.status, p.notes, p.name_ar, len(p.unverified)), (Prospect.HOLD, "called", "البنك النموذجي", 2), fmt)
            self.assertEqual((p.phone, p.fit_reason), ("+44 20 560 0000", '=HYPERLINK("x")'), fmt)  # guard mark removed again

    def test_xlsx_import_adds_companies_and_unverified_sheet(self):
        from openpyxl import Workbook
        import io
        wb = Workbook()
        ws = wb.active
        ws.title = "Companies"
        ws.append(["Company (EN)", "Country", "Website", "Company email (as published)", "Email verified?", "Fit score (1-5)",
                   "Priority", "Suggested first service(s)", "Status (sales team)"])
        ws.append(["Citrus Telecom", "Exampleland", "https://www.citrus.example", "info@citrus.example", "Yes", 4, "B", "M2 Campaign + S2 Support", None])
        ws.append(["", "Exampleland", "https://nameless.example"])                        # no name: skipped with a reason
        us = wb.create_sheet("Unverified info")
        us.append(["Country", "Company", "Type", "Role", "Name", "Email", "Source"])
        us.append(["Exampleland", "Citrus Telecom", "Person", "CIO", "Test Person", "cio@citrus.example", "https://www.citrus.example/about"])
        buf = io.BytesIO()
        wb.save(buf)
        prev = self.upload("research.xlsx", buf.getvalue())
        res = prev.context["preview"]
        self.assertEqual((res.added, res.skipped, res.entries), (1, 1, 1))
        self.assertEqual(res.errors, [(3, "no company name")])
        self.assertEqual(Prospect.objects.count(), 0)                         # preview saves nothing
        self.confirm(prev)
        p = Prospect.objects.get()
        self.assertEqual((p.services, p.email_verified, p.fit_score, p.domain), (["M2", "S2"], True, 4, "citrus.example"))
        self.assertEqual(p.unverified[0]["email"], "cio@citrus.example")
        self.assertEqual(self.confirm(prev).status_code, 302)                 # a used preview cannot be saved twice
        self.assertEqual(Prospect.objects.count(), 1)

    def test_add_only_mode_and_moved_company_keeps_status(self):
        p = prospect(status=Prospect.MOVED)
        csv_text = "Company,Country,Website,Status\nSample Bank,Exampleland,https://www.samplebank.example/,Do not contact\nZinc,Exampleland,https://zinc.example,\n"
        res = self.upload("x.csv", csv_text.encode("utf-8"), mode="add").context["preview"]
        self.assertEqual((res.added, res.updated, res.skipped), (1, 0, 1))
        self.confirm(self.upload("x.csv", csv_text.encode("utf-8"), mode="update"))
        p.refresh_from_db()
        self.assertEqual(p.status, Prospect.MOVED)

    def test_bad_files_and_permissions(self):
        r = self.upload("notes.txt", b"hello")
        self.assertContains(r, "Use an Excel (.xlsx), CSV or JSON file.")
        r = self.upload("broken.xlsx", b"not a zip")
        self.assertContains(r, "Not a valid Excel file")
        sales = User.objects.create_user("rep", password="x", is_staff=True)
        sales.groups.add(Group.objects.get_or_create(name="sales")[0])
        self.client.force_login(sales)
        self.assertEqual(self.client.get(reverse("crm:prospects_export")).status_code, 403)
        self.assertEqual(self.client.get(reverse("crm:prospects_import")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("crm:prospects")), reverse("crm:prospects_import"))

    def test_unverified_contacts_workbook_merges_entries_only(self):
        from openpyxl import Workbook
        import io
        p = prospect()
        wb = Workbook()
        ws = wb.active
        ws.title = "Unverified info"
        ws.append(["Country", "Company", "Type", "Role", "Name", "Email (as published)", "Phone (as published)", "Source URL"])
        ws.append(["Exampleland", "Sample Bank", "Company channel", "Procurement", "", "tenders@samplebank.example", "", "https://www.samplebank.example/t"])
        ws.append(["Exampleland", "Unknown Co", "Person", "CIO", "X", "cio@unknown.example", "", "https://u"])
        buf = io.BytesIO()
        wb.save(buf)
        res = self.upload("unverified.xlsx", buf.getvalue(), mode="unverified").context["preview"]
        self.assertEqual((res.added, res.updated, res.skipped, res.entries), (0, 1, 1, 1))
        self.confirm(self.upload("unverified.xlsx", buf.getvalue(), mode="unverified"))
        p.refresh_from_db()
        self.assertEqual([(e["role"], e["email"]) for e in p.unverified], [("Procurement", "tenders@samplebank.example")])
