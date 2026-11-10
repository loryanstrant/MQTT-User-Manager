"""Export an allowlisted public tree from a committed revision, never its history."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path, PurePosixPath

EXACT = {
    ".dockerignore",
    ".env.example",
    ".gitignore",
    ".github/workflows/container.yml",
    "AGENTS.md",
    "CHANGELOG.md",
    "Dockerfile",
    "LICENSE",
    "README.md",
    "compose.example.yaml",
    "compose.production.yaml",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements.txt",
    "wsgi.py",
}
PREFIXES = ("app/", "docs/", "tests/")
INTERNAL = {"tests/test_public_snapshot.py"}
PRIVATE = re.compile(
    rb"strant\.(?:casa|com)|\b(?:METROPLEX|SOUNDWAVE|BLASTER|PERCEPTOR|TELETRAAN)\b"
    rb"|192\.168\.(?:69|169)\.|/data/sessions/|c204b6db|8fab1fe",
    re.IGNORECASE,
)
SECRET = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{20,}"
)
RASTER = {".png", ".jpg", ".jpeg", ".ico", ".webp"}


def allowed(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        return False
    return name not in INTERNAL and (name in EXACT or name.startswith(PREFIXES))


def export(repo, revision, destination):
    repo, destination = Path(repo), Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Use an empty destination for the public snapshot")
    entries = subprocess.check_output(
        ["git", "-C", str(repo), "ls-tree", "-rz", revision], timeout=30
    ).split(b"\0")
    files = []
    for entry in filter(None, entries):
        metadata, raw_name = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        name = raw_name.decode("utf-8")
        if not allowed(name):
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError("Public export refuses links and special entries")
        data = subprocess.check_output(
            ["git", "-C", str(repo), "cat-file", "blob", oid], timeout=30
        )
        if SECRET.search(data):
            raise ValueError(f"Public export blocked: possible secret in {name}")
        if Path(name).suffix.lower() not in RASTER and PRIVATE.search(data):
            raise ValueError(f"Public export blocked: private deployment reference in {name}")
        files.append((name, mode, data))
    if not {"README.md", "LICENSE", "app/__init__.py"}.issubset({f[0] for f in files}):
        raise ValueError("Public export is missing required project files")
    destination.mkdir(parents=True, exist_ok=True)
    for name, mode, data in files:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o755 if mode == "100755" else 0o644)
    return len(files)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--repo", default=".", type=Path)
    parser.add_argument("--revision", default="HEAD")
    args = parser.parse_args()
    print(f"Exported {export(args.repo, args.revision, args.destination)} public files")
