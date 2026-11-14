"""Render pages to HTML with the active theme (Jinja2).

A RenderContext loads everything a build needs once (languages, settings, pages,
entries, menus, media) so a full-site build makes a handful of queries.
"""
import hashlib
import json
from functools import cached_property

from django.conf import settings
from jinja2 import Environment, FileSystemLoader, StrictUndefined, Undefined, pass_context, select_autoescape
from markupsafe import Markup, escape

from .models import Entry, Language, Media, Menu, Page, PageTranslation, Setting
from .theme import load_theme


class SoftUndefined(Undefined):
    """Missing optional block fields render as empty strings instead of failing the build."""
    def __getattr__(self, name):
        return self


class RenderContext:
    def __init__(self, preview=False, theme=None):
        self.preview = preview
        self.theme = theme or load_theme()
        self.site_url = settings.TECHNTING_CMS_SITE_URL
        self.env = Environment(
            loader=FileSystemLoader(str(self.theme.templates_dir)),
            autoescape=select_autoescape(["html", "xml", "j2"], default=True),
            undefined=StrictUndefined if settings.DEBUG and not preview else SoftUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.undefined = SoftUndefined
        self.env.globals.update(
            t=self._t, url=self._url, entry=self._entry, entries=self._entries, media=self._media,
            menu=self._menu, asset=self._asset, abs_url=self.abs_url, json_ld=self._json_ld,
            render_block=self._render_block, setting=self._setting, alternates=self._alternates,
            entry_url=self._entry_url, plugin_html=self._plugin_html, outline=outline, turnstile_key=self._turnstile_key,
            admin_url=settings.TECHNTING_CMS_ADMIN_URL.rstrip("/"),  # dashboard host: forms (Technting Forms) post their answers there
            social_links=self._social_links, same_as=self._same_as, contact_info=self._contact_info,
            site_name=settings.TECHNTING_CMS_SITE_NAME,
        )
        self.env.filters["nl2br"] = lambda s: Markup("<br>".join(escape(s or "").split("\n")))
        self.env.filters["bidi"] = lambda s: Markup(f"<bdi>{escape(s)}</bdi>")
        self.env.filters["count_ar"] = count_ar
        self.env.filters["datefmt"] = datefmt
        self.env.filters["rfc822"] = rfc822
        self.env.filters["embed_url"] = embed_url

    # ---------------------------------------------------------------- data
    @cached_property
    def languages(self):
        return list(Language.objects.all())

    @cached_property
    def default_language(self):
        return next((l for l in self.languages if l.is_default), self.languages[0])

    @cached_property
    def settings_map(self):
        return {s.key: s.value for s in Setting.objects.all()}

    @cached_property
    def translations(self):
        qs = PageTranslation.objects.select_related("page", "language", "og_image")
        return [t for t in qs if self.preview or t.is_live]

    @cached_property
    def pages_by_key(self):
        out = {}
        for t in self.translations:
            if t.page.key:
                out.setdefault(t.page.key, {})[t.language.code] = t
        return out

    @cached_property
    def translations_by_page(self):
        out = {}
        for t in self.translations:
            out.setdefault(t.page_id, {})[t.language.code] = t
        return out

    @cached_property
    def entries_raw(self):
        qs = Entry.objects.prefetch_related("translations__language")
        if not self.preview:
            from django.db.models import Q
            from django.utils import timezone
            now = timezone.now()
            qs = (qs.filter(is_published=True).filter(Q(publish_at__isnull=True) | Q(publish_at__lte=now))
                  .filter(Q(unpublish_at__isnull=True) | Q(unpublish_at__gt=now)))
        out = {}
        for e_ in qs.order_by("collection", "order", "id"):
            out.setdefault(e_.collection, []).append(e_)
        return out

    @cached_property
    def media_map(self):
        return {m.pk: m for m in Media.objects.all()}

    @cached_property
    def menus(self):
        return {(m.key, m.language.code): m.items for m in Menu.objects.select_related("language")}

    @cached_property
    def asset_versions(self):
        versions = {}
        static = self.theme.static_dir
        if static.exists():
            for f in static.rglob("*"):
                if f.is_file():
                    versions[f.relative_to(static).as_posix()] = hashlib.sha1(f.read_bytes()).hexdigest()[:10]
        return versions

    @cached_property
    def entry_routes(self):
        """[(collection, Entry, Language, url)] for every collection with a route."""
        out = []
        for coll, spec in self.theme.routed_collections().items():
            for e_ in self.entries_raw.get(coll, []):
                for lang in self.languages:
                    prefix = f"/{lang.url_prefix}" if lang.url_prefix else ""
                    out.append((coll, e_, lang, prefix + spec["route"].format(key=e_.key)))
        return out

    def entry_route_url(self, collection, key, lang_code):
        spec = self.theme.collections.get(collection, {})
        if not spec.get("route"):
            return None
        lang = next((l for l in self.languages if l.code == lang_code), self.default_language)
        prefix = f"/{lang.url_prefix}" if lang.url_prefix else ""
        return prefix + spec["route"].format(key=key)

    # ---------------------------------------------------------------- helpers exposed to templates
    def abs_url(self, path):
        return self.site_url + path

    @pass_context
    def _t(self, ctx, key):
        return self.theme.string(key, ctx["lang"]["code"])

    @cached_property
    def _turnstile_site_key(self):
        try:
            from shield.turnstile import site_key
            return site_key()
        except Exception:
            return ""

    def _turnstile_key(self):
        """Cloudflare Turnstile site key when the website forms must pass the human check (Technting Shield), else ""."""
        return self._turnstile_site_key

    @pass_context
    def _setting(self, ctx, key, default=""):
        value = self.settings_map.get(key, default)
        if isinstance(value, dict) and ctx["lang"]["code"] in value:
            return value[ctx["lang"]["code"]]
        return value

    def _social_links(self):
        """Footer social icons, the same in every language (Settings -> Social profiles and phone)."""
        from .social import footer_links
        return footer_links(self.settings_map)

    def _same_as(self):
        from .social import same_as
        return same_as(self.settings_map)

    def _contact_info(self):
        from .social import contact
        return contact(self.settings_map)

    @pass_context
    def _url(self, ctx, key, lang=None):
        lang = lang or ctx["lang"]["code"]
        by_lang = self.pages_by_key.get(key, {})
        t = by_lang.get(lang) or by_lang.get(self.default_language.code)
        return t.url if t else "#"

    @pass_context
    def _plugin_html(self, ctx, hook):
        from .plugins import apply_filters
        if self.preview and hook == "head_html":
            pass  # previews get plugin output too, so editors see the real page
        parts = apply_filters(hook, [], page=ctx.get("page"), lang=ctx.get("lang"), preview=self.preview)
        return Markup("\n".join(str(p) for p in parts if p))

    @pass_context
    def _entry_url(self, ctx, collection, key, lang=None):
        return self.entry_route_url(collection, key, lang or ctx["lang"]["code"]) or "#"

    @pass_context
    def _alternates(self, ctx):
        if ctx["page"].get("alternates"):  # theme output pages (e.g. /links/) carry their own language versions
            return ctx["page"]["alternates"]
        page_id = ctx["page"]["id"]
        if isinstance(page_id, str) and ":" in page_id:
            coll, key = page_id.split(":", 1)
            return [{"code": l.code, "url": self.entry_route_url(coll, key, l.code),
                     "abs": self.abs_url(self.entry_route_url(coll, key, l.code)), "native": l.native_name}
                    for l in self.languages]
        return [{"code": code, "url": t.url, "abs": self.abs_url(t.url), "native": t.language.native_name}
                for code, t in self.translations_by_page.get(page_id, {}).items()]

    def entry_dict(self, e_, lang):
        data = dict(e_.data)
        trs = {t.language.code: t.data for t in e_.translations.all()}
        base = trs.get(self.default_language.code, {})
        data.update(base)
        data.update({k: v for k, v in trs.get(lang, {}).items() if v not in ("", None, [], {})})
        data["key"] = e_.key
        data["order"] = e_.order
        return data

    @pass_context
    def _entry(self, ctx, collection, key):
        for e_ in self.entries_raw.get(collection, []):
            if e_.key == key:
                return self.entry_dict(e_, ctx["lang"]["code"])
        return None

    @pass_context
    def _entries(self, ctx, collection, **where):
        out = []
        for e_ in self.entries_raw.get(collection, []):
            d = self.entry_dict(e_, ctx["lang"]["code"])
            if all(d.get(k) == v for k, v in where.items()):
                out.append(d)
        return out

    @pass_context
    def _media(self, ctx, media_id, variant=None):
        m = self.media_map.get(int(media_id)) if str(media_id or "").isdigit() else None
        if not m:
            return None
        name = m.variants.get(variant, m.file.name) if variant else m.file.name
        alt = m.alt.get(ctx["lang"]["code"]) or m.alt.get(self.default_language.code) or ""
        return {"url": settings.TECHNTING_CMS_PUBLIC_MEDIA_PREFIX + name, "alt": alt, "width": m.width, "height": m.height,
                "abs": self.abs_url(settings.TECHNTING_CMS_PUBLIC_MEDIA_PREFIX + name)}

    @pass_context
    def _menu(self, ctx, key):
        return self.menus.get((key, ctx["lang"]["code"]), [])

    def _asset(self, path):
        v = self.asset_versions.get(path, "0")
        return f"/assets/{path}?v={v}"

    @staticmethod
    def _json_ld(obj):
        text = json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")
        return Markup(f'<script type="application/ld+json">{text}</script>')

    @pass_context
    def _render_block(self, ctx, block):
        tpl = self.env.get_template(f"blocks/{block['type']}.html")
        local = dict(ctx.get_all())
        local.update(block=block.get("data", {}), block_id=block.get("id", ""))
        html = tpl.render(local)
        devices = block.get("devices") or []
        if devices and len(devices) < 3:
            # display:contents wrapper; the theme CSS hides it per screen size (.vis-hide-phone / -tablet / -desktop)
            hide = " ".join(f"vis-hide-{d}" for d in ("phone", "tablet", "desktop") if d not in devices)
            html = f'<div class="vis {hide}">{html}</div>'
        return Markup(html)

    # ---------------------------------------------------------------- page rendering
    def lang_dict(self, language):
        return {"code": language.code, "dir": language.direction, "prefix": language.url_prefix,
                "locale": language.locale, "name": language.name, "native": language.native_name,
                "home": f"/{language.url_prefix}/" if language.url_prefix else "/"}

    def page_dict(self, t):
        og = None
        if t.og_image_id:
            og = self.media_map.get(t.og_image_id)
        return {
            "id": t.page_id, "key": t.page.key, "template": t.page.template, "data": t.page.data,
            "title": t.title, "slug": t.slug, "path": t.path, "url": t.url, "abs_url": self.abs_url(t.url),
            "seo_title": t.seo_title or t.title, "seo_description": t.seo_description,
            "og_image": (self.abs_url(settings.TECHNTING_CMS_PUBLIC_MEDIA_PREFIX + og.file.name) if og else None),
            # hidden blocks stay in the editor but never reach the site, its search index or llms.txt
            "noindex": t.noindex, "blocks": [b for b in (t.blocks or []) if not b.get("hidden") and self._shown(b)], "updated_at": t.updated_at,
        }

    def _shown(self, block):
        """The public demo never publishes raw HTML blocks, whatever the database holds."""
        from .demo import has_code_field, on
        return not (on() and has_code_field(self.theme.blocks.get(block.get("type"))))

    def render(self, t):
        tpl = self.env.get_template(f"{t.page.template}.html")
        return tpl.render(page=self.page_dict(t), lang=self.lang_dict(t.language),
                          languages=[self.lang_dict(l) for l in self.languages], site_url=self.site_url,
                          preview=self.preview)

    def render_entry(self, collection, e_, lang, url):
        spec = self.theme.collections[collection]
        data = self.entry_dict(e_, lang.code)
        title = data.get(spec.get("title_field", "name")) or e_.key
        page = {"id": f"{collection}:{e_.key}", "key": f"{collection}-{e_.key}", "template": spec.get("route_template", collection),
                "data": {}, "entry": data, "collection": collection, "title": title, "slug": e_.key, "path": url,
                "url": url, "abs_url": self.abs_url(url), "seo_title": data.get("seo_title") or title,
                "seo_description": data.get("seo_description") or data.get("desc") or data.get("promise") or "",
                "og_image": None, "noindex": False, "blocks": [], "updated_at": e_.updated_at}
        cover = self.media_map.get(int(data["cover"])) if str(data.get("cover") or "").isdigit() else None
        if cover:  # the cover doubles as the social sharing image
            name = cover.variants.get("1600w", cover.file.name)
            page["og_image"] = self.abs_url(settings.TECHNTING_CMS_PUBLIC_MEDIA_PREFIX + name)
        tpl = self.env.get_template(f"{page['template']}.html")
        return tpl.render(page=page, lang=self.lang_dict(lang), languages=[self.lang_dict(l) for l in self.languages],
                          site_url=self.site_url, preview=self.preview)

    def render_named(self, template, lang, page=None, **extra):
        """Render a non-page template (sitemap, llms.txt, 404) in a given language."""
        page = page or {"id": None, "key": None, "data": {}, "title": "", "seo_title": "", "seo_description": "",
                        "abs_url": self.site_url + "/", "url": "/", "noindex": True, "blocks": []}
        return self.env.get_template(template).render(
            lang=self.lang_dict(lang), languages=[self.lang_dict(l) for l in self.languages],
            site_url=self.site_url, preview=self.preview, page=page, **extra)

    def output_pages(self):
        """[(output spec, Language, file path, page dict)] for the per-language theme outputs (feed, search, links...).

        An output with "page" is an HTML page with its own URL and title (theme string of that key). It is noindex
        unless the output sets "noindex": false; "sitemap": true also lists it in sitemap.xml."""
        out_list = []
        for out in self.theme.outputs:
            if out.get("requires_page") and out["requires_page"] not in self.pages_by_key:
                continue  # e.g. no blog feed while the blog page is unpublished
            langs = self.languages if out.get("per_language", True) else [self.default_language]
            rels = {}
            for lang in langs:
                prefix = f"{lang.url_prefix}/" if lang.url_prefix else ""
                rels[lang.code] = out["path"].format(prefix=prefix, lang=lang.code)
            urls = {c: "/" + (r[:-len("index.html")] if r.endswith("index.html") else r) for c, r in rels.items()}
            alts = [{"code": l.code, "url": urls[l.code], "abs": self.abs_url(urls[l.code]), "native": l.native_name}
                    for l in langs] if out.get("page") and len(langs) > 1 else []
            for lang in langs:
                page = None
                if out.get("page"):
                    url, key = urls[lang.code], out["page"]
                    title = self.theme.string(key, lang.code)
                    desc_key = key + "_description"
                    desc = self.theme.string(desc_key, lang.code) if desc_key in self.theme.strings else ""
                    page = {"id": None, "key": key, "data": {}, "title": title, "seo_title": title, "seo_description": desc,
                            "abs_url": self.abs_url(url), "url": url, "noindex": out.get("noindex", True) is not False,
                            "blocks": [], "alternates": alts}
                out_list.append((out, lang, rels[lang.code], page))
        return out_list

    def sitemap_items(self):
        items = []
        for t in self.translations:
            if t.noindex or not t.page.in_sitemap:
                continue
            alts = [{"code": c, "href": self.abs_url(x.url)} for c, x in self.translations_by_page.get(t.page_id, {}).items()]
            items.append({"loc": self.abs_url(t.url), "lastmod": t.updated_at.date().isoformat(),
                          "alternates": alts if len(alts) > 1 else []})
        for coll, e_, lang, url in self.entry_routes:
            alts = [{"code": l.code, "href": self.abs_url(self.entry_route_url(coll, e_.key, l.code))} for l in self.languages]
            items.append({"loc": self.abs_url(url), "lastmod": e_.updated_at.date().isoformat(),
                          "alternates": alts if len(alts) > 1 else []})
        from django.utils import timezone
        for out, lang, rel, page in self.output_pages():
            if page and out.get("sitemap") and not page["noindex"]:
                items.append({"loc": page["abs_url"], "lastmod": timezone.localdate().isoformat(),
                              "alternates": [{"code": a["code"], "href": a["abs"]} for a in page["alternates"]]})
        from .plugins import apply_filters
        return apply_filters("sitemap_items", items)


def outline(html):
    """Give every <h2> in rich text a stable id and return the headings for a table of contents.

    Returns {"html": Markup, "headings": [{"id", "text"}], "words": int}. Ids come from the heading text
    (Arabic letters kept), so links to a section survive edits elsewhere in the article.
    """
    import re
    from django.utils.text import slugify
    seen, heads = set(), []

    def add_id(m):
        attrs, inner = m.group(1) or "", m.group(2)
        text = re.sub(r"<[^>]+>", "", inner).strip()
        found = re.search(r'\sid="([^"]+)"', attrs)
        hid = found.group(1) if found else (slugify(text, allow_unicode=True)[:60] or f"section-{len(heads) + 1}")
        base, n = hid, 2
        while hid in seen:
            hid, n = f"{base}-{n}", n + 1
        seen.add(hid)
        heads.append({"id": hid, "text": text})
        attrs = attrs if found else f'{attrs} id="{hid}"'
        return f"<h2{attrs}>{inner}</h2>"

    out = re.sub(r"<h2(\s[^>]*)?>(.*?)</h2>", add_id, str(html or ""), flags=re.S | re.I)
    words = len(re.findall(r"\w+", re.sub(r"<[^>]+>", " ", out)))
    return {"html": Markup(out), "headings": heads, "words": words}


MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "ar": ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"],
}


def datefmt(value, lang="en"):
    """'2026-10-14' -> '14 October 2026' / '14 أكتوبر 2026' (Western digits, Gulf month names)."""
    try:
        y, m, d = (int(x) for x in str(value)[:10].split("-"))
    except ValueError:
        return value or ""
    return f"{d} {MONTHS.get(lang, MONTHS['en'])[m - 1]} {y}"


def embed_url(url):
    """YouTube / Vimeo page URL -> privacy-friendly embed URL. Anything else returns '' (never embedded)."""
    import re
    url = str(url or "").strip()
    m = re.match(r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if m:
        return f"https://www.youtube-nocookie.com/embed/{m.group(1)}?rel=0"
    m = re.match(r"^https?://(?:www\.)?(?:player\.)?vimeo\.com/(?:video/)?(\d{6,12})", url)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}?dnt=1"
    return ""


def rfc822(value):
    import datetime
    from email.utils import format_datetime
    try:
        y, m, d = (int(x) for x in str(value)[:10].split("-"))
        return format_datetime(datetime.datetime(y, m, d, 9, 0, tzinfo=datetime.timezone.utc))
    except ValueError:
        return ""


def count_ar(n,one="خدمة واحدة", two="خدمتان", few="خدمات", many="خدمة"):
    n = int(n)
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n <= 10:
        return f"{n} {few}"
    return f"{n} {many}"
