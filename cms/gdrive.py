"""Minimal Google Drive client for offsite backups, with the same methods as cms/s3.py (put_file, put_bytes,
get_bytes, get_to_file, head, delete, list), so cms/offsite.py uploads, prunes, checks and restores unchanged.

  * Sign-in uses Google's device flow ("TVs and Limited Input devices" OAuth client): the dashboard shows a short
    code, an admin types it at google.com/device and allows access. No callback address is needed on the site.
  * The scope is drive.file: Technting CMS sees only the files it created, never the rest of the Drive.
  * Everything lives in one folder the app creates (default "Technting CMS backups"). Drive has no paths, so each
    object is one file in that folder whose name is the full key ("technting-cms/technting-cms-20261016-023000/offsite.json").
  * Uploads are resumable and sent in 8 MiB pieces; a dropped connection continues where Google stopped.
Standard library only, like cms/s3.py.
"""
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode

from .s3 import S3Error

OAUTH = "https://oauth2.googleapis.com"
API = "https://www.googleapis.com"
SCOPE = "https://www.googleapis.com/auth/drive.file"
FOLDER_MIME = "application/vnd.google-apps.folder"
CHUNK = 8 << 20          # Google wants pieces in multiples of 256 KiB
RESUME_TRIES = 3
RETRY_WAIT = 2           # seconds, times the attempt number
FIELDS = "id,name,size,md5Checksum,modifiedTime"


class DriveError(S3Error):
    """Same shape as S3Error (status, code), so offsite.py and the settings page report both alike."""


def _call(method, url, data=None, headers=None, timeout=120):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read(4000) if method != "HEAD" else b""
        code, message = exc.reason or "", ""
        try:
            err = json.loads(body)
            if isinstance(err.get("error"), dict):     # Drive API: {"error": {"code", "message", "errors": [{"reason"}]}}
                e = err["error"]
                code = ((e.get("errors") or [{}])[0].get("reason")) or e.get("status") or code
                message = e.get("message", "")
            else:                                      # OAuth: {"error": "invalid_grant", "error_description": ...}
                code, message = err.get("error") or code, err.get("error_description", "")
        except (ValueError, AttributeError):
            pass
        err = DriveError(exc.code, code, str(message)[:200])
        err.range = exc.headers.get("Range", "") if exc.headers else ""   # resumable uploads answer 308 + Range
        raise err from None


def _form(path, fields):
    with _call("POST", OAUTH + path, urlencode(fields).encode(),
               {"Content-Type": "application/x-www-form-urlencoded"}, timeout=30) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------- device sign-in
def device_start(client_id):
    """Ask Google for a sign-in code: {device_code, user_code, verification_url, expires_in, interval}."""
    out = _form("/device/code", {"client_id": client_id, "scope": SCOPE})
    out["verification_url"] = out.get("verification_url") or out.get("verification_uri") or "https://www.google.com/device"
    return out


def device_poll(client_id, client_secret, device_code):
    """One check whether the admin allowed access. Returns the refresh token, or None while Google still waits.
    Raises DriveError with code access_denied, expired_token, slow_down or invalid_client otherwise."""
    try:
        out = _form("/token", {"client_id": client_id, "client_secret": client_secret, "device_code": device_code,
                               "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
    except DriveError as exc:
        if exc.code == "authorization_pending":
            return None
        raise
    if SCOPE not in out.get("scope", "").split():
        raise DriveError(0, "ScopeMissing", "Google did not grant access to the backup files")
    if not out.get("refresh_token"):
        raise DriveError(0, "NoRefreshToken", "Google did not return a refresh token")
    return out["refresh_token"]


# ---------------------------------------------------------------- client
def _q(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


class Drive:
    def __init__(self, client_id, client_secret, refresh_token, folder, timeout=120):
        self.client_id, self.client_secret, self.refresh_token = client_id, client_secret, refresh_token
        self.folder_name, self.timeout = folder, timeout
        self._token, self._expires, self._folder = "", 0, None

    # -- auth and requests
    def _access(self, force=False):
        if force or not self._token or time.time() > self._expires - 60:
            try:
                out = _form("/token", {"client_id": self.client_id, "client_secret": self.client_secret,
                                       "refresh_token": self.refresh_token, "grant_type": "refresh_token"})
            except DriveError as exc:
                if exc.code == "invalid_grant":
                    raise DriveError(exc.status, "invalid_grant", "Google access expired or was removed; "
                                     "connect Google Drive again in Offsite settings") from None
                raise
            self._token, self._expires = out["access_token"], time.time() + int(out.get("expires_in", 3600))
        return self._token

    def request(self, method, url, data=None, headers=None):
        """Call the Drive API with a fresh access token (refreshed once on 401)."""
        for attempt in (0, 1):
            h = {"Authorization": "Bearer " + self._access(force=attempt == 1), **(headers or {})}
            try:
                return _call(method, url, data, h, self.timeout)
            except DriveError as exc:
                if exc.status != 401 or attempt:
                    raise

    def _json(self, method, path, params=None, body=None):
        url = API + path + ("?" + urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        with self.request(method, url, data, {"Content-Type": "application/json"} if data else None) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}

    def _search(self, q, fields=FIELDS, order="createdTime"):
        out, token = [], None
        while True:
            params = {"q": q, "fields": f"nextPageToken,files({fields})", "pageSize": 1000, "orderBy": order,
                      "spaces": "drive"}
            if token:
                params["pageToken"] = token
            page = self._json("GET", "/drive/v3/files", params)
            out += page.get("files", [])
            token = page.get("nextPageToken")
            if not token:
                return out

    def folder(self):
        """Id of the backup folder, created on first use (drive.file sees only folders this app made)."""
        if not self._folder:
            found = self._search(f"name = {_q(self.folder_name)} and mimeType = '{FOLDER_MIME}' and trashed = false "
                                 "and 'root' in parents", "id")
            self._folder = found[0]["id"] if found else \
                self._json("POST", "/drive/v3/files", {"fields": "id"},
                           {"name": self.folder_name, "mimeType": FOLDER_MIME})["id"]
        return self._folder

    def _find(self, key):
        return self._search(f"name = {_q(key)} and {_q(self.folder())} in parents and trashed = false")

    def account(self):
        """Email address of the connected Google account ("" if Google does not say)."""
        try:
            return self._json("GET", "/drive/v3/about", {"fields": "user(emailAddress)"}).get("user", {}).get("emailAddress", "")
        except DriveError:
            return ""

    # -- the interface offsite.py uses
    def _upload(self, key, stream, size, content_type):
        old = self._find(key)
        url = API + "/upload/drive/v3/files?" + urlencode({"uploadType": "resumable", "fields": FIELDS})
        meta = json.dumps({"name": key, "parents": [self.folder()]}).encode()
        with self.request("POST", url, meta, {"Content-Type": "application/json; charset=UTF-8",
                                              "X-Upload-Content-Type": content_type,
                                              "X-Upload-Content-Length": str(size)}) as r:
            session = r.headers.get("Location")
        if not session:
            raise DriveError(0, "NoUploadSession", "Google did not start the upload")
        done, sent, tries, ask = None, 0, 0, False
        while done is None:
            if ask:                                    # after a failure: ask how much Google kept
                piece, rng, end = b"", f"bytes */{size}", sent
            else:
                stream.seek(sent)
                piece = stream.read(CHUNK)
                end = sent + len(piece)
                rng = f"bytes {sent}-{end - 1}/{size}" if piece else f"bytes */{size}"
            try:
                done, sent = self._send(session, piece, rng, end)
                ask = False
            except (DriveError, OSError) as exc:
                if isinstance(exc, DriveError) and exc.status < 500 and exc.status != 429:
                    raise
                tries += 1
                if tries > RESUME_TRIES:
                    raise
                time.sleep(RETRY_WAIT * tries)
                ask = True
        if int(done.get("size", -1)) != size:
            raise DriveError(0, "SizeMismatch", f"{key}: Google stored {done.get('size')} bytes, sent {size}")
        for f in old:                                  # replace: the new file is complete, so drop older ones
            self._delete_id(f["id"])
        return done

    def _send(self, session, piece, rng, end):
        """PUT one piece. Returns (file metadata, offset) when finished, else (None, bytes Google has)."""
        try:
            with self.request("PUT", session, piece, {"Content-Range": rng, "Content-Length": str(len(piece))}) as r:
                return json.loads(r.read()), end
        except DriveError as exc:
            if exc.status != 308:
                raise
            got = getattr(exc, "range", "")
            return None, int(got.rsplit("-", 1)[1]) + 1 if got else 0

    def put_file(self, key, path, sha256_hex=None, size=None):
        with open(path, "rb") as f:
            f.seek(0, 2)
            self._upload(key, f, f.tell(), "application/octet-stream")

    def put_bytes(self, key, data, content_type="application/json"):
        self._upload(key, io.BytesIO(data), len(data), content_type)

    def _media(self, key):
        found = self._find(key)
        if not found:
            raise DriveError(404, "NoSuchKey", key)
        return self.request("GET", f"{API}/drive/v3/files/{quote(found[-1]['id'])}?alt=media")

    def get_bytes(self, key, limit=10 << 20):
        with self._media(key) as r:
            return r.read(limit)

    def get_to_file(self, key, path):
        """Stream a file to disk. Returns the SHA-256 hex of what was received."""
        sha = hashlib.sha256()
        with self._media(key) as r, open(path, "wb") as out:
            for chunk in iter(lambda: r.read(1 << 20), b""):
                out.write(chunk)
                sha.update(chunk)
        return sha.hexdigest()

    def head(self, key):
        found = self._find(key)
        if not found:
            return None
        f = found[-1]
        return {"size": int(f.get("size", 0)), "etag": f.get("md5Checksum", "")}

    def _delete_id(self, file_id):
        try:
            self.request("DELETE", f"{API}/drive/v3/files/{quote(file_id)}").close()
        except DriveError as exc:
            if exc.status != 404:
                raise

    def delete(self, key):
        """Delete for good (not to the bin), like the S3 version, so old copies stop using the Drive quota."""
        for f in self._find(key):
            self._delete_id(f["id"])

    def list(self, prefix=""):
        """Every backup file whose name starts with prefix: [{key, size, etag, modified}]."""
        files = self._search(f"{_q(self.folder())} in parents and trashed = false", order="name")
        return [{"key": f["name"], "size": int(f.get("size", 0)), "etag": f.get("md5Checksum", ""),
                 "modified": f.get("modifiedTime", "")} for f in files if f["name"].startswith(prefix)]
