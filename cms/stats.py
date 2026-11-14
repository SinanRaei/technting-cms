"""Site stats without cookies (in the spirit of Jetpack Stats and Plausible).

The site-stats plugin adds a small script to public pages that sends one beacon per page view to /api/hit on the
dashboard host. We store the path, page language, traffic source, campaign tags from the link (utm_source,
utm_medium, utm_campaign, utm_content, reduced to short codes), country (from Cloudflare's CF-IPCountry header),
device class and a visitor code: a hash of IP address, browser and a salt that is replaced every day and never
kept. The IP address itself is never stored, nothing is stored in the visitor's browser, and the same person
cannot be followed from one day to the next. Signed-in dashboard users are not counted.
"""
import hashlib
import json
import re
import secrets
from collections import Counter, defaultdict
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from django.utils import timezone

PLUGIN = "site-stats"
KEEP_DAYS = 400
BOTS = re.compile(r"bot|crawl|spider|slurp|headless|lighthouse|pingdom|uptime|monitor|preview|facebookexternalhit|"
                  r"embedly|python|curl|wget|httpclient|go-http|java/|okhttp|axios|node-fetch|scrapy|phantom", re.I)

# (pattern on the referrer host, source name, channel). First match wins, so specific hosts come first.
SOURCES = [
    (r"(^|\.)gemini\.google\.com$", "Gemini", "ai"), (r"(^|\.)(chatgpt\.com|chat\.openai\.com)$", "ChatGPT", "ai"),
    (r"(^|\.)perplexity\.ai$", "Perplexity", "ai"), (r"(^|\.)claude\.ai$", "Claude", "ai"),
    (r"(^|\.)copilot\.microsoft\.com$", "Copilot", "ai"), (r"(^|\.)(deepseek\.com|chat\.deepseek\.com)$", "DeepSeek", "ai"),
    (r"(^|\.)mail\.google\.com$", "Gmail", "email"), (r"(^|\.)(outlook\.(live|office|office365)\.com)$", "Outlook", "email"),
    (r"(^|\.)google\.[a-z.]+$", "Google", "search"), (r"(^|\.)bing\.com$", "Bing", "search"),
    (r"(^|\.)duckduckgo\.com$", "DuckDuckGo", "search"), (r"(^|\.)yahoo\.[a-z.]+$", "Yahoo", "search"),
    (r"(^|\.)yandex\.[a-z.]+$", "Yandex", "search"), (r"(^|\.)baidu\.com$", "Baidu", "search"),
    (r"(^|\.)ecosia\.org$", "Ecosia", "search"), (r"(^|\.)brave\.com$", "Brave Search", "search"),
    (r"(^|\.)(linkedin\.com|lnkd\.in)$", "LinkedIn", "social"), (r"(^|\.)(x\.com|twitter\.com|t\.co)$", "X", "social"),
    (r"(^|\.)(facebook\.com|fb\.com|fb\.me)$", "Facebook", "social"), (r"(^|\.)instagram\.com$", "Instagram", "social"),
    (r"(^|\.)(whatsapp\.com|wa\.me)$", "WhatsApp", "social"), (r"(^|\.)(youtube\.com|youtu\.be)$", "YouTube", "social"),
    (r"(^|\.)reddit\.com$", "Reddit", "social"), (r"(^|\.)t\.me$", "Telegram", "social"),
    (r"(^|\.)github\.com$", "GitHub", "referral"),
]
CHANNEL_LABELS = {"direct": "Direct", "search": "Search engines", "ai": "AI assistants", "social": "Social media",
                  "email": "Email", "referral": "Other websites", "campaign": "Campaigns"}
DEVICE_LABELS = {"mobile": "Mobile", "tablet": "Tablet", "desktop": "Desktop"}
LANG_LABELS = {"en": "English", "ar": "Arabic"}

COUNTRIES = {
    "JO": ("Jordan", "الأردن"), "SA": ("Saudi Arabia", "السعودية"), "AE": ("United Arab Emirates", "الإمارات"),
    "QA": ("Qatar", "قطر"), "KW": ("Kuwait", "الكويت"), "BH": ("Bahrain", "البحرين"), "OM": ("Oman", "عُمان"),
    "EG": ("Egypt", "مصر"), "IQ": ("Iraq", "العراق"), "LB": ("Lebanon", "لبنان"), "PS": ("Palestine", "فلسطين"),
    "SY": ("Syria", "سوريا"), "MA": ("Morocco", "المغرب"), "DZ": ("Algeria", "الجزائر"), "TN": ("Tunisia", "تونس"),
    "LY": ("Libya", "ليبيا"), "SD": ("Sudan", "السودان"), "YE": ("Yemen", "اليمن"), "TR": ("Türkiye", "تركيا"),
    "US": ("United States", "الولايات المتحدة"), "GB": ("United Kingdom", "المملكة المتحدة"), "CA": ("Canada", "كندا"),
    "DE": ("Germany", "ألمانيا"), "FR": ("France", "فرنسا"), "NL": ("Netherlands", "هولندا"), "IE": ("Ireland", "أيرلندا"),
    "ES": ("Spain", "إسبانيا"), "IT": ("Italy", "إيطاليا"), "SE": ("Sweden", "السويد"), "CH": ("Switzerland", "سويسرا"),
    "IN": ("India", "الهند"), "PK": ("Pakistan", "باكستان"), "SG": ("Singapore", "سنغافورة"), "CN": ("China", "الصين"),
    "JP": ("Japan", "اليابان"), "KR": ("South Korea", "كوريا الجنوبية"), "AU": ("Australia", "أستراليا"),
    "BR": ("Brazil", "البرازيل"), "RU": ("Russia", "روسيا"), "ZA": ("South Africa", "جنوب أفريقيا"),
    "NG": ("Nigeria", "نيجيريا"), "KE": ("Kenya", "كينيا"), "ID": ("Indonesia", "إندونيسيا"), "MY": ("Malaysia", "ماليزيا"),
}


def enabled():
    from .plugins import enabled_names
    return PLUGIN in enabled_names()


def _salt(today):
    """Today's salt. Yesterday's is overwritten, so old visitor codes can never be recomputed."""
    from .models import Setting
    key = f"stats-salt:{today}"
    salt = cache.get(key)
    if salt:
        return salt
    s, _ = Setting.objects.get_or_create(key="stats_salt", defaults={"value": {}})
    if s.value.get("day") != today:
        s.value = {"day": today, "salt": secrets.token_hex(16)}
        s.save(update_fields=["value"])
    cache.set(key, s.value["salt"], 3600)
    return s.value["salt"]


def visitor_code(ip, ua, today):
    return hashlib.sha256(f"{_salt(today)}|{ip}|{ua}".encode()).hexdigest()[:16]


def classify(referrer, utm_source="", site_host=""):
    """(source, channel, referrer host) for a page view."""
    if utm_source:
        return utm_source[:60].lower(), "campaign", ""
    host = (urlparse(referrer).hostname or "").lower() if referrer else ""
    if host.startswith("www."):
        host = host[4:]
    if not host or host == site_host or host.endswith("." + site_host):
        return "", "direct", ""
    for pattern, name, channel in SOURCES:
        if re.search(pattern, host):
            return name, channel, host
    return host[:80], "referral", host[:120]


UTM_BAD = re.compile(r"[^a-z0-9_.+-]+")


def utm(value, limit):
    """A campaign tag as a short lower-case code (letters, digits, _ . + -). Anything else becomes "_", so an e-mail
    address or free text pasted into a link cannot be stored as typed."""
    value = UTM_BAD.sub("_", str(value or "").strip().lower()[:limit * 2]).strip("_")
    return value[:limit]


def device_of(width):
    try:
        w = int(width)
    except (TypeError, ValueError):
        return ""
    return "mobile" if w < 768 else "tablet" if w < 1100 else "desktop"


def record(request, data):
    """Store one page view. Returns False when it is ignored."""
    from .forms_api import client_ip
    from .models import Hit
    ua = request.META.get("HTTP_USER_AGENT", "")
    if not ua or BOTS.search(ua) or getattr(request, "user", None) and request.user.is_authenticated:
        return False
    path = str(data.get("p") or "")[:300]
    if not path.startswith("/") or "//" in path or any(ord(c) < 32 for c in path):
        return False
    ip = client_ip(request)
    key = f"hits:{hashlib.sha256(ip.encode()).hexdigest()[:16]}"
    n = cache.get(key, 0)
    if n >= 120:  # 120 page views per 10 minutes from one address is not a person reading
        return False
    cache.set(key, n + 1, 600)
    now = timezone.now()
    today = timezone.localdate(now).isoformat()
    site_host = (urlparse(settings.TECHNTING_CMS_SITE_URL).hostname or "").removeprefix("www.")
    source, channel, ref_host = classify(str(data.get("r") or "")[:500], utm(data.get("u"), 60), site_host)
    lang = str(data.get("l") or "")[:8].lower()
    country = request.META.get("HTTP_CF_IPCOUNTRY", "")[:2].upper()
    Hit.objects.create(
        ts=now, path=path, lang=lang if re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", lang) else "",
        source=source, channel=channel, ref_host=ref_host, campaign=utm(data.get("c"), 80),
        medium=utm(data.get("m"), 60), content=utm(data.get("n"), 80),
        country=country if re.fullmatch(r"[A-Z]{2}", country) and country not in ("XX", "T1") else "",
        device=device_of(data.get("w")), visitor=visitor_code(ip, ua, today),
        status=404 if data.get("s") == 404 else 200)
    return True


def prune():
    """Delete page views older than KEEP_DAYS (at most once a day)."""
    from .models import Hit
    if cache.get("stats-pruned"):
        return 0
    cache.set("stats-pruned", 1, 86400)
    return Hit.objects.filter(ts__lt=timezone.now() - timedelta(days=KEEP_DAYS)).delete()[0]


# ---------------------------------------------------------------- reports
def _period(days):
    end = timezone.now()
    return end - timedelta(days=days), end


def _summary(qs):
    rows = list(qs.values("visitor", "ts"))
    daily = {(timezone.localdate(r["ts"]), r["visitor"]) for r in rows}
    return {"views": len(rows), "visitors": len(daily)}


def _change(now, before):
    if not before:
        return None
    return round((now - before) * 100 / before)


def campaign_table(rows, campaign="", content=""):
    """Visits and page views per utm_campaign / utm_content / utm_source / utm_medium, optionally filtered.

    A visit is one visitor on one day who arrived with these tags; page views count only the tagged pages."""
    groups = defaultdict(lambda: {"visits": set(), "views": 0})
    campaigns, contents = Counter(), Counter()
    for r in rows:
        if not (r["campaign"] or r["content"] or r["medium"] or r["channel"] == "campaign"):
            continue
        visit = (timezone.localdate(r["ts"]), r["visitor"])
        campaigns[r["campaign"]] += 1
        if campaign and r["campaign"] != campaign:
            continue
        contents[r["content"]] += 1
        if content and r["content"] != content:
            continue
        g = groups[(r["campaign"], r["content"], r["source"] if r["channel"] == "campaign" else "", r["medium"])]
        g["views"] += 1
        g["visits"].add(visit)
    table = [{"campaign": k[0], "content": k[1], "source": k[2], "medium": k[3], "visits": len(v["visits"]), "views": v["views"]}
             for k, v in groups.items()]
    table.sort(key=lambda x: (-x["visits"], -x["views"], x["campaign"], x["content"]))
    return {"rows": table[:200], "campaigns": sorted(campaigns), "contents": sorted(contents),
            "campaign": campaign, "content": content,
            "visits": sum(x["visits"] for x in table), "views": sum(x["views"] for x in table)}


def report(days=30, lang="en", campaign="", content=""):
    from .models import FormSubmission, Hit
    start, end = _period(days)
    prev_start = start - (end - start)
    ok = Hit.objects.filter(status=200)
    cur = ok.filter(ts__gte=start, ts__lt=end)
    prev = ok.filter(ts__gte=prev_start, ts__lt=start)
    s_now, s_prev = _summary(cur), _summary(prev)
    enq = FormSubmission.objects.filter(created_at__gte=start, created_at__lt=end).count()
    enq_prev = FormSubmission.objects.filter(created_at__gte=prev_start, created_at__lt=start).count()
    from urllib.parse import urlsplit
    enq_pages = Counter(urlsplit(p).path or "/" for p in FormSubmission.objects.filter(
        created_at__gte=start, created_at__lt=end).values_list("page", flat=True) if p)

    rows = list(cur.values("ts", "visitor", "path", "source", "channel", "country", "device", "lang", "campaign", "medium",
                           "content"))
    by_day = defaultdict(lambda: {"views": 0, "visitors": set()})
    pages, page_vis = Counter(), defaultdict(set)
    sources, channels, countries, devices, langs, campaigns = (Counter() for _ in range(6))
    first_hit = {}
    for r in sorted(rows, key=lambda r: r["ts"]):
        d = timezone.localdate(r["ts"])
        visit = (d, r["visitor"])
        by_day[d]["views"] += 1
        by_day[d]["visitors"].add(r["visitor"])
        pages[r["path"]] += 1
        page_vis[r["path"]].add(visit)
        if visit not in first_hit:  # count source, country, device once per visitor per day
            first_hit[visit] = r
            channels[r["channel"] or "direct"] += 1
            if r["source"]:
                sources[r["source"]] += 1
            countries[r["country"] or "--"] += 1
            devices[r["device"] or "--"] += 1
            langs[r["lang"] or "--"] += 1
            if r["campaign"]:
                campaigns[r["campaign"]] += 1

    # chart: one bar per day (weeks for a year)
    step = 7 if days > 120 else 1
    first_day = timezone.localdate(start)
    series = []
    for i in range(0, days, step):
        span = [first_day + timedelta(days=i + k) for k in range(step)]
        series.append({"day": span[0], "views": sum(by_day[d]["views"] for d in span if d in by_day),
                       "visitors": sum(len(by_day[d]["visitors"]) for d in span if d in by_day)})
    peak = max([s["views"] for s in series] + [1])
    for s in series:
        s["h_views"] = round(s["views"] * 100 / peak, 1)
        s["h_visitors"] = round(s["visitors"] * 100 / peak, 1)

    def country_name(code):
        names = COUNTRIES.get(code)
        if code == "--":
            return "Unknown"
        return (names[1] if lang == "ar" else names[0]) if names else code

    def top(counter, n=10, label=lambda k: k):
        total = sum(counter.values()) or 1
        return [{"key": k, "label": label(k), "count": c, "pct": round(c * 100 / total)} for k, c in counter.most_common(n)]

    not_found = (Hit.objects.filter(status=404, ts__gte=start, ts__lt=end).values("path")
                 .annotate(n=Count("id")).order_by("-n")[:15])
    live = Hit.objects.filter(ts__gte=timezone.now() - timedelta(minutes=30)).values("visitor").distinct().count()
    return {
        "days": days, "start": start, "end": end, "live": live,
        "visitors": s_now["visitors"], "views": s_now["views"], "enquiries": enq,
        "visitors_change": _change(s_now["visitors"], s_prev["visitors"]), "views_change": _change(s_now["views"], s_prev["views"]),
        "enquiries_change": _change(enq, enq_prev),
        "per_visit": round(s_now["views"] / s_now["visitors"], 1) if s_now["visitors"] else 0,
        "enquiry_rate": round(enq * 100 / s_now["visitors"], 1) if s_now["visitors"] else 0,
        "series": series, "peak": peak, "step": step,
        "pages": [{"path": p, "views": c, "visitors": len(page_vis[p])} for p, c in pages.most_common(15)],
        "enquiry_pages": [{"path": p, "count": c, "views": pages.get(p, 0)} for p, c in enq_pages.most_common(15)],
        "sources": top(sources), "channels": top(channels, 7, lambda k: CHANNEL_LABELS.get(k, k)),
        "countries": top(countries, 12, country_name), "devices": top(devices, 4, lambda k: DEVICE_LABELS.get(k, "Unknown")),
        "langs": top(langs, 4, lambda k: LANG_LABELS.get(k, "Unknown")), "campaigns": top(campaigns),
        "campaign_table": campaign_table(rows, utm(campaign, 80), utm(content, 80)),
        "not_found": list(not_found),
    }


def week_summary():
    """Visitors in the last 7 days and the change from the 7 days before (dashboard card)."""
    from .models import Hit
    start, end = _period(7)
    ok = Hit.objects.filter(status=200)
    now = _summary(ok.filter(ts__gte=start, ts__lt=end))
    before = _summary(ok.filter(ts__gte=start - timedelta(days=7), ts__lt=start))
    return {"visitors": now["visitors"], "views": now["views"], "change": _change(now["visitors"], before["visitors"])}


def beacon_script(status=200):
    endpoint = settings.TECHNTING_CMS_ADMIN_URL.rstrip("/") + "/api/hit"
    return ("<script>(function(){try{if(navigator.webdriver)return;var q=new URLSearchParams(location.search),"
            "b=JSON.stringify({p:location.pathname,r:document.referrer,l:document.documentElement.lang,w:innerWidth,"
            "s:%d,u:q.get('utm_source')||'',m:q.get('utm_medium')||'',c:q.get('utm_campaign')||'',"
            "n:q.get('utm_content')||''}),x=%s;"
            "if(navigator.sendBeacon&&navigator.sendBeacon(x,b))return;"
            "fetch(x,{method:'POST',body:b,keepalive:true,mode:'no-cors',credentials:'include'})}catch(e){}})();</script>"
            % (status, json.dumps(endpoint)))
