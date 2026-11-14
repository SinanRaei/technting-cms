"""Site health: checks the freshly built site before it goes live and keeps the result for the dashboard.

Runs on the temporary build folder inside publish_site (no network, about a second for a hundred pages):
broken internal links, missing titles, descriptions or H1, duplicate titles, very long titles, images without an
alt attribute, missing canonical and pages that point to a missing asset. Results go to VAR_DIR/health.json.

Accessibility (WCAG basics): page language, links and buttons without a name, form fields without a label, frames
without a title, skipped heading levels, vague link text and repeated ids.
Speed (from the built files, no network): page weight, large images, images without width and height (the page
jumps while loading) and scripts in <head> that block the first paint.
Search: structured data (JSON-LD) that rich results would reject and sharing images smaller than 1200×630 (cms/seo.py).
"""
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.utils import timezone

HEALTH_FILE = "health.json"


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.in_title, self.description, self.canonical, self.robots = "", False, None, None, ""
        self.h1, self.links, self.images_no_alt, self.assets = 0, [], 0, []
        self.lang, self.in_head, self.headings, self.ids = None, False, [], {}
        self.empty_links, self.vague_links, self.empty_buttons, self.unlabelled, self.iframes_no_title = 0, [], 0, 0, 0
        self.images = []                      # (src, has width and height)
        self.blocking_scripts = 0
        self._a = None                        # open <a>: [text, has a name]
        self._button = None
        self._label_depth, self._label_for, self._fields = 0, set(), []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "head":
            self.in_head = True
        if a.get("id"):
            self.ids[a["id"]] = self.ids.get(a["id"], 0) + 1
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append(int(tag[1]))
        if tag == "a" and a.get("href"):
            self._a = ["", bool(a.get("aria-label") or a.get("aria-labelledby") or a.get("title"))]
        elif tag == "img" and self._a is not None and (a.get("alt") or "").strip():
            self._a[1] = True
        elif tag == "svg" and self._a is not None and a.get("aria-label"):
            self._a[1] = True
        elif tag == "button":
            self._button = ["", bool(a.get("aria-label") or a.get("aria-labelledby") or a.get("title"))]
        elif tag == "label":
            self._label_depth += 1
            if a.get("for"):
                self._label_for.add(a["for"])
        elif tag in ("input", "select", "textarea"):
            kind = (a.get("type") or "text").lower()
            hidden = kind in ("hidden", "submit", "button", "reset", "image") or a.get("aria-hidden") == "true" or a.get("tabindex") == "-1"
            if not hidden:
                self._fields.append((a.get("id"), self._label_depth > 0, bool(a.get("aria-label") or a.get("aria-labelledby") or a.get("title"))))
        elif tag == "iframe" and not (a.get("title") or "").strip():
            self.iframes_no_title += 1
        elif tag == "script" and self.in_head and a.get("src") and "defer" not in a and "async" not in a and a.get("type") != "module":
            self.blocking_scripts += 1
        if tag == "img" and a.get("src"):
            self.images.append((a["src"], bool(a.get("width") and a.get("height"))))
        if tag == "title":
            self.in_title = True
        elif tag == "meta" and a.get("name") == "description":
            self.description = a.get("content") or ""
        elif tag == "meta" and a.get("name") == "robots":
            self.robots = a.get("content") or ""
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "h1":
            self.h1 += 1
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "img":
            if "alt" not in a:
                self.images_no_alt += 1
            if a.get("src"):
                self.assets.append(a["src"])
        elif tag in {"script", "link"} and (a.get("src") or (tag == "link" and a.get("rel") in {"stylesheet", "preload", "icon"})):
            self.assets.append(a.get("src") or a.get("href"))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "head":
            self.in_head = False
        elif tag == "a" and self._a is not None:
            text = " ".join(self._a[0].split())
            if not text and not self._a[1]:
                self.empty_links += 1
            elif text.lower().strip(".…→←› ") in VAGUE:
                self.vague_links.append(text)
            self._a = None
        elif tag == "button" and self._button is not None:
            if not " ".join(self._button[0].split()) and not self._button[1]:
                self.empty_buttons += 1
            self._button = None
        elif tag == "label":
            self._label_depth = max(0, self._label_depth - 1)

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self._a is not None:
            self._a[0] += data
        if self._button is not None:
            self._button[0] += data

    def close(self):
        super().close()
        self.unlabelled = sum(1 for fid, wrapped, named in self._fields if not (wrapped or named or (fid and fid in self._label_for)))


VAGUE = {"click here", "here", "read more", "more", "link", "this", "اضغط هنا", "هنا", "المزيد", "اقرأ المزيد", "رابط"}
PAGE_WEIGHT_LIMIT = 1_500_000      # bytes for HTML + CSS + JS + images + fonts the page references
IMAGE_LIMIT = 400_000


def _size(root: Path, src: str):
    """Bytes of a site file referenced as /path, or None when it is not ours."""
    u = urlparse(src)
    if u.scheme in {"http", "https"} and u.netloc != urlparse(settings.TECHNTING_CMS_SITE_URL).netloc:
        return None
    path = unquote(u.path)
    rel = path.lstrip("/")
    media = settings.TECHNTING_CMS_PUBLIC_MEDIA_PREFIX.strip("/") + "/"
    f = Path(settings.MEDIA_ROOT) / rel[len(media):] if rel.startswith(media) else root / rel
    try:
        return f.stat().st_size if f.is_file() else None
    except OSError:
        return None


def _target_exists(root: Path, path: str, redirects: set):
    """True when a site-relative path resolves to a built file, an uploaded file or a configured redirect."""
    path = unquote(path.split("#", 1)[0].split("?", 1)[0])
    if not path or path in redirects:
        return True
    rel = path.lstrip("/")
    candidates = [root / rel] if not path.endswith("/") else [root / rel / "index.html"]
    if not path.endswith("/") and "." not in rel.rsplit("/", 1)[-1]:
        candidates.append(root / rel / "index.html")
    if rel.startswith(settings.TECHNTING_CMS_PUBLIC_MEDIA_PREFIX.strip("/") + "/"):
        candidates.append(Path(settings.MEDIA_ROOT) / rel[len(settings.TECHNTING_CMS_PUBLIC_MEDIA_PREFIX.strip("/")) + 1:])
    return any(c.is_file() for c in candidates)


def check_build(root: Path):
    from .models import Redirect
    from .seo import OG_IMAGE, og_image_check, page_schema
    og_seen = {}
    site = urlparse(settings.TECHNTING_CMS_SITE_URL).netloc
    redirects = set(Redirect.objects.values_list("source", flat=True))
    issues, titles, pages = [], {}, 0

    def add(kind, page, detail=""):
        issues.append({"kind": kind, "page": page, "detail": detail})

    for f in sorted(root.rglob("*.html")):
        rel = f.relative_to(root).as_posix()
        if rel == "404.html" or rel.startswith("assets/"):
            continue
        url = "/" + (rel[:-len("index.html")] if rel.endswith("index.html") else rel)
        p = _Page()
        text = f.read_text(encoding="utf-8", errors="replace")
        p.feed(text)
        pages += 1
        indexable = "noindex" not in p.robots
        title = re.sub(r"\s+", " ", p.title).strip()
        if not title:
            add("missing_title", url)
        elif indexable:
            titles.setdefault(title, []).append(url)
            if len(title) > 70:
                add("long_title", url, f"{len(title)} characters")
        if indexable and not (p.description or "").strip():
            add("missing_description", url)
        if indexable and not p.canonical:
            add("missing_canonical", url)
        if p.h1 == 0:
            add("missing_h1", url)
        elif p.h1 > 1:
            add("multiple_h1", url, f"{p.h1} H1 headings")
        if p.images_no_alt:
            add("image_no_alt", url, f"{p.images_no_alt} images")
        if indexable:
            problems = page_schema(text)[1]
            if problems:
                add("schema_error", url, "; ".join(problems)[:200])
            m = OG_IMAGE.search(text)
            key = m.group(1) if m else ""
            if key not in og_seen:
                og_seen[key] = og_image_check(text, root)
            if not og_seen[key][0]:
                add("og_image", url, og_seen[key][2])
        p.close()
        # accessibility
        if not p.lang:
            add("a11y_no_lang", url)
        if p.empty_links:
            add("a11y_empty_link", url, f"{p.empty_links}")
        if p.empty_buttons:
            add("a11y_empty_button", url, f"{p.empty_buttons}")
        if p.unlabelled:
            add("a11y_unlabelled_field", url, f"{p.unlabelled}")
        if p.iframes_no_title:
            add("a11y_iframe_no_title", url, f"{p.iframes_no_title}")
        skips = [f"H{a}→H{b}" for a, b in zip(p.headings, p.headings[1:]) if b > a + 1]
        if skips:
            add("a11y_heading_skip", url, ", ".join(sorted(set(skips))))
        if p.vague_links:
            add("a11y_vague_link", url, ", ".join(sorted(set(p.vague_links)))[:120])
        dup_ids = sorted(i for i, n in p.ids.items() if n > 1)
        if dup_ids:
            add("a11y_duplicate_id", url, ", ".join(dup_ids)[:120])
        # speed
        html_bytes = f.stat().st_size
        weight, counted = html_bytes, set()
        for src in p.assets + [s for s, _ in p.images]:
            if src and src not in counted:
                counted.add(src)
                weight += _size(root, src) or 0
        if weight > PAGE_WEIGHT_LIMIT:
            add("speed_heavy_page", url, f"{weight / 1_000_000:.1f} MB")
        big = [(s, _size(root, s)) for s, _ in p.images]
        big = sorted({s: n for s, n in big if n and n > IMAGE_LIMIT}.items(), key=lambda x: -x[1])
        if big:
            add("speed_large_image", url, ", ".join(f"{s.rsplit('/', 1)[-1]} ({n // 1000} KB)" for s, n in big[:3]))
        no_size = sum(1 for _, sized in p.images if not sized)
        if no_size:
            add("speed_image_no_size", url, f"{no_size}")
        if p.blocking_scripts:
            add("speed_blocking_script", url, f"{p.blocking_scripts}")
        seen = set()
        for href in p.links + p.assets:
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                continue
            u = urlparse(href)
            if u.scheme in {"http", "https"} and u.netloc != site:
                continue  # external links are not fetched here
            path = u.path if u.scheme else (href if href.startswith("/") else None)
            if path is None:  # relative link: resolve against this page
                base = url if url.endswith("/") else url.rsplit("/", 1)[0] + "/"
                path = urlparse(base + href).path
            if path in seen:
                continue
            seen.add(path)
            if not _target_exists(root, path, redirects):
                add("broken_link", url, path)
    for title, urls in titles.items():
        if len(urls) > 1:
            for u in urls:
                add("duplicate_title", u, title)
    return {"checked_at": timezone.now().isoformat(), "pages": pages, "issues": issues}


def save(result):
    Path(settings.VAR_DIR, HEALTH_FILE).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


def load():
    p = Path(settings.VAR_DIR, HEALTH_FILE)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
