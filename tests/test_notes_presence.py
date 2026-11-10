import threading
from datetime import datetime, timezone

import pytest

from app.notes import NotesStore
from app.passwd import AccountError
from app.presence import PresenceTracker

NOW = 1794300000


def connected(t, client="client", username="device"):
    return (
        f"{t}: New client connected from 10.0.0.1:1234 as {client} (p2, c1, k60, u'{username}').\n"
    )


def test_notes_atomic_concurrent_and_private(tmp_path):
    path = tmp_path / "notes.json"
    notes = NotesStore(path)
    assert notes.read() == {}
    errors = []

    def set_note(name):
        try:
            notes.set(name, "Synthetic note " + name)
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=set_note, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(1)
    assert not errors and set(notes.read()) == {"a", "b"}
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".notes-stage-*"))
    notes.set("a", "")
    assert set(notes.read()) == {"b"}


@pytest.mark.parametrize(
    "content", ["[]", '{"a":1}', '{"a":"one","a":"two"}', "bad", '{"bad:name":"hello"}']
)
def test_notes_malformed(tmp_path, content):
    path = tmp_path / "notes.json"
    path.write_text(content)
    path.chmod(0o600)
    with pytest.raises(AccountError):
        NotesStore(path).read()


def test_notes_permission_and_size(tmp_path):
    path = tmp_path / "notes.json"
    path.write_text("{}")
    with pytest.raises(AccountError):
        NotesStore(path).read()
    path.chmod(0o600)
    with pytest.raises(AccountError):
        NotesStore(path).set("device", "x" * 2001)


def tracker(path, **kwargs):
    return PresenceTracker(path, clock=lambda: NOW + 1000, **kwargs)


def test_multiple_sessions_shared_user(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text(connected(NOW, "one") + connected(NOW + 1, "two"))
    presence = tracker(path)
    row = presence.rows(["device"])["device"]
    assert row["status"] == "connected" and row["connections"] == 2
    with path.open("a") as stream:
        stream.write(f"{NOW + 2}: Client one disconnected.\n")
    row = presence.rows(["device"])["device"]
    assert row["connections"] == 1 and row["status"] == "connected"
    with path.open("a") as stream:
        stream.write(f"{NOW + 3}: Client two closed its connection.\n")
    row = presence.rows(["device"])["device"]
    assert row["status"] == "disconnected" and row["connections"] == 0
    assert row["last_seen"] == datetime.fromtimestamp(NOW + 3, timezone.utc).isoformat()
    assert "AEDT" in row["last_seen_local"]


@pytest.mark.parametrize(
    "ending",
    [
        "disconnected.",
        "disconnected due to protocol error.",
        "closed its connection.",
        "has exceeded timeout, disconnecting.",
        "already connected, closing old connection.",
        "has been disconnected by administrative action.",
    ],
)
@pytest.mark.parametrize("address", ["", " [10.0.0.1:1234]", " [2001:db8::1:1234]"])
def test_disconnect_variants(tmp_path, ending, address):
    path = tmp_path / "broker.log"
    path.write_text(connected(NOW) + f"{NOW + 1}: Client client{address} {ending}\n")
    row = tracker(path).rows(["device"])["device"]
    assert row["status"] == "disconnected" and row["connections"] == 0
    assert row["last_seen"] == datetime.fromtimestamp(NOW + 1, timezone.utc).isoformat()


def test_local_iso_address_disconnect_preserves_other_session(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text(
        "2026-11-10T21:00:00: New client connected from 10.0.0.1:1234 as one "
        "(p4, c1, k60, u'device').\n"
        "2026-11-10T21:00:01: New client connected from 10.0.0.2:1235 as two "
        "(p4, c1, k60, u'device').\n"
        "2026-11-10T21:00:02: Client one [10.0.0.1:1234] disconnected.\n"
    )
    presence = PresenceTracker(path, clock=lambda: 2000000000)
    row = presence.rows(["device"])["device"]
    assert row["status"] == "connected" and row["connections"] == 1
    with path.open("a") as stream:
        stream.write("2026-11-10T21:00:03: Client two [10.0.0.2:1235] disconnected.\n")
    row = presence.rows(["device"])["device"]
    assert row["status"] == "disconnected" and row["connections"] == 0
    assert row["last_seen"] == "2026-11-10T10:00:03+00:00"
    assert "21:00:03 AEDT" in row["last_seen_local"]


def test_rotation_unknown_then_new_evidence(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text(connected(NOW))
    presence = tracker(path)
    assert presence.rows(["device"])["device"]["status"] == "connected"
    path.rename(tmp_path / "broker.log.1")
    path.write_text(f"{NOW + 2}: Client client disconnected.\n")
    row = presence.rows(["device"])["device"]
    assert row["status"] == "unknown" and row["last_seen"] is not None
    with path.open("a") as stream:
        stream.write(connected(NOW + 3))
    assert presence.rows(["device"])["device"]["status"] == "connected"


def test_copytruncate_regrowth_and_restart(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text(connected(NOW))
    presence = tracker(path)
    presence.rows(["device"])
    path.write_text(f"{NOW + 1}: mosquitto version 2.1.2 starting\n" + "#" * 200 + "\n")
    row = presence.rows(["device"])["device"]
    assert row["status"] == "unknown" and row["connections"] == 0
    with path.open("a") as stream:
        stream.write(connected(NOW + 2) + f"{NOW + 3}: mosquitto version 2.1.2 terminating\n")
    assert presence.rows(["device"])["device"]["status"] == "disconnected"


def test_partial_line_and_no_invented_activity(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text(connected(NOW).rstrip())
    presence = tracker(path)
    assert presence.rows(["device"])["device"]["status"] == "unknown"
    with path.open("a") as stream:
        stream.write("\n")
    first = presence.rows(["device"])["device"]
    assert first["status"] == "connected"
    assert presence.rows(["device"])["device"]["last_seen"] == first["last_seen"]


def test_missing_log_unknown(tmp_path):
    assert tracker(tmp_path / "missing").rows(["never"])["never"]["status"] == "unknown"


def test_reconnect_is_opt_in(tmp_path):
    path = tmp_path / "broker.log"
    text = connected(NOW)
    for i in range(1, 4):
        text += f"{NOW + i * 2}: Client client disconnected.\n" + connected(NOW + i * 2 + 1)
    text += f"{NOW + 9}: Client client disconnected.\n"
    path.write_text(text)
    assert tracker(path).rows(["device"])["device"]["status"] == "disconnected"
    presence = PresenceTracker(
        path, reconnect_count=3, reconnect_window=100, clock=lambda: NOW + 10
    )
    assert presence.rows(["device"])["device"]["status"] == "reconnecting"


def test_bounded_log_memory_and_scan(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text(
        "garbage\n" * 200 + "".join(connected(NOW + i, str(i), f"u{i}") for i in range(12))
    )
    presence = tracker(path, max_scan=400, max_sessions=2, max_accounts=3)
    presence.rows(["u1", "u11"])
    assert (
        len(presence.sessions) <= 2
        and len(presence.observed) <= 3
        and presence.offset <= path.stat().st_size
    )
    assert presence.incomplete
