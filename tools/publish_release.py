"""Publish a Technting CMS release in one command: test, build, check, upload to Cloudflare R2, verify it is live.

  python tools/publish_release.py              # the version in technting_cms/__init__.py at HEAD
  python tools/publish_release.py --dry-run    # everything except the upload and the live checks
  python tools/publish_release.py --selftest   # only the R2 signature check (AWS documentation examples)

Steps, each stops the run when it fails:
  1. clean      the working tree has no uncommitted changes (the release is built from HEAD)
  2. tests      manage.py test, in a throw-away data folder
  3. build      tools/make_release.py: technting-cms-X.Y.Z.zip, .tar.gz and SHA256SUMS in dist/X.Y.Z/
  4. smoke      the zip unpacked in a temporary folder: manage.py check, migrate on a fresh SQLite database, the
                updater's own release checks (cms.updater.read_release); with SMOKE_LICENCE set, also a real licence
                check with licenses.technting.com (cms.licence.ask) that must answer "active"
  5. upload     PUT technting-cms/technting-cms-X.Y.Z.zip to the private R2 bucket (refused when it is already there,
                unless --force), then HEAD to compare the size
  6. live       the update feed on technting.com names the new version (its pick is cached up to 10 minutes, so this
                waits at most 15), then the zip behind the feed's link is downloaded and its SHA-256 compared

The download form, the e-mailed links and Settings, Updates in every installed CMS all read the newest zip in the
bucket, so step 5 is the whole publication: nothing else is edited by hand.

Settings come from the environment or from a file outside the repository (default ~/.technting/release.env, one
NAME=value per line), never from this repository:
  R2_ACCOUNT     the Cloudflare account id
  R2_KEY_ID      an R2 API token's access key id, "Object Read & Write" on the release bucket only
  R2_SECRET      that token's secret access key
                 Without R2_KEY_ID and R2_SECRET the upload goes through Wrangler instead, signed in once with
                 `wrangler login` (WRANGLER: the path of wrangler.js; default the newest one in the npx cache), so no
                 key is kept anywhere by this script
  R2_BUCKET      default technting-downloads
  R2_PREFIX      default technting-cms/
  FEED_URL       default https://technting.com/wp-json/technting/v1/cms-update
  SMOKE_LICENCE  optional: a licence key kept for this smoke test (one installation: the id is kept next to the file)
  SMOKE_DOMAIN   default smoke-test.technting.com
Secrets are never printed.
"""
import argparse
import datetime
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = {"R2_BUCKET": "technting-downloads", "R2_PREFIX": "technting-cms/", "SMOKE_DOMAIN": "smoke-test.technting.com",
            "FEED_URL": "https://technting.com/wp-json/technting/v1/cms-update"}
LIVE_WAIT_SECONDS = 15 * 60


def say(step, text):
    print(f"[{step}] {text}", flush=True)


def fail(step, text):
    print(f"[{step}] FAILED: {text}", flush=True)
    sys.exit(1)


# ---------------------------------------------------------------- settings
def load_settings(path):
    conf = dict(DEFAULTS)
    p = Path(path).expanduser()
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                conf[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("R2_ACCOUNT", "R2_KEY_ID", "R2_SECRET", "R2_BUCKET", "R2_PREFIX", "FEED_URL", "SMOKE_LICENCE", "SMOKE_DOMAIN", "WRANGLER"):
        if os.environ.get(k):
            conf[k] = os.environ[k]
    return conf, p


# ---------------------------------------------------------------- Signature V4 (header style), as S3 and R2 accept it
def enc(v, path=False):
    e = urllib.parse.quote(str(v), safe="-_.~")
    return e.replace("%2F", "/") if path else e


def sign(method, host, path, query, headers, payload_hash, key_id, secret, region, now):
    """Headers to send (Authorization, x-amz-date, x-amz-content-sha256 and the given ones). `headers` are extra
    headers to sign, `path` is not encoded, `now` a datetime in UTC."""
    amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    scope = f"{day}/{region}/s3/aws4_request"
    h = {k.lower(): str(v).strip() for k, v in headers.items()}
    h.update({"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz})
    names = sorted(h)
    canonical_query = "&".join(f"{enc(k)}={enc(v)}" for k, v in sorted(query.items()))
    creq = "\n".join([method, enc(path, True), canonical_query, "".join(f"{n}:{h[n]}\n" for n in names), ";".join(names), payload_hash])
    sts = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(creq.encode()).hexdigest()])
    k = hmac.new(("AWS4" + secret).encode(), day.encode(), hashlib.sha256).digest()
    for part in (region, "s3", "aws4_request"):
        k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    out = {n: h[n] for n in names if n != "host"}
    out["Authorization"] = f"AWS4-HMAC-SHA256 Credential={key_id}/{scope}, SignedHeaders={';'.join(names)}, Signature={sig}"
    return out


def selftest():
    """The AWS documentation's header-signed examples (GET Object and PUT Object), byte for byte."""
    key, secret = "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    now = datetime.datetime(2013, 5, 24, tzinfo=datetime.timezone.utc)
    empty = hashlib.sha256(b"").hexdigest()
    get = sign("GET", "examplebucket.s3.amazonaws.com", "/test.txt", {}, {"Range": "bytes=0-9"}, empty, key, secret, "us-east-1", now)
    body = b"Welcome to Amazon S3."
    put = sign("PUT", "examplebucket.s3.amazonaws.com", "/test$file.text", {},
               {"Date": "Fri, 24 May 2013 00:00:00 GMT", "x-amz-storage-class": "REDUCED_REDUNDANCY"},
               hashlib.sha256(body).hexdigest(), key, secret, "us-east-1", now)
    ok = (get["Authorization"].endswith("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")
          and put["Authorization"].endswith("Signature=98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd"))
    say("selftest", "Signature V4 matches the AWS examples" if ok else "Signature V4 does NOT match the AWS examples")
    return ok


def r2(conf, method, key, body=b"", content_type=None):
    host = f"{conf['R2_ACCOUNT']}.r2.cloudflarestorage.com"
    path = f"/{conf['R2_BUCKET']}/{key}"
    extra = {"Content-Type": content_type} if content_type else {}
    headers = sign(method, host, path, {}, extra, hashlib.sha256(body).hexdigest(), conf["R2_KEY_ID"], conf["R2_SECRET"], "auto",
                   datetime.datetime.now(datetime.timezone.utc))
    req = urllib.request.Request(f"https://{host}{enc(path, True)}", data=body if method == "PUT" else None, method=method,
                                 headers={**headers, **extra})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {})


# ---------------------------------------------------------------- steps
def run(cmd, cwd, env=None, timeout=1800):
    r = subprocess.run(cmd, cwd=str(cwd), env={**os.environ, **(env or {})}, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def version_at_head():
    import re
    text = subprocess.run(["git", "show", "HEAD:technting_cms/__init__.py"], cwd=ROOT, capture_output=True, text=True).stdout
    m = re.search(r'__version__\s*=\s*"(\d+\.\d+\.\d+)"', text)
    return m.group(1) if m else None


def step_clean():
    out = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if out:
        fail("clean", "uncommitted changes; commit them first:\n" + out)
    say("clean", "working tree is clean")


def step_tests(work):
    var = work / "test-var"
    var.mkdir()
    code, out = run([sys.executable, "manage.py", "test"], ROOT, {"PYTHONIOENCODING": "utf-8", "TECHNTING_CMS_DEBUG": "1",
                                                                 "TECHNTING_CMS_VAR_DIR": str(var)})
    tail = [ln for ln in out.splitlines() if ln.startswith(("Ran ", "OK", "FAILED"))]
    if code:
        fail("tests", "\n".join(out.splitlines()[-40:]))
    say("tests", " ".join(tail))


def step_build(version, dist):
    code, out = run([sys.executable, "tools/make_release.py", "--out", str(dist)], ROOT)
    if code:
        fail("build", out)
    zp = dist / f"technting-cms-{version}.zip"
    if not zp.is_file():
        fail("build", f"{zp.name} was not written")
    digest = hashlib.sha256(zp.read_bytes()).hexdigest()
    say("build", f"{zp.name} {zp.stat().st_size:,} bytes, sha256 {digest}")
    return zp, digest


def step_smoke(version, zp, work, conf, settings_path):
    folder = work / "smoke"
    with zipfile.ZipFile(zp) as z:
        z.extractall(folder)
    app = folder / f"technting-cms-{version}"
    var = folder / "var"
    var.mkdir()
    env = {"PYTHONIOENCODING": "utf-8", "TECHNTING_CMS_DEBUG": "1", "TECHNTING_CMS_VAR_DIR": str(var)}
    for cmd in (["manage.py", "check"], ["manage.py", "migrate", "--noinput"]):
        code, out = run([sys.executable, *cmd], app, env, timeout=600)
        if code:
            fail("smoke", f"{' '.join(cmd)}:\n{out[-2000:]}")
    probe = ("from cms import updater; f = updater.read_release(r'%s', '%s'); print('release-ok', len(f))" % (zp, version))
    code, out = run([sys.executable, "manage.py", "shell", "-c", probe], app, env)
    if code or "release-ok" not in out:
        fail("smoke", "the updater refuses the zip:\n" + out[-2000:])
    say("smoke", "unpacked copy: check and migrate pass, the updater accepts the zip")
    key = conf.get("SMOKE_LICENCE", "")
    if not key:
        say("smoke", "licence: skipped (no SMOKE_LICENCE)")
        return
    id_file = settings_path.parent / "smoke-installation-id"
    inst = id_file.read_text(encoding="utf-8").strip() if id_file.is_file() else ""
    script = work / "smoke_wizard.py"
    script.write_text(SMOKE_WIZARD, encoding="utf-8")
    code, out = run([sys.executable, str(script)], app, {**env, "SMOKE_LICENCE": key, "SMOKE_DOMAIN": conf["SMOKE_DOMAIN"],
                                                         "SMOKE_INSTALLATION_ID": inst}, timeout=900)
    res = {}
    for ln in out.splitlines():
        if ln.startswith("SMOKE "):
            k, _, v = ln[6:].partition("=")
            res[k] = v
    if res.get("installation") and not inst:
        id_file.write_text(res["installation"], encoding="utf-8")   # one installation for every later smoke test
    if code or res.get("wizard") != "done" or res.get("status") != "active" or res.get("recheck") != "active":
        tail = "\n".join(ln for ln in out.splitlines()[-25:] if "tai1." not in ln.lower())   # never print the key
        fail("smoke", f"setup wizard with the real licence server: wizard={res.get('wizard')}, status={res.get('status')}, "
                      f"recheck={res.get('recheck')}\n{tail}")
    say("smoke", "licence: the setup wizard accepted the key with licenses.technting.com (active), and a second check is active too")


# The setup wizard of the unpacked release, driven step by step with Django's test client, with the real licence server:
# every step must move on, the Finish must sign the administrator in, the licence must be stored as active, and a second
# check (the twice-daily one) must answer active for the same installation.
SMOKE_WIZARD = r'''
import os, secrets, sys
sys.path.insert(0, os.getcwd())     # the unpacked release (this script lives in another folder)
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "technting_cms.settings")
django.setup()
from django.test.utils import setup_test_environment
setup_test_environment()            # test host allowed, e-mail kept in memory
from django.test import Client
from cms import licence
from cms.models import Setting
inst = os.environ.get("SMOKE_INSTALLATION_ID", "")
if inst:
    Setting.objects.update_or_create(key="installation", defaults={"value": {"id": inst}})
print("SMOKE installation=" + licence.installation_id())
c = Client()
pw = "Smoke-" + secrets.token_urlsafe(18)
steps = [("site", {"site_name": "Technting smoke test", "site_url": "https://" + os.environ["SMOKE_DOMAIN"]}),
         ("languages", {"languages": "en", "default": "en"}),
         ("admin", {"username": "smoke", "email": "smoke@example.com", "password": pw, "password2": pw}),
         ("theme", {"theme": "technting"}),
         ("email", {"action": "skip"}),
         ("licence", {"licence_key": os.environ["SMOKE_LICENCE"]})]
nxt = {"site": "languages", "languages": "admin", "admin": "theme", "theme": "email", "email": "licence", "licence": "finish"}
for step, data in steps:
    r = c.post(f"/setup/{step}/", data)
    if r.status_code != 302 or not r["Location"].endswith(f"/setup/{nxt[step]}/"):
        print(f"SMOKE wizard=stuck at {step} ({r.status_code})")
        raise SystemExit(1)
r = c.post("/setup/finish/", {})
if r.status_code != 302 or "_auth_user_id" not in c.session:
    print(f"SMOKE wizard=finish failed ({r.status_code})")
    raise SystemExit(1)
print("SMOKE wizard=done")
print("SMOKE status=" + str(Setting.objects.get(key="licence").value.get("status")))
print("SMOKE recheck=" + licence.check_now()["status"])
r = c.get("/settings/licence/")
print("SMOKE page=" + str(r.status_code))
'''


def find_wrangler(conf):
    if conf.get("WRANGLER"):
        return Path(conf["WRANGLER"])
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".npm")) / "npm-cache" / "_npx"
    found = sorted(base.glob("*/node_modules/wrangler/bin/wrangler.js"), key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


def wrangler(conf, *args):
    env = {"CLOUDFLARE_ACCOUNT_ID": conf["R2_ACCOUNT"]}
    return run(["node", str(find_wrangler(conf)), *args], ROOT, env, timeout=600)


def step_upload_wrangler(conf, version, zp, force, work):
    key = f"{conf['R2_BUCKET']}/{conf['R2_PREFIX']}technting-cms-{version}.zip"
    back = work / "check.zip"
    code, _ = wrangler(conf, "r2", "object", "get", key, "--file", str(back), "--remote")
    if code == 0 and back.is_file() and not force:
        fail("upload", f"{key} is already in the bucket. Raise the version, or pass --force")
    back.unlink(missing_ok=True)
    code, out = wrangler(conf, "r2", "object", "put", key, "--file", str(zp), "--content-type", "application/zip", "--remote")
    if code:
        fail("upload", "wrangler r2 object put failed:\n" + "\n".join(ln for ln in out.splitlines()[-15:] if "token" not in ln.lower()))
    code, _ = wrangler(conf, "r2", "object", "get", key, "--file", str(back), "--remote")
    if code or not back.is_file() or back.read_bytes() != zp.read_bytes():
        fail("upload", "after the upload, the object in the bucket is not the same file")
    say("upload", f"{key} is in the bucket ({zp.stat().st_size:,} bytes, read back and identical), through Wrangler")


def step_upload(conf, version, zp, force):
    key = f"{conf['R2_PREFIX']}technting-cms-{version}.zip"
    status, head = r2(conf, "HEAD", key)
    if status == 200 and not force:
        fail("upload", f"{key} is already in the bucket ({head.get('Content-Length')} bytes). Raise the version, or pass --force")
    if status not in (200, 404):
        fail("upload", f"the bucket answered {status} (check R2_ACCOUNT, R2_BUCKET and the token's permissions)")
    data = zp.read_bytes()
    status, _ = r2(conf, "PUT", key, data, "application/zip")
    if status != 200:
        fail("upload", f"PUT answered {status}")
    status, head = r2(conf, "HEAD", key)
    if status != 200 or int(head.get("Content-Length", -1)) != len(data):
        fail("upload", f"after the upload, HEAD answered {status} with {head.get('Content-Length')} bytes, not {len(data)}")
    say("upload", f"{key} is in the bucket ({len(data):,} bytes)")


def step_live(conf, version, digest):
    deadline = time.time() + LIVE_WAIT_SECONDS
    feed = None
    while time.time() < deadline:
        try:
            req = urllib.request.Request(conf["FEED_URL"] + "?v=0.0.0", headers={"User-Agent": "TechntingCMS-release/" + version})
            with urllib.request.urlopen(req, timeout=30) as r:
                feed = json.loads(r.read().decode("utf-8"))
        except (OSError, ValueError) as exc:
            feed = {"error": type(exc).__name__}
        if feed.get("version") == version:
            break
        say("live", f"the feed still names {feed.get('version') or feed.get('error')}; checking again in 60 seconds")
        time.sleep(60)
    else:
        fail("live", f"after {LIVE_WAIT_SECONDS // 60} minutes the feed still names {(feed or {}).get('version')}")
    with urllib.request.urlopen(urllib.request.Request(feed["url"], headers={"User-Agent": "TechntingCMS-release/" + version}), timeout=120) as r:
        got = hashlib.sha256(r.read()).hexdigest()
    if got != digest:
        fail("live", f"the zip behind the feed has sha256 {got}, not {digest}")
    say("live", f"technting.com offers {version}; the download matches sha256 {digest}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--settings", default=os.environ.get("TECHNTING_RELEASE_ENV", "~/.technting/release.env"))
    ap.add_argument("--dry-run", action="store_true", help="test, build and smoke-test only: no upload, no live checks")
    ap.add_argument("--force", action="store_true", help="replace a zip of the same version already in the bucket")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--smoke-only", action="store_true", help="only the smoke test, on the zip technting.com offers now")
    opts = ap.parse_args()
    if not selftest():
        sys.exit(1)
    if opts.selftest:
        return
    conf, settings_path = load_settings(opts.settings)
    if opts.smoke_only:
        work = Path(tempfile.mkdtemp(prefix="technting-smoke-"))
        try:
            req = urllib.request.Request(conf["FEED_URL"] + "?v=0.0.0", headers={"User-Agent": "TechntingCMS-release/smoke"})
            with urllib.request.urlopen(req, timeout=30) as r:
                feed = json.loads(r.read().decode("utf-8"))
            version = feed["version"]
            zp = work / f"technting-cms-{version}.zip"
            with urllib.request.urlopen(urllib.request.Request(feed["url"], headers=req.headers), timeout=120) as r:
                zp.write_bytes(r.read())
            say("live", f"technting.com offers {version} (sha256 {hashlib.sha256(zp.read_bytes()).hexdigest()})")
            step_smoke(version, zp, work, conf, settings_path)
            say("done", f"smoke test of the live {version} passed")
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return
    use_wrangler = not (conf.get("R2_KEY_ID") and conf.get("R2_SECRET"))
    if not opts.dry_run:
        if not conf.get("R2_ACCOUNT"):
            fail("settings", f"missing R2_ACCOUNT (in {settings_path} or the environment)")
        if use_wrangler and not find_wrangler(conf):
            fail("settings", "no R2_KEY_ID / R2_SECRET and no Wrangler found (run `npx wrangler login` once)")
    version = version_at_head()
    if not version:
        fail("version", "no X.Y.Z __version__ in technting_cms/__init__.py at HEAD")
    say("version", version)
    step_clean()
    work = Path(tempfile.mkdtemp(prefix="technting-release-"))
    try:
        if not opts.skip_tests:
            step_tests(work)
        zp, digest = step_build(version, ROOT / "dist" / version)
        step_smoke(version, zp, work, conf, settings_path)
        if opts.dry_run:
            say("done", "dry run: nothing was uploaded")
            return
        if use_wrangler:
            step_upload_wrangler(conf, version, zp, opts.force, work)
        else:
            step_upload(conf, version, zp, opts.force)
        step_live(conf, version, digest)
        say("done", f"Technting CMS {version} is published: the download form and Settings, Updates offer it now")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
