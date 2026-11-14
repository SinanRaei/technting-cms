"""Database snapshots for `manage.py backup`, `restore_backup` and Technting Backup, per database engine.

  sqlite      technting_cms.sqlite3   SQLite's online backup API, then PRAGMA integrity_check
  mysql       database.sql.gz         mysqldump (or mariadb-dump) --single-transaction --routines, restored with mysql
  postgresql  database.sql.gz         pg_dump --clean --if-exists (plain SQL), restored with psql

Passwords never appear on a command line: MySQL / MariaDB read theirs from a temporary option file (mode 600),
PostgreSQL from PGPASSWORD in the child's environment. Older backups have no "engine" in their manifest: SQLite.
"""
import gzip
import os
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path

from django.conf import settings

SQLITE_FILE = "technting_cms.sqlite3"
DUMP_FILE = "database.sql.gz"
DB_FILES = (SQLITE_FILE, DUMP_FILE)
# the last line each dump tool writes when it finished; a dump without it was cut short
COMPLETE = {"mysql": b"-- Dump completed", "postgresql": b"-- PostgreSQL database dump complete"}
TOOLS = {"dump": {"mysql": ("mariadb-dump", "mysqldump"), "postgresql": ("pg_dump",)},
         "load": {"mysql": ("mariadb", "mysql"), "postgresql": ("psql",)}}
TIMEOUT = 6 * 3600


class DumpError(Exception):
    pass


def engine(db=None):
    """sqlite, mysql or postgresql for a DATABASES entry (the default one when not given)."""
    backend = (db or settings.DATABASES["default"])["ENGINE"]
    for name in ("sqlite", "mysql", "postgresql"):
        if name in backend:
            return name
    raise DumpError(f"backups do not support the database backend {backend}")


def describe():
    """"MariaDB 11.8.3", "SQLite 3.46.1" ...: the database this site runs on, for the setup wizard and Updates page."""
    from django.db import connection
    try:
        name = engine()
        if name == "sqlite":
            return f"SQLite {sqlite3.sqlite_version}"
        if name == "mysql":
            label = "MariaDB" if connection.mysql_is_mariadb else "MySQL"
            return f"{label} {'.'.join(str(n) for n in connection.mysql_version)}"
        connection.ensure_connection()
        v = connection.pg_version
        return f"PostgreSQL {v // 10000}.{v % 10000}"
    except Exception as exc:  # shown in the dashboard only; never stop a page for it
        return f"{settings.DATABASES['default']['ENGINE'].rsplit('.', 1)[-1]} ({type(exc).__name__})"


def file_for(name):
    return SQLITE_FILE if name == "sqlite" else DUMP_FILE


def manifest_engine(manifest):
    """The engine a backup was made from; backups made before 0.3.0 are SQLite."""
    return (manifest.get("database") or {}).get("engine", "sqlite")


def manifest_file(manifest):
    return (manifest.get("database") or {}).get("file") or file_for(manifest_engine(manifest))


def tool(kind, name):
    for exe in TOOLS[kind][name]:
        path = shutil.which(exe)
        if path:
            return path
    raise DumpError(f"{TOOLS[kind][name][-1]} was not found. Install the {name} client tools "
                    "(Debian / Ubuntu: mariadb-client or postgresql-client; the Docker image has both).")


@contextmanager
def _mysql_options(db):
    """A [client] option file with the password, readable only by this user, removed afterwards."""
    password = db.get("PASSWORD") or ""
    if "\n" in password or "\r" in password:
        raise DumpError("the database password contains a line break")
    fd, path = tempfile.mkstemp(prefix="technting-cms-db-", suffix=".cnf")
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            escaped = password.replace("\\", "\\\\").replace('"', '\\"')
            f.write(f'[client]\npassword="{escaped}"\n')
        yield path
    finally:
        os.unlink(path)


@contextmanager
def _command(kind, db):
    """(argv, env) to run the dump or load tool for db."""
    name = engine(db)
    exe = tool(kind, name)
    host, port, user = db.get("HOST") or "127.0.0.1", str(db.get("PORT") or ""), db.get("USER") or ""
    env = {k: v for k, v in os.environ.items() if k not in ("MYSQL_PWD", "PGPASSWORD")}
    if name == "mysql":
        with _mysql_options(db) as cnf:
            where = ["--socket", host] if host.startswith("/") else ["--host", host] + (["--port", port] if port else [])
            argv = [exe, f"--defaults-extra-file={cnf}", *where, "--user", user, "--default-character-set=utf8mb4"]
            if kind == "dump":
                argv += ["--single-transaction", "--routines", "--no-tablespaces"]
            yield argv + [db["NAME"]], env
        return
    env["PGPASSWORD"] = db.get("PASSWORD") or ""
    argv = [exe, "--host", host] + (["--port", port] if port else []) + ["--username", user, "--no-password"]
    if kind == "dump":
        argv += ["--no-owner", "--no-privileges", "--clean", "--if-exists", "--encoding=UTF8"]
    else:
        argv += ["--quiet", "--set", "ON_ERROR_STOP=1", "--single-transaction"]
    yield argv + ["--dbname", db["NAME"]], env


def _stderr(f):
    f.seek(0)
    return f.read().decode("utf-8", "replace").strip()[-500:]


def dump(out_dir, db=None):
    """Write this site's database into out_dir. Returns the manifest "database" entry without the checksum."""
    from django.db import connection
    db = db or settings.DATABASES["default"]
    name = engine(db)
    out = Path(out_dir) / file_for(name)
    if not connection.in_atomic_block:   # (tests run inside a transaction)
        connection.close()
    if name == "sqlite":
        # closing(): "with sqlite3.connect()" alone only commits; the files would stay open in the web process
        with closing(sqlite3.connect(str(db["NAME"]))) as src, closing(sqlite3.connect(str(out))) as dst:
            src.backup(dst)
        with closing(sqlite3.connect(str(out))) as check:
            ok = check.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise DumpError(f"Backup integrity check failed: {ok}")
    else:
        with _command("dump", db) as (argv, env), tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=err, env=env)
            try:
                with gzip.open(out, "wb", compresslevel=6) as gz:
                    shutil.copyfileobj(proc.stdout, gz, 1 << 20)
            finally:
                proc.stdout.close()
                code = proc.wait(timeout=TIMEOUT)
            if code != 0:
                out.unlink(missing_ok=True)
                raise DumpError(f"{Path(argv[0]).name} failed ({code}): {_stderr(err)}")
        check_dump(out, name)
    return {"engine": name, "file": out.name}


def check_dump(path, name, tables=()):
    """Read a gzip SQL dump to the end: it must be whole and end with the dump tool's completion line.
    Returns the names in `tables` that the dump creates."""
    tail, found = b"", set()
    wanted = {t.encode() for t in tables}
    try:
        with gzip.open(path, "rb") as gz:
            for line in gz:
                if wanted and line.startswith(b"CREATE TABLE"):
                    words = line.split()
                    table = words[2].strip(b"`\"").rsplit(b".", 1)[-1].strip(b"`\"") if len(words) > 2 else b""
                    if table in wanted:
                        found.add(table.decode())
                tail = (tail + line)[-4096:]
    except (OSError, EOFError) as exc:
        raise DumpError(f"the database dump is damaged ({exc})") from None
    if COMPLETE[name] not in tail:
        raise DumpError("the database dump is incomplete (no completion line at the end)")
    return found


def load(path, db=None):
    """Replace the tables of db with a gzip SQL dump made by dump()."""
    db = db or settings.DATABASES["default"]
    from django.db import connection
    if not connection.in_atomic_block:   # (tests run inside a transaction)
        connection.close()
    with _command("load", db) as (argv, env), tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=log, stderr=err, env=env)
        try:
            with gzip.open(path, "rb") as gz:
                shutil.copyfileobj(gz, proc.stdin, 1 << 20)
        except BrokenPipeError:
            pass   # the tool stopped on an error; its message is in err
        finally:
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
            code = proc.wait(timeout=TIMEOUT)
        if code != 0:
            raise DumpError(f"{Path(argv[0]).name} failed ({code}): {_stderr(err)}")
