"""Create a small demo site (English + Arabic) for the starter theme: languages, a home page built from the theme's
section blocks, services, blog, contact and privacy pages, three services, a sample blog post, the header button and
the header and footer menus. Safe to run again: anything that already exists is left as it is.

  python manage.py seed_demo
  python manage.py publish
"""
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from cms.fields import clean_blocks, clean_fields
from cms.models import Entry, EntryTranslation, Language, Menu, Page, PageTranslation, Setting
from cms.theme import load_theme


def bid():
    return uuid.uuid4().hex[:8]


def link(label, url):
    return {"label": label, "url": url}


# ---------------------------------------------------------------- services (collection "service")
SERVICES = [
    {"key": "websites", "data": {"area": "websites", "icon": "layers", "featured": True, "price_min": 900},
     "en": {"name": "Websites", "summary": "A fast, bilingual website that is easy to update, built from ready sections.",
            "body": "<p>We plan the pages with you, write the structure in English and Arabic, and publish a site that "
                    "loads quickly on any phone.</p><p>You keep full control: every page is edited in the dashboard.</p>",
            "includes": [{"name": "Page plan and sitemap"}, {"name": "Design from the starter theme"},
                         {"name": "English and Arabic pages"}, {"name": "Search engine basics"}],
            "price": "From $900"},
     "ar": {"name": "المواقع الإلكترونية", "summary": "موقع سريع بلغتين يسهل تحديثه، مبني من أقسام جاهزة.",
            "body": "<p>نخطط الصفحات معكم، ونكتب هيكلها بالعربية والإنجليزية، وننشر موقعاً يعمل بسرعة على أي هاتف.</p>"
                    "<p>تبقى إدارة الموقع بأيديكم، فكل صفحة تُعدَّل من لوحة التحكم.</p>",
            "includes": [{"name": "خطة الصفحات وخريطة الموقع"}, {"name": "تصميم مبني على القالب الأساسي"},
                         {"name": "صفحات بالعربية والإنجليزية"}, {"name": "أساسيات الظهور في محركات البحث"}],
            "price": "ابتداءً من 900 دولار"}},
    {"key": "content", "data": {"area": "content", "icon": "chat", "featured": True, "price_min": 400},
     "en": {"name": "Content", "summary": "Clear pages and articles in both languages, written for your customers.",
            "body": "<p>We turn what you know into short, useful pages and articles, and publish them on a steady schedule.</p>",
            "includes": [{"name": "Content plan"}, {"name": "Two articles a month"}, {"name": "Arabic written natively"}],
            "price": "From $400 a month"},
     "ar": {"name": "المحتوى", "summary": "صفحات ومقالات واضحة باللغتين، مكتوبة لعملائكم.",
            "body": "<p>نحوّل خبرتكم إلى صفحات ومقالات قصيرة ومفيدة، وننشرها وفق جدول منتظم.</p>",
            "includes": [{"name": "خطة للمحتوى"}, {"name": "مقالان كل شهر"}, {"name": "نصوص عربية مكتوبة بالعربية أصلاً"}],
            "price": "ابتداءً من 400 دولار شهرياً"}},
    {"key": "support", "data": {"area": "support", "icon": "shield", "featured": True, "price_min": 150},
     "en": {"name": "Care and support", "summary": "Updates, backups and quick help when something needs to change.",
            "body": "<p>We keep the site updated and backed up, check it every month, and answer your questions by email.</p>",
            "includes": [{"name": "Monthly updates"}, {"name": "Encrypted backups"}, {"name": "Reply within one working day"}],
            "price": "From $150 a month"},
     "ar": {"name": "الرعاية والدعم", "summary": "تحديثات ونسخ احتياطية ومساعدة سريعة عند الحاجة إلى أي تعديل.",
            "body": "<p>نحدّث الموقع ونحفظ نسخه الاحتياطية ونراجعه كل شهر، ونجيب عن أسئلتكم بالبريد الإلكتروني.</p>",
            "includes": [{"name": "تحديثات شهرية"}, {"name": "نسخ احتياطية مشفّرة"}, {"name": "رد خلال يوم عمل واحد"}],
            "price": "ابتداءً من 150 دولاراً شهرياً"}},
]

# ---------------------------------------------------------------- a sample blog post (collection "post")
POST = {"key": "first-week", "data": {"area": "websites", "services": ["websites"]},
        "en": {"title": "Five things to set up in your first week",
               "excerpt": "A short checklist for a new site: the pages, the menus, the contact details and the first article.",
               "body": "<p>A new website feels finished long before it is ready. These five steps make it useful from day one.</p>"
                       "<h2>1. Write the home page last</h2><p>Start with the pages people ask about most. The home page then points to them.</p>"
                       "<h2>2. Check both languages</h2><p>Read every Arabic page on a phone. Headings, buttons and menus should feel native.</p>"
                       "<h2>3. Set the contact details</h2><p>Add the contact email, phone and social profiles in Settings, so the footer and the forms use them.</p>"
                       "<h2>4. Publish one article</h2><p>One clear article answers a real question and gives search engines something to read.</p>"
                       "<h2>5. Turn on backups</h2><p>Schedule an encrypted offsite copy before you invite anyone else to edit.</p>",
               "faq": [{"question": "Do I need all five?", "answer": "No. Start with the contact details and backups, then add the rest."},
                       {"question": "Where do I change the menus?", "answer": "In the dashboard under Menus, for each language."}],
               "seo_title": "Five things to set up in your first week",
               "seo_description": "A short checklist for a new website: pages, menus, contact details, a first article and backups."},
        "ar": {"title": "خمس خطوات لأسبوعكم الأول مع الموقع",
               "excerpt": "قائمة قصيرة لموقع جديد: الصفحات والقوائم وبيانات التواصل وأول مقال.",
               "body": "<p>يبدو الموقع الجديد مكتملاً قبل أن يصبح جاهزاً فعلاً. هذه الخطوات الخمس تجعله مفيداً من اليوم الأول.</p>"
                       "<h2>1. اكتبوا الصفحة الرئيسية في النهاية</h2><p>ابدؤوا بالصفحات التي يسأل عنها الناس أكثر، ثم اجعلوا الصفحة الرئيسية تقود إليها.</p>"
                       "<h2>2. راجعوا اللغتين</h2><p>اقرؤوا كل صفحة عربية على الهاتف، وتأكدوا أن العناوين والأزرار والقوائم تبدو طبيعية.</p>"
                       "<h2>3. أضيفوا بيانات التواصل</h2><p>أدخلوا البريد الإلكتروني والهاتف وحسابات التواصل الاجتماعي في الإعدادات، ليستخدمها التذييل والنماذج.</p>"
                       "<h2>4. انشروا مقالاً واحداً</h2><p>مقال واضح واحد يجيب عن سؤال حقيقي، ويمنح محركات البحث محتوى تقرؤه.</p>"
                       "<h2>5. فعّلوا النسخ الاحتياطي</h2><p>جدولوا نسخة احتياطية مشفّرة خارج الخادم قبل أن تدعوا أي شخص آخر إلى التحرير.</p>",
               "faq": [{"question": "هل أحتاج إلى الخطوات الخمس كلها؟", "answer": "لا. ابدؤوا ببيانات التواصل والنسخ الاحتياطي، ثم أضيفوا الباقي."},
                       {"question": "أين أعدّل القوائم؟", "answer": "من لوحة التحكم في قسم القوائم، لكل لغة على حدة."}],
               "seo_title": "خمس خطوات لأسبوعكم الأول مع الموقع",
               "seo_description": "قائمة قصيرة لموقع جديد: الصفحات والقوائم وبيانات التواصل وأول مقال والنسخ الاحتياطي."}}

# ---------------------------------------------------------------- page text per language
T = {
    "en": {
        "home": "Home", "home_seo": "A fast, bilingual website built with Technting CMS.",
        "hero": {"eyebrow": "Technting CMS starter", "title": "A clear, fast website", "title_highlight": "in two languages.",
                 "lede": "This is demo content from the starter theme. Every section on this page is a block you can edit, move or hide in the dashboard.",
                 "primary": link("See the services", "{p}/services/"), "secondary": link("Get in touch", "#contact"),
                 "points": [{"text": "English and Arabic"}, {"text": "Static, fast pages"}, {"text": "Built-in CRM"}]},
        "features": {"eyebrow": "What you get", "title": "Everything a small business site needs.",
                     "intro": "Pages, articles, forms and enquiries in one dashboard. Publishing writes plain static files, so the site stays fast and safe.",
                     "items": [("layers", "Ready sections", "Hero, features, steps, pricing, FAQ and more. Add them in any order."),
                               ("globe", "Two languages", "Every page has an English and an Arabic version, with right-to-left layout built in."),
                               ("spark", "Fast by default", "Pages are published as static files with self-hosted fonts and no heavy scripts."),
                               ("mail", "Enquiries in one place", "Contact forms land in the inbox and the CRM, with an email copy to your team."),
                               ("chart", "Search basics", "Clean addresses, a sitemap, structured data and a search page out of the box."),
                               ("shield", "Backups and security", "Encrypted backups, a firewall and sign-in protection are part of the dashboard.")]},
        "split": {"eyebrow": "Made to be edited", "title": "Change a page in minutes, not days.",
                  "text": "Pick a block, fill in the fields and preview the page in both languages. When it reads well, publish.",
                  "points": [{"text": "Drag sections into a new order"}, {"text": "Hide a section on phones or desktops"},
                             {"text": "Schedule pages and posts for later"}],
                  "link": link("Read the first-week checklist", "{p}/blog/first-week/")},
        "services": {"eyebrow": "Services", "title": "Pick a starting point.", "intro": "Three sample services. Replace them with your own under Services in the dashboard.",
                     "more": link("All services", "{p}/services/")},
        "steps": {"eyebrow": "How it works", "title": "From first call to a live site.",
                  "items": [("Talk", "A short call to agree on goals, pages and languages."),
                            ("Plan", "A page plan and a written scope, so nothing is a surprise."),
                            ("Build", "Pages built from the theme blocks, reviewed in both languages."),
                            ("Launch", "Published, backed up and handed over with a short guide.")]},
        "stats": {"eyebrow": "In numbers", "title": "Small theme, full toolkit.",
                  "items": [("2", "Languages", "English and Arabic, side by side"), ("24", "Blocks", "Sections you can mix on any page"),
                            ("1", "Dashboard", "Pages, CRM, forms and backups"), ("0", "Plugins needed", "To publish your first site")]},
        "quotes": {"eyebrow": "Testimonials", "title": "What customers say.",
                   "items": [("Replace this sample quote with a real one from a customer. Keep it short and specific.", "Customer name", "Role, company"),
                             ("A good quote names the result: a clearer site, more enquiries, less time spent on updates.", "Customer name", "Role, company"),
                             ("Ask permission before you publish a name, and add a photo in the block if you have one.", "Customer name", "Role, company")]},
        "pricing": {"eyebrow": "Pricing", "title": "Simple, written prices.", "intro": "Sample plans. Change the names, prices and items in the block.",
                    "plans": [("Starter", "$900", "one-off", "A five-page site in two languages.", ["Five pages", "Contact form", "One round of changes"], False),
                              ("Growth", "$1,900", "one-off", "A larger site with a blog and services.", ["Up to twelve pages", "Blog and search", "Two rounds of changes", "Launch support"], True),
                              ("Care", "$150", "a month", "Updates, backups and help after launch.", ["Monthly updates", "Encrypted backups", "Email support"], False)],
                    "button": "Ask about this plan", "note": "Prices are examples for the demo. Final scope and price are agreed in writing."},
        "faq": {"eyebrow": "FAQ", "title": "Questions, answered.",
                "items": [("Can I use my own logo and colours?", "Yes. Set the site name in the settings, replace the logo files in the theme and change the colour tokens at the top of theme.css."),
                          ("Is the Arabic version a translation of the English one?", "Each language has its own page text, so the Arabic can be written natively rather than translated word for word."),
                          ("Where do enquiries go?", "To the inbox in the dashboard and to the CRM as a new deal. A copy is emailed to the leads address in Settings."),
                          ("Do I need a developer to publish?", "No. Editors publish from the dashboard. Developers can still change the theme templates when needed.")]},
        "posts": {"eyebrow": "From the blog", "title": "Latest articles", "more": link("All articles", "{p}/blog/")},
        "cta": {"eyebrow": "Get in touch", "title": "Tell us about your website.",
                "text": "A short message is enough. We reply by email within one working day.", "button": "Send an enquiry",
                "secondary": link("See the services", "{p}/services/")},
        "services_page": ("Services", "What we can do for you.", "Each service has its own page with what is included and a short enquiry form."),
        "blog_page": ("Blog", "Notes, news and practical articles.", "Our first articles are on the way."),
        "contact_page": ("Contact", "Tell us what you need.", "Send a short message and we will reply by email."),
        "privacy": ("Privacy notice", "<h2>Who we are</h2><p>Replace this text with your own privacy notice: who you are, what you "
                                      "collect, why, how long you keep it and how people can reach you.</p><h2>Enquiries</h2><p>When you "
                                      "send an enquiry, we use your details only to reply to it.</p>"),
        "menu_site": "Site", "menu_company": "Company", "search": "Search", "cta_label": "Get in touch",
    },
    "ar": {
        "home": "الرئيسية", "home_seo": "موقع سريع بلغتين مبني بنظام Technting CMS.",
        "hero": {"eyebrow": "القالب الأساسي لنظام Technting CMS", "title": "موقع واضح وسريع", "title_highlight": "بلغتين.",
                 "lede": "هذا محتوى تجريبي من القالب الأساسي. كل قسم في هذه الصفحة كتلة يمكنكم تعديلها أو نقلها أو إخفاؤها من لوحة التحكم.",
                 "primary": link("اطّلعوا على الخدمات", "{p}/services/"), "secondary": link("تواصلوا معنا", "#contact"),
                 "points": [{"text": "العربية والإنجليزية"}, {"text": "صفحات ثابتة وسريعة"}, {"text": "نظام مدمج لإدارة العملاء"}]},
        "features": {"eyebrow": "ما تحصلون عليه", "title": "كل ما يحتاج إليه موقع شركة صغيرة.",
                     "intro": "الصفحات والمقالات والنماذج والاستفسارات في لوحة تحكم واحدة. ويُنشر الموقع ملفات ثابتة، فيبقى سريعاً وآمناً.",
                     "items": [("layers", "أقسام جاهزة", "واجهة رئيسية ومزايا وخطوات وأسعار وأسئلة شائعة وغيرها، بالترتيب الذي تريدونه."),
                               ("globe", "لغتان", "لكل صفحة نسخة عربية ونسخة إنجليزية، مع دعم كامل للكتابة من اليمين إلى اليسار."),
                               ("spark", "سرعة من البداية", "تُنشر الصفحات ملفات ثابتة بخطوط مستضافة على الموقع نفسه ومن دون نصوص برمجية ثقيلة."),
                               ("mail", "الاستفسارات في مكان واحد", "تصل رسائل نماذج التواصل إلى صندوق الوارد ونظام إدارة العملاء، مع نسخة بالبريد لفريقكم."),
                               ("chart", "أساسيات البحث", "روابط واضحة وخريطة للموقع وبيانات منظمة وصفحة بحث جاهزة."),
                               ("shield", "نسخ احتياطي وحماية", "نسخ احتياطية مشفّرة وجدار حماية وحماية لتسجيل الدخول ضمن لوحة التحكم.")]},
        "split": {"eyebrow": "مصمم للتعديل", "title": "عدّلوا الصفحة في دقائق لا في أيام.",
                  "text": "اختاروا كتلة واملؤوا حقولها، ثم عاينوا الصفحة باللغتين. وعندما يصبح النص جاهزاً، انشروها.",
                  "points": [{"text": "غيّروا ترتيب الأقسام بالسحب"}, {"text": "أخفوا أي قسم على الهاتف أو الحاسوب"},
                             {"text": "جدولوا نشر الصفحات والمقالات لوقت لاحق"}],
                  "link": link("اقرؤوا قائمة الأسبوع الأول", "{p}/blog/first-week/")},
        "services": {"eyebrow": "الخدمات", "title": "اختاروا نقطة البداية.", "intro": "ثلاث خدمات تجريبية. استبدلوها بخدماتكم من قسم الخدمات في لوحة التحكم.",
                     "more": link("كل الخدمات", "{p}/services/")},
        "steps": {"eyebrow": "طريقة العمل", "title": "من أول مكالمة إلى موقع منشور.",
                  "items": [("نتحدث", "مكالمة قصيرة نتفق فيها على الأهداف والصفحات واللغات."),
                            ("نخطط", "خطة للصفحات ونطاق عمل مكتوب، حتى لا تكون هناك مفاجآت."),
                            ("نبني", "صفحات مبنية من كتل القالب، تُراجَع باللغتين."),
                            ("نطلق", "ننشر الموقع ونحفظ نسخة احتياطية منه ونسلمه مع دليل قصير.")]},
        "stats": {"eyebrow": "بالأرقام", "title": "قالب صغير وأدوات متكاملة.",
                  "items": [("2", "لغتان", "العربية والإنجليزية جنباً إلى جنب"), ("24", "كتلة", "أقسام يمكن جمعها في أي صفحة"),
                            ("1", "لوحة تحكم", "للصفحات وإدارة العملاء والنماذج والنسخ الاحتياطي"), ("0", "إضافات مطلوبة", "لنشر موقعكم الأول")]},
        "quotes": {"eyebrow": "آراء العملاء", "title": "ماذا يقول عملاؤنا.",
                   "items": [("استبدلوا هذا الاقتباس التجريبي برأي حقيقي من أحد عملائكم، واجعلوه قصيراً ومحدداً.", "اسم العميل", "المنصب، الشركة"),
                             ("الاقتباس الجيد يذكر النتيجة: موقع أوضح، أو استفسارات أكثر، أو وقت أقل في التحديثات.", "اسم العميل", "المنصب، الشركة"),
                             ("اطلبوا الإذن قبل نشر أي اسم، وأضيفوا صورة في الكتلة إن توفرت.", "اسم العميل", "المنصب، الشركة")]},
        "pricing": {"eyebrow": "الأسعار", "title": "أسعار واضحة ومكتوبة.", "intro": "باقات تجريبية. غيّروا الأسماء والأسعار والبنود من الكتلة.",
                    "plans": [("الأساسية", "900 دولار", "دفعة واحدة", "موقع من خمس صفحات بلغتين.", ["خمس صفحات", "نموذج تواصل", "جولة تعديلات واحدة"], False),
                              ("النمو", "1,900 دولار", "دفعة واحدة", "موقع أكبر مع مدونة وصفحات للخدمات.", ["حتى اثنتي عشرة صفحة", "مدونة وبحث", "جولتا تعديلات", "دعم عند الإطلاق"], True),
                              ("الرعاية", "150 دولاراً", "شهرياً", "تحديثات ونسخ احتياطي ومساعدة بعد الإطلاق.", ["تحديثات شهرية", "نسخ احتياطية مشفّرة", "دعم بالبريد الإلكتروني"], False)],
                    "button": "استفسروا عن هذه الباقة", "note": "الأسعار أمثلة لأغراض العرض. ونتفق كتابياً على النطاق والسعر النهائيين."},
        "faq": {"eyebrow": "أسئلة شائعة", "title": "إجابات عن أسئلتكم.",
                "items": [("هل يمكنني استخدام شعاري وألواني؟", "نعم. اكتبوا اسم الموقع في الإعدادات، واستبدلوا ملفات الشعار في القالب، وغيّروا متغيرات الألوان في أعلى الملف theme.css."),
                          ("هل النسخة العربية ترجمة للنسخة الإنجليزية؟", "لكل لغة نص صفحة مستقل، لذلك يمكن كتابة العربية بأسلوب عربي أصيل بدلاً من الترجمة الحرفية."),
                          ("أين تصل الاستفسارات؟", "تصل إلى صندوق الوارد في لوحة التحكم، وإلى نظام إدارة العملاء صفقةً جديدة، مع نسخة إلى بريد الاستفسارات المحدد في الإعدادات."),
                          ("هل أحتاج إلى مطوّر لنشر الموقع؟", "لا. ينشر المحررون الموقع من لوحة التحكم، ويبقى بإمكان المطورين تعديل قوالب الموقع عند الحاجة.")]},
        "posts": {"eyebrow": "من المدونة", "title": "أحدث المقالات", "more": link("كل المقالات", "{p}/blog/")},
        "cta": {"eyebrow": "تواصلوا معنا", "title": "حدّثونا عن موقعكم.",
                "text": "تكفي رسالة قصيرة، وسنرد عليكم بالبريد الإلكتروني خلال يوم عمل واحد.", "button": "أرسلوا استفساراً",
                "secondary": link("اطّلعوا على الخدمات", "{p}/services/")},
        "services_page": ("الخدمات", "ما يمكننا تقديمه لكم.", "لكل خدمة صفحة خاصة توضح ما تشمله، مع نموذج استفسار قصير."),
        "blog_page": ("المدونة", "ملاحظات وأخبار ومقالات عملية.", "مقالاتنا الأولى قيد الإعداد."),
        "contact_page": ("تواصلوا معنا", "أخبرونا بما تحتاجون إليه.", "أرسلوا رسالة قصيرة وسنرد عليكم بالبريد الإلكتروني."),
        "privacy": ("إشعار الخصوصية", "<h2>من نحن</h2><p>استبدلوا هذا النص بإشعار الخصوصية الخاص بكم: من أنتم، وما البيانات التي "
                                      "تجمعونها، ولماذا، ومدة الاحتفاظ بها، وكيف يمكن التواصل معكم.</p><h2>الاستفسارات</h2><p>عندما "
                                      "ترسلون استفساراً، نستخدم بياناتكم للرد عليه فقط.</p>"),
        "menu_site": "الموقع", "menu_company": "الشركة", "search": "بحث", "cta_label": "تواصلوا معنا",
    },
}


def fill(value, prefix):
    """Put the language prefix into every "{p}/..." address of a block's data."""
    if isinstance(value, dict):
        return {k: fill(v, prefix) for k, v in value.items()}
    if isinstance(value, list):
        return [fill(v, prefix) for v in value]
    if isinstance(value, str) and value.startswith("{p}"):
        return prefix + value[3:]
    return value


def home_blocks(c, p):
    pr = c["pricing"]
    data = [
        ("hero", {**c["hero"], "style": "dark"}),
        ("features", {**{k: c["features"][k] for k in ("eyebrow", "title", "intro")}, "columns": "3",
                      "items": [{"icon": i, "title": h, "text": x} for i, h, x in c["features"]["items"]]}),
        ("split", {**c["split"], "image_side": "end"}),
        ("services", {**c["services"], "featured_only": True}),
        ("steps", {"eyebrow": c["steps"]["eyebrow"], "title": c["steps"]["title"],
                   "items": [{"title": h, "text": x} for h, x in c["steps"]["items"]]}),
        ("stats", {"eyebrow": c["stats"]["eyebrow"], "title": c["stats"]["title"], "style": "dark",
                   "items": [{"value": v, "label": l, "text": x} for v, l, x in c["stats"]["items"]]}),
        ("testimonials", {"eyebrow": c["quotes"]["eyebrow"], "title": c["quotes"]["title"],
                          "items": [{"quote": q, "name": n, "role": r} for q, n, r in c["quotes"]["items"]]}),
        ("pricing", {"eyebrow": pr["eyebrow"], "title": pr["title"], "intro": pr["intro"], "note": pr["note"],
                     "plans": [{"name": n, "price": v, "period": per, "summary": s, "features": [{"text": x} for x in fs],
                                "button": link(pr["button"], "#contact"), "featured": feat} for n, v, per, s, fs, feat in pr["plans"]]}),
        ("faq", {"eyebrow": c["faq"]["eyebrow"], "title": c["faq"]["title"],
                 "items": [{"question": q, "answer": a} for q, a in c["faq"]["items"]]}),
        ("posts_list", {**c["posts"], "limit": 3}),
        ("cta", c["cta"]),
    ]
    return [{"id": bid(), "type": t, "data": fill(d, p)} for t, d in data]


class Command(BaseCommand):
    help = "Create demo content (EN + AR pages, services, a blog post, menus) for the starter theme."

    @transaction.atomic
    def handle(self, *args, **opts):
        theme = load_theme()
        en, _ = Language.objects.get_or_create(code="en", defaults={"name": "English", "native_name": "English", "is_default": True,
                                                                    "locale": "en_GB", "order": 0})
        ar, _ = Language.objects.get_or_create(code="ar", defaults={"name": "Arabic", "native_name": "العربية", "direction": "rtl",
                                                                    "url_prefix": "ar", "locale": "ar_AR", "order": 1})
        site = settings.TECHNTING_CMS_SITE_NAME
        made = {"pages": 0, "entries": 0}

        def entry(collection, key, shared, langs, order):
            if collection not in theme.collections:
                return
            e, created = Entry.objects.get_or_create(collection=collection, key=key, defaults={
                "order": order, "data": clean_fields(theme.collection_fields(collection, translatable=False), shared)})
            made["entries"] += int(created)
            for lang in (en, ar):
                if lang.code in langs and not EntryTranslation.objects.filter(entry=e, language=lang).exists():
                    EntryTranslation.objects.create(entry=e, language=lang, data=clean_fields(
                        theme.collection_fields(collection, translatable=True), langs[lang.code]))

        def page(key, template, order, lang, title, slug, blocks, seo_title=None, seo_description=""):
            pg, _ = Page.objects.get_or_create(key=key, defaults={"template": template, "order": order})
            if PageTranslation.objects.filter(page=pg, language=lang).exists():
                return
            PageTranslation.objects.create(page=pg, language=lang, title=title, slug=slug, status=PageTranslation.PUBLISHED,
                                           seo_title=seo_title or title, seo_description=seo_description,
                                           blocks=clean_blocks(theme, blocks))
            made["pages"] += 1

        for i, s in enumerate(SERVICES):
            entry("service", s["key"], s["data"], {"en": s["en"], "ar": s["ar"]}, i)
        entry("post", POST["key"], {**POST["data"], "date": timezone.localdate().isoformat()}, {"en": POST["en"], "ar": POST["ar"]}, 0)

        for lang in (en, ar):
            c, p = T[lang.code], (f"/{lang.url_prefix}" if lang.url_prefix else "")
            page("home", "home", 0, lang, c["home"], "", home_blocks(c, p), f"{site} · {c['home']}", c["home_seo"])
            title, lead, text = c["services_page"]
            page("services", "default", 10, lang, title, "services", [
                {"id": bid(), "type": "page_hero", "data": {"title": title, "lead": lead, "text": text}},
                {"id": bid(), "type": "services", "data": {"link_label": ""}},
                {"id": bid(), "type": "cta", "data": fill(c["cta"], p)}], seo_description=lead)
            title, lead, empty = c["blog_page"]
            page("blog", "default", 20, lang, title, "blog", [
                {"id": bid(), "type": "page_hero", "data": {"title": title, "lead": lead}},
                {"id": bid(), "type": "posts_list", "data": {"limit": 0, "empty_text": empty}}], seo_description=lead)
            title, lead, text = c["contact_page"]
            page("contact", "default", 30, lang, title, "contact", [
                {"id": bid(), "type": "page_hero", "data": {"title": title, "lead": lead}},
                {"id": bid(), "type": "enquiry", "data": {}}], seo_description=text)
            title, body = c["privacy"]
            page("privacy", "default", 90, lang, title, "privacy", [
                {"id": bid(), "type": "page_hero", "data": {"title": title}},
                {"id": bid(), "type": "rich_text", "data": {"body": body}}])

            Menu.objects.get_or_create(key="header", language=lang, defaults={"items": [
                {"label": c["home"], "url": f"{p}/"},
                {"label": c["services_page"][0], "url": f"{p}/services/"},
                {"label": c["blog_page"][0], "url": f"{p}/blog/"},
                {"label": c["contact_page"][0], "url": f"{p}/contact/"}]})
            Menu.objects.get_or_create(key="footer", language=lang, defaults={"items": [
                {"label": c["menu_site"], "url": "", "children": [
                    {"label": c["services_page"][0], "url": f"{p}/services/"},
                    {"label": c["blog_page"][0], "url": f"{p}/blog/"},
                    {"label": c["search"], "url": f"{p}/search/"}]},
                {"label": c["menu_company"], "url": "", "children": [
                    {"label": c["contact_page"][0], "url": f"{p}/contact/"},
                    {"label": c["privacy"][0], "url": f"{p}/privacy/"}]}]})

        Setting.objects.get_or_create(key="header_cta", defaults={"value": {
            l.code: {"label": T[l.code]["cta_label"], "url": (f"/{l.url_prefix}" if l.url_prefix else "") + "/contact/"} for l in (en, ar)}})
        self.stdout.write(self.style.SUCCESS(
            f"Demo content ready ({made['pages']} page translations and {made['entries']} entries created). Run: manage.py publish"))
