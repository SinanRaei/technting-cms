"""External link check: are the sources our pages and articles cite still there?

Collects every external href from published page blocks and entry translations, fetches each once (HEAD, then GET when
HEAD is refused) with a browser user agent and a short timeout, and keeps the result in VAR_DIR/external_links.json
for the Site health page. Sites that block automated requests (401/403/429) are reported as "blocked", not broken.
Runs from publish_due when the last check is older than CHECK_EVERY_DAYS, or from the Site health page on demand.
"""
import json
import re
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

FILE = "external_links.json"
CHECK_EVERY_DAYS = 30
HREF = re.compile(r'href="(https?://[^"]+)"')
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36 Technting-CMS-linkcheck"
_running = threading.Lock()


def _texts(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from _texts(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _texts(x)


def collect():
    """{url: [where, ...]} for external links on published content."""
    from .models import Entry, PageTranslation
    site = urlparse(settings.TECHNTING_CMS_SITE_URL).netloc
    found = {}

    def add(text, where):
        for u in HREF.findall(text or ""):
            if urlparse(u).netloc != site:
                found.setdefault(u.replace("&amp;", "&"), set()).add(where)
    for t in PageTranslation.objects.select_related("page", "language"):
        if t.is_live:
            for s in _texts(t.blocks):
                add(s, f"page {t.page.key or t.page_id} ({t.language.code})")
    for e in Entry.objects.filter(is_published=True).prefetch_related("translations__language"):
        for t in e.translations.all():
            for s in _texts(t.data):
                add(s, f"{e.collection} {e.key} ({t.language.code})")
    return {u: sorted(w) for u, w in found.items()}


def probe(url):
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return {"status": r.status, "final": r.geturl() if r.geturl() != url else ""}
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (400, 403, 405, 429, 501):
                continue  # many servers refuse HEAD; try GET
            return {"status": e.code}
        except Exception as e:  # DNS, TLS, timeout
            if method == "HEAD":
                continue
            return {"status": 0, "error": type(e).__name__}
    return {"status": 0, "error": "unreachable"}


def verdict(r):
    """ok | blocked (refuses robots) | unreachable (no answer to our server) | not_found (404/410) | error (other)."""
    s = r.get("status", 0)
    if 200 <= s < 400:
        return "ok"
    if s in (401, 403, 429):
        return "blocked"
    if s == 0:
        return "unreachable"
    if s in (404, 410):
        return "not_found"
    return "error"


def run():
    if not _running.acquire(blocking=False):
        return None
    try:
        links = collect()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = dict(zip(links, pool.map(probe, links)))
        items = [{"url": u, "where": links[u], **results[u], "verdict": verdict(results[u])} for u in sorted(links)]
        data = {"checked_at": timezone.now().isoformat(), "count": len(items), "items": items}
        Path(settings.VAR_DIR, FILE).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return data
    finally:
        _running.release()


def run_in_background():
    threading.Thread(target=run, daemon=True).start()


def load():
    p = Path(settings.VAR_DIR, FILE)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except ValueError:
        return None


def due():
    d = load()
    if not d:
        return True
    from django.utils.dateparse import parse_datetime
    last = parse_datetime(d["checked_at"])
    return not last or timezone.now() - last > timedelta(days=CHECK_EVERY_DAYS)
