"""Media library scan: every uploaded file must really be what its name says (JPEG, PNG, WebP, GIF, PDF, MP4, WebM)
and must not hide code (PHP, scripts, shell). Uploads are already checked when they arrive; this catches files put
in the folder some other way, or a weakness found later. Only new or changed files are read again.
Results: VAR_DIR/shield/media.json.
"""
import json
import re
import time
from pathlib import Path

from django.conf import settings

from . import conf

MAGIC = {
    ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"], ".png": [b"\x89PNG\r\n\x1a\n"], ".gif": [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"], ".pdf": [b"%PDF-"], ".webm": [b"\x1a\x45\xdf\xa3"], ".mp4": [], ".m4v": [],
}
CODE = re.compile(rb"(?i)<\?php|<\?=|<script[\s>]|<%[=@\s]|#!/(usr/)?bin/|\beval\s*\(|base64_decode\s*\(|\bshell_exec\s*\(|\bpassthru\s*\(")
PDF_JS = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile)\b")
SCRIPT_EXT = re.compile(r"(?i)\.(php\d?|phtml|phar|py|pl|cgi|sh|asp|aspx|jsp|exe|html?|svg|js)(\.|$)")
CHUNK = 256 * 1024


def _looks_right(ext, head):
    if ext in (".mp4", ".m4v"):
        return head[4:8] == b"ftyp"
    if ext == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    return any(head.startswith(m) for m in MAGIC[ext])


def inspect(path):
    """[(level, problem)] for one file; empty when it is fine."""
    out = []
    name = path.name
    ext = path.suffix.lower()
    if SCRIPT_EXT.search(name):
        out.append(("high", "script or page file in the media folder"))
    if ext not in MAGIC:
        if not out:
            out.append(("medium", "file type the media library does not accept"))
        return out
    with open(path, "rb") as f:
        head = f.read(CHUNK)
        size = path.stat().st_size
        tail = b""
        if size > 2 * CHUNK:
            f.seek(size - CHUNK)
            tail = f.read(CHUNK)
    if not _looks_right(ext, head):
        out.append(("high", "content does not match the file type"))
    if ext != ".pdf" and (CODE.search(head) or CODE.search(tail)):
        out.append(("high", "hidden code inside the file"))
    if ext == ".pdf" and (PDF_JS.search(head) or PDF_JS.search(tail)):
        out.append(("medium", "PDF that runs scripts or carries attachments"))
    return out


def path():
    return conf.data_dir() / "media.json"


def load():
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run():
    """Scan new and changed files. Returns (state, newly found problem files)."""
    root = Path(settings.MEDIA_ROOT)
    old = load() or {}
    seen = old.get("files") or {}
    files, problems, new, read = {}, {}, [], 0
    for p in root.rglob("*") if root.is_dir() else []:
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        st = p.stat()
        key = [st.st_size, int(st.st_mtime)]
        prev = seen.get(rel)
        if prev and prev[:2] == key:
            found = prev[2]
        else:
            try:
                found = inspect(p)
            except OSError:
                continue
            read += 1
        files[rel] = key + [found]
        if found:
            problems[rel] = found
            if rel not in (old.get("problems") or {}):
                new.append(rel)
    state = {"checked_at": time.time(), "files": files, "problems": problems, "count": len(files), "read": read}
    path().write_text(json.dumps(state), encoding="utf-8")
    return state, new
