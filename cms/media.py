"""Media uploads: type checks, image metadata and WebP variants."""
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import get_valid_filename
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import Media

ALLOWED = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    "application/pdf": ".pdf",
    "video/mp4": ".mp4", "video/webm": ".webm",
}
MAX_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 95 * 1024 * 1024  # Cloudflare (free plan) rejects request bodies over 100 MB
WIDTHS = (480, 960, 1600)
# Always refused by name, even when the content looks like an image: a server that runs files by extension must never
# get one of these (the type check above already refuses their content; this also covers names like x.php.png)
BLOCKED_EXTENSIONS = {".php", ".phtml", ".phar", ".pl", ".py", ".pyc", ".rb", ".cgi", ".sh", ".bash", ".bat", ".cmd",
                      ".ps1", ".exe", ".dll", ".msi", ".jar", ".js", ".mjs", ".html", ".htm", ".xhtml", ".shtml",
                      ".svg", ".svgz", ".xml", ".asp", ".aspx", ".jsp", ".htaccess"}
# Public demo (TECHNTING_CMS_DEMO_MODE): only these types, the name must match the content, and smaller files
DEMO_ALLOWED = {"image/jpeg": {".jpg", ".jpeg"}, "image/png": {".png"}, "image/webp": {".webp"}, "image/gif": {".gif"},
                "application/pdf": {".pdf"}}
DEMO_MAX_BYTES = 5 * 1024 * 1024
DEMO_LIBRARY_BYTES = 300 * 1024 * 1024   # the whole demo media library, until the next reset
PDF_ACTIVE = (b"/JavaScript", b"/Launch", b"/EmbeddedFile", b"/RichMedia")   # long names only: short ones occur by chance


class MediaError(Exception):
    pass


def _sniff(upload):
    head = upload.read(16)
    upload.seek(0)
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head[4:8] == b"ftyp" and head[8:12] not in (b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"avif", b"avis"):
        return "video/mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    return None


def safe_stem(name):
    """File name without its extension; inner dots become dashes, so x.php.png is stored as x-php.png."""
    return Path(get_valid_filename(name or "")).stem.replace(".", "-")[:60].strip("-_") or "file"


def check_upload(upload):
    """The file's type from its first bytes (never from its name), or MediaError."""
    from .demo import on as demo_on
    exts = {s.lower() for s in Path(upload.name or "").suffixes}
    if exts & BLOCKED_EXTENSIONS:
        raise MediaError("Files with this extension cannot be uploaded.")
    mime = _sniff(upload)
    if demo_on():
        if mime not in DEMO_ALLOWED or upload.size > DEMO_MAX_BYTES:
            raise MediaError("In the public demo, only JPEG, PNG, WebP, GIF and PDF files up to 5 MB can be uploaded.")
        if Path(upload.name or "").suffix.lower() not in DEMO_ALLOWED[mime]:
            raise MediaError("The file extension does not match its content.")
        if mime == "application/pdf" and _pdf_active(upload):
            raise MediaError("PDF files with scripts or attachments cannot be uploaded in the public demo.")
        return mime
    limit = MAX_VIDEO_BYTES if (mime or "").startswith("video/") else MAX_BYTES
    if upload.size > limit:
        raise MediaError("Videos can be up to 95 MB and other files up to 20 MB. For longer videos, use YouTube or Vimeo.")
    if mime not in ALLOWED:
        raise MediaError("Only JPEG, PNG, WebP, GIF, PDF, MP4 and WebM files can be uploaded.")
    return mime


def _pdf_active(upload):
    data = upload.read()
    upload.seek(0)
    return any(key in data for key in PDF_ACTIVE)


def check_library_space(size):
    """Public demo: stop at DEMO_LIBRARY_BYTES so visitors cannot fill the disk before the next reset."""
    from django.db.models import Sum
    from .demo import on as demo_on
    if demo_on() and (Media.objects.aggregate(n=Sum("size"))["n"] or 0) + size > DEMO_LIBRARY_BYTES:
        raise MediaError("The demo media library is full. Delete some files first.")


def save_upload(upload, user=None):
    mime = check_upload(upload)
    check_library_space(upload.size)
    stem = safe_stem(upload.name)
    m = Media(title=stem.replace("-", " ").replace("_", " "), mime=mime, size=upload.size,
              uploaded_by=user if user and user.is_authenticated else None)
    m.file.save(stem + ALLOWED[mime], upload, save=False)
    if mime.startswith("image/"):
        try:
            with Image.open(m.file.path) as im:
                im = ImageOps.exif_transpose(im)
                m.width, m.height = im.size
                m.variants = make_variants(im, m.file.name)
        except UnidentifiedImageError as exc:
            Path(m.file.path).unlink(missing_ok=True)
            raise MediaError("The image could not be read.") from exc
    m.save()
    return m


def make_variants(im, name):
    variants = {}
    base = Path(name)
    rgb = im.convert("RGBA") if im.mode in ("P", "LA", "RGBA") else im.convert("RGB")
    for w in WIDTHS:
        if im.width <= w and w != WIDTHS[0]:
            continue
        copy = rgb.copy()
        if copy.width > w:
            copy.thumbnail((w, w * 10), Image.LANCZOS)
        rel = str(base.with_name(f"{base.stem}-{w}w.webp")).replace("\\", "/")
        out = Path(settings.MEDIA_ROOT) / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        copy.save(out, "WEBP", quality=82, method=5)
        variants[f"{w}w"] = rel
    return variants


def delete_media(m):
    root = Path(settings.MEDIA_ROOT)
    for rel in [m.file.name, *m.variants.values()]:
        (root / rel).unlink(missing_ok=True)
    m.delete()


def media_json(m, lang="en"):
    prefix = settings.TECHNTING_CMS_PUBLIC_MEDIA_PREFIX
    thumb = m.variants.get("480w", m.file.name) if m.is_image else None
    kind = "image" if m.is_image else ("video" if m.mime.startswith("video/") else "file")
    return {"id": m.pk, "kind": kind, "title": m.title, "url": prefix + m.file.name, "thumb": (prefix + thumb) if thumb else None,
            "variants_960": (prefix + m.variants["960w"]) if m.variants.get("960w") else None,
            "mime": m.mime, "width": m.width, "height": m.height, "size": m.size, "alt": m.alt,
            "uploaded_at": timezone.localtime(m.uploaded_at).strftime("%Y-%m-%d %H:%M")}
