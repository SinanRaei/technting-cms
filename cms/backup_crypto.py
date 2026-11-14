"""Client-side encryption for offsite backups (Technting Backup).

Files are encrypted on the server before they leave it, with a passphrase that the site owner keeps. The storage
provider only ever sees encrypted bytes. Without the passphrase the copies cannot be opened by anyone, including us.

Format (version 1), streamed in 1 MiB chunks so large media archives never sit in memory:
  header  b"GETBKP01" | salt (16) | log2(N) r p (1 byte each) | chunk size (4, big-endian)
  chunks  length (4, big-endian) | AES-256-GCM(chunk)   nonce = counter (11 bytes) + last-chunk flag (1 byte)
The key is scrypt(passphrase, salt); every file has its own salt, so every file has its own key. The header is the
associated data of every chunk and the last chunk is flagged, so a cut-off or altered file fails to decrypt.

This module does not need Django, so a backup can be opened on any computer with Python and `cryptography`:
  python backup_crypto.py decrypt media.tar.gz.enc media.tar.gz      (asks for the passphrase)
"""
import hashlib
import os
import struct
import sys

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"GETBKP01"
CHUNK = 1 << 20
LOG_N, R, P = 17, 8, 1   # scrypt cost: about 128 MB of memory and a fraction of a second per file
HEADER = struct.Struct(">8s16sBBBI")


class DecryptError(ValueError):
    pass


def _key(passphrase, salt, log_n=LOG_N, r=R, p=P):
    n = 1 << log_n
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=128 * r * (n + p + 2) + (1 << 20))


def key_id(passphrase):
    """Short fingerprint that tells which passphrase encrypted a copy (it does not reveal the passphrase)."""
    return _key(passphrase, b"technting-cms-backup-key-id", log_n=14).hex()[:12]


def _nonce(counter, last):
    return counter.to_bytes(11, "big") + (b"\x01" if last else b"\x00")


def encrypt_file(src, dst, passphrase):
    """Encrypt src into dst. Returns (bytes written, sha256 hex, md5 hex) of dst, for the integrity index."""
    salt = os.urandom(16)
    header = HEADER.pack(MAGIC, salt, LOG_N, R, P, CHUNK)
    aead = AESGCM(_key(passphrase, salt))
    sha, md5, size = hashlib.sha256(), hashlib.md5(), 0

    def write(out, data):
        nonlocal size
        out.write(data)
        sha.update(data)
        md5.update(data)
        size += len(data)

    with open(src, "rb") as f, open(dst, "wb") as out:
        write(out, header)
        counter, chunk = 0, f.read(CHUNK)
        while True:
            following = f.read(CHUNK) if chunk else b""
            last = not following
            ct = aead.encrypt(_nonce(counter, last), chunk, header)
            write(out, struct.pack(">I", len(ct)) + ct)
            if last:
                break
            counter, chunk = counter + 1, following
    return size, sha.hexdigest(), md5.hexdigest()


def decrypt_file(src, dst, passphrase):
    """Decrypt src into dst. Raises DecryptError for a wrong passphrase or a damaged / cut-off file."""
    with open(src, "rb") as f:
        header = f.read(HEADER.size)
        if len(header) != HEADER.size:
            raise DecryptError("not a Technting CMS encrypted backup")
        magic, salt, log_n, r, p, chunk_size = HEADER.unpack(header)
        if magic != MAGIC or not (10 <= log_n <= 22) or chunk_size > 64 * CHUNK:
            raise DecryptError("not a Technting CMS encrypted backup")
        aead = AESGCM(_key(passphrase, salt, log_n, r, p))
        counter = 0
        with open(dst, "wb") as out:
            while True:
                raw = f.read(4)
                if len(raw) != 4:
                    raise DecryptError("the file is cut off")
                (n,) = struct.unpack(">I", raw)
                if n > chunk_size + 16:
                    raise DecryptError("damaged file")
                ct = f.read(n)
                if len(ct) != n:
                    raise DecryptError("the file is cut off")
                for last in (False, True):
                    try:
                        out.write(aead.decrypt(_nonce(counter, last), ct, header))
                        break
                    except InvalidTag:
                        continue
                else:
                    raise DecryptError("wrong passphrase or damaged file")
                if last:
                    break
                counter += 1
            if f.read(1):
                raise DecryptError("unexpected data after the end of the file")


def main(argv):
    import getpass
    if len(argv) != 4 or argv[1] not in ("decrypt", "encrypt"):
        print(__doc__)
        return 2
    passphrase = os.environ.get("TECHNTING_CMS_BACKUP_PASSPHRASE") or getpass.getpass("Passphrase: ")
    try:
        (decrypt_file if argv[1] == "decrypt" else encrypt_file)(argv[2], argv[3], passphrase)
    except DecryptError as exc:
        print(f"Could not decrypt: {exc}")
        return 1
    print(f"Wrote {argv[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
