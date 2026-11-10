import os
import threading
import time
from unittest.mock import patch

import pytest
from conftest import hash_line, login
from test_notes_presence import NOW, connected

from app import unverified_client
from app.passwd import AccountError, CriticalError, snapshot
from app.presence import PresenceTracker
from app.tasks import OperationManager


def test_default_verifier_refuses_before_write(rig):
    rig["store"].verifier = unverified_client
    with pytest.raises(AccountError) as error:
        rig["store"].mutate("change", "device", "synthetic-long-password")
    assert error.value.code == "verification_unavailable"
    assert not rig["command"].calls and not rig["signals"]
    assert not rig["store"].backups.exists()


def test_external_change_during_verify_latches_without_overwriting(rig):
    data = hash_line("outsider", 9)

    def verify(*_):
        rig["path"].write_bytes(data)
        return True

    rig["store"].verifier = verify
    with pytest.raises(CriticalError):
        rig["store"].mutate("change", "device", "synthetic-long-password")
    assert rig["path"].read_bytes() == data and rig["store"].blocked()


def test_special_files_do_not_block(tmp_path):
    path = tmp_path / "fifo"
    os.mkfifo(path)
    start = time.monotonic()
    with pytest.raises(AccountError):
        snapshot(path)
    row = PresenceTracker(path).rows(["device"])["device"]
    assert row["status"] == "unknown" and time.monotonic() - start < 1


def test_unicode_csrf_and_wrong_admin_clean_refusal(client):
    headers = login(client)
    headers["X-CSRF-Token"] = "é"
    assert (
        client.post(
            "/api/passwords/generate", base_url="https://manager.test", headers=headers
        ).status_code
        == 403
    )
    headers = login(client)
    response = client.post(
        "/auth/login",
        base_url="https://manager.test",
        headers=headers,
        json={"username": "é", "password": "synthetic-admin-password"},
    )
    assert response.status_code == 401


def test_worker_system_exit_no_traceback(capsys):
    manager = OperationManager()

    def job(_):
        raise SystemExit("private-command-argument")

    task = manager.submit("owner", job)
    for _ in range(100):
        if manager.active is None:
            break
        time.sleep(0.01)
    assert manager.get(task, "owner")["status"] == "failed"
    assert "private" not in capsys.readouterr().err


def test_failed_thread_start_cleans_active_slot():
    manager = OperationManager()
    with patch.object(threading.Thread, "start", side_effect=RuntimeError("private")):
        with pytest.raises(AccountError):
            manager.submit("owner", lambda _: {})
    assert manager.active is None and not manager.results


def test_client_id_takeover_keeps_other_shared_connection(tmp_path):
    path = tmp_path / "log"
    path.write_text(
        connected(NOW, "one", "device")
        + connected(NOW + 1, "two", "device")
        + connected(NOW + 2, "one", "other")
    )
    tracker = PresenceTracker(path, clock=lambda: NOW + 3)
    rows = tracker.rows(["device", "other"])
    assert rows["device"]["connections"] == 1 and rows["device"]["status"] == "connected"
    assert rows["other"]["connections"] == 1


def test_iso_timestamps_are_observed_not_clock(tmp_path):
    path = tmp_path / "log"
    path.write_text(connected(NOW).replace(str(NOW), "2026-11-10T10:00:00Z"))
    tracker = PresenceTracker(path, clock=lambda: 2000000000)
    row = tracker.rows(["device"])["device"]
    assert row["last_seen"] == "2026-11-10T10:00:00+00:00"
    assert "21:00:00 AEDT" in row["last_seen_local"]
