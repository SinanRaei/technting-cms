"""On-page SEO checklist for routed collection entries (blog posts, lab pages...).

entry_checks() looks at the saved data of one language and returns a score, a search-result
snippet preview and a list of checks. It runs on the server when the editor opens the entry,
so it reflects the last save. Checks only advise; nothing blocks publishing.

Readability is measured the same way in Arabic and English (sentence, paragraph and section length), with a little
more room for Arabic, whose sentences run longer. Structured data (JSON-LD) and the sharing image are checked on the
published page, so they reflect the last publish. With Technting SEO on, the searches that find the article on Google
are shown, and other pages' searches become internal-link ideas.
"""
import html
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.conf import settings

TAG = re.compile(r"<[^>]+>")
WORD = re.compile(r"\w+", re.UNICODE)
H2 = re.compile(r"<h2[\s>]", re.I)
HREF = re.compile(r'<a\s[^>]*href="([^"]+)"', re.I)
IMG = re.compile(r"<img\s[^>]*>", re.I)
ALT = re.compile(r'\salt="\s*[^"\s][^"]*"', re.I)
FIRST_P = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)
H2_TEXT = re.compile(r"<h2[^>]*>(.*?)</h2>", re.I | re.S)
PARA = re.compile(r"<(p|li)[^>]*>(.*?)</\1>", re.I | re.S)
SECTION = re.compile(r"<h[23][\s>]", re.I)
SENTENCE_END = re.compile(r"[.!?؟]+(?=\s|$)")
LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
OG_IMAGE = re.compile(r'<meta\s+property="og:image"\s+content="([^"]+)"')
READING = {"ar": {"sentence": 25, "long": 30}, "en": {"sentence": 20, "long": 25}}   # average and "long" words per sentence
PARAGRAPH_MAX, SECTION_MAX = 150, 350
DENSITY = (0.5, 2.5, 3.5)   # % of the words: natural from, natural to, over-use above


def text_of(rich):
    return html.unescape(TAG.sub(" ", rich or ""))


def words(text):
    return len(WORD.findall(text or ""))


def norm(s):
    """Lower-case, strip Arabic diacritics/tatweel and unify alef forms so keyword matching is fair."""
    s = (s or "").lower()
    s = re.sub(r"[ً-ْـ]", "", s)
    return re.sub(r"[إأآ]", "ا", s)


def check(label, ok, warn=False, detail="", weight=1):
    return {"label": label, "ok": bool(ok), "warn": bool(warn) and not ok, "detail": detail, "weight": weight}


def entry_checks(theme, collection, entry, language, extras=True):
    """extras=False skips link ideas and Google searches (for lists that only need the score)."""
    spec = theme.collections.get(collection, {})
    if not spec.get("route"):
        return None
    from .models import EntryTranslation, Language
    trs = {t.language.code: t.data for t in EntryTranslation.objects.filter(entry=entry).select_related("language")}
    data = dict(entry.data)
    data.update(trs.get(language.code, {}))
    fields = {f["name"]: f for f in spec.get("fields", [])}
    title = data.get(spec.get("title_field", "name")) or ""
    seo_title = data.get("seo_title") or title
    desc = data.get("seo_description") or data.get("excerpt") or data.get("summary") or data.get("desc") or ""
    rich_names = [n for n, f in fields.items() if f["type"] == "richtext"]
    body = " ".join(data.get(n) or "" for n in rich_names)
    body_text = text_of(body)
    kw = (data.get("focus_keyword") or "").strip()
    prefix = f"/{language.url_prefix}" if language.url_prefix else ""
    url = settings.TECHNTING_CMS_SITE_URL + prefix + spec["route"].format(key=entry.key)

    items = []
    full_title = f"{seo_title} | {settings.TECHNTING_CMS_SITE_NAME}"
    items.append(check("Title length 30 to 60 characters", 30 <= len(full_title) <= 60, warn=20 <= len(full_title) <= 70,
                       detail=f"{len(full_title)}", weight=2))
    items.append(check("Description 70 to 160 characters", 70 <= len(desc) <= 160, warn=50 <= len(desc) <= 200,
                       detail=f"{len(desc)}", weight=2))
    if "focus_keyword" in fields:
        items.append(check("Focus keyword set", kw, weight=1))
        if kw:
            k = norm(kw)
            first_p = FIRST_P.search(body)
            items.append(check("Keyword in the SEO title", k in norm(seo_title), weight=2))
            items.append(check("Keyword in the description", k in norm(desc), weight=1))
            items.append(check("Keyword in the first paragraph", first_p and k in norm(text_of(first_p.group(1))), weight=1))
            if rich_names:
                h2s = [norm(text_of(h)) for h in H2_TEXT.findall(body)]
                parts = [w for w in k.split() if len(w) > 2]
                in_h2 = any(k in h or (len(parts) > 1 and all(w in h for w in parts)) for h in h2s)
                items.append(check("Keyword in a subheading (H2)", in_h2, warn=bool(h2s), weight=1))
                items.append(keyword_density(k, body_text))
            if re.fullmatch(r"[a-z0-9 \-]+", k):
                items.append(check("Keyword in the address", k.replace(" ", "-") in entry.key.lower() or all(w in entry.key.lower() for w in k.split()),
                                   warn=True, weight=1))
    if rich_names:
        n = words(body_text)
        items.append(check("At least 800 words", n >= 800, warn=n >= 500, detail=f"{n}", weight=2))
        h2 = len(H2.findall(body))
        items.append(check("Two or more H2 subheadings", h2 >= 2, detail=f"{h2}", weight=1))
        links = HREF.findall(body)
        site = settings.TECHNTING_CMS_SITE_URL.split("//", 1)[-1]
        internal = [h for h in links if h.startswith("/") or site in h]
        external = [h for h in links if h.startswith("http") and site not in h]
        items.append(check("Two or more links to our own pages", len(internal) >= 2, warn=len(internal) == 1, detail=f"{len(internal)}", weight=1))
        items.append(check("Links to an authoritative source", external, warn=True, detail=f"{len(external)}", weight=1))
        items += readability(body, language.code)
        imgs = IMG.findall(body)
        if imgs:
            missing = sum(1 for i in imgs if not ALT.search(i))
            items.append(check("Images in the text have alt text", missing == 0, detail=f"{missing} missing" if missing else "", weight=1))
    if "cover" in fields:
        from .models import Media
        m = Media.objects.filter(pk=data.get("cover")).first() if str(data.get("cover") or "").isdigit() else None
        alt = (m.alt.get(language.code) or "") if m else ""
        items.append(check("Cover image with alt text", m and alt, warn=bool(m), weight=1))
    if "faq" in fields:
        faq = [r for r in (data.get("faq") or []) if r.get("question") and r.get("answer")]
        items.append(check("Three or more FAQ answers", len(faq) >= 3, warn=len(faq) > 0, detail=f"{len(faq)}", weight=1))
    others = [l for l in Language.objects.all() if l.code != language.code]
    missing = [l.code.upper() for l in others if not trs.get(l.code)]
    items.append(check("Translated into every site language", not missing, warn=True, detail=", ".join(missing), weight=1))
    path = url[len(settings.TECHNTING_CMS_SITE_URL):]
    items += published_checks(path) if entry.is_published else []

    total = sum(i["weight"] for i in items)
    got = sum(i["weight"] * (1 if i["ok"] else 0.5 if i["warn"] else 0) for i in items)
    snippet = {"url": url.replace("https://", ""), "title": full_title if len(full_title) <= 62 else full_title[:60] + "…",
               "description": desc if len(desc) <= 162 else desc[:158] + "…"}
    cover = None
    if "cover" in fields and str(data.get("cover") or "").isdigit():
        from django.urls import reverse
        from .models import Media
        m = Media.objects.filter(pk=data.get("cover")).first()
        if m:
            rel = (m.variants or {}).get("960w") or m.file.name
            cover = reverse("cms:upload", args=[rel])
    social = {"title": seo_title, "description": desc if len(desc) <= 110 else desc[:107] + "…", "image": cover,
              "domain": settings.TECHNTING_CMS_SITE_URL.split("//", 1)[-1]}
    from . import seo_pro
    search = seo_pro.page_queries(path) if extras and seo_pro.enabled() else []
    return {"score": round(100 * got / total) if total else 0, "items": items, "snippet": snippet, "social": social,
            "link_ideas": link_ideas(theme, entry, language, body) if rich_names and extras else [], "search": search}


def keyword_density(k, body_text):
    """Share of the words taken by the focus keyword: too low reads off-topic, too high reads as stuffing."""
    n = words(body_text)
    times = norm(body_text).count(k)
    pct = 100 * times * len(k.split()) / n if n else 0
    low, high, over = DENSITY
    return check("Keyword used naturally (0.5 to 2.5% of the words)", times and low <= pct <= high,
                 warn=times and pct <= over, detail=f"{pct:.1f}% · {times}×", weight=1)


def readability(body, lang_code):
    """Sentence, paragraph and section length; the same measures in Arabic and English, with more room in Arabic."""
    limits = READING.get(lang_code, READING["en"])
    paras = [text_of(m.group(2)) for m in PARA.finditer(body)]
    sentences = [s for p in paras for s in SENTENCE_END.split(p) if words(s) >= 3]
    out = []
    if sentences:
        lengths = [words(s) for s in sentences]
        avg = sum(lengths) / len(lengths)
        long_share = round(100 * sum(1 for n in lengths if n > limits["long"]) / len(lengths))
        out.append(check(f"Short sentences (under {limits['sentence']} words on average)", avg <= limits["sentence"] and long_share <= 25,
                         warn=avg <= limits["sentence"] + 5, detail=f"{avg:.0f}", weight=1))
    if paras:
        longest = max(words(p) for p in paras)
        too_long = sum(1 for p in paras if words(p) > PARAGRAPH_MAX)
        out.append(check(f"Short paragraphs (under {PARAGRAPH_MAX} words)", too_long == 0, warn=too_long == 1,
                         detail=f"{longest}" if too_long else "", weight=1))
    sections = [words(text_of(s)) for s in SECTION.split(body)]
    if sections and sum(sections) >= 300:
        out.append(check(f"A subheading at least every {SECTION_MAX} words", max(sections) <= SECTION_MAX,
                         warn=max(sections) <= SECTION_MAX * 1.5, detail=f"{max(sections)}", weight=1))
    return out


# ---------------------------------------------------------------- published page: structured data and sharing image
REQUIRED = {"BlogPosting": ("headline", "image", "datePublished", "author"), "Article": ("headline", "image", "datePublished", "author"),
            "FAQPage": ("mainEntity",), "BreadcrumbList": ("itemListElement",), "Organization": ("name", "url"),
            "ProfessionalService": ("name", "url"), "WebSite": ("name", "url"), "OfferCatalog": ("name",)}
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def schema_problems(obj):
    """What Google's rich results would reject in one JSON-LD object (the properties our templates promise)."""
    kind = obj.get("@type") if isinstance(obj, dict) else None
    if not kind:
        return ["an item without @type"]
    out = [f"{kind}: missing {p}" for p in REQUIRED.get(kind, ()) if obj.get(p) in (None, "", [], {})]
    if "schema.org" not in str(obj.get("@context", "")):
        out.append(f"{kind}: @context is not schema.org")
    if kind in ("BlogPosting", "Article"):
        if len(str(obj.get("headline") or "")) > 110:
            out.append(f"{kind}: headline longer than 110 characters")
        for p in ("datePublished", "dateModified"):
            if obj.get(p) and not ISO_DATE.match(str(obj[p])):
                out.append(f"{kind}: {p} is not a date (YYYY-MM-DD)")
        author = obj.get("author")
        if isinstance(author, dict) and not author.get("name"):
            out.append(f"{kind}: author has no name")
    if kind == "FAQPage":
        for q in obj.get("mainEntity") or []:
            if not (isinstance(q, dict) and q.get("name") and (q.get("acceptedAnswer") or {}).get("text")):
                out.append("FAQPage: a question without its answer")
                break
    if kind == "BreadcrumbList":
        items = [i for i in obj.get("itemListElement") or [] if isinstance(i, dict)]
        if [i.get("position") for i in items] != list(range(1, len(items) + 1)):
            out.append("BreadcrumbList: positions must run 1, 2, 3…")
        if any(not i.get("name") for i in items) or any(not i.get("item") for i in items[:-1]):
            out.append("BreadcrumbList: an item without a name or address")
    return out


def page_schema(html_text):
    """(types found, problems) for every JSON-LD block in a built page."""
    types, problems = [], []
    for raw in LD.findall(html_text):
        try:
            data = json.loads(raw)
        except ValueError:
            problems.append("a JSON-LD block is not valid JSON")
            continue
        objs = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for obj in objs:
            types.append(str(obj.get("@type")) if isinstance(obj, dict) else "?")
            problems += schema_problems(obj)
    return types, problems


def built_file(path):
    """The published HTML file for a site path, or None."""
    rel = unquote(urlparse(path).path).lstrip("/")
    root = Path(settings.TECHNTING_CMS_OUTPUT_DIR)
    f = root / rel / "index.html" if not rel or rel.endswith("/") else root / rel
    return f if f.is_file() else None


def image_file(src, root=None):
    """Local file behind an image address on our site (uploads, or theme assets in root), or None."""
    u = urlparse(src)
    if u.netloc and u.netloc != urlparse(settings.TECHNTING_CMS_SITE_URL).netloc:
        return None
    rel = unquote(u.path).lstrip("/")
    media = settings.TECHNTING_CMS_PUBLIC_MEDIA_PREFIX.strip("/") + "/"
    f = Path(settings.MEDIA_ROOT) / rel[len(media):] if rel.startswith(media) else Path(root or settings.TECHNTING_CMS_OUTPUT_DIR) / rel
    return f if f.is_file() else None


def og_image_check(html_text, root=None):
    """(ok, warn, detail): LinkedIn, WhatsApp and X show a large card from 1200×630 (about 1.91:1), up to 5 MB."""
    m = OG_IMAGE.search(html_text)
    if not m:
        return False, False, "none"
    f = image_file(html.unescape(m.group(1)), root)
    if not f:
        return False, True, "not found on this server"
    try:
        from PIL import Image
        with Image.open(f) as im:
            w, h = im.size
    except Exception:
        return False, False, "not an image"
    size = f.stat().st_size
    ok = w >= 1200 and h >= 630 and 1.5 <= w / h <= 2.1 and size <= 5_000_000
    return ok, w >= 600 and h >= 315 and size <= 5_000_000, f"{w}×{h}, {size // 1000} KB"


def published_checks(path):
    f = built_file(path)
    if not f:
        return [check("Structured data and sharing image are checked after publishing", False, warn=True, weight=0)]
    text = f.read_text(encoding="utf-8", errors="replace")
    types, problems = page_schema(text)
    ok, warn, detail = og_image_check(text)
    return [check("Structured data (JSON-LD) is valid", types and not problems,
                  detail="; ".join(problems)[:200] if problems else ", ".join(dict.fromkeys(types)), weight=1),
            check("Sharing image at least 1200×630", ok, warn=warn, detail=detail, weight=1)]


def link_ideas(theme, entry, language, body, limit=6):
    """Our own pages whose name, focus keyword or Google searches (Technting SEO) appear in this text but are not linked
    yet (internal-link ideas)."""
    from . import seo_pro
    from .models import Entry
    searches = seo_pro.queries_by_path() if seo_pro.enabled() else {}
    site = settings.TECHNTING_CMS_SITE_URL.split("//", 1)[-1]
    linked = {h.split(site, 1)[-1].split("#")[0] for h in HREF.findall(body)}
    text = norm(text_of(body))
    prefix = f"/{language.url_prefix}" if language.url_prefix else ""
    routed = {k: c for k, c in theme.collections.items() if c.get("route")}
    out = []
    others = (Entry.objects.filter(collection__in=list(routed), is_published=True).exclude(pk=entry.pk)
              .prefetch_related("translations__language"))
    for e in others:
        t = next((x.data for x in e.translations.all() if x.language_id == language.pk), None)
        if not t:
            continue
        d = dict(e.data or {})
        d.update(t)
        url = prefix + routed[e.collection]["route"].format(key=e.key)
        if url in linked:
            continue
        title = d.get(routed[e.collection].get("title_field", "name")) or e.key
        own = [d.get("focus_keyword"), d.get("short_name"), title]
        found = [q for q in searches.get(url, []) if " " in q.strip()]   # one-word searches are too vague to link
        for phrase in own + found:
            phrase = (phrase or "").strip()
            if len(phrase) >= 4 and norm(phrase) in text:
                out.append({"title": title, "url": url, "phrase": phrase, "search": phrase in found and phrase not in own})
                break
        if len(out) >= limit:
            break
    return out
