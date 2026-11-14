from django import forms
from django.contrib.auth import get_user_model

from .models import CURRENCIES, Contact, Deal, Organization, Prospect


class Translated:
    """Translate labels and choice labels into the dashboard language (cms.ui_i18n)."""

    def translate(self, lang):
        from cms.ui_i18n import tr
        for f in self.fields.values():
            f.label = tr(str(f.label), lang)
            if hasattr(f, "choices"):
                f.choices = [(k, tr(str(v), lang)) for k, v in f.choices]


def staff_users():
    return get_user_model().objects.filter(is_active=True, is_staff=True).order_by("first_name", "username")


class UserChoice(forms.ModelChoiceField):
    def label_from_instance(self, u):
        return u.get_full_name() or u.get_username()


class DealForm(Translated, forms.ModelForm):
    owner = UserChoice(queryset=staff_users(), required=False, label="Owner")
    currency = forms.ChoiceField(choices=[(c, c) for c in CURRENCIES], label="Currency")
    services = forms.CharField(required=False, label="Services (codes, e.g. W1, W4)")

    class Meta:
        model = Deal
        fields = ["title", "organization", "contact", "value", "currency", "probability", "expected_close", "owner",
                  "source", "priority", "lab", "services"]
        labels = {"title": "Deal name", "organization": "Organisation", "contact": "Main contact", "value": "Value",
                  "probability": "Probability (%)", "expected_close": "Expected close", "source": "Source",
                  "priority": "Priority", "lab": "Area"}
        widgets = {"expected_close": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *a, lang="en", **kw):
        super().__init__(*a, **kw)
        self.fields["owner"].queryset = staff_users()
        self.fields["organization"].queryset = Organization.objects.order_by("name")
        self.fields["contact"].queryset = Contact.objects.order_by("name")
        from cms.models import Entry
        from .views import LAB_NAMES
        labs = [(e.key, LAB_NAMES.get(e.key, e.key.capitalize())) for e in Entry.objects.filter(collection="lab").order_by("order")]
        labs = labs or list(LAB_NAMES.items())  # themes without "lab" entries: the areas from cms/areas.py
        if self.instance and self.instance.lab and self.instance.lab not in dict(labs):
            labs.append((self.instance.lab, self.instance.lab.capitalize()))  # keep a stored value the list no longer has
        self.fields["lab"] = forms.ChoiceField(choices=[("", "-")] + labs, required=False, label="Area")
        if self.instance and self.instance.pk:
            self.initial["services"] = ", ".join(self.instance.services or [])
        self.translate(lang)

    def clean_services(self):
        import re
        return [c for c in re.split(r"[\s,;]+", (self.cleaned_data.get("services") or "").upper()) if re.fullmatch(r"[A-Z]{1,3}\d{1,2}", c)][:12]

    def clean_probability(self):
        p = self.cleaned_data.get("probability") or 0
        return max(0, min(100, p))


class ContactForm(Translated, forms.ModelForm):
    owner = UserChoice(queryset=staff_users(), required=False, label="Owner")

    class Meta:
        model = Contact
        fields = ["name", "email", "phone", "job_title", "organization", "language", "source", "lawful_basis",
                  "marketing_opt_in", "linkedin", "owner", "notes"]
        labels = {"name": "Full name", "email": "Email", "phone": "Phone", "job_title": "Job title", "organization": "Organisation",
                  "language": "Preferred language", "source": "Source", "lawful_basis": "Lawful basis for processing",
                  "marketing_opt_in": "Agreed to receive marketing emails", "linkedin": "LinkedIn profile", "notes": "Notes"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 3}),
                   "language": forms.Select(choices=[("", "-"), ("en", "English"), ("ar", "العربية")])}

    def __init__(self, *a, lang="en", **kw):
        super().__init__(*a, **kw)
        self.fields["owner"].queryset = staff_users()
        self.fields["organization"].queryset = Organization.objects.order_by("name")
        self.translate(lang)


class OrganizationForm(Translated, forms.ModelForm):
    owner = UserChoice(queryset=staff_users(), required=False, label="Owner")

    class Meta:
        model = Organization
        fields = ["name", "domain", "website", "industry", "country", "size", "owner", "notes"]
        labels = {"name": "Organisation name", "domain": "Email domain (for matching enquiries)", "website": "Website",
                  "industry": "Industry", "country": "Country", "size": "Size (employees)", "notes": "Notes"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *a, lang="en", **kw):
        super().__init__(*a, **kw)
        self.fields["owner"].queryset = staff_users()
        self.translate(lang)

    def clean_domain(self):
        d = (self.cleaned_data.get("domain") or "").lower().strip()
        return d.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]


class ProspectForm(Translated, forms.ModelForm):
    owner = UserChoice(queryset=staff_users(), required=False, label="Owner")
    services = forms.CharField(required=False, label="Suggested services (codes, e.g. W4, C1)")

    class Meta:
        model = Prospect
        fields = ["name", "name_ar", "country", "city", "sector", "sub_sector", "size_band", "ownership", "listed_on", "website",
                  "email", "email_source", "email_verified", "phone", "phone_source", "phone_verified", "contact_page", "linkedin",
                  "officer", "fit_score", "priority", "services", "fit_reason", "fit_source", "checked_on", "owner", "notes"]
        labels = {"name": "Company name", "name_ar": "Arabic name", "country": "Country", "city": "City", "sector": "Sector",
                  "sub_sector": "Sub-sector", "size_band": "Size (as published)", "ownership": "Ownership", "listed_on": "Listed on",
                  "website": "Website", "email": "Company email (as published)", "email_source": "Page where the email was found",
                  "email_verified": "Email seen on the company's own site", "phone": "Main phone (as published)",
                  "phone_source": "Page where the phone was found", "phone_verified": "Phone seen on the company's own site",
                  "contact_page": "Contact page or form", "linkedin": "LinkedIn company page",
                  "officer": "Named officer (only if on their own site)", "fit_score": "Fit score (1-5)", "priority": "Priority",
                  "fit_reason": "Why they fit", "fit_source": "Source for why they fit", "checked_on": "Date checked", "notes": "Notes"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 3}), "fit_reason": forms.Textarea(attrs={"rows": 3}),
                   "checked_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *a, lang="en", **kw):
        super().__init__(*a, **kw)
        self.fields["owner"].queryset = staff_users()
        if self.instance and self.instance.pk:
            self.initial["services"] = ", ".join(self.instance.services or [])
        self.translate(lang)

    def clean_services(self):
        import re
        return [c for c in re.split(r"[\s,;+]+", (self.cleaned_data.get("services") or "").upper()) if re.fullmatch(r"[A-Z]{1,3}\d{1,2}", c)][:12]

    def clean_fit_score(self):
        return max(1, min(5, self.cleaned_data.get("fit_score") or 3))

    def clean_email(self):
        e = (self.cleaned_data.get("email") or "").strip()
        if e and "@" not in e:
            raise forms.ValidationError("Enter an email address.")
        return e
