import os
from unittest.mock import patch

import pytest
from conftest import login
from test_notes_presence import NOW, connected

from app.passwd import AccountError, CriticalError, PasswordCommand
from app.presence import PresenceTracker


def test_pending_interrupted_transaction_blocks_new_instance(rig):
    rig["store"].backups.mkdir(mode=0o700)
    (rig["store"].backups / "TRANSACTION_PENDING").write_text("synthetic interruption")
    assert rig["store"].blocked()
    with pytest.raises(CriticalError):
        rig["store"].mutate("delete", "device")
    assert rig["path"].read_bytes() == rig["original"]


def test_journal_is_present_during_reload_cleared_after_success(rig):
    seen = []
    rig["store"].reload = lambda: seen.append(
        (rig["store"].backups / "TRANSACTION_PENDING").exists()
    )
    rig["store"].mutate("delete", "device")
    assert seen == [True] and not rig["store"].blocked()


def test_replace_fails_before_publication_does_not_reload(rig):
    with patch("app.passwd.os.replace", side_effect=OSError("synthetic disk error")):
        with pytest.raises(AccountError, match="Nothing was applied"):
            rig["store"].mutate("delete", "device")
    assert (
        rig["path"].read_bytes() == rig["original"]
        and not rig["signals"]
        and not rig["store"].blocked()
    )


def test_fsync_failure_after_replace_restores(rig):
    from app import passwd

    sync = passwd.fsync_directory
    failures = [0]

    def fail(directory):
        if directory == rig["path"].parent and failures[0] == 0:
            failures[0] += 1
            raise OSError("synthetic fsync error")
        sync(directory)

    with patch("app.passwd.fsync_directory", side_effect=fail):
        with pytest.raises(AccountError, match="restored"):
            rig["store"].mutate("delete", "device")
    assert rig["path"].read_bytes() == rig["original"] and not rig["store"].blocked()


def test_rollback_replace_failure_critical(rig):
    replace = os.replace
    count = [0]
    rig["store"].verifier = lambda *_: False

    def fail(src, dst):
        count[0] += 1
        if count[0] == 2:
            raise OSError("synthetic rollback failure")
        return replace(src, dst)

    with patch("app.passwd.os.replace", side_effect=fail):
        with pytest.raises(CriticalError):
            rig["store"].mutate("change", "device", "synthetic-long-password")
    assert rig["store"].blocked()


def test_640_preserved(rig):
    rig["path"].chmod(0o640)
    rig["store"].mutate("delete", "device")
    assert rig["path"].stat().st_mode & 0o777 == 0o640


def test_command_timeout_redacted(rig):
    import subprocess

    with patch("app.passwd.subprocess.run", side_effect=subprocess.TimeoutExpired(["secret"], 1)):
        with pytest.raises(AccountError) as error:
            PasswordCommand(stdin_verified=True)(
                rig["path"], "change", "device", "synthetic-long-password"
            )
    assert "secret" not in str(error.value)


def test_logout_revokes_copied_cookie(client, web):
    headers = login(client)
    copied = client.get_cookie("mqtt_admin", domain="manager.test").value
    assert (
        client.post("/auth/logout", base_url="https://manager.test", headers=headers).status_code
        == 200
    )
    attacker = web.test_client()
    attacker.set_cookie("mqtt_admin", copied, domain="manager.test")
    assert attacker.get("/api/accounts", base_url="https://manager.test").status_code == 401


def test_check_connections_not_presence(tmp_path):
    path = tmp_path / "log"
    path.write_text(connected(NOW, "mqtt-manager-check-synthetic"))
    presence = PresenceTracker(path, clock=lambda: NOW + 1)
    row = presence.rows(["device"])["device"]
    assert row["status"] == "unknown" and row["last_seen"] is None
