"""Where each media file is used, and replacing a file in place (in the spirit of Enable Media Replace and
Media Cleaner for WordPress).

Image and video fields store the media id; rich text stores the public file address. The index looks for both, so a
file counts as "in use" when any page, record, menu or setting points at it.
"""
import json
from pathlib import Path

from django.conf import settings
from django.urls import reverse

from .models import Entry, Media, Menu, PageTranslation, Setting

BASE_KEYS = {"image", "poster", "photo", "cover", "og_image", "logo", "video", "media", "icon_image"}


def media_keys():
    """Field names that hold a media id: the theme's image and video fields plus common names."""
    from .theme import load_theme
    keys = set(BASE_KEYS)

    def walk(v):
        if isinstance(v, dict):
            if v.get("type") in ("image", "video") and v.get("name"):
                keys.add(v["name"])
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    theme = load_theme()
    walk([theme.collections, theme.blocks, theme.templates])
    return keys


def _ids(value, keys, found):
    if isinstance(value, dict):
        for k, v in value.items():
            if k in keys and (isinstance(v, int) or (isinstance(v, str) and v.isdigit())):
                found.add(int(v))
            else:
                _ids(v, keys, found)
    elif isinstance(value, list):
        for v in value:
            _ids(v, keys, found)


def _sources():
    """(label, edit url, json value) for everything that can point at a file."""
    for t in PageTranslation.objects.select_related("page", "language"):
        yield (f"{t.title} ({t.language.code.upper()})", reverse("cms:page_edit", args=[t.page_id, t.language.code]),
               {"blocks": t.blocks, "data": t.page.data, "og_image": t.og_image_id})
    for e in Entry.objects.prefetch_related("translations__language"):
        trs = {x.language.code: x.data for x in e.translations.all()}
        title = next((d.get("title") or d.get("name") for d in trs.values() if d.get("title") or d.get("name")), e.key)
        yield (f"{e.collection}: {title}", reverse("cms:entry_edit", args=[e.collection, e.pk, "en"]), {"data": e.data, "tr": trs})
    for m in Menu.objects.select_related("language"):
        yield (f"Menu {m.key} ({m.language.code.upper()})", reverse("cms:menus"), m.items)
    for s in Setting.objects.exclude(key__startswith="stats").exclude(key="smtp"):
        yield (f"Setting {s.key}", reverse("cms:settings"), s.value)


def usage_index():
    """{media id: [(label, url), ...]} for every file referenced anywhere."""
    keys = media_keys()
    files = {}
    for m in Media.objects.all():
        for rel in [m.file.name, *(m.variants or {}).values()]:
            if rel:
                files[rel] = m.pk
    index = {}
    for label, url, value in _sources():
        found = set()
        _ids(value, keys, found)
        text = json.dumps(value, ensure_ascii=False)
        for rel, pk in files.items():
            if rel in text:
                found.add(pk)
        for pk in found:
            index.setdefault(pk, [])
            if (label, url) not in index[pk]:
                index[pk].append((label, url))
    return index


def _replace_text(old_new):
    """Swap file addresses inside page, record, menu and setting content. Returns how many records changed."""
    from .models import EntryTranslation
    changed = 0

    def swap(v):
        if isinstance(v, str):
            for o, n in old_new:
                v = v.replace(o, n)
            return v
        if isinstance(v, list):
            return [swap(x) for x in v]
        if isinstance(v, dict):
            return {k: swap(x) for k, x in v.items()}
        return v

    def touches(v):
        s = json.dumps(v, ensure_ascii=False)
        return any(o in s for o, _ in old_new)
    for t in PageTranslation.objects.all():
        if touches(t.blocks):
            t.blocks = swap(t.blocks)
            t.save(update_fields=["blocks"])
            changed += 1
    for t in EntryTranslation.objects.all():
        if touches(t.data):
            t.data = swap(t.data)
            t.save(update_fields=["data"])
            changed += 1
    for e in Entry.objects.all():
        if touches(e.data):
            e.data = swap(e.data)
            e.save(update_fields=["data"])
            changed += 1
    for m in Menu.objects.all():
        if touches(m.items):
            m.items = swap(m.items)
            m.save(update_fields=["items"])
            changed += 1
    return changed


def replace_file(m, upload):
    """Put a new file behind an existing media item. Fields that store the id follow automatically; rich text
    addresses are updated. The new file gets a new name, so browsers and Cloudflare never show the old one."""
    from PIL import Image, ImageOps
    from .media import ALLOWED, MediaError, check_library_space, check_upload, make_variants, safe_stem
    mime = check_upload(upload)   # type by content, size limits and the public demo rules
    if mime.split("/")[0] != (m.mime or "").split("/")[0] or (m.mime == "application/pdf") != (mime == "application/pdf"):
        raise MediaError("Replace an image with an image, a video with a video and a PDF with a PDF.")
    check_library_space(max(0, upload.size - (m.size or 0)))
    root = Path(settings.MEDIA_ROOT)
    old_file, old_variants = m.file.name, dict(m.variants or {})
    stem = safe_stem(upload.name)
    m.file.save(stem + ALLOWED[mime], upload, save=False)
    m.mime, m.size, m.variants = mime, upload.size, {}
    if mime.startswith("image/"):
        with Image.open(m.file.path) as im:
            im = ImageOps.exif_transpose(im)
            m.width, m.height = im.size
            m.variants = make_variants(im, m.file.name)
    else:
        m.width = m.height = None
    m.save()
    prefix = settings.TECHNTING_CMS_PUBLIC_MEDIA_PREFIX
    pairs = [(prefix + old_file, prefix + m.file.name)]
    for w, rel in old_variants.items():
        new = m.variants.get(w) or m.file.name
        pairs.append((prefix + rel, prefix + new))
    changed = _replace_text(pairs)
    for rel in [old_file, *old_variants.values()]:
        if rel not in {m.file.name, *m.variants.values()}:
            (root / rel).unlink(missing_ok=True)
    return changed
