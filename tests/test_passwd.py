import os
import threading
import time
from unittest.mock import patch

import pytest
from conftest import hash_line

from app.passwd import (
    AccountError,
    BrokerReloader,
    CriticalError,
    PasswordCommand,
    file_lock,
    parse_password_file,
    snapshot,
    validate_password,
    validate_username,
)


@pytest.mark.parametrize(
    "action,name", [("add", "new"), ("change", "device"), ("delete", "device")]
)
def test_mutation_preserves_others_and_backup(rig, action, name):
    store = rig["store"]
    before = parse_password_file(rig["original"])
    result = store.mutate(action, name, "synthetic-long-password" if action != "delete" else None)
    after = parse_password_file(rig["path"].read_bytes())
    assert after["homeassistant"] == before["homeassistant"]
    assert result["status"] == "succeeded"
    assert rig["signals"] == [True]
    assert rig["verifications"] == ([] if action == "delete" else [name])
    assert len(after) == len(before) + (1 if action == "add" else -1 if action == "delete" else 0)
    backups = list(store.backups.glob("backup-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == rig["original"]
    assert backups[0].stat().st_mode & 0o777 == 0o600
    assert store.backups.stat().st_mode & 0o777 == 0o700
    assert rig["path"].stat().st_mode & 0o777 == 0o600
    assert not list(rig["path"].parent.glob(".mqtt-manager-stage-*"))


@pytest.mark.parametrize(
    "data",
    [
        b"broken\n",
        b"x:garbage\n",
        hash_line("a") * 2,
        hash_line("a").rstrip(),
        b"a:b:c\n",
        b"\n",
        b"-option:$7$101$eA==$eA==\n",
        b"a:$7$0$eA==$eA==\n",
        b"a:$7$10$eA==$invalid\n",
    ],
)
def test_malformed_refused(data):
    with pytest.raises(AccountError):
        parse_password_file(data)


@pytest.mark.parametrize("username", ["-b", "a:b", "a\nx", "a b", "", "a" * 129, "a/../x", "é"])
def test_unsafe_names(username):
    with pytest.raises(AccountError):
        validate_username(username)


@pytest.mark.parametrize("password", ["short", "x" * 257, "x" * 12 + "\n", "x" * 12 + "\x00", None])
def test_unsafe_password(password):
    with pytest.raises(AccountError):
        validate_password(password)


@pytest.mark.parametrize(
    "action,name,code",
    [
        ("add", "device", "exists"),
        ("delete", "homeassistant", "protected"),
        ("change", "absent", "missing"),
        ("wrong", "device", "invalid_action"),
    ],
)
def test_invalid_actions_no_changes(rig, action, name, code):
    with pytest.raises(AccountError) as error:
        rig["store"].mutate(action, name, "synthetic-long-password")
    assert error.value.code == code
    assert not rig["command"].calls and not rig["signals"]
    assert rig["path"].read_bytes() == rig["original"]


def test_unrelated_hash_change_refused(rig):
    rig["command"].hook = lambda path, *_: path.write_bytes(
        hash_line("homeassistant", 4) + hash_line("device", 11)
    )
    with pytest.raises(AccountError, match="more than"):
        rig["store"].mutate("change", "device", "synthetic-long-password")
    assert rig["path"].read_bytes() == rig["original"] and not rig["signals"]


@pytest.mark.parametrize(
    "replacement",
    [
        hash_line("device", 5),
        hash_line("homeassistant") + hash_line("device", 2),
        hash_line("homeassistant") + b"device:invalid\n",
    ],
)
def test_count_noop_corruption_refused(rig, replacement):
    rig["command"].hook = lambda path, *_: path.write_bytes(replacement)
    with pytest.raises(AccountError):
        rig["store"].mutate("change", "device", "synthetic-long-password")
    assert rig["path"].read_bytes() == rig["original"]


def test_external_change_preserved(rig):
    external = hash_line("homeassistant", 8) + hash_line("device", 9)
    rig["command"].hook = lambda *_: rig["path"].write_bytes(external)
    with pytest.raises(AccountError) as error:
        rig["store"].mutate("change", "device", "synthetic-long-password")
    assert error.value.code == "external_change"
    assert rig["path"].read_bytes() == external and not rig["signals"]


def test_command_failure_is_private(rig):
    def fail(*args):
        raise RuntimeError("secret password hash argument must not escape")

    rig["store"].command = fail
    with pytest.raises(AccountError) as error:
        rig["store"].mutate("change", "device", "synthetic-long-password")
    assert "secret" not in str(error.value)
    assert rig["path"].read_bytes() == rig["original"]


def test_failed_fresh_connection_rolls_back(rig):
    rig["store"].verifier = lambda *_: False
    with pytest.raises(AccountError, match="restored"):
        rig["store"].mutate("change", "device", "synthetic-long-password")
    assert rig["path"].read_bytes() == rig["original"]
    assert len(rig["signals"]) == 2
    assert not rig["store"].blocked()


def test_first_reload_failure_rolls_back(rig):
    calls = []

    def reload():
        calls.append(1)
        if len(calls) == 1:
            raise AccountError("reload_failed", "Broker reload failed.")

    rig["store"].reload = reload
    with pytest.raises(AccountError, match="restored"):
        rig["store"].mutate("delete", "device")
    assert rig["path"].read_bytes() == rig["original"] and len(calls) == 2


def test_rollback_reload_failure_persistent_critical(rig):
    def fail():
        raise RuntimeError("private")

    rig["store"].reload = fail
    with pytest.raises(CriticalError):
        rig["store"].mutate("change", "device", "synthetic-long-password")
    assert rig["store"].blocked()
    assert (rig["store"].backups / "RECOVERY_REQUIRED").exists()
    rig["store"].critical = False
    with pytest.raises(CriticalError):
        rig["store"].mutate("add", "new", "synthetic-long-password")


def test_external_change_after_publish_not_overwritten(rig):
    external = hash_line("outsider", 7)

    def fail():
        rig["path"].write_bytes(external)
        raise AccountError("reload_failed", "Failed")

    rig["store"].reload = fail
    with pytest.raises(CriticalError):
        rig["store"].mutate("delete", "device")
    assert rig["path"].read_bytes() == external


def test_permission_rejection(rig):
    rig["path"].chmod(0o644)
    with pytest.raises(AccountError, match="mode"):
        rig["store"].mutate("delete", "device")
    rig["path"].chmod(0o600)
    rig["store"].broker_uid += 1
    with pytest.raises(AccountError):
        rig["store"].mutate("delete", "device")


def test_symlink_and_hardlink_rejection(rig, tmp_path):
    link = tmp_path / "link"
    link.symlink_to(rig["path"])
    with pytest.raises(OSError):
        snapshot(link)
    link.unlink()
    os.link(rig["path"], link)
    with pytest.raises(AccountError):
        snapshot(link)


def test_unsafe_backup_directory(rig):
    rig["store"].backups.mkdir(mode=0o755)
    with pytest.raises(AccountError, match="unsafe"):
        rig["store"].mutate("delete", "device")
    assert rig["path"].read_bytes() == rig["original"]


def test_newest_twenty_backups(rig):
    for _ in range(23):
        rig["store"].mutate("change", "device", "synthetic-long-password")
    assert len(list(rig["store"].backups.glob("backup-*"))) == 20


def test_lock_timeout(tmp_path):
    with file_lock(tmp_path / "lock"):
        with pytest.raises(AccountError) as error:
            with file_lock(tmp_path / "lock", timeout=0.01):
                pass
    assert error.value.code == "busy"


def test_concurrent_mutations_serialized(rig):
    active, maximum = 0, 0
    guard = threading.Lock()
    command = rig["command"]

    def slow(*args):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        command(*args)
        with guard:
            active -= 1

    rig["store"].command = slow
    errors = []

    def worker(name):
        try:
            rig["store"].mutate("add", name, "synthetic-long-password")
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("one", "two")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2)
    assert not errors and maximum == 1
    assert set(rig["store"].accounts()) == {"one", "two", "homeassistant", "device"}


def test_adapter_never_password_in_argv(rig):
    command = PasswordCommand(stdin_verified=True)
    with patch("app.passwd.subprocess.run") as run:
        run.return_value.returncode = 0
        command(rig["path"], "change", "device", "synthetic-long-password")
        args, kwargs = run.call_args
        assert "synthetic-long-password" not in repr(args)
        assert (
            kwargs["shell"] is False
            and kwargs["input"] == b"synthetic-long-password\nsynthetic-long-password\n"
        )
    with pytest.raises(AccountError):
        PasswordCommand()(rig["path"], "change", "device", "synthetic-long-password")


def test_reloader_refuses_self_pid1_and_wrong_executable(tmp_path):
    signals = []
    root = tmp_path / "1"
    root.mkdir()
    (root / "exe").symlink_to("/usr/bin/python")
    (root / "comm").write_text("python\n")
    (root / "cmdline").write_bytes(b"/usr/bin/python\0")
    (root / "status").write_text(
        f"Uid:\t{os.geteuid()}\t{os.geteuid()}\t{os.geteuid()}\t{os.geteuid()}\n"
    )
    reload = BrokerReloader(
        broker_uid=os.geteuid(), proc=tmp_path, signaler=lambda *args: signals.append(args)
    )
    with pytest.raises(AccountError):
        reload()
    (root / "exe").unlink()
    (root / "exe").symlink_to("/usr/sbin/mosquitto")
    (root / "comm").write_text("mosquitto\n")
    (root / "cmdline").write_bytes(b"/usr/sbin/mosquitto\0-c\0/synthetic/config\0")
    with patch("app.passwd.os.getpid", return_value=1):
        with pytest.raises(AccountError):
            reload()
    assert signals == []
    reload()
    assert len(signals) == 1 and signals[0][0] == 1
