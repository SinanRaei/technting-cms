"""Database engine settings (TECHNTING_CMS_DB_*) and engine-specific backups (cms/dbdump.py). The dump tools are
mocked, so these run on any database. Run: manage.py test cms.test_database"""
import gzip
import io
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from cms import dbdump, offsite
from cms.management.commands.backup import archives
from cms.models import Setting
from technting_cms.database import database_config, engine_name

SECRET = 'pa$$ "quoted" \\ word'
SERVER_DB = {"NAME": "technting_cms", "USER": "technting", "PASSWORD": SECRET, "HOST": "db.internal", "PORT": "3307"}
MYSQL_DUMP = b"-- MariaDB dump\nCREATE TABLE `cms_page` (\n  `id` bigint\n);\nCREATE TABLE `cms_entry` (\n);\n-- Dump completed on 2026-11-10 12:00:00\n"
PG_DUMP = (b"-- PostgreSQL database dump\nCREATE TABLE public.cms_page (\n);\nCREATE TABLE public.cms_entry (\n);\n"
           b"-- PostgreSQL database dump complete\n")


class SettingsParsingTests(SimpleTestCase):
    def test_sqlite_is_the_default(self):
        for environ in ({}, {"TECHNTING_CMS_DB_ENGINE": ""}, {"TECHNTING_CMS_DB_ENGINE": " SQLite3 "}):
            cfg = database_config(environ, Path("/srv/var"))
            self.assertEqual(cfg["ENGINE"], "django.db.backends.sqlite3")
            self.assertEqual(cfg["NAME"], Path("/srv/var") / "technting_cms.sqlite3")
            self.assertEqual(cfg["CONN_MAX_AGE"], 0)
        self.assertEqual(engine_name({}), "sqlite")

    def test_mysql_and_mariadb(self):
        env = {"TECHNTING_CMS_DB_ENGINE": "mysql", "TECHNTING_CMS_DB_NAME": "cms", "TECHNTING_CMS_DB_USER": "cms",
               "TECHNTING_CMS_DB_PASSWORD": " keep spaces "}
        cfg = database_config(env, Path("var"))
        self.assertEqual(cfg["ENGINE"], "django.db.backends.mysql")
        self.assertEqual((cfg["HOST"], cfg["PORT"], cfg["PASSWORD"]), ("127.0.0.1", "3306", " keep spaces "))
        self.assertEqual(cfg["OPTIONS"], {"charset": "utf8mb4", "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
                                          "isolation_level": "read committed"})
        self.assertEqual(cfg["TEST"]["CHARSET"], "utf8mb4")
        self.assertEqual(cfg["CONN_MAX_AGE"], 0)
        self.assertEqual(database_config({**env, "TECHNTING_CMS_DB_ENGINE": "MariaDB"}, Path("var"))["ENGINE"],
                         "django.db.backends.mysql")

    def test_postgresql(self):
        env = {"TECHNTING_CMS_DB_ENGINE": "postgresql", "TECHNTING_CMS_DB_NAME": "cms", "TECHNTING_CMS_DB_USER": "cms",
               "TECHNTING_CMS_DB_PASSWORD": "x", "TECHNTING_CMS_DB_HOST": "pg.internal", "TECHNTING_CMS_DB_PORT": "6432"}
        cfg = database_config(env, Path("var"))
        self.assertEqual(cfg["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual((cfg["HOST"], cfg["PORT"]), ("pg.internal", "6432"))
        self.assertNotIn("OPTIONS", cfg)
        self.assertEqual(database_config({**env, "TECHNTING_CMS_DB_PORT": ""}, Path("var"))["PORT"], "5432")

    def test_unknown_engine_stops(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "TECHNTING_CMS_DB_ENGINE='oracle' is not supported"):
            database_config({"TECHNTING_CMS_DB_ENGINE": "oracle"}, Path("var"))

    def test_missing_values_stop(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            database_config({"TECHNTING_CMS_DB_ENGINE": "mysql", "TECHNTING_CMS_DB_USER": "cms"}, Path("var"))
        self.assertIn("TECHNTING_CMS_DB_NAME, TECHNTING_CMS_DB_PASSWORD", str(ctx.exception))
        self.assertNotIn("TECHNTING_CMS_DB_USER", str(ctx.exception))

    def test_bad_port_stops(self):
        env = {"TECHNTING_CMS_DB_ENGINE": "mysql", "TECHNTING_CMS_DB_NAME": "a", "TECHNTING_CMS_DB_USER": "b",
               "TECHNTING_CMS_DB_PASSWORD": "c", "TECHNTING_CMS_DB_PORT": "99999"}
        with self.assertRaisesMessage(ImproperlyConfigured, "not a port number"):
            database_config(env, Path("var"))


class FakeProc:
    """Stands in for subprocess.Popen: remembers the call, hands out `output` and keeps what is written to stdin."""
    calls = []

    def __init__(self, argv, stdout=None, stdin=None, stderr=None, env=None, output=b"", code=0):
        cnf = next((a.split("=", 1)[1] for a in argv if a.startswith("--defaults-extra-file=")), None)
        self.call = {"argv": list(argv), "env": env, "options": Path(cnf).read_text(encoding="utf-8") if cnf else None}
        FakeProc.calls.append(self.call)
        self.stdout = io.BytesIO(output)
        self.stdin = io.BytesIO()
        self.stdin.close = lambda: self.call.setdefault("stdin", self.stdin.getvalue())
        self.code = code
        if code and stderr is not None:
            stderr.write(b"access denied")

    def wait(self, timeout=None):
        return self.code


def fake_tools(output=b"", code=0, missing=()):
    FakeProc.calls = []
    popen = mock.patch("cms.dbdump.subprocess.Popen",
                       side_effect=lambda argv, **kw: FakeProc(argv, output=output, code=code, **kw))
    which = mock.patch("cms.dbdump.shutil.which", side_effect=lambda n: None if n in missing else f"/usr/bin/{n}")
    return popen, which


class TempDirMixin:
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)


class DumpCommandTests(TempDirMixin, SimpleTestCase):
    def dump(self, engine, output, **kw):
        popen, which = fake_tools(output, **kw)
        db = {**SERVER_DB, "ENGINE": f"django.db.backends.{engine}"}
        with popen, which, mock.patch("django.db.connection"):
            return dbdump.dump(self.tmp, db)

    def test_mysql_uses_mysqldump_with_an_option_file(self):
        info = self.dump("mysql", MYSQL_DUMP)
        self.assertEqual(info, {"engine": "mysql", "file": "database.sql.gz"})
        call = FakeProc.calls[0]
        argv = call["argv"]
        self.assertTrue(argv[0].endswith("mariadb-dump"))
        self.assertTrue(argv[1].startswith("--defaults-extra-file="))   # must come first
        for flag in ("--single-transaction", "--routines", "--default-character-set=utf8mb4"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[-1], "technting_cms")
        self.assertIn("db.internal", argv)
        self.assertIn("3307", argv)
        self.assertNotIn(SECRET, " ".join(argv))
        self.assertNotIn("MYSQL_PWD", call["env"])
        self.assertEqual(call["options"], '[client]\npassword="pa$$ \\"quoted\\" \\\\ word"\n')
        self.assertFalse(Path(argv[1].split("=", 1)[1]).exists())         # removed afterwards
        self.assertEqual(gzip.decompress((self.tmp / "database.sql.gz").read_bytes()), MYSQL_DUMP)

    def test_mysqldump_name_when_mariadb_dump_is_missing(self):
        self.dump("mysql", MYSQL_DUMP, missing=("mariadb-dump",))
        self.assertTrue(FakeProc.calls[0]["argv"][0].endswith("mysqldump"))

    def test_postgresql_uses_pg_dump_and_pgpassword(self):
        info = self.dump("postgresql", PG_DUMP)
        self.assertEqual(info["engine"], "postgresql")
        call = FakeProc.calls[0]
        self.assertTrue(call["argv"][0].endswith("pg_dump"))
        for flag in ("--no-password", "--clean", "--if-exists", "--no-owner"):
            self.assertIn(flag, call["argv"])
        self.assertEqual(call["env"]["PGPASSWORD"], SECRET)
        self.assertNotIn(SECRET, " ".join(call["argv"]))

    def test_cut_short_dump_is_refused(self):
        with self.assertRaisesMessage(dbdump.DumpError, "incomplete"):
            self.dump("mysql", MYSQL_DUMP.rsplit(b"-- Dump", 1)[0])

    def test_failing_tool_reports_its_error(self):
        with self.assertRaisesMessage(dbdump.DumpError, "access denied"):
            self.dump("mysql", b"", code=2)
        self.assertFalse((self.tmp / "database.sql.gz").exists())

    def test_missing_tool(self):
        with self.assertRaisesMessage(dbdump.DumpError, "client tools"):
            self.dump("postgresql", PG_DUMP, missing=("pg_dump",))

    def test_load_streams_the_dump_into_mysql(self):
        path = self.tmp / "database.sql.gz"
        path.write_bytes(gzip.compress(MYSQL_DUMP))
        popen, which = fake_tools()
        with popen, which, mock.patch("django.db.connection"):
            dbdump.load(path, {**SERVER_DB, "ENGINE": "django.db.backends.mysql"})
        call = FakeProc.calls[0]
        self.assertTrue(call["argv"][0].endswith("/mariadb"))
        self.assertEqual(call["stdin"], MYSQL_DUMP)
        self.assertNotIn(SECRET, " ".join(call["argv"]))

    def test_engine_names(self):
        self.assertEqual(dbdump.engine({"ENGINE": "django.db.backends.sqlite3"}), "sqlite")
        self.assertEqual(dbdump.engine({"ENGINE": "django.db.backends.mysql"}), "mysql")
        self.assertEqual(dbdump.engine({"ENGINE": "django.db.backends.postgresql"}), "postgresql")


class BackupCommandTests(TempDirMixin, TestCase):
    def backup(self, engine, output):
        popen, which = fake_tools(output)
        p = override_settings(MEDIA_ROOT=self.tmp / "media")
        with popen, which, p, mock.patch("cms.dbdump.engine", return_value=engine):
            call_command("backup", dest=str(self.tmp / "backups"), stdout=io.StringIO())
        folder = next((self.tmp / "backups").glob("technting-cms-*"))
        return folder, json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    def test_mysql_backup_writes_a_dump_and_lists_it(self):
        folder, manifest = self.backup("mysql", MYSQL_DUMP)
        self.assertTrue(FakeProc.calls[0]["argv"][0].endswith("mariadb-dump"))
        self.assertEqual((manifest["database"]["engine"], manifest["database"]["file"]), ("mysql", "database.sql.gz"))
        self.assertIn("pages", manifest["database"])
        self.assertFalse((folder / "technting_cms.sqlite3").exists())
        self.assertEqual(archives(manifest), [("database.sql.gz", "database"), ("media.tar.gz", "media")])
        self.assertEqual(offsite.snapshot_files(manifest), ["database.sql.gz", "media.tar.gz", "manifest.json"])
        self.assertEqual(offsite.open_database(folder, manifest), (manifest["database"]["pages"], manifest["database"]["entries"]))

    def test_postgresql_backup(self):
        folder, manifest = self.backup("postgresql", PG_DUMP)
        self.assertTrue(FakeProc.calls[0]["argv"][0].endswith("pg_dump"))
        self.assertEqual(manifest["database"]["engine"], "postgresql")
        self.assertEqual(offsite.open_database(folder, manifest)[0], manifest["database"]["pages"])

    def test_failed_dump_is_remembered(self):
        with self.assertRaises(SystemExit):
            self.backup("mysql", b"-- not finished\n")
        self.assertIn("incomplete", Setting.objects.get(key="backup_failed").value["error"])

    def test_restore_refuses_another_engine(self):
        folder, manifest = self.backup("mysql", MYSQL_DUMP)
        with mock.patch("cms.dbdump.engine", return_value="sqlite"), \
                self.assertRaisesMessage(CommandError, "holds a mysql database and this site uses sqlite"):
            call_command("restore_backup", str(folder), "--yes", stdout=io.StringIO())

    def test_restore_loads_the_dump_after_saving_the_current_database(self):
        folder, manifest = self.backup("mysql", MYSQL_DUMP)
        popen, which = fake_tools(MYSQL_DUMP)
        var = self.tmp / "var"
        var.mkdir()
        with popen, which, override_settings(VAR_DIR=var, MEDIA_ROOT=self.tmp / "media"), \
                mock.patch("cms.dbdump.engine", return_value="mysql"):
            call_command("restore_backup", str(folder), "--yes", stdout=io.StringIO())
        dump_call, load_call = FakeProc.calls
        self.assertTrue(dump_call["argv"][0].endswith("mariadb-dump"))
        self.assertTrue(load_call["argv"][0].endswith("/mariadb"))
        self.assertEqual(load_call["stdin"], MYSQL_DUMP)
        self.assertEqual(len(list(var.glob("database-before-restore-*/database.sql.gz"))), 1)


class OlderBackupTests(TempDirMixin, SimpleTestCase):
    def test_manifest_without_engine_is_sqlite(self):
        manifest = {"created": "2026-01-01", "database": {"bytes": 1, "sha256": "x"}, "media": {"files": 0}}
        self.assertEqual(dbdump.manifest_engine(manifest), "sqlite")
        self.assertEqual(archives(manifest), [("technting_cms.sqlite3", "database"), ("media.tar.gz", "media")])
        self.assertEqual(offsite.snapshot_files(manifest), ["technting_cms.sqlite3", "media.tar.gz", "manifest.json"])

    def test_dump_without_content_tables_fails_the_restore_test(self):
        (self.tmp / "database.sql.gz").write_bytes(gzip.compress(b"-- Dump completed on 2026\n"))
        manifest = {"database": {"engine": "mysql", "file": "database.sql.gz"}}
        with self.assertRaisesMessage(ValueError, "no content tables"):
            offsite.open_database(self.tmp, manifest)

    def test_damaged_dump(self):
        (self.tmp / "database.sql.gz").write_bytes(gzip.compress(MYSQL_DUMP)[:-12])
        with self.assertRaisesMessage(ValueError, "damaged"):
            offsite.open_database(self.tmp, {"database": {"engine": "mysql", "file": "database.sql.gz"}})
