import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.passwd import AccountError
from app.verifier import FreshConnectVerifier


@pytest.mark.parametrize(
    "password",
    [
        "alpha beta gamma",
        " leading-space-pass",
        "trailing-space-pass ",
        'has"quote\\slash#pass',
        "éclair-雪-password",
        "            ",
    ],
)
def test_private_options_exact_and_cleanup(password):
    paths = []

    def run(args, **kwargs):
        path = Path(args[args.index("-o") + 1])
        paths.append(path)
        assert path.stat().st_mode & 0o777 == 0o600
        assert password not in repr(args)
        content = path.read_text()
        assert content.startswith("-u device\n-P ")
        assert kwargs["shell"] is False
        assert args[args.index("-i") + 1].startswith("mqtt-manager-check-")
        if len(paths) == 1:
            return subprocess.CompletedProcess(args, 5, b"")
        assert content == "-u device\n-P " + password + "\n"
        return subprocess.CompletedProcess(args, 0, b"Client check received CONNACK (0)\n")

    with patch("app.verifier.subprocess.run", side_effect=run):
        assert FreshConnectVerifier("mosquitto")("device", password)
    assert all(not path.exists() for path in paths)


def test_anonymous_or_fallback_listener_refused():
    with patch(
        "app.verifier.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, b"received CONNACK (0)\n"),
    ):
        with pytest.raises(AccountError, match="incorrect password"):
            FreshConnectVerifier("mosquitto")("device", "synthetic-long-password")


def test_client_failure_private():
    with patch("app.verifier.subprocess.run", side_effect=OSError("private secret")):
        with pytest.raises(AccountError) as error:
            FreshConnectVerifier("mosquitto")("device", "synthetic-long-password")
    assert "secret" not in str(error.value)


def test_timeout_false_and_no_generic_success():
    verifier = FreshConnectVerifier("mosquitto", deadline=1)
    with patch("app.verifier.subprocess.run", side_effect=subprocess.TimeoutExpired(["secret"], 1)):
        assert verifier._attempt("device", "synthetic-long-password", 0.01) is False
    with patch(
        "app.verifier.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, b"generic success\n"),
    ):
        assert verifier._attempt("device", "synthetic-long-password", 0.01) is False


def test_public_shell_no_account_data(client):
    response = client.get("/", base_url="https://manager.test")
    assert response.status_code == 200
    assert b"accounts.js" in response.data and b"remove-dialog" in response.data
    assert b"synthetic-admin-password" not in response.data
    assert client.get("/api/accounts", base_url="https://manager.test").status_code == 401


def test_public_shell_keeps_observation_guidance_without_log_warning(client):
    response = client.get("/", base_url="https://manager.test")
    assert response.status_code == 200
    assert b"Connection status is estimated from broker logs, not a live session list." in response.data
    assert b"Last seen means the last logged connection event, not the last message." in response.data
    assert b"Incomplete logs are shown" not in response.data
    assert b"Incomplete log evidence" not in response.data


def test_identity_wrong_command_refused(tmp_path):
    from app.passwd import BrokerReloader

    root = tmp_path / "1"
    root.mkdir()
    (root / "comm").write_text("mosquitto\n")
    (root / "cmdline").write_bytes(b"/usr/bin/python\0")
    (root / "status").write_text("Uid:\t" + "\t".join([str(os.geteuid())] * 4))
    signals = []
    with pytest.raises(AccountError):
        BrokerReloader(
            broker_uid=os.geteuid(), proc=tmp_path, signaler=lambda *x: signals.append(x)
        )()
    assert signals == []


def test_branding_assets_and_safe_repo_link(client):
    response = client.get("/", base_url="https://manager.test")
    assert b"favicon.ico" in response.data and b"favicon-32.png" in response.data
    assert b"https://github.com/loryanstrant/MQTT-User-Manager" in response.data
    assert b'rel="noopener noreferrer"' in response.data
    assert b"GitHub<span" in response.data
    for filename, magic in [
        ("icon.png", b"\x89PNG"),
        ("favicon-32.png", b"\x89PNG"),
        ("github-mark.png", b"\x89PNG"),
        ("favicon.ico", b"\x00\x00\x01\x00"),
    ]:
        asset = client.get("/static/" + filename, base_url="https://manager.test")
        assert asset.status_code == 200 and asset.data.startswith(magic)
