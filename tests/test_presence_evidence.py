"""Row-level evidence warnings must distinguish history from fresh connections."""

from test_notes_presence import NOW, connected, tracker


def test_fresh_connection_clears_only_its_row_warning(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text("unavailable earlier history\n" * 100 + connected(NOW))
    presence = tracker(path, max_scan=200)
    rows = presence.rows(["device", "unseen"])
    assert presence.incomplete  # Global history is still incomplete.
    assert rows["device"]["log_incomplete"] is True
    assert rows["device"]["status"] == "connected"
    assert rows["device"]["presence_uncertain"] is False
    assert rows["unseen"]["status"] == "unknown"
    assert rows["unseen"]["presence_uncertain"] is True


def test_retained_last_seen_does_not_clear_warning_after_rotation(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text(connected(NOW))
    presence = tracker(path)
    before = presence.rows(["device"])["device"]
    assert before["presence_uncertain"] is False
    path.rename(tmp_path / "broker.log.1")
    path.write_text(f"{NOW + 1}: unrelated log event\n")
    after = presence.rows(["device"])["device"]
    assert after["last_seen"] == before["last_seen"]
    assert after["status"] == "unknown"
    assert after["presence_uncertain"] is True
    with path.open("a") as stream:
        stream.write(connected(NOW + 2))
    assert presence.rows(["device"])["device"]["presence_uncertain"] is False


def test_missing_log_invalidates_previously_fresh_evidence(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text(connected(NOW))
    presence = tracker(path)
    assert presence.rows(["device"])["device"]["presence_uncertain"] is False
    path.unlink()
    row = presence.rows(["device"])["device"]
    assert row["last_seen"] is not None
    assert row["status"] == "unknown"
    assert row["presence_uncertain"] is True


def test_incomplete_history_cannot_prove_all_shared_sessions_disconnected(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text(connected(NOW, "one") + connected(NOW + 1, "two"))
    presence = tracker(path)
    assert presence.rows(["device"])["device"]["presence_uncertain"] is False
    with path.open("a") as stream:
        stream.write(f"{NOW + 2}: Client one disconnected.\n")
    assert presence.rows(["device"])["device"]["presence_uncertain"] is False
    with path.open("a") as stream:
        stream.write(f"{NOW + 3}: Client two disconnected.\n")
    row = presence.rows(["device"])["device"]
    assert row["status"] == "disconnected"
    assert row["last_seen"] is not None
    assert row["presence_uncertain"] is True


def test_complete_restart_history_needs_no_warning_on_disconnect(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text(
        f"{NOW}: mosquitto version 2.1.2 starting\n"
        + connected(NOW + 1)
        + f"{NOW + 2}: Client client disconnected.\n"
    )
    row = tracker(path).rows(["device"])["device"]
    assert row["status"] == "disconnected"
    assert row["presence_uncertain"] is False


def test_oversized_line_requires_new_connection_evidence(tmp_path):
    path = tmp_path / "broker.log"
    path.write_text(connected(NOW))
    presence = tracker(path)
    assert presence.rows(["device"])["device"]["presence_uncertain"] is False
    with path.open("a") as stream:
        stream.write("x" * 4097 + "\n")
    row = presence.rows(["device"])["device"]
    assert row["status"] == "unknown"
    assert row["presence_uncertain"] is True
    assert row["last_seen"] is not None
    with path.open("a") as stream:
        stream.write(connected(NOW + 1))
    assert presence.rows(["device"])["device"]["presence_uncertain"] is False
