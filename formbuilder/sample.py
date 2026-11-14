"""A small sample questionnaire: a two-part "Website check" with scores, bands, tags and a results page.

It shows what Technting Forms can do (steps, choice values, calculations, internal scores, conditional options and
texts, results blocks, CRM mapping) and is the fixture the formbuilder tests run against. Create it from the shell:

    python manage.py shell -c "from formbuilder import sample; sample.build()"

Every text is bilingual ({"en", "ar"}); edit the copy in the dashboard (Forms) after creating it.
"""
SLUG = "website-check"
BANDS = ["weak", "fair", "good", "strong"]
PARTS = [("A", "content"), ("B", "reach")]
QUESTIONS = {"A": ["A1", "A2", "A3"], "B": ["B1", "B2", "B3"]}
ALL_Q = [k for p, _ in PARTS for k in QUESTIONS[p]]
COUNTRIES = ["us", "uk", "other"]
STD = [("o0", 0), ("o1", 1), ("o2", 2), ("o3", 3)]
EXTRA = {"A2": [("none", 0)]}                                     # shown only when A1 is "o0"
OPTION_IF = {("A2", "none"): 'answer("A1") == "o0"'}

T = {
    "title": ("Website check", "فحص الموقع"),
    "intro": ("Six short questions about your website. You get your scores at the end.",
              "ستة أسئلة قصيرة عن موقعكم. تظهر النتيجة في النهاية."),
    "step.profile": ("About you", "عنكم"),
    "step.content": ("Content", "المحتوى"),
    "step.reach": ("Reach", "الوصول"),
    "step.consent": ("Consent", "الموافقة"),
    "P1": ("Your name", "الاسم"), "P2": ("Company", "الشركة"), "P3": ("Country", "الدولة"),
    "P4": ("Work email", "البريد الإلكتروني للعمل"), "P5": ("Phone", "الهاتف"),
    "P3.us": ("United States", "الولايات المتحدة"), "P3.uk": ("United Kingdom", "المملكة المتحدة"), "P3.other": ("Other", "أخرى"),
    "A1": ("How often do you publish new pages or posts?", "كم مرة تنشرون صفحات أو مقالات جديدة؟"),
    "A2": ("Are your pages available in every language your customers use?", "هل صفحاتكم متاحة بكل اللغات التي يستخدمها عملاؤكم؟"),
    "A3": ("Does each page have a clear next step for the reader?", "هل في كل صفحة خطوة تالية واضحة للقارئ؟"),
    "B1": ("Do you check how people find the site (search, social, email)?", "هل تتابعون كيف يصل الناس إلى الموقع (البحث، التواصل الاجتماعي، البريد)؟"),
    "B2": ("Do you collect enquiries and answer them within a day?", "هل تجمعون الاستفسارات وتردّون عليها خلال يوم؟"),
    "B3": ("Do you send a newsletter or updates to subscribers?", "هل ترسلون نشرة أو تحديثات للمشتركين؟"),
    "o0": ("Not at all", "لا، أبداً"), "o1": ("Sometimes", "أحياناً"), "o2": ("Usually", "غالباً"), "o3": ("Always", "دائماً"),
    "dk": ("I don't know", "لا أعرف"), "none": ("We have no pages yet", "ليست لدينا صفحات بعد"),
    "A1.note": ("For example: a short post every month keeps the site fresh.", "مثلاً: مقال قصير كل شهر يبقي الموقع محدّثاً."),
    "C1": ("I agree that my answers are stored to send me the results.", "أوافق على حفظ إجاباتي لإرسال النتيجة إليّ."),
    "r.title": ('Results for {{ answer("P2") }}', 'نتيجة {{ answer("P2") }}'),
    "r.position": ("Weakest part: {{ label(weakest) }}. Average: {{ avg }}.", "الجزء الأضعف: {{ label(weakest) }}. المتوسط: {{ avg }}."),
    "h.verify": ("Worth checking first", "يستحق المراجعة أولاً"),
    "verify.intro": ("These answers were zero or unknown:", "هذه الإجابات كانت صفراً أو غير معروفة:"),
    "verify.empty": ("Nothing stands out.", "لا شيء لافت."),
    "unknowns.line": ("Several answers were \"I don't know\": the scores are a rough guide.",
                      "عدة إجابات كانت «لا أعرف»، لذلك النتيجة تقديرية."),
    "book.label": ("Talk to us", "تحدّثوا معنا"),
    "book.note": ("A short call, no obligation.", "مكالمة قصيرة دون أي التزام."),
    "thank_you": ("Thank you. We will be in touch.", "شكراً لكم. سنتواصل معكم."),
    "email.subject": ('Your website check: {{ answer("P2") }}', 'فحص موقعكم: {{ answer("P2") }}'),
    "email.intro": ('Hello {{ answer("P1") }}, here are your results.', 'مرحباً {{ answer("P1") }}، هذه نتيجتكم.'),
    "email.outro": ("Reply to this email if you have questions.", "ردّوا على هذه الرسالة إن كانت لديكم أسئلة."),
}
LABELS = {"weak": ("Weak", "ضعيف"), "fair": ("Fair", "مقبول"), "good": ("Good", "جيد"), "strong": ("Strong", "قوي"),
          "content": ("Content", "المحتوى"), "reach": ("Reach", "الوصول")}


def P(key):
    en, ar = T[key]
    return {"en": en, "ar": ar}


def pair(t):
    return {"en": t[0], "ar": t[1]}


def option_rows(key):
    return STD + EXTRA.get(key, [])


def calcs():
    b = '["weak", "fair", "good", "strong"]'
    out = []
    for p, name in PARTS:
        keys = ", ".join(f'"{k}"' for k in QUESTIONS[p])
        out += [{"name": f"{p}_raw", "expr": f'total("score", {keys})', "label": ""},
                {"name": f"{p}_score", "expr": f"round({p}_raw * 100 / 9)", "label": f"{name.capitalize()} score"},
                {"name": f"{p}_band", "expr": f"band({p}_score, [25, 50, 75], {b})", "label": f"{name.capitalize()} band"}]
    out += [
        {"name": "avg", "expr": "round((A_score + B_score) / 2)", "label": "Average"},
        {"name": "weakest", "expr": f'argmin(["content", "reach"], [rank(A_band, {b}), rank(B_band, {b})], [A_score, B_score])',
         "label": "Weakest part"},
        {"name": "unknowns", "expr": "unknowns(" + ", ".join(f'"{k}"' for k in ALL_Q) + ")", "label": "Unknown answers"},
        {"name": "lead_total", "expr": "A_raw + B_raw", "label": "Lead score (internal)", "internal": True},
        {"name": "lead_band", "expr": '"hot" if lead_total >= 14 else ("warm" if lead_total >= 8 else "cold")',
         "label": "Lead reading (internal)", "internal": True},
    ]
    for c in out:
        c.setdefault("internal", False)
    return out


TAGS = [{"name": "personal-email", "if": 'free_email(answer("P4"))'},
        {"name": "country:other", "if": 'answer("P3") == "other"'}]


def results(site_url):
    booking = {"en": f'{{{{ setting("booking_url") or "{site_url}/contact/" }}}}',
               "ar": f'{{{{ setting("booking_url") or "{site_url}/ar/contact/" }}}}'}
    labels = {k: pair(v) for k, v in LABELS.items()}
    part_blocks = [{"type": "lookup", "key": f"{p}_band", "title": {"en": f'{{{{ label("{n}") }}}}', "ar": f'{{{{ label("{n}") }}}}'},
                    "texts": {b: {"en": f"{LABELS[n][0]}: {LABELS[b][0]}.", "ar": f"{LABELS[n][1]}: {LABELS[b][1]}."} for b in BANDS}}
                   for p, n in PARTS]
    return {"labels": labels, "blocks": [
        {"type": "heading", "level": 1, "text": P("r.title")},
        {"type": "text", "style": "p", "text": P("r.position")},
        {"type": "scores", "items": [{"label": {"en": f'{{{{ label("{n}") }}}}', "ar": f'{{{{ label("{n}") }}}}'},
                                      "score": f"{p}_score", "band": f"{p}_band"} for p, n in PARTS]},
        *part_blocks,
        {"type": "heading", "level": 2, "text": P("h.verify")},
        {"type": "verify", "intro": P("verify.intro"), "empty": P("verify.empty"), "include": "unknown(this) or score(this) == 0",
         "fields": ALL_Q},
        {"type": "text", "style": "note", "if": 'answer("A2") == "none"', "text": P("A1.note")},
        {"type": "text", "style": "p", "if": "unknowns >= 3", "text": P("unknowns.line")},
        {"type": "button", "label": P("book.label"), "url": booking, "note": P("book.note")},
    ]}


def build(slug=SLUG, site_url=None, user=None):
    """Create the sample form (status draft). Returns the Form."""
    from django.conf import settings
    from .models import Field, Form, Option, Step
    site_url = (site_url or settings.TECHNTING_CMS_SITE_URL).rstrip("/")
    form = Form.objects.create(
        slug=slug, title=P("title"), intro=P("intro"), status=Form.DRAFT, languages=["en", "ar"], created_by=user, calcs=calcs(),
        settings={"public": True, "results": "show", "respondent_email": True, "turnstile": True, "notify_email": "",
                  "privacy_email": "", "booking_url": "", "retention_months": 24, "draft_days": 30, "tags": TAGS,
                  "thank_you": P("thank_you"),
                  "email": {"subject": P("email.subject"), "intro": P("email.intro"), "outro": P("email.outro")},
                  "crm": {"mode": "deal", "service": "S1", "lab": "", "task": {"subject": "Call {name} about the results", "hours": 24}},
                  "owner": {"mode": "rotate", "users": []},
                  "map": {"name": "P1", "company": "P2", "country": "P3", "email": "P4", "phone": "P5", "consent": "C1"}},
        results=results(site_url))
    prof = Step.objects.create(form=form, key="profile", order=10, title=P("step.profile"))
    kinds = [("P1", Field.TEXT, "name"), ("P2", Field.TEXT, "organization"), ("P3", Field.SELECT, ""), ("P4", Field.EMAIL, "email"),
             ("P5", Field.PHONE, "tel")]
    for n, (key, ftype, auto) in enumerate(kinds, start=1):
        f = Field.objects.create(step=prof, key=key, order=n * 10, type=ftype, label=P(key), required=key != "P5",
                                 options_extra={"autocomplete": auto, "max_length": 150} if auto else {})
        if key == "P3":
            Option.objects.bulk_create([Option(field=f, key=k, order=i * 10, label=P(f"P3.{k}")) for i, k in enumerate(COUNTRIES, start=1)])
    for order, (p, name) in enumerate(PARTS, start=2):
        step = Step.objects.create(form=form, key=name, order=order * 10, title=P(f"step.{name}"))
        for n, key in enumerate(QUESTIONS[p], start=1):
            texts = [{"if": 'answer("P3") == "other"', "text": P("A1.note")}] if key == "A1" else []
            f = Field.objects.create(step=step, key=key, order=n * 10, type=Field.RADIO, label=P(key), required=True, texts=texts,
                                     options_extra={"group": p})
            rows = option_rows(key) + [("dk", 0)]
            Option.objects.bulk_create([
                Option(field=f, key=k, order=i * 10, label=P(k), is_unknown=k == "dk", values={"score": s},
                       visible_if=OPTION_IF.get((key, k), "")) for i, (k, s) in enumerate(rows, start=1)])
    consent = Step.objects.create(form=form, key="consent", order=50, title=P("step.consent"))
    Field.objects.create(step=consent, key="C1", order=10, type=Field.CONSENT, required=True, label=P("C1"))
    return form
