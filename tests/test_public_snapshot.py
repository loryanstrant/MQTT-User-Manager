"""Private publication gate; intentionally excluded from the public snapshot."""

import subprocess

import pytest

from scripts.public_snapshot import allowed, export


def committed(tmp_path, extra=None):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    values = {
        "README.md": b"Public product documentation\n",
        "LICENSE": b"Synthetic license\n",
        "app/__init__.py": b"# Public product\n",
        "scripts/internal.py": b"strant.casa\n",
        "tests/test_public_snapshot.py": b"METROPLEX\n",
        "_IMAGES/private.txt": b"private details\n",
        ".env": b"secret=private\n",
        ".gitea/workflows/internal.yml": b"internal publication workflow\n",
    }
    values.update(extra or {})
    for name, data in values.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Synthetic fixture",
        ],
        check=True,
    )
    return repo


def test_export_only_public_files_no_git_history(tmp_path):
    repo = committed(tmp_path)
    # Uncommitted state must not affect publication of the chosen revision.
    (repo / "README.md").write_text("private uncommitted detail strant.casa")
    destination = tmp_path / "public"
    assert export(repo, "HEAD", destination) == 3
    assert (destination / "README.md").read_text() == "Public product documentation\n"
    assert not (destination / ".git").exists()
    assert not (destination / "scripts").exists()
    assert not (destination / "tests/test_public_snapshot.py").exists()
    assert not (destination / ".env").exists()


@pytest.mark.parametrize("data", [b"server METROPLEX", b"https://x.strant.casa", b"192.168.169.10"])
def test_private_reference_blocks_export_before_writes(tmp_path, data):
    repo = committed(tmp_path, {"docs/leak.md": data})
    destination = tmp_path / "public"
    with pytest.raises(ValueError, match="private deployment reference"):
        export(repo, "HEAD", destination)
    assert not destination.exists()


def test_secret_marker_blocks_export(tmp_path):
    repo = committed(tmp_path, {"docs/leak.md": b"-----BEGIN PRIVATE KEY-----"})
    with pytest.raises(ValueError, match="possible secret"):
        export(repo, "HEAD", tmp_path / "public")


def test_export_refuses_symlink(tmp_path):
    repo = committed(tmp_path)
    (repo / "app/link.py").symlink_to("/etc/passwd")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Synthetic link",
        ],
        check=True,
    )
    with pytest.raises(ValueError, match="links and special"):
        export(repo, "HEAD", tmp_path / "public")


def test_destination_must_be_empty(tmp_path):
    repo = committed(tmp_path)
    destination = tmp_path / "public"
    destination.mkdir()
    (destination / "keep").write_text("keep")
    with pytest.raises(ValueError, match="empty destination"):
        export(repo, "HEAD", destination)
    assert (destination / "keep").read_text() == "keep"


def test_allowlist_rejects_private_roots_and_paths():
    for name in (
        ".git/config",
        "../README.md",
        "/README.md",
        "scripts/publish_snapshot.sh",
        "tests/test_public_snapshot.py",
        "_CONSULTANT/report.md",
        ".env",
    ):
        assert not allowed(name)
    for name in ("README.md", "app/static/icon.png", "docs/screenshots/accounts.png"):
        assert allowed(name)


def test_whole_publisher_appends_clean_snapshot_and_is_idempotent(tmp_path):
    import os
    from pathlib import Path

    repo = committed(tmp_path)
    (repo / "scripts").mkdir(exist_ok=True)
    project = Path(__file__).resolve().parents[1]
    for name in ("public_snapshot.py", "publish_snapshot.sh"):
        (repo / "scripts" / name).write_bytes((project / "scripts" / name).read_bytes())
    subprocess.run(["git", "-C", str(repo), "add", "scripts"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Private canonical history",
        ],
        check=True,
    )
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "-qb", "main", str(seed)], check=True)
    (seed / "LICENSE").write_bytes(b"Synthetic license\n")
    (seed / "README.md").write_text("Public seed\n")
    subprocess.run(["git", "-C", str(seed), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(seed),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Public seed",
        ],
        check=True,
    )
    target = repo / ".offline-target.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(target)], check=True)
    env = {
        **os.environ,
        "PUBLIC_GITHUB_TOKEN": "synthetic-unused-offline-token",
        "PUBLICATION_SCRATCH": ".publication-test",
        "PUBLICATION_OFFLINE_TEST_TARGET": str(target),
    }
    for expected in ("Published clean public snapshot", "Public snapshot already current"):
        result = subprocess.run(
            ["bash", "scripts/publish_snapshot.sh"],
            cwd=repo,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )
        assert expected in result.stdout
        assert "synthetic-unused-offline-token" not in result.stdout + result.stderr
        assert not (repo / ".publication-test").exists()
    assert (
        subprocess.check_output(
            ["git", "--git-dir", str(target), "rev-list", "--count", "main"]
        ).strip()
        == b"2"
    )
    names = subprocess.check_output(
        ["git", "--git-dir", str(target), "ls-tree", "-r", "--name-only", "main"]
    ).decode()
    assert ".env" not in names and "scripts/" not in names and "_IMAGES" not in names
    messages = subprocess.check_output(
        ["git", "--git-dir", str(target), "log", "--format=%s", "main"]
    ).decode()
    assert "Private canonical history" not in messages
