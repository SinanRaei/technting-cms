"""Settings, Updates from the published releases (cms/updater.py, release mode): the feed, the checks on the zip, the
install itself, removed files, the up-to-date case and the Git fallback. No network: urlopen is replaced.
Run: manage.py test cms.test_updater"""
import io
import json
import shutil
import tempfile
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, override_settings

from cms import updater

FEED = "https://updates.example.test/cms-update"
ZIP_URL = "https://r2.example.test/technting-cms-0.10.0.zip?X-Amz-Signature=abc"


def make_zip(version="0.10.0", files=None, top=None, extra=None):
    top = top or f"technting-cms-{version}"
    files = files if files is not None else {
        "manage.py": b"# manage\n",
        "technting_cms/__init__.py": f'__version__ = "{version}"\n'.encode(),
        "cms/kept.py": b"kept = 2\n",
        "cms/new.py": b"new = 1\n",
        "requirements.txt": b"Django>=5.2,<5.3\n",
        "README.md": b"# readme\n",
        "deploy/nginx.conf": b"server {}\n",
        "install.sh": b"#!/bin/sh\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for rel, data in files.items():
            z.writestr(f"{top}/{rel}", data)
        for info, data in (extra or []):
            z.writestr(info, data)
    return buf.getvalue()


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class ReleaseUpdates(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.base, self.var = self.tmp / "app", self.tmp / "var"
        (self.base / "technting_cms").mkdir(parents=True)
        (self.base / "cms").mkdir()
        self.var.mkdir()
        (self.base / "technting_cms" / "__init__.py").write_text('__version__ = "0.3.0"\n', encoding="utf-8")
        (self.base / "manage.py").write_text("# manage\n", encoding="utf-8")
        (self.base / "cms" / "kept.py").write_text("kept = 1\n", encoding="utf-8")
        (self.base / "cms" / "dropped.py").write_text("dropped = 1\n", encoding="utf-8")
        (self.base / "requirements.txt").write_text("Django>=5.2,<5.3\n", encoding="utf-8")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        ov = override_settings(VAR_DIR=self.var, TECHNTING_CMS_UPDATE_TARGET=self.base,
                               TECHNTING_CMS_UPDATE_SRC=self.tmp / "none.git", TECHNTING_CMS_DEMO_MODE=False)
        ov.enable()
        self.addCleanup(ov.disable)
        for name, value in (("REMOTE", ""), ("FEED", FEED)):
            p = mock.patch.object(updater, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.feed = {"version": "0.10.0", "file": "technting-cms-0.10.0.zip", "url": ZIP_URL, "expires": 300}
        self.zip = make_zip()
        self.calls = []
        p = mock.patch("urllib.request.urlopen", side_effect=self.urlopen)
        p.start()
        self.addCleanup(p.stop)

    def urlopen(self, req, timeout=None):
        url = req.full_url
        self.calls.append(url)
        if url.startswith(FEED):
            if self.feed is None:
                raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)
            return FakeResponse(json.dumps(self.feed).encode())
        if url == ZIP_URL:
            return FakeResponse(self.zip)
        raise AssertionError(f"unexpected URL {url}")

    def run_update(self):
        with mock.patch("django.core.management.call_command"), mock.patch.object(updater, "_run", return_value="ok") as run:
            ok = updater.run_update("owner", restart=False)
        return ok, run

    # ------------------------------------------------------------ source, version, feed
    def test_mode(self):
        self.assertEqual(updater.mode(), "release")
        with mock.patch.object(updater, "REMOTE", "git@example.test:repo.git"):
            self.assertEqual(updater.mode(), "git")
        (self.tmp / "none.git").mkdir()
        self.assertEqual(updater.mode(), "git", "a server that already keeps a clone stays on Git")

    def test_installed_is_the_code_on_disk(self):
        self.assertEqual(updater.installed()["version"], "0.3.0")
        updater._write("version.json", updater.release_info("0.2.0"))
        self.assertEqual(updater.installed()["version"], "0.3.0", "an update by hand counts")

    def test_check_finds_the_newer_release(self):
        info = updater.fetch()
        self.assertEqual(info["version"], "0.10.0")
        self.assertIn("?v=0.3.0", self.calls[0])
        self.assertTrue(self.calls[0].startswith(FEED))
        saved = json.loads((self.var / "update_check.json").read_text(encoding="utf-8"))
        self.assertNotIn("url", saved["latest"], "the short-lived link is not kept")
        self.assertEqual([c["short"] for c in updater.pending()], ["0.10.0"])

    def test_version_order_is_numeric(self):
        (self.base / "technting_cms" / "__init__.py").write_text('__version__ = "0.9.0"\n', encoding="utf-8")
        updater.fetch()
        self.assertEqual(len(updater.pending()), 1, "0.10.0 is newer than 0.9.0")
        self.feed["version"] = "0.9.0"
        updater.fetch()
        self.assertEqual(updater.pending(), [])

    def test_feed_errors(self):
        self.feed = None
        with self.assertRaisesRegex(RuntimeError, "503"):
            updater.fetch()
        self.feed = {"version": "latest", "url": ZIP_URL}
        with self.assertRaises(RuntimeError):
            updater.fetch()
        self.feed = {"version": "0.10.0", "url": "http://plain.example.test/x.zip"}
        with self.assertRaises(RuntimeError, msg="https only"):
            updater.fetch()

    # ------------------------------------------------------------ checks on the zip
    def check_zip(self, data, version="0.10.0"):
        p = self.tmp / "check.zip"
        p.write_bytes(data)
        return updater.read_release(p, version)

    def test_zip_checks(self):
        files = self.check_zip(self.zip)
        self.assertEqual(files["cms/new.py"], b"new = 1\n")
        self.assertNotIn("technting-cms-0.10.0/manage.py", files, "the top folder is stripped")
        with self.assertRaisesRegex(updater.Step, "0.9.0, not 0.10.0"):
            self.check_zip(make_zip("0.9.0"))
        with self.assertRaisesRegex(updater.Step, "Unexpected path"):
            self.check_zip(make_zip(extra=[("technting-cms-0.10.0/../evil.py", b"x")]))
        with self.assertRaisesRegex(updater.Step, "not a Technting CMS release"):
            self.check_zip(make_zip(extra=[("other/manage.py", b"x")]))
        link = zipfile.ZipInfo("technting-cms-0.10.0/cms/link.py")
        link.external_attr = 0o120777 << 16
        with self.assertRaisesRegex(updater.Step, "link"):
            self.check_zip(make_zip(extra=[(link, b"/etc/passwd")]))
        with self.assertRaisesRegex(updater.Step, "not a valid zip"):
            self.check_zip(b"not a zip")
        with self.assertRaisesRegex(updater.Step, "not a Technting CMS release"):
            self.check_zip(make_zip(files={"README.md": b"x"}))

    # ------------------------------------------------------------ the update
    def test_update_installs_the_release(self):
        updater._write("release-files.json", ["cms/dropped.py", "cms/kept.py", "manage.py"])
        ok, run = self.run_update()
        st = updater.state()
        self.assertTrue(ok, st)
        self.assertEqual([s["name"] for s in st["steps"]], ["download", "backup", "files", "database", "static", "publish"])
        self.assertEqual((st["from"], st["to"]), ("0.3.0", "0.10.0"))
        self.assertEqual((self.base / "cms" / "new.py").read_text(encoding="utf-8"), "new = 1\n")
        self.assertEqual((self.base / "cms" / "kept.py").read_text(encoding="utf-8"), "kept = 2\n")
        self.assertFalse((self.base / "cms" / "dropped.py").exists(), "a file the release dropped is removed")
        self.assertFalse((self.base / "README.md").exists())
        self.assertFalse((self.base / "deploy").exists())
        self.assertEqual(updater.installed()["version"], "0.10.0")
        version = json.loads((self.var / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(version["by"], "owner")
        self.assertNotIn("url", version)
        listed = json.loads((self.var / "release-files.json").read_text(encoding="utf-8"))
        self.assertIn("cms/new.py", listed)
        self.assertNotIn("README.md", listed)
        manifest = json.loads((self.base / "code-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["commit"], "v0.10.0")
        from shield.integrity import blob_hash
        self.assertEqual(manifest["files"]["cms/new.py"], blob_hash(b"new = 1\n"))
        self.assertIn("cms", updater.installed_paths())
        self.assertFalse(any("pip" in str(c) for c in run.call_args_list), "requirements.txt did not change")
        self.assertEqual(updater.pending(), [])

    def test_up_to_date_downloads_nothing(self):
        self.feed["version"] = "0.3.0"
        ok, run = self.run_update()
        self.assertTrue(ok)
        self.assertEqual(updater.state().get("note"), "already up to date")
        self.assertNotIn(ZIP_URL, self.calls)
        run.assert_not_called()

    def test_a_wrong_release_changes_nothing(self):
        self.zip = make_zip("0.9.0", top="technting-cms-0.10.0")
        ok, run = self.run_update()
        st = updater.state()
        self.assertFalse(ok)
        self.assertEqual(st["steps"][-1]["name"], "download")
        self.assertFalse(st["rolled_back"])
        self.assertFalse((self.base / "cms" / "new.py").exists())
        self.assertEqual(updater.installed()["version"], "0.3.0")
        run.assert_not_called()

    def test_a_failed_step_puts_the_old_code_back(self):
        def run(cmd, timeout=600):
            if "migrate" in cmd:
                raise updater.Step("migration failed")
            return "ok"
        with mock.patch("django.core.management.call_command"), mock.patch.object(updater, "_run", side_effect=run):
            ok = updater.run_update("owner", restart=False)
        st = updater.state()
        self.assertFalse(ok)
        self.assertTrue(st["rolled_back"], st)
        self.assertFalse((self.base / "cms" / "new.py").exists(), "files the update added are removed")
        self.assertEqual((self.base / "cms" / "kept.py").read_text(encoding="utf-8"), "kept = 1\n")
        self.assertEqual(updater.installed()["version"], "0.3.0")
        self.assertFalse((self.var / "release-files.json").exists())
