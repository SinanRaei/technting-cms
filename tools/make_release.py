"""Build the Technting CMS release archives from a Git commit.

  python tools/make_release.py                 # HEAD, version from technting_cms/__init__.py in that commit
  python tools/make_release.py --ref v0.2.0 --out dist

Writes OUT/technting-cms-<version>.zip, OUT/technting-cms-<version>.tar.gz and OUT/SHA256SUMS. The archives hold
`git archive` of the commit (committed files only, never the working tree) under the folder technting-cms-<version>/,
without tests and development files (see EXCLUDE). Nothing is tagged or pushed.
"""
import argparse
import copy
import fnmatch
import gzip
import hashlib
import io
import re
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE = [
    "tools/*", ".claude/*", ".github/*", ".gitignore",
    "*/tests.py", "*/tests_*.py", "*/test_*.py", "*/tests/*",
]


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if r.returncode != 0:
        sys.exit(r.stderr.decode("utf-8", "replace").strip() or f"git {args[0]} failed")
    return r.stdout


def version_at(ref):
    try:
        text = git("show", f"{ref}:technting_cms/__init__.py").decode("utf-8")
    except SystemExit:
        return None
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else None


def excluded(name):
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="HEAD", help="commit, branch or tag to package (default HEAD)")
    ap.add_argument("--version", help="override the version read from the commit")
    ap.add_argument("--out", default=str(ROOT / "dist"), help="output folder (default dist/)")
    opts = ap.parse_args()

    commit = git("rev-parse", "--verify", f"{opts.ref}^{{commit}}").decode().strip()
    version = opts.version or version_at(commit)
    if not version:
        sys.exit(f"No __version__ in technting_cms/__init__.py at {opts.ref}. Commit it first or pass --version.")
    if not re.fullmatch(r"\d+\.\d+\.\d+([.-][0-9A-Za-z.]+)?", version):
        sys.exit(f"Version {version!r} does not look like 1.2.3")
    name = f"technting-cms-{version}"
    out = Path(opts.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = int(git("show", "-s", "--format=%ct", commit).decode().strip() or time.time())

    source = tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", commit)))
    members = [m for m in source.getmembers() if not excluded(m.name)]

    tar_path, zip_path = out / f"{name}.tar.gz", out / f"{name}.zip"
    with open(tar_path, "wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=stamp) as gz, \
            tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for src in members:
            data = source.extractfile(src) if src.isfile() else None
            m = copy.copy(src)
            m.name = f"{name}/{m.name}"
            m.uid = m.gid = 0
            m.uname = m.gname = ""
            m.pax_headers = {}
            if m.isfile() and m.name.endswith(".sh"):
                m.mode |= 0o755   # install.sh and the Docker scripts stay runnable after unpacking
            tar.addfile(m, data)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for m in members:
            if not m.isfile():
                continue
            info = zipfile.ZipInfo(f"{name}/{m.name}", date_time=time.gmtime(stamp)[:6])
            mode = m.mode | (0o755 if m.name.endswith(".sh") else 0)
            info.external_attr = (mode & 0o777 | 0o100000) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, source.extractfile(m).read())

    sums = out / "SHA256SUMS"
    sums.write_bytes("".join(f"{sha256(p)}  {p.name}\n" for p in (tar_path, zip_path)).encode())   # LF on every system
    files = sum(1 for m in members if m.isfile())
    print(f"{name} from {commit[:12]}: {files} files")
    for p in (tar_path, zip_path, sums):
        print(f"  {p}  {p.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
