"""Minimal S3 client for offsite backups: Cloudflare R2, Backblaze B2 and any S3-compatible storage.

Only what backups need (put, get, head, delete, list) with AWS Signature Version 4 and path-style addresses.
Written with the standard library instead of boto3: the signing is about 30 lines, while boto3 and botocore add
tens of megabytes and frequent releases to keep up with. Every upload is signed with its SHA-256, so the storage
refuses a body that changed on the way.
"""
import hashlib
import hmac
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


class S3Error(Exception):
    def __init__(self, status, code, message=""):
        super().__init__(f"{status} {code}: {message}".strip(": "))
        self.status, self.code = status, code


def _enc(s, safe="~"):
    return quote(s, safe=safe)


def canonical_query(params):
    return "&".join(f"{_enc(str(k))}={_enc(str(v))}" for k, v in sorted((params or {}).items()))


def sign(method, url, headers, payload_hash, access_key, secret_key, region, now=None):
    """Return headers with x-amz-date, x-amz-content-sha256 and Authorization added (AWS SigV4, service s3).

    `url` must already be encoded the way it is sent (path and query); the query must be in canonical order."""
    now = now or datetime.now(timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    u = urlparse(url)
    h = {k.lower(): str(v).strip() for k, v in headers.items()}
    h.update({"host": u.netloc, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash})
    names = sorted(h)
    canonical = "\n".join([method, u.path or "/", u.query, "".join(f"{k}:{h[k]}\n" for k in names), ";".join(names), payload_hash])
    scope = f"{day}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = ("AWS4" + secret_key).encode()
    for part in (day, region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    h["authorization"] = f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={';'.join(names)}, Signature={signature}"
    return h


class S3:
    def __init__(self, endpoint, region, bucket, access_key, secret_key, timeout=120):
        u = urlparse(endpoint.rstrip("/"))
        local = u.hostname in ("127.0.0.1", "localhost")
        if u.scheme != "https" and not (u.scheme == "http" and local):
            raise ValueError("The storage address must start with https://")
        self.base = f"{u.scheme}://{u.netloc}"
        self.region, self.bucket = region or "auto", bucket
        self.access_key, self.secret_key, self.timeout = access_key, secret_key, timeout

    def _url(self, key="", query=None):
        path = "/" + _enc(self.bucket) + ("/" + _enc(key, safe="/~") if key else "")
        q = canonical_query(query)
        return self.base + path + ("?" + q if q else "")

    def request(self, method, key="", query=None, body=None, payload_hash=EMPTY_SHA256, headers=None):
        url = self._url(key, query)
        h = sign(method, url, headers or {}, payload_hash, self.access_key, self.secret_key, self.region)
        h.pop("host")
        req = urllib.request.Request(url, data=body, method=method, headers=h)
        try:
            return urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            data = exc.read(4000) if method != "HEAD" else b""
            code, message = exc.reason, ""
            try:
                root = ET.fromstring(data)
                code, message = root.findtext("Code") or code, root.findtext("Message") or ""
            except ET.ParseError:
                pass
            raise S3Error(exc.code, code, message[:200]) from None

    def put_file(self, key, path, sha256_hex, size):
        if size > 5 * 1024 ** 3:
            raise S3Error(0, "EntityTooLarge", "files over 5 GB need multipart upload, which is not supported")
        with open(path, "rb") as f:
            self.request("PUT", key, body=f, payload_hash=sha256_hex,
                         headers={"Content-Length": str(size), "Content-Type": "application/octet-stream"}).close()

    def put_bytes(self, key, data, content_type="application/json"):
        self.request("PUT", key, body=data, payload_hash=hashlib.sha256(data).hexdigest(),
                     headers={"Content-Length": str(len(data)), "Content-Type": content_type}).close()

    def get_bytes(self, key, limit=10 << 20):
        with self.request("GET", key) as r:
            return r.read(limit)

    def get_to_file(self, key, path):
        """Stream an object to a file. Returns the SHA-256 hex of what was received."""
        sha = hashlib.sha256()
        with self.request("GET", key) as r, open(path, "wb") as out:
            for chunk in iter(lambda: r.read(1 << 20), b""):
                out.write(chunk)
                sha.update(chunk)
        return sha.hexdigest()

    def head(self, key):
        try:
            with self.request("HEAD", key) as r:
                return {"size": int(r.headers.get("Content-Length", 0)), "etag": (r.headers.get("ETag") or "").strip('"')}
        except S3Error as exc:
            if exc.status == 404:
                return None
            raise

    def delete(self, key):
        self.request("DELETE", key).close()

    def list(self, prefix=""):
        """Every object under prefix: [{key, size, etag, modified}]."""
        out, token = [], None
        while True:
            q = {"list-type": "2", "prefix": prefix}
            if token:
                q["continuation-token"] = token
            with self.request("GET", query=q) as r:
                root = ET.fromstring(r.read())
            for c in root.iter(NS + "Contents"):
                out.append({"key": c.findtext(NS + "Key"), "size": int(c.findtext(NS + "Size") or 0),
                            "etag": (c.findtext(NS + "ETag") or "").strip('"'), "modified": c.findtext(NS + "LastModified") or ""})
            token = root.findtext(NS + "NextContinuationToken")
            if root.findtext(NS + "IsTruncated") != "true" or not token:
                return out
