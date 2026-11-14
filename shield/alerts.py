"""Security alert emails. Only administrators get them, and only those who turned them on in My account
(like the weekly summary). Each kind of alert is sent at most once an hour per person."""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache

log = logging.getLogger(__name__)

TEXT = {
    "en": {
        "new_device": ("New sign-in to your Technting CMS account", "Someone signed in to your account from a browser or device we have not seen before."),
        "new_country": ("Sign-in to your Technting CMS account from a new country", "Someone signed in to your account from a country you have not signed in from before."),
        "breached_password": ("Your Technting CMS password has appeared in a data breach", "The password you signed in with appears in known data breaches. Attackers try such passwords first. Change it in My account now."),
        "guessing": ("Someone is guessing a Technting CMS password", "Many wrong passwords were tried for this account in the last hour. Technting Shield locks out the addresses; make sure two-step verification is on."),
        "ct_new": ("New certificate issued for our domain", "A certificate authority issued a new certificate for our domain. If nobody on the team or Cloudflare asked for it, someone may be preparing a fake copy of the site."),
        "integrity": ("Code files changed on the server", "Technting Shield found code files on the server that differ from the committed version. If this was not a deployment, check the server now."),
        "web_root": ("Unexpected file in the public website folder", "A file that a static website never needs (such as a .php script) appeared in the public folder."),
        "vuln": ("Security update needed for Technting CMS", "A package that Technting CMS uses has a known security problem. A developer should update it."),
        "feed_failed": ("A Technting Shield threat list is out of date", "A threat list could not be downloaded for several days. The last good copy is still used."),
        "public_changed": ("The public website was changed outside Technting CMS", "Files on example.com no longer match what Technting CMS published (or were deleted). Someone may have changed the site on the server. Publishing again restores them; then find out how it happened."),
        "domain_dns": ("Our domain's records changed", "The name servers, mail servers or site address of our domain changed. If nobody on the team did this, the domain may have been taken over: check the domain account and Cloudflare now."),
        "lookalike": ("A domain that looks like ours was registered", "Someone registered a name one typo away from ours. It may be used for fake emails or a fake copy of the site. Warn the team and clients, and report it to the registrar if it is abused."),
        "media": ("Suspicious file in the media library", "A file in the media library is not what its name says or hides code. Check it and delete it if nobody on the team uploaded it."),
        "hello": "Hello", "details": "Details", "open": "Open Technting Shield", "account": "If this was you, you can ignore this email.",
        "why": "You get these emails because you turned on security alerts in My account (Technting CMS). Turn them off there at any time.",
    },
    "ar": {
        "new_device": ("تسجيل دخول جديد إلى حسابكم في Technting CMS", "سجّل أحدهم الدخول إلى حسابكم من متصفح أو جهاز لم نره من قبل."),
        "new_country": ("تسجيل دخول إلى حسابكم في Technting CMS من دولة جديدة", "سجّل أحدهم الدخول إلى حسابكم من دولة لم تسجّلوا الدخول منها من قبل."),
        "breached_password": ("كلمة مرور حسابكم في Technting CMS ظهرت في تسريب بيانات", "كلمة المرور التي دخلتم بها موجودة في تسريبات بيانات معروفة، والمهاجمون يجرّبون هذه الكلمات أولاً. غيّروها الآن من «حسابي»."),
        "guessing": ("أحدهم يحاول تخمين كلمة مرور في Technting CMS", "جُرّبت كلمات مرور خاطئة كثيرة لهذا الحساب خلال الساعة الماضية. يحظر Technting Shield العناوين المهاجِمة؛ تأكدوا أن التحقق بخطوتين مفعّل."),
        "ct_new": ("صدرت شهادة جديدة لنطاقنا", "أصدرت جهة شهادات شهادة جديدة لنطاقنا. إذا لم يطلبها أحد من الفريق أو Cloudflare، فقد يكون أحدهم يجهّز نسخة مزيفة من الموقع."),
        "integrity": ("تغيّرت ملفات الكود على الخادم", "وجد Technting Shield ملفات كود على الخادم تختلف عن النسخة المعتمدة. إذا لم يكن ذلك تحديثاً مقصوداً، افحصوا الخادم الآن."),
        "web_root": ("ملف غير متوقع في مجلد الموقع العام", "ظهر في المجلد العام ملف لا يحتاجه موقع ثابت (مثل سكربت ‎.php‎)."),
        "vuln": ("يلزم تحديث أمني لـ Technting CMS", "إحدى الحزم التي يستخدمها Technting CMS فيها ثغرة أمنية معروفة، ويجب أن يحدّثها مطوّر."),
        "feed_failed": ("قائمة تهديدات في Technting Shield غير محدّثة", "تعذّر تنزيل إحدى قوائم التهديدات منذ عدة أيام، وما زالت آخر نسخة سليمة مستخدمة."),
        "public_changed": ("تغيّر الموقع العام من خارج Technting CMS", "ملفات على example.com لم تعد تطابق ما نشره Technting CMS (أو حُذفت). ربما غيّر أحدهم الموقع على الخادم. إعادة النشر ترجعها كما كانت، ثم ابحثوا كيف حدث ذلك."),
        "domain_dns": ("تغيّرت سجلات نطاقنا", "تغيّرت خوادم الأسماء أو خوادم البريد أو عنوان الموقع لنطاقنا. إذا لم يفعل ذلك أحد من الفريق، فقد يكون النطاق سُرق: افحصوا حساب النطاق وCloudflare الآن."),
        "lookalike": ("سُجّل نطاق يشبه نطاقنا", "سجّل أحدهم اسماً يختلف عن اسمنا بحرف واحد. قد يُستخدم لرسائل مزيفة أو نسخة مزيفة من الموقع. نبّهوا الفريق والعملاء، وأبلغوا جهة التسجيل إذا أسيء استخدامه."),
        "media": ("ملف مشبوه في مكتبة الوسائط", "ملف في مكتبة الوسائط ليس كما يقول اسمه أو يخفي كوداً. افحصوه واحذفوه إذا لم يرفعه أحد من الفريق."),
        "hello": "مرحباً", "details": "التفاصيل", "open": "فتح Technting Shield", "account": "إذا كنتم أنتم من سجّل الدخول، تجاهلوا هذه الرسالة.",
        "why": "تصلكم هذه الرسائل لأنكم فعّلتم تنبيهات الأمان من «حسابي» في Technting CMS، ويمكنكم إيقافها من هناك في أي وقت.",
    },
}
SIGN_IN = {"new_device", "new_country", "breached_password"}


def pref(user):
    from cms.models import Setting
    v = Setting.objects.filter(key=f"shield_alerts:{user.pk}").values_list("value", flat=True).first() or {}
    return {"on": bool(v.get("on")), "lang": v.get("lang") if v.get("lang") in TEXT else "en"}


def set_pref(user, on, lang):
    from cms.models import Setting
    Setting.objects.update_or_create(key=f"shield_alerts:{user.pk}", defaults={"value": {"on": bool(on), "lang": lang if lang in TEXT else "en"}})


def _send(user, kind, detail="", ua=""):
    from cms import mail
    p = pref(user)
    if not (p["on"] and user.is_active and user.is_superuser and user.email and mail.ready()):
        return False
    key = f"shield-alert:{kind}:{user.pk}"
    if cache.get(key):
        return False
    cache.set(key, 1, 3600)
    t = TEXT[p["lang"]]
    subject, intro = t[kind]
    lines = [f"{t['hello']} {user.get_full_name() or user.get_username()},", "", intro, ""]
    if detail or ua:
        lines += [f"{t['details']}: {detail}".strip()] + ([ua] if ua else []) + [""]
    if kind in SIGN_IN:
        lines += [t["account"], ""]
    lines += [f"{t['open']}: {settings.TECHNTING_CMS_ADMIN_URL}/shield/", "", "--", t["why"]]
    try:
        mail.send(subject, "\n".join(lines), [user.email])
        return True
    except Exception as exc:
        log.warning("shield alert email failed: %s", type(exc).__name__)
        return False


def send_user(user, kind, detail="", ua=""):
    """An alert about the person's own account."""
    return _send(user, kind, detail, ua)


def send_admins(kind, detail=""):
    """An alert for every administrator who turned alerts on. Returns how many were sent."""
    return sum(_send(u, kind, detail) for u in get_user_model().objects.filter(is_superuser=True, is_active=True))
