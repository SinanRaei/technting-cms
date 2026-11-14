"""Weekly summary email (in the spirit of Jetpack's and Site Kit's email reports).

Each person turns it on for themselves in My account; nothing is sent to anyone who has not. It goes out on Sunday
from 08:00 (the start of the working week in much of the Arab region), from publish_due, once per week.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

SEND_WEEKDAY, SEND_HOUR = 6, 8   # Sunday (Monday = 0), 08:00 local time

TEXT = {
    "en": {"subject": "Technting: your week on the website", "hello": "Here is last week on example.com.",
           "visitors": "Visitors", "views": "Page views", "change": "vs the week before", "enquiries": "New enquiries",
           "deals": "New deals in the CRM", "subs": "New newsletter subscribers", "top": "Most visited pages",
           "sources": "Where visitors came from", "coming": "Scheduled to publish this week", "nothing": "Nothing scheduled.",
           "attention": "Needs attention", "ok": "Nothing needs attention.", "open": "Open the dashboard",
           "why": "You get this email because you turned on the weekly summary in My account. Turn it off there at any time.",
           "no_stats": "Stats are off.", "offsite": "Offsite backups", "offsite_none": "no copy yet",
           "restore_ok": "restore test passed", "restore_bad": "restore test FAILED", "seo": "Google search (28 days, compared with the 28 before)", "clicks": "Clicks",
           "shown": "Times shown", "position": "Average position", "top_q": "Top searches", "losing": "Pages losing clicks",
           "page_two": "Searches on page 2 worth improving", "index": "Key pages not in Google yet",
           "speed": "Slowest page on mobile (PageSpeed, out of 100)", "seo_more": "Details on the SEO page",
           "up": "Keywords moving up", "down": "Keywords moving down", "sitemap": "Sitemap errors in Search Console"},
    "ar": {"subject": "Technting: أسبوعكم على الموقع", "hello": "هذا ملخص الأسبوع الماضي على example.com.",
           "visitors": "الزوار", "views": "مشاهدات الصفحات", "change": "مقارنة بالأسبوع السابق", "enquiries": "استفسارات جديدة",
           "deals": "صفقات جديدة في CRM", "subs": "مشتركون جدد في النشرة", "top": "أكثر الصفحات زيارة",
           "sources": "من أين جاء الزوار", "coming": "مجدول للنشر هذا الأسبوع", "nothing": "لا يوجد شيء مجدول.",
           "attention": "يحتاج إلى انتباه", "ok": "لا يوجد ما يحتاج إلى انتباه.", "open": "فتح لوحة التحكم",
           "why": "تصلكم هذه الرسالة لأنكم فعّلتم الملخص الأسبوعي من «حسابي»، ويمكنكم إيقافه من هناك في أي وقت.",
           "no_stats": "الإحصائيات متوقفة.", "offsite": "النسخ الاحتياطية خارج الخادم", "offsite_none": "لا توجد نسخة بعد",
           "restore_ok": "نجحت تجربة الاسترجاع", "restore_bad": "فشلت تجربة الاسترجاع", "seo": "البحث في Google (آخر 28 يوماً مقارنة بالأيام الـ28 التي قبلها)", "clicks": "النقرات",
           "shown": "مرات الظهور", "position": "متوسط الترتيب", "top_q": "أكثر عبارات البحث", "losing": "صفحات تخسر نقرات",
           "page_two": "عبارات بحث في الصفحة الثانية تستحق التحسين", "index": "صفحات مهمة لم تظهر في Google بعد",
           "speed": "أبطأ صفحة على الجوال (PageSpeed من 100)", "seo_more": "التفاصيل في صفحة SEO",
           "up": "كلمات مفتاحية تتقدم", "down": "كلمات مفتاحية تتراجع", "sitemap": "أخطاء خريطة الموقع في Search Console"},
}


def pref(user):
    from .models import Setting
    v = Setting.objects.filter(key=f"digest:{user.pk}").values_list("value", flat=True).first() or {}
    return {"on": bool(v.get("on")), "lang": v.get("lang") if v.get("lang") in TEXT else "en"}


def set_pref(user, on, lang):
    from .models import Setting
    Setting.objects.update_or_create(key=f"digest:{user.pk}", defaults={"value": {"on": bool(on), "lang": lang if lang in TEXT else "en"}})


def recipients():
    from .models import Setting
    User = get_user_model()
    out = []
    for s in Setting.objects.filter(key__startswith="digest:"):
        if not (s.value or {}).get("on"):
            continue
        u = User.objects.filter(pk=s.key.split(":", 1)[1], is_active=True).exclude(email="").first()
        if u and u.is_staff:
            out.append((u, s.value.get("lang") if s.value.get("lang") in TEXT else "en"))
    return out


def facts(now=None):
    """Numbers for the last 7 days (shared by every language)."""
    from crm.models import Deal, Subscriber
    from . import stats
    from .models import Entry, FormSubmission, PageTranslation
    now = now or timezone.now()
    start = now - timedelta(days=7)
    f = {"enquiries": FormSubmission.objects.filter(created_at__gte=start).count(),
         "deals": Deal.objects.filter(created_at__gte=start).count(),
         "subs": Subscriber.objects.filter(status=Subscriber.CONFIRMED, confirmed_at__gte=start).count(),
         "stats": None, "coming": [], "attention": [], "offsite": None}
    try:
        from . import offsite
        f["offsite"] = offsite.summary(now)
    except Exception:
        pass
    if stats.enabled():
        rep = stats.report(7)
        f["stats"] = {"visitors": rep["visitors"], "views": rep["views"], "change": rep["visitors_change"],
                      "pages": rep["pages"][:5], "sources": [(c["label"], c["count"]) for c in rep["channels"][:4]]}
    week = now + timedelta(days=7)
    for e in Entry.objects.filter(is_published=True, publish_at__gt=now, publish_at__lte=week).prefetch_related("translations__language"):
        t = next((x.data for x in e.translations.all() if x.language.is_default), {}) or {}
        f["coming"].append((timezone.localtime(e.publish_at), t.get("title") or t.get("name") or e.key))
    for t in PageTranslation.objects.filter(status=PageTranslation.SCHEDULED, publish_at__gt=now, publish_at__lte=week):
        f["coming"].append((timezone.localtime(t.publish_at), t.title))
    f["coming"].sort()
    try:
        from . import security_check as sc
        rows, required = sc.accounts()
        for i in sc.findings(rows, required, sc.public_checks(), sc.sign_ins(), sc.backup_age_hours()):
            if i["level"] == "high":
                f["attention"].append((i["text"], i["detail"]))
    except Exception:
        pass
    try:
        from shield.report import digest_lines
        f["shield"] = digest_lines()  # administrators only (see render)
    except Exception:
        f["shield"] = []
    try:
        from . import seo_pro
        f["seo"] = seo_pro.digest_facts()
    except Exception:
        f["seo"] = None
    from .health import load as health_load
    h = health_load()
    if h and h.get("issues"):
        f["attention"].append(("Site health", str(len(h["issues"]))))
    return f


def render(f, lang, admin=False):
    from .ui_i18n import count, tr
    t = TEXT[lang]
    lines = [t["hello"], ""]
    if f["stats"]:
        s = f["stats"]
        ch = "" if s["change"] is None else f" ({'+' if s['change'] > 0 else ''}{s['change']}% {t['change']})"
        lines += [f"{t['visitors']}: {s['visitors']}{ch}", f"{t['views']}: {s['views']}"]
    else:
        lines.append(t["no_stats"])
    lines += [f"{t['enquiries']}: {f['enquiries']}", f"{t['deals']}: {f['deals']}", f"{t['subs']}: {f['subs']}"]
    o = f.get("offsite") if admin else None   # backups are an administrator matter, like Technting Shield
    if o:
        line = f"{t['offsite']}: " + (f"{o['newest']:%Y-%m-%d %H:%M} · {count(o['count'], 'copies', lang)} · {o['bytes'] / 1e6:.0f} MB"
                                      if o["newest"] else t["offsite_none"])
        if o["restore_at"]:
            line += f" · {t['restore_ok'] if o['restore_ok'] else t['restore_bad']} {o['restore_at']:%Y-%m-%d}"
        lines.append(line)
    lines.append("")
    if f["stats"] and f["stats"]["pages"]:
        lines.append(t["top"] + ":")
        lines += [f"  {p['path']}  ({p['views']})" for p in f["stats"]["pages"]]
        lines.append("")
    if f["stats"] and f["stats"]["sources"]:
        lines.append(t["sources"] + ": " + ", ".join(f"{tr(label, lang)} {n}" for label, n in f["stats"]["sources"]))
        lines.append("")
    lines += seo_lines(f.get("seo"), t)
    lines.append(t["coming"] + ":")
    lines += [f"  {when:%Y-%m-%d %H:%M}  {title}" for when, title in f["coming"]] or ["  " + t["nothing"]]
    lines.append("")
    lines.append(t["attention"] + ":")
    attention = f["attention"] + (f.get("shield") or [] if admin else [])
    lines += ["  " + tr(text, lang) + (f" ({detail})" if detail else "") for text, detail in attention] or ["  " + t["ok"]]
    lines += ["", f"{t['open']}: {settings.TECHNTING_CMS_ADMIN_URL}/", "", "--", t["why"]]
    return t["subject"], "\n".join(lines)


def seo_lines(s, t):
    """The Technting SEO part of the email: a few numbers and at most three items per list."""
    if not s:
        return []
    out = []
    g = s.get("search")
    if g:
        def ch(c):
            return "" if c is None else f" ({'+' if c > 0 else ''}{c}%)"
        out += [t["seo"] + ":", f"  {t['clicks']}: {g['clicks']}{ch(g['clicks_change'])} · {t['shown']}: {g['impressions']}"
                f"{ch(g['impressions_change'])} · {t['position']}: {g['position'] or '-'}"]
        if g["top"]:
            out.append(f"  {t['top_q']}: " + ", ".join(f"{q} ({n})" for q, n in g["top"]))
        if g["losing"]:
            out.append(f"  {t['losing']}: " + ", ".join(f"{p} ({a} → {b})" for p, a, b in g["losing"]))
        if g["page_two"]:
            out.append(f"  {t['page_two']}: " + ", ".join(f"{q} (#{pos:.0f})" for q, pos in g["page_two"]))
    for key in ("up", "down"):
        if s.get(key):
            out.append(f"  {t[key]}: " + ", ".join(f"{k} (#{a:.0f} → #{b:.0f})" for k, a, b in s[key]))
    if s.get("sitemap_errors"):
        out.append(f"  {t['sitemap']}: {s['sitemap_errors']}")
    if s.get("index_problems"):
        out.append(f"  {t['index']}: {s['index_problems']}")
    if s.get("speed"):
        out.append(f"  {t['speed']}: {s['speed']['path']} {s['speed']['score']}")
    if out:
        out += [f"  {t['seo_more']}: {settings.TECHNTING_CMS_ADMIN_URL}/seo/", ""]
    return out


def due(now=None):
    from .models import Setting
    now = timezone.localtime(now or timezone.now())
    if now.weekday() != SEND_WEEKDAY or now.hour < SEND_HOUR:
        return False
    week = now.strftime("%G-W%V")
    return (Setting.objects.filter(key="digest_sent").values_list("value", flat=True).first() or {}).get("week") != week


def send_all(force=False, now=None):
    """Send to everyone who opted in. Returns the number of emails sent."""
    from . import mail
    from .models import Setting
    if not (force or due(now)) or not mail.ready():
        return 0
    people = recipients()
    week = timezone.localtime(now or timezone.now()).strftime("%G-W%V")
    Setting.objects.update_or_create(key="digest_sent", defaults={"value": {"week": week}})
    if not people:
        return 0
    f = facts(now)
    sent = 0
    for user, lang in people:
        subject, body = render(f, lang, admin=user.is_superuser)
        try:
            mail.send(subject, body, [user.email])
            sent += 1
        except Exception:
            pass
    return sent
