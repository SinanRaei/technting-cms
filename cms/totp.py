"""Time-based one-time passwords (RFC 6238, SHA-1, 6 digits, 30 s) and recovery codes."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from django.contrib.auth.hashers import check_password, make_password

STEP = 30
DIGITS = 6


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret, step):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def verify(secret, code, last_step=0, window=1, now=None):
    """Return the matching time step, or None. Steps at or before last_step are rejected (no replay)."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != DIGITS or not secret:
        return None
    current = int((now or time.time()) // STEP)
    for step in range(current - window, current + window + 1):
        if step > last_step and hmac.compare_digest(_code(secret, step), code):
            return step
    return None


def provisioning_uri(secret, username, issuer="Technting CMS"):
    label = quote(f"{issuer}:{username}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP}"


def qr_svg(uri):
    import segno
    return segno.make(uri, error="m").svg_inline(scale=5, dark="#0b1320", light="#ffffff")


def new_recovery_codes(n=10):
    plain = ["-".join(secrets.token_hex(2) for _ in range(3)) for _ in range(n)]  # e.g. 4f2a-91c0-7b3e
    return plain, [make_password(c) for c in plain]


def use_recovery_code(hashes, code):
    """Return the remaining hashes if code matched one (it is consumed), else None."""
    code = (code or "").strip().lower()
    for i, h in enumerate(hashes):
        if check_password(code, h):
            return hashes[:i] + hashes[i + 1:]
    return None
