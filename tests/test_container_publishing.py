"""Offline publishing failures; fake Docker and git only, never a registry."""

import importlib.util
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("image_smoke", ROOT / "tests/container_image_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_hash_timeout_cleans_both_container_names(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "__file__", str(tmp_path / "tests/container_image_smoke.py"))
    calls = []

    def docker(*args, **kwargs):
        calls.append(args)
        if args[0] == "run":
            raise smoke.SmokeFailure("hash timeout")
        return ""

    monkeypatch.setattr(smoke, "docker", docker)
    with pytest.raises(smoke.SmokeFailure, match="hash timeout"):
        smoke.smoke("synthetic-image")
    names = [args[2] for args in calls if args[:2] == ("rm", "-f")]
    assert len(names) == 2
    assert names[1] == names[0] + "-hash"
    assert not list((tmp_path / ".scratch").iterdir())


def test_cleanup_attempts_both_names_when_first_removal_fails(monkeypatch):
    calls = []

    def docker(*args, **kwargs):
        calls.append(args)
        if args[2] == "synthetic":
            raise smoke.SmokeFailure("cleanup unavailable")

    monkeypatch.setattr(smoke, "docker", docker)
    with pytest.raises(smoke.SmokeFailure, match="cleanup"):
        smoke.remove_containers("synthetic", "synthetic-hash")
    assert calls == [("rm", "-f", "synthetic"), ("rm", "-f", "synthetic-hash")]


def test_docker_remove_missing_is_not_a_failure(monkeypatch):
    result = subprocess.CompletedProcess([], 1, "", "Error response from daemon: No such container: synthetic")
    monkeypatch.setattr(smoke.subprocess, "run", Mock(return_value=result))
    assert smoke.docker("rm", "-f", "synthetic") == ""


def test_other_remove_errors_still_fail_without_echo(monkeypatch):
    result = subprocess.CompletedProcess([], 1, "", "synthetic-private-marker daemon unavailable")
    monkeypatch.setattr(smoke.subprocess, "run", Mock(return_value=result))
    with pytest.raises(smoke.SmokeFailure) as error:
        smoke.docker("rm", "-f", "synthetic")
    assert "synthetic-private-marker" not in str(error.value)


def test_timeout_is_sanitized(monkeypatch):
    failure = subprocess.TimeoutExpired([], 1, output="synthetic-private-marker")
    monkeypatch.setattr(smoke.subprocess, "run", Mock(side_effect=failure))
    with pytest.raises(smoke.SmokeFailure) as error:
        smoke.docker("run", "synthetic")
    assert "synthetic-private-marker" not in str(error.value)


def publish_step():
    workflow = (ROOT / ".github/workflows/container.yml").read_text()
    block = workflow.split("- name: Publish the exact tested image\n", 1)[1].split("run: |\n", 1)[1]
    return "\n".join(line[10:] for line in block.splitlines())


@pytest.mark.parametrize("stale,fail_latest", [(False, False), (True, False), (False, True)])
def test_registry_promotion_paths(tmp_path, stale, fail_latest):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "docker").write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n'
        'if [ "$1" = push ] && [ "${2##*:}" = latest ] && [ "$FAIL_LATEST" = 1 ]; then exit 1; fi\n'
    )
    (binaries / "git").write_text('#!/bin/sh\nprintf "%s\\trefs/heads/main\\n" "$MAIN_SHA"\n')
    for binary in binaries.iterdir():
        binary.chmod(0o700)
    calls = tmp_path / "calls"
    summary = tmp_path / "summary"
    sha = "a" * 40
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", publish_step()], text=True, capture_output=True,
        env={**os.environ, "PATH": str(binaries) + ":" + os.environ["PATH"],
             "CALLS": str(calls), "GITHUB_STEP_SUMMARY": str(summary),
             "GITHUB_REPOSITORY": "example/project", "GITHUB_SHA": sha,
             "MAIN_SHA": "b" * 40 if stale else sha,
             "IMAGE_REPOSITORY": "ghcr.io/example/project", "FAIL_LATEST": str(int(fail_latest))},
        timeout=5,
    )
    commands = calls.read_text().splitlines()
    assert commands[0] == "push ghcr.io/example/project:sha-" + sha
    report = summary.read_text()
    assert "Revision image uploaded" in report
    if stale:
        assert len(commands) == 1
        assert "Latest unchanged" in report
    else:
        assert commands[-1] == "push ghcr.io/example/project:latest"
        assert ("Latest upload failed" if fail_latest else "Latest uploaded") in report
    assert result.returncode == int(fail_latest)
