"""Offline regression checks from the single post-handoff review pass."""

from unittest.mock import patch

import pytest
from conftest import hash_line, login
from test_notes_presence import NOW, connected

from app.passwd import CriticalError
from app.presence import PresenceTracker

BASE = "https://manager.test"


def test_anonymous_login_prunes_expired_session_capacity(client, web):
    web.extensions["valid_sessions"].update({str(i): 1000 for i in range(64)})
    with patch("app.auth.time.monotonic", return_value=2000):
        login(client)
    assert len(web.extensions["valid_sessions"]) == 1


def test_replacing_own_session_works_at_capacity(client, web):
    headers = login(client)
    with client.session_transaction(base_url=BASE) as session:
        previous = session["sid"]
    registry = web.extensions["valid_sessions"]
    expiry = registry[previous]
    registry.update({str(i): expiry for i in range(63)})
    response = client.post(
        "/auth/login",
        base_url=BASE,
        json={"username": "admin", "password": "synthetic-admin-password"},
        headers=headers,
    )
    assert response.status_code == 200
    assert len(registry) == 64 and previous not in registry


def test_real_active_capacity_still_refuses_new_login(client, web):
    web.extensions["valid_sessions"].update({str(i): 3000 for i in range(64)})
    with patch("app.auth.time.monotonic", return_value=2000):
        csrf = client.get("/auth/csrf", base_url=BASE).json["csrf_token"]
        response = client.post(
            "/auth/login",
            base_url=BASE,
            json={"username": "admin", "password": "synthetic-admin-password"},
            headers={"Origin": BASE, "X-CSRF-Token": csrf},
        )
    assert response.status_code == 429
    assert len(web.extensions["valid_sessions"]) == 64


@pytest.mark.parametrize("gap", ["skipped", "missing", "overflow"])
def test_log_gap_resets_reconnect_evidence(tmp_path, gap):
    path = tmp_path / "log"
    path.write_text(
        connected(NOW)
        + f"{NOW + 1}: Client client disconnected.\n"
        + connected(NOW + 2)
        + f"{NOW + 3}: Client client disconnected.\n"
    )
    tracker = PresenceTracker(
        path,
        max_scan=1000,
        max_sessions=1,
        reconnect_count=2,
        reconnect_window=100,
        clock=lambda: NOW + 20,
    )
    tracker.rows(["device"])
    assert list(tracker.reconnections["device"]) == [NOW + 2]
    if gap == "skipped":
        with path.open("a") as stream:
            stream.write("gap\n" * 300)
    elif gap == "missing":
        path.rename(tmp_path / "unavailable")
        assert tracker.rows(["device"])["device"]["status"] == "unknown"
        (tmp_path / "unavailable").rename(path)
    else:
        with path.open("a") as stream:
            stream.write(connected(NOW + 4, "one", "other") + connected(NOW + 5, "two", "other"))
        tracker.rows(["device", "other"])
    with path.open("a") as stream:
        stream.write(connected(NOW + 6) + f"{NOW + 7}: Client client disconnected.\n")
    row = tracker.rows(["device"])["device"]
    assert row["status"] == "disconnected"
    assert row["log_incomplete"]
    assert not tracker.reconnections.get("device")


@pytest.mark.parametrize("change", ["content", "metadata"])
def test_external_edit_during_rollback_reload_latches(rig, change):
    signals = []
    external = hash_line("outsider", 9)

    def reload():
        signals.append(True)
        if len(signals) == 2:
            if change == "content":
                rig["path"].write_bytes(external)
            else:
                rig["path"].chmod(0o640)

    rig["store"].reload = reload
    rig["store"].verifier = lambda *_: False
    with pytest.raises(CriticalError):
        rig["store"].mutate("change", "device", "synthetic-long-password")
    assert rig["store"].blocked()
    assert (rig["store"].backups / "TRANSACTION_PENDING").exists()
    assert (rig["store"].backups / "RECOVERY_REQUIRED").exists()
    if change == "content":
        assert rig["path"].read_bytes() == external
    else:
        assert rig["path"].stat().st_mode & 0o777 == 0o640


def test_external_edit_during_recovery_stage_not_overwritten(rig):
    original_stage = rig["store"]._stage
    calls = []
    external = hash_line("outsider", 9)

    def stage(data, original):
        calls.append(True)
        result = original_stage(data, original)
        if len(calls) == 2:
            rig["path"].write_bytes(external)
        return result

    rig["store"]._stage = stage
    rig["store"].verifier = lambda *_: False
    with pytest.raises(CriticalError):
        rig["store"].mutate("change", "device", "synthetic-long-password")
    assert rig["path"].read_bytes() == external and rig["store"].blocked()
    assert not list(rig["path"].parent.glob(".mqtt-manager-stage-*"))
