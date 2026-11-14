"""Build the public site into static files and sync them into the web root.

The build renders into a fresh temporary folder, then copies only changed files into
TECHNTING_CMS_OUTPUT_DIR and removes files that a previous build created but this one did not
(tracked in .technting-cms-manifest.json). Files the CMS never created are left alone.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import PageTranslation, PublishLog, Redirect
from .render import RenderContext

MANIFEST = ".technting-cms-manifest.json"
_lock = threading.Lock()


def _write(root: Path, rel: str, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        content = content.encode("utf-8")
    path.write_bytes(content)


def build(target: Path):
    """Render the whole site into target. Returns the number of HTML pages."""
    ctx = RenderContext(preview=False)
    pages = 0
    for t in ctx.translations:
        html = ctx.render(t)
        rel = t.url.lstrip("/") + "index.html"
        _write(target, rel, html)
        pages += 1

    for coll, e_, lang, url in ctx.entry_routes:
        _write(target, url.lstrip("/") + "index.html", ctx.render_entry(coll, e_, lang, url))
        pages += 1

    default = ctx.default_language
    # Theme-provided extra outputs (404, sitemap, robots, llms...)
    extra = {"404.html": "special/404.html", "sitemap.xml": "special/sitemap.xml",
             "robots.txt": "special/robots.txt", "llms.txt": "special/llms.txt"}
    for out_name, tpl in extra.items():
        if (ctx.theme.templates_dir / tpl).exists():
            page = None
            if out_name == "404.html":
                page = {"id": None, "key": "404", "data": {}, "title": "Page not found", "seo_title": "Page not found",
                        "seo_description": "", "abs_url": ctx.abs_url("/404.html"), "url": "/404.html", "noindex": True, "blocks": []}
            _write(target, out_name, ctx.render_named(tpl, default, page=page, translations=ctx.translations,
                                                    ctx=ctx, now=timezone.now()))

    from .demo import on as demo_on
    if demo_on():   # a public demo stays out of search engines, whatever the theme's robots.txt says
        _write(target, "robots.txt", "User-agent: *\nDisallow: /\n")

    # Per-language outputs declared by the theme, e.g. {"template": "special/feed.xml", "path": "{prefix}blog/feed.xml"}
    # (HTML page outputs such as search and links get their own URL and title; see RenderContext.output_pages)
    for out, lang, rel, page in ctx.output_pages():
        _write(target, rel, ctx.render_named(out["template"], lang, page=page, translations=ctx.translations,
                                             ctx=ctx, now=timezone.now()))

    # Static theme assets and uploaded media
    if ctx.theme.static_dir.exists():
        shutil.copytree(ctx.theme.static_dir, target / "assets", dirs_exist_ok=True)
        # files that must live at the site root under stable names (favicon.ico, manifest...): search engines and
        # browsers request them there directly, so they always match the theme's current icons
        for name, rel in ctx.theme.root_files.items():
            src = ctx.theme.static_dir / rel
            if src.is_file() and "/" not in name and not name.startswith("."):
                shutil.copyfile(src, target / name)
    media_root = Path(settings.MEDIA_ROOT)
    if media_root.exists():
        shutil.copytree(media_root, target / settings.TECHNTING_CMS_PUBLIC_MEDIA_PREFIX.strip("/"), dirs_exist_ok=True)

    # Redirect map for nginx (included once in the vhost; see deploy/README)
    write_redirects()
    from .plugins import do_action
    do_action("publish_build", target=target, ctx=ctx)
    if demo_on():
        noindex_html(target)
    return pages


ROBOTS_META = re.compile(r"<meta\s+name=[\"']robots[\"'][^>]*>\s*", re.I)
HEAD_TAG = re.compile(r"<head(\s[^>]*)?>", re.I)


def noindex_html(root: Path):
    """Public demo: every published HTML page carries a robots noindex tag, whatever the theme renders. A CDN can put
    its own robots.txt in front of ours (Cloudflare's managed one allows everything), so the tag is what holds."""
    for f in root.rglob("*.html"):
        text = f.read_text(encoding="utf-8")
        new, n = HEAD_TAG.subn(lambda m: m.group(0) + '<meta name="robots" content="noindex, nofollow">',
                               ROBOTS_META.sub("", text), count=1)
        if n and new != text:
            f.write_text(new, encoding="utf-8")


SAFE_PATH = re.compile(r"^/[A-Za-z0-9/_.~%-]*$")
SAFE_URL = re.compile(r"^(https?://[A-Za-z0-9.-]+)?/[A-Za-z0-9/_.~%#?=&-]*$")


def valid_redirect(source, target):
    return bool(SAFE_PATH.match(source or "")) and bool(SAFE_URL.match(target or "")) and source != target


def write_redirects():
    """nginx include with one exact-match location per redirect. Only validated characters reach the file,
    and it is rewritten only when its content changes (a systemd path unit tests and reloads nginx)."""
    lines = ["# Generated by Technting CMS. Do not edit; manage redirects in the dashboard."]
    for r in Redirect.objects.all():
        if valid_redirect(r.source, r.target):
            lines.append(f"location = {r.source} {{ return {301 if r.permanent else 302} {r.target}; }}")
    content = "\n".join(lines) + "\n"
    path = Path(settings.VAR_DIR) / "redirects.conf"
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    (Path(settings.VAR_DIR) / "redirects.map").unlink(missing_ok=True)


def _digest(path: Path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def sync(source: Path, dest: Path):
    """Copy changed files from source into dest; delete files we created before but no longer produce."""
    dest.mkdir(parents=True, exist_ok=True)
    old_manifest = {}
    mf = Path(settings.VAR_DIR) / MANIFEST  # kept outside the web root
    if mf.exists():
        old_manifest = json.loads(mf.read_text(encoding="utf-8"))
    new_manifest, changed, changed_files = {}, 0, []
    for f in source.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(source).as_posix()
        digest = _digest(f)
        new_manifest[rel] = digest
        target = dest / rel
        if not target.exists() or old_manifest.get(rel) != digest or _digest(target) != digest:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".technting-cms-tmp")
            shutil.copyfile(f, tmp)
            os.replace(tmp, target)
            changed += 1
            changed_files.append(rel)
    removed = 0
    for rel in set(old_manifest) - set(new_manifest):
        target = dest / rel
        if target.exists():
            target.unlink()
            removed += 1
            # remove folders left empty by the deletion, never above the web root
            parent = target.parent
            while parent != dest and dest in parent.parents and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
    mf.write_text(json.dumps(new_manifest, indent=0, sort_keys=True), encoding="utf-8")
    sync.last_changed = changed_files
    return changed, removed


def publish_site(user=None):
    """Build and sync. Serialised with a lock; returns the PublishLog."""
    log = PublishLog.objects.create(triggered_by=user if user and user.is_authenticated else None)
    with _lock:
        started = time.monotonic()
        try:
            PageTranslation.objects.filter(status=PageTranslation.SCHEDULED, publish_at__lte=timezone.now()).update(
                status=PageTranslation.PUBLISHED, published_at=timezone.now())
            with tempfile.TemporaryDirectory(prefix="technting-cms-build-") as tmp:
                pages = build(Path(tmp))
                try:  # health check of the build; never blocks publishing
                    from .health import check_build, save
                    save(check_build(Path(tmp)))
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception("site health check failed")
                changed, removed = sync(Path(tmp), Path(settings.TECHNTING_CMS_OUTPUT_DIR))
            log.ok = True
            log.pages = pages
            changed_urls = [settings.TECHNTING_CMS_SITE_URL + "/" + (f[:-10] if f.endswith("index.html") else f)
                            for f in getattr(sync, "last_changed", []) if f.endswith(".html") and f != "404.html"]
            log.message = f"{pages} pages, {changed} files updated, {removed} removed in {time.monotonic() - started:.1f}s"
        except Exception as exc:  # the editor sees the failure in the dashboard
            log.ok = False
            log.message = f"{type(exc).__name__}: {exc}"
        log.finished_at = timezone.now()
        log.save()
    if log.ok:
        from .plugins import do_action
        do_action("publish_after", log=log, changed_urls=changed_urls, output_dir=Path(settings.TECHNTING_CMS_OUTPUT_DIR))
    return log
