"""Technting SEO: how the site does in Google and Bing, from free APIs, kept fresh by publish_due.

Sources (each optional; the plugin "seo-pro" must be on):
  Google Search Console  Search Analytics (clicks, impressions, CTR and position per page and query) once a day, and
                         URL Inspection (index status, last crawl) for the key pages once a week. It signs in as a
                         Google Cloud service account that the owner adds as a user on the Search Console property; the
                         JSON key is uploaded in the plugin settings and stored encrypted (see plugins.keep_secrets).
  PageSpeed Insights     Core Web Vitals from real Chrome users plus Lighthouse scores, once a month for the home pages
                         and the newest articles, two addresses per publish_due run (needs a free API key).
  Bing Webmaster Tools   clicks and impressions per query and page once a week (free API key).
Keyword tracking: after each daily fetch, the Google position of every article's focus keyword (each language) is
kept for KEEP_DAYS days, so the SEO page can show the change over 7 and 28 days. The sitemap status (last read by
Google, errors, warnings) is read once a week with the index check.
Results are JSON files in VAR_DIR/seo/ that the SEO page, the article SEO check and the weekly email read. Network
failures are recorded as a short message per source and never raised, so publishing is never affected.
"""
import base64
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

from django.conf import settings
from django.utils import timezone

PLUGIN = "seo-pro"
DIR = "seo"
DAYS, LAG = 28, 3            # compare the last 28 days with the 28 before; Search Console data settles after ~3 days
TIMEOUT, PSI_TIMEOUT = 30, 90
SC = "https://searchconsole.googleapis.com"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
PSI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
BING = "https://ssl.bing.com/webmaster/api.svc/json/"
EVERY = {"search": timedelta(hours=20), "inspect": timedelta(days=7), "bing": timedelta(days=7)}
RETRY_AFTER = timedelta(hours=6)   # after a failure, wait before trying again (a wrong key must not hit the API every 5 min)
NEWEST_POSTS = {"inspect": 8, "pagespeed": 3}
MIN_IMPRESSIONS = 5
KEEP_DAYS = 120
_tokens, _running = {}, threading.Lock()


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- storage and settings
def _file(name):
    d = Path(settings.VAR_DIR, DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def load(name):
    p = _file(name)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except ValueError:
        return None


def save(name, data):
    p = _file(name)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def enabled():
    from .plugins import enabled_names
    return PLUGIN in enabled_names()


def conf():
    """Plugin settings with the secrets decrypted. google is the parsed key file or None."""
    from .plugins import plugin_settings, secret
    try:
        google = json.loads(secret(PLUGIN, "google_key") or "null")
    except ValueError:
        google = None
    prop = (plugin_settings(PLUGIN).get("property") or "").strip() or settings.TECHNTING_CMS_SITE_URL + "/"
    return {"google": google if isinstance(google, dict) else None, "property": prop,
            "pagespeed": secret(PLUGIN, "pagespeed_key").strip(), "bing": secret(PLUGIN, "bing_key").strip()}


def key_problem(info):
    """Why a parsed key file cannot be used, or ''."""
    if not info:
        return "No service account key uploaded."
    if info.get("type") != "service_account" or not info.get("client_email") or not info.get("private_key"):
        return "This file is not a service account key. Download a JSON key from the service account's Keys tab."
    return ""


def status():
    return load("status.json") or {}


def _set_status(source, ok, error="", code=None, now=None):
    s = status()
    s[source] = {"ok": ok, "at": (now or timezone.now()).isoformat(), "error": error, "code": code}
    save("status.json", s)


# ---------------------------------------------------------------- HTTP
def _call(url, body=None, headers=None, form=False, timeout=TIMEOUT):
    """JSON from a Google or Bing API. Raises ApiError with the service's own message; never echoes the URL (it may
    carry an API key)."""
    h = {"Accept": "application/json", "User-Agent": "Technting-CMS-seo-pro"}
    h.update(headers or {})
    data = None
    if body is not None:
        data = urlencode(body).encode() if form else json.dumps(body).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8", "replace") or "{}")
        except ValueError:
            detail = {}
        err = detail.get("error") if isinstance(detail, dict) else None
        msg = (err.get("message") if isinstance(err, dict) else detail.get("error_description") or detail.get("Message") or err) \
            if isinstance(detail, dict) else None
        raise ApiError(str(msg or e.reason or "error")[:300], e.code) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ApiError(f"No answer from the service ({e.__class__.__name__}).") from None


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def google_token(info):
    """OAuth access token for the service account (JWT bearer grant, RS256), kept in memory until it expires."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    problem = key_problem(info)
    if problem:
        raise ApiError(problem)
    ck = hashlib.sha256((info["client_email"] + info.get("private_key_id", "")).encode()).hexdigest()
    tok = _tokens.get(ck)
    if tok and tok[1] > time.time():
        return tok[0]
    now = int(time.time())
    head = {"alg": "RS256", "typ": "JWT"}
    if info.get("private_key_id"):
        head["kid"] = info["private_key_id"]
    claims = {"iss": info["client_email"], "scope": SCOPE, "aud": TOKEN_URL, "iat": now, "exp": now + 3600}
    signing = _b64(json.dumps(head).encode()) + "." + _b64(json.dumps(claims).encode())
    try:
        key = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
        sig = key.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
    except (ValueError, TypeError, AttributeError):
        raise ApiError("The private key in the key file cannot be read. Download a new JSON key.") from None
    r = _call(TOKEN_URL, {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": signing + "." + _b64(sig)}, form=True)
    if not r.get("access_token"):
        raise ApiError("Google did not return an access token.")
    _tokens[ck] = (r["access_token"], time.time() + min(int(r.get("expires_in", 3600)), 3600) - 300)
    return r["access_token"]


# ---------------------------------------------------------------- site addresses
def _lang_prefixes():
    from .models import Language
    return {l.code: l.url_prefix for l in Language.objects.all()}


def lang_of(path, prefixes=None):
    prefixes = prefixes if prefixes is not None else _lang_prefixes()
    for code, prefix in prefixes.items():
        if prefix and (path == f"/{prefix}" or path.startswith(f"/{prefix}/")):
            return code
    return next((c for c, p in prefixes.items() if not p), "en")


def path_of(url):
    return urlparse(url).path or "/"


def _live_urls():
    """Addresses in the published sitemap (None when the site has not been built here)."""
    f = Path(settings.TECHNTING_CMS_OUTPUT_DIR) / "sitemap.xml"
    if not f.exists():
        return None
    return set(re.findall(r"<loc>([^<]+)</loc>", f.read_text(encoding="utf-8", errors="replace")))


def key_urls(posts):
    """Home and blog pages in every language, then the newest live articles in every language."""
    from .models import Entry, PageTranslation
    from .theme import load_theme
    live = _live_urls()
    site = settings.TECHNTING_CMS_SITE_URL
    out = []
    for key in ("home", "blog"):
        for t in PageTranslation.objects.filter(page__key=key).select_related("page", "language").order_by("language__order"):
            if t.is_live and not t.noindex:
                out.append(site + t.url)
    route = load_theme().collections.get("post", {}).get("route")
    if route:
        prefixes = _lang_prefixes()
        newest = sorted(Entry.objects.filter(collection="post", is_published=True),
                        key=lambda e: (str((e.data or {}).get("date") or ""), e.updated_at), reverse=True)
        n = 0
        for e in newest:
            urls = [site + (f"/{p}" if p else "") + route.format(key=e.key) for p in prefixes.values()]
            urls = [u for u in urls if live is None or u in live]
            if urls:
                out += urls
                n += 1
            if n >= posts:
                break
    return list(dict.fromkeys(out))


# ---------------------------------------------------------------- Google Search Console: search analytics
def periods(today):
    end = today - timedelta(days=LAG)
    start = end - timedelta(days=DAYS - 1)
    prev_end = start - timedelta(days=1)
    return start, end, prev_end - timedelta(days=DAYS - 1), prev_end


def _rows(rows, *names):
    return [dict(zip(names, r.get("keys", [])), clicks=r.get("clicks", 0), impressions=r.get("impressions", 0),
                 ctr=round(r.get("ctr", 0), 4), position=round(r.get("position", 0), 1)) for r in rows]


def fetch_search(c, today=None):
    today = today or timezone.localdate()
    start, end, ps, pe = periods(today)
    tok = google_token(c["google"])
    url = f"{SC}/webmasters/v3/sites/{quote(c['property'], safe='')}/searchAnalytics/query"

    def q(s, e, dims, limit=1000):
        body = {"startDate": s.isoformat(), "endDate": e.isoformat(), "dimensions": dims, "rowLimit": limit, "type": "web"}
        return _call(url, body, headers={"Authorization": "Bearer " + tok}).get("rows", [])
    data = {"fetched_at": timezone.now().isoformat(), "property": c["property"],
            "period": {"start": start.isoformat(), "end": end.isoformat(), "prev_start": ps.isoformat(), "prev_end": pe.isoformat()},
            "daily": _rows(q(ps, end, ["date"], 200), "date"),
            "pages": _rows(q(start, end, ["page"]), "page"), "prev_pages": _rows(q(ps, pe, ["page"]), "page"),
            "queries": _rows(q(start, end, ["query"]), "query"), "prev_queries": _rows(q(ps, pe, ["query"]), "query"),
            "page_queries": _rows(q(start, end, ["page", "query"], 5000), "page", "query")}
    save("search.json", data)
    record_keywords(data)
    return data


def _totals(rows):
    clicks = sum(r["clicks"] for r in rows)
    imp = sum(r["impressions"] for r in rows)
    pos = sum(r["position"] * r["impressions"] for r in rows) / imp if imp else None
    return {"clicks": clicks, "impressions": imp, "ctr": round(100 * clicks / imp, 1) if imp else 0,
            "position": round(pos, 1) if pos else None}


def _change(now, before):
    if not before:
        return None
    return round(100 * (now - before) / before)


def search_report(data=None):
    """Everything the SEO page shows about Google search, or None before the first fetch."""
    data = data or load("search.json")
    if not data:
        return None
    p = data["period"]
    prefixes = _lang_prefixes()
    cur = _totals([d for d in data["daily"] if d["date"] >= p["start"]])
    prev = _totals([d for d in data["daily"] if d["date"] <= p["prev_end"]])
    totals = dict(cur)
    totals.update(clicks_change=_change(cur["clicks"], prev["clicks"]), impressions_change=_change(cur["impressions"], prev["impressions"]),
                  position_before=prev["position"], ctr_before=prev["ctr"])
    peak = max([d["impressions"] for d in data["daily"]] + [1])
    series = [{"day": d["date"], "clicks": d["clicks"], "impressions": d["impressions"], "current": d["date"] >= p["start"],
               "h_impressions": round(100 * d["impressions"] / peak), "h_clicks": round(100 * d["clicks"] / peak)} for d in data["daily"]]
    before = {r["page"]: r for r in data["prev_pages"]}
    pages = []
    for r in data["pages"]:
        b = before.get(r["page"], {})
        pages.append(dict(r, path=path_of(r["page"]), lang=lang_of(path_of(r["page"]), prefixes), prev_clicks=b.get("clicks", 0),
                          prev_position=b.get("position")))
    seen = {r["page"] for r in data["pages"]}
    gone = [dict(r, path=path_of(r["page"]), lang=lang_of(path_of(r["page"]), prefixes), prev_clicks=r["clicks"], clicks=0,
                 impressions=0, ctr=0, position=None, prev_position=r["position"]) for r in data["prev_pages"] if r["page"] not in seen]
    losing = sorted([r for r in pages + gone if r["prev_clicks"] - r["clicks"] >= 2 and r["clicks"] <= 0.8 * r["prev_clicks"]],
                    key=lambda r: r["clicks"] - r["prev_clicks"])[:10]
    by_lang = {}
    for r in pages:
        by_lang.setdefault(r["lang"], []).append(r)
    langs = [dict(_totals(rows), code=code, pages=len(rows)) for code, rows in sorted(by_lang.items())]
    best_page = {}
    for r in data["page_queries"]:
        if r["impressions"] > best_page.get(r["query"], {}).get("impressions", -1):
            best_page[r["query"]] = r
    prev_q = {r["query"]: r for r in data["prev_queries"]}
    queries = [dict(r, path=path_of(best_page.get(r["query"], {}).get("page", "")) if r["query"] in best_page else "",
                    prev_position=prev_q.get(r["query"], {}).get("position")) for r in data["queries"]]
    page_two = sorted([q for q in queries if 10 < q["position"] <= 20 and q["impressions"] >= MIN_IMPRESSIONS],
                      key=lambda q: -q["impressions"])[:15]
    low_ctr = sorted([dict(r, ctr_pct=round(100 * r["ctr"], 1)) for r in pages
                      if r["position"] and r["position"] <= 10 and r["impressions"] >= 50 and r["ctr"] < 0.02],
                     key=lambda r: -r["impressions"])[:10]
    return {"fetched_at": data["fetched_at"], "period": p, "totals": totals, "series": series, "langs": langs,
            "pages": sorted(pages, key=lambda r: (-r["clicks"], -r["impressions"]))[:25],
            "queries": sorted(queries, key=lambda r: (-r["clicks"], -r["impressions"]))[:25],
            "losing": losing, "page_two": page_two, "low_ctr": low_ctr}


def page_queries(path, limit=10):
    """Searches that showed this page on Google (28 days), most impressions first."""
    data = load("search.json")
    if not data:
        return []
    rows = [r for r in data["page_queries"] if path_of(r["page"]) == path]
    rows.sort(key=lambda r: (-r["impressions"], -r["clicks"]))
    return [dict(r, page_two=10 < r["position"] <= 20) for r in rows[:limit]]


def queries_by_path(per_page=5):
    """{path: [query, ...]} the searches each page is found for; used for internal-link ideas."""
    data = load("search.json")
    out = {}
    for r in sorted((data or {}).get("page_queries", []), key=lambda r: -r["impressions"]):
        lst = out.setdefault(path_of(r["page"]), [])
        if len(lst) < per_page:
            lst.append(r["query"])
    return out


# ---------------------------------------------------------------- Google Search Console: URL inspection
def inspect_urls(c, urls=None):
    tok = google_token(c["google"])
    prefixes = _lang_prefixes()
    items = []
    for url in urls if urls is not None else key_urls(NEWEST_POSTS["inspect"]):
        try:
            r = _call(f"{SC}/v1/urlInspection/index:inspect", {"inspectionUrl": url, "siteUrl": c["property"], "languageCode": "en-US"},
                      headers={"Authorization": "Bearer " + tok})
        except ApiError as e:
            if e.status in (401, 403):
                raise
            items.append({"url": url, "path": path_of(url), "lang": lang_of(path_of(url), prefixes), "error": str(e)})
            continue
        s = (r.get("inspectionResult") or {}).get("indexStatusResult") or {}
        items.append({"url": url, "path": path_of(url), "lang": lang_of(path_of(url), prefixes), "verdict": s.get("verdict"),
                      "coverage": s.get("coverageState") or "", "last_crawl": s.get("lastCrawlTime") or "",
                      "fetch": s.get("pageFetchState") or "", "robots": s.get("robotsTxtState") or "",
                      "indexing": s.get("indexingState") or "", "google_canonical": s.get("googleCanonical") or "",
                      "user_canonical": s.get("userCanonical") or ""})
    data = {"checked_at": timezone.now().isoformat(), "items": items}
    save("inspect.json", data)
    return data


def inspect_report():
    data = load("inspect.json")
    if not data:
        return None
    items = data["items"]
    for i in items:
        i["crawled"] = (i.get("last_crawl") or "")[:10]
        i["canonical_differs"] = bool(i.get("google_canonical") and i.get("user_canonical") and i["google_canonical"] != i["user_canonical"])
    return {"checked_at": data["checked_at"], "items": items, "indexed": sum(1 for i in items if i.get("verdict") == "PASS"),
            "problems": sum(1 for i in items if i.get("verdict") not in ("PASS", None) or i.get("error"))}


def fetch_sitemaps(c):
    """The sitemaps Search Console knows for the property: last read by Google, errors, warnings, addresses sent."""
    tok = google_token(c["google"])
    r = _call(f"{SC}/webmasters/v3/sites/{quote(c['property'], safe='')}/sitemaps", headers={"Authorization": "Bearer " + tok})
    items = [{"path": s.get("path", ""), "submitted": (s.get("lastSubmitted") or "")[:10], "downloaded": (s.get("lastDownloaded") or "")[:10],
              "pending": bool(s.get("isPending")), "errors": int(s.get("errors") or 0), "warnings": int(s.get("warnings") or 0),
              "urls": sum(int(x.get("submitted") or 0) for x in s.get("contents") or [])} for s in r.get("sitemap", [])]
    data = {"checked_at": timezone.now().isoformat(), "items": items,
            "ours": any(i["path"].rstrip("/") == settings.TECHNTING_CMS_SITE_URL + "/sitemap.xml" for i in items)}
    save("sitemaps.json", data)
    return data


# ---------------------------------------------------------------- keyword tracking
def tracked():
    """Every published article (routed collections with a focus keyword field) in every language it is written in."""
    from .models import Entry, Language
    from .theme import load_theme
    langs = list(Language.objects.all())
    out = []
    for coll, spec in load_theme().collections.items():
        if not spec.get("route") or not any(f["name"] == "focus_keyword" for f in spec.get("fields", [])):
            continue
        for e in Entry.objects.filter(collection=coll, is_published=True).prefetch_related("translations"):
            trs = {t.language_id: t.data for t in e.translations.all()}
            for l in langs:
                if l.pk not in trs:
                    continue
                d = dict(e.data or {})
                d.update(trs[l.pk])
                out.append({"id": f"{coll}:{e.key}:{l.code}", "entry": e, "collection": coll, "lang": l,
                            "path": (f"/{l.url_prefix}" if l.url_prefix else "") + spec["route"].format(key=e.key),
                            "keyword": (d.get("focus_keyword") or "").strip(), "title": d.get(spec.get("title_field", "name")) or e.key,
                            "fingerprint": hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:16]})
    return out


def record_keywords(data=None):
    """Keep today's Google position of every focus keyword (on its own article, or on another of our pages)."""
    from .seo import norm
    data = data or load("search.json")
    if not data:
        return None
    on_page, anywhere = {}, {}
    for r in data["page_queries"]:
        k = norm(r["query"])
        on_page.setdefault((path_of(r["page"]), k), r)
        if r["impressions"] > anywhere.get(k, {}).get("impressions", -1):
            anywhere[k] = r
    snap = {}
    for t in tracked():
        if not t["keyword"]:
            continue
        k = norm(t["keyword"])
        r = on_page.get((t["path"], k))
        other = path_of(anywhere[k]["page"]) if not r and k in anywhere else ""
        r = r or anywhere.get(k)
        snap[t["id"]] = {"keyword": t["keyword"], "position": r["position"] if r else None, "clicks": r["clicks"] if r else 0,
                         "impressions": r["impressions"] if r else 0, "other_page": other}
    hist = load("keywords.json") or {"days": {}}
    hist["days"][data["period"]["end"]] = snap
    for day in sorted(hist["days"])[:-KEEP_DAYS]:
        del hist["days"][day]
    save("keywords.json", hist)
    return snap


def _score(theme, t, entry_checks):
    """An article's SEO score, cached until it is saved again or the site is published again."""
    from django.core.cache import cache
    from .models import PublishLog
    built = PublishLog.objects.filter(ok=True).values_list("started_at", flat=True).first()
    key = "seo-score:" + hashlib.sha256(f"{t['id']}|{t['fingerprint']}|{t['entry'].updated_at}|{built}".encode()).hexdigest()[:32]
    score = cache.get(key)
    if score is None:
        try:
            score = (entry_checks(theme, t["collection"], t["entry"], t["lang"], extras=False) or {}).get("score")
        except Exception:
            return None
        cache.set(key, score, 7 * 86400)
    return score


def _moved(now, before):
    """Places gained (positive) or lost (negative); None when either side is missing."""
    if not now or not before or now.get("position") is None or before.get("position") is None:
        return None
    return round(before["position"] - now["position"], 1)


def keyword_report(scores=True):
    """One row per article and language: focus keyword, position now, change over 7 and 28 days, SEO score."""
    from django.urls import reverse
    hist = load("keywords.json") or {"days": {}}
    days = sorted(hist["days"])
    latest = hist["days"][days[-1]] if days else {}

    def back(n):
        if not days:
            return {}
        limit = (date.fromisoformat(days[-1]) - timedelta(days=n)).isoformat()
        older = [d for d in days if d <= limit]
        return hist["days"][older[-1]] if older else {}
    week, month = back(7), back(28)
    theme = None
    if scores:
        from .seo import entry_checks
        from .theme import load_theme
        theme = load_theme()
    rows = []
    for t in tracked():
        cur = latest.get(t["id"]) if t["keyword"] else None
        row = {"title": t["title"], "path": t["path"], "lang": t["lang"].code, "keyword": t["keyword"],
               "position": (cur or {}).get("position"), "clicks": (cur or {}).get("clicks", 0), "impressions": (cur or {}).get("impressions", 0),
               "other_page": (cur or {}).get("other_page", ""), "week": _moved(cur, week.get(t["id"])), "month": _moved(cur, month.get(t["id"])),
               "edit": reverse("cms:entry_edit", args=[t["collection"], t["entry"].pk, t["lang"].code]), "score": None}
        if theme is not None:
            row["score"] = _score(theme, t, entry_checks)
        rows.append(row)
    rows.sort(key=lambda r: (not r["keyword"], r["position"] is None, r["position"] or 0, r["path"]))
    moved = [r for r in rows if r["week"] is not None and abs(r["week"]) >= 3]
    return {"as_of": days[-1] if days else None, "rows": rows, "missing": sum(1 for r in rows if not r["keyword"]),
            "up": sorted([r for r in moved if r["week"] > 0], key=lambda r: -r["week"])[:5],
            "down": sorted([r for r in moved if r["week"] < 0], key=lambda r: r["week"])[:5]}


def dashboard_summary():
    """Clicks from Google for the dashboard card, or None."""
    if not enabled():
        return None
    s = search_report()
    return {"clicks": s["totals"]["clicks"], "change": s["totals"]["clicks_change"], "position": s["totals"]["position"],
            "page_two": len(s["page_two"])} if s else None


# ---------------------------------------------------------------- PageSpeed Insights
CWV = {"lcp_ms": (2500, 4000), "inp_ms": (200, 500), "cls": (0.1, 0.25)}   # good up to, poor above


def rating(metric, value):
    if value is None:
        return ""
    good, poor = CWV[metric]
    return "good" if value <= good else "poor" if value > poor else "needs"


def pagespeed(url, key):
    params = [("url", url), ("strategy", "mobile"), ("key", key)] + [("category", c) for c in ("PERFORMANCE", "ACCESSIBILITY", "BEST_PRACTICES", "SEO")]
    r = _call(PSI + "?" + urlencode(params), timeout=PSI_TIMEOUT)
    lh = r.get("lighthouseResult") or {}
    scores = {k.replace("-", "_"): round(v["score"] * 100) for k, v in (lh.get("categories") or {}).items() if isinstance(v, dict) and v.get("score") is not None}
    field = None
    for source, le in (("page", r.get("loadingExperience")), ("origin", r.get("originLoadingExperience"))):
        m = (le or {}).get("metrics") or {}
        if m:
            cls = (m.get("CUMULATIVE_LAYOUT_SHIFT_SCORE") or {}).get("percentile")
            field = {"source": source, "overall": le.get("overall_category") or "",
                     "lcp_ms": (m.get("LARGEST_CONTENTFUL_PAINT_MS") or {}).get("percentile"),
                     "inp_ms": (m.get("INTERACTION_TO_NEXT_PAINT") or {}).get("percentile"),
                     "cls": round(cls / 100, 2) if cls is not None else None}
            break
    audits = lh.get("audits") or {}
    lab = {"lcp_ms": (audits.get("largest-contentful-paint") or {}).get("numericValue"),
           "cls": (audits.get("cumulative-layout-shift") or {}).get("numericValue"),
           "tbt_ms": (audits.get("total-blocking-time") or {}).get("numericValue")}
    return {"url": url, "checked_at": timezone.now().isoformat(), "scores": scores, "field": field,
            "lab": {k: (round(v, 2) if k == "cls" else round(v)) if v is not None else None for k, v in lab.items()}}


def pagespeed_step(c, limit=2, now=None, restart=False):
    """Check up to `limit` addresses from this month's list; the list is rebuilt at the start of every month."""
    now = timezone.localtime(now or timezone.now())
    month = now.strftime("%Y-%m")
    data = load("pagespeed.json") or {}
    if restart or data.get("month") != month:
        previous = {u: r.get("scores", {}) for u, r in (data.get("results") or {}).items()}
        data = {"month": month, "started_at": now.isoformat(), "queue": key_urls(NEWEST_POSTS["pagespeed"]), "results": {},
                "previous": previous or data.get("previous", {}), "tries": {}}
        save("pagespeed.json", data)
    done = 0
    while data["queue"] and done < limit:
        url = data["queue"][0]
        try:
            data["results"][url] = pagespeed(url, c["pagespeed"])
        except ApiError as e:
            tries = data["tries"][url] = data["tries"].get(url, 0) + 1
            if e.status in (400, 403, 429) or tries >= 3:   # bad key, quota used up or keeps failing: note it, move on
                data["results"][url] = {"url": url, "checked_at": now.isoformat(), "error": str(e), "code": e.status}
                data["queue"].pop(0)
            save("pagespeed.json", data)
            raise                                           # the rest waits for the next try (RETRY_AFTER)
        data["queue"].pop(0)
        done += 1
        save("pagespeed.json", data)
    return done


def pagespeed_report():
    data = load("pagespeed.json")
    if not data:
        return None
    prefixes = _lang_prefixes()
    rows = []
    for url, r in data.get("results", {}).items():
        f = r.get("field") or {}
        before = (data.get("previous") or {}).get(url, {}).get("performance")
        perf = (r.get("scores") or {}).get("performance")
        rows.append(dict(r, path=path_of(url), lang=lang_of(path_of(url), prefixes), perf_change=None if before is None or perf is None else perf - before,
                         ratings={m: rating(m, f.get(m)) for m in CWV}))
    return {"month": data["month"], "rows": rows, "pending": len(data.get("queue", [])),
            "lowest": min((r for r in rows if (r.get("scores") or {}).get("performance") is not None),
                          key=lambda r: r["scores"]["performance"], default=None),
            "poor": sum(1 for r in rows for v in r["ratings"].values() if v == "poor")}


# ---------------------------------------------------------------- Bing Webmaster Tools
def _bing_date(value):
    m = re.search(r"/Date\((\d+)", str(value or ""))
    return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=dt_timezone.utc).date() if m else None


def _bing_sum(rows, since):
    out = {}
    for r in rows or []:
        d = _bing_date(r.get("Date"))
        if d and d < since:
            continue
        k = r.get("Query") or ""
        o = out.setdefault(k, {"key": k, "clicks": 0, "impressions": 0, "_pos": 0.0})
        o["clicks"] += int(r.get("Clicks") or 0)
        imp = int(r.get("Impressions") or 0)
        o["impressions"] += imp
        pos = r.get("AvgImpressionPosition")
        if pos is not None and pos > 0:
            o["_pos"] += float(pos) * imp
    rows = []
    for o in out.values():
        o["position"] = round(o.pop("_pos") / o["impressions"], 1) if o["impressions"] else None
        rows.append(o)
    return sorted(rows, key=lambda r: (-r["clicks"], -r["impressions"]))


def fetch_bing(c, today=None):
    since = (today or timezone.localdate()) - timedelta(days=DAYS)
    args = urlencode({"apikey": c["bing"], "siteUrl": c["property"]})
    queries = _bing_sum(_call(BING + "GetQueryStats?" + args).get("d"), since)
    pages = _bing_sum(_call(BING + "GetPageStats?" + args).get("d"), since)
    data = {"fetched_at": timezone.now().isoformat(), "since": since.isoformat(),
            "totals": {"clicks": sum(r["clicks"] for r in pages), "impressions": sum(r["impressions"] for r in pages)},
            "queries": queries[:50], "pages": [dict(r, path=path_of(r["key"])) for r in pages[:50]]}
    save("bing.json", data)
    return data


# ---------------------------------------------------------------- schedule
def _due(source, now, force):
    st = status().get(source) or {}
    if not force and st and not st.get("ok") and st.get("at") and now - datetime.fromisoformat(st["at"]) < RETRY_AFTER:
        return False
    if source == "pagespeed":
        data = load("pagespeed.json") or {}
        return force or data.get("month") != timezone.localtime(now).strftime("%Y-%m") or bool(data.get("queue"))
    if force:
        return True
    stamp = {"search": "fetched_at", "inspect": "checked_at", "bing": "fetched_at"}[source]
    last = (load(f"{source}.json") or {}).get(stamp)
    return not last or now - datetime.fromisoformat(last) >= EVERY[source]


def _run(source, fn, now=None):
    try:
        fn()
        _set_status(source, True, now=now)
        return f"{source}: updated"
    except ApiError as e:
        _set_status(source, False, str(e), e.status, now)
        return f"{source}: {e}"
    except Exception as e:  # a bug here must never stop publishing
        _set_status(source, False, e.__class__.__name__, now=now)
        return f"{source}: failed ({e.__class__.__name__})"


def run_due(now=None, force=False):
    """Fetch whatever is due. Called from publish_due every 5 minutes; returns one line per source it touched."""
    if not enabled():
        return []
    now = now or timezone.now()
    c = conf()
    out = []
    if c["google"] and _due("search", now, force):
        out.append(_run("search", lambda: fetch_search(c, timezone.localdate(now)), now))
    if c["google"] and _due("inspect", now, force):
        out.append(_run("inspect", lambda: (inspect_urls(c), fetch_sitemaps(c)), now))
    if c["bing"] and _due("bing", now, force):
        out.append(_run("bing", lambda: fetch_bing(c, timezone.localdate(now)), now))
    if c["pagespeed"] and _due("pagespeed", now, False):
        out.append(_run("pagespeed", lambda: pagespeed_step(c, now=now), now))
    return out


def refresh_in_background(pagespeed_restart=False):
    """The SEO page's "Refresh now": runs in a thread because the APIs can take a minute. False if already running."""
    if not _running.acquire(blocking=False):
        return False

    def work():
        from django.db import connection
        try:
            run_due(force=True)
            c = conf()
            if pagespeed_restart and c["pagespeed"]:
                _run("pagespeed", lambda: pagespeed_step(c, restart=True))
        finally:
            connection.close()
            _running.release()
    threading.Thread(target=work, daemon=True).start()
    return True


def refreshing():
    return _running.locked()


# ---------------------------------------------------------------- weekly email
def digest_facts():
    """A few numbers for the weekly summary email, or None when nothing has been fetched."""
    if not enabled():
        return None
    s, i, p = search_report(), inspect_report(), pagespeed_report()
    if not (s or i or p):
        return None
    out = {"search": None, "index_problems": i["problems"] if i else None, "speed": None}
    if s:
        t = s["totals"]
        out["search"] = {"clicks": t["clicks"], "clicks_change": t["clicks_change"], "impressions": t["impressions"],
                         "impressions_change": t["impressions_change"], "position": t["position"],
                         "top": [(q["query"], q["clicks"]) for q in s["queries"][:3]],
                         "losing": [(r["path"], r["prev_clicks"], r["clicks"]) for r in s["losing"][:3]],
                         "page_two": [(q["query"], q["position"]) for q in s["page_two"][:3]]}
    if p and p["lowest"]:
        out["speed"] = {"path": p["lowest"]["path"], "score": p["lowest"]["scores"]["performance"], "poor": p["poor"]}
    k = keyword_report(scores=False)
    out["up"] = [(r["keyword"], r["position"] + r["week"], r["position"]) for r in k["up"][:3]]
    out["down"] = [(r["keyword"], r["position"] + r["week"], r["position"]) for r in k["down"][:3]]
    sm = load("sitemaps.json")
    out["sitemap_errors"] = sum(i["errors"] for i in sm["items"]) if sm else 0
    return out
