"""Serialized, defensive password-file transactions. No shell or secret logging."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import os
import re
import secrets
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class AccountError(Exception):
    """Only these deliberately public messages may cross the API boundary."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class CriticalError(AccountError):
    def __init__(self):
        super().__init__(
            "critical", "Recovery failed. Account changes are blocked; follow the recovery guide."
        )


def validate_username(username: str) -> str:
    if not isinstance(username, str) or not re.fullmatch(
        r"[A-Za-z0-9_][A-Za-z0-9_.@-]{0,127}", username
    ):
        raise AccountError(
            "invalid_username",
            "Use 1–128 letters, numbers, dots, underscores, @ or hyphens; start with a letter, number or underscore.",
        )
    return username


def validate_password(password: str) -> str:
    if (
        not isinstance(password, str)
        or not 12 <= len(password) <= 256
        or any(ord(c) < 32 or ord(c) == 127 for c in password)
    ):
        raise AccountError(
            "invalid_password", "Use a password of 12–256 characters without control characters."
        )
    return password


def generate_password() -> str:
    return secrets.token_urlsafe(24)


def _valid_hash(value: bytes) -> bool:
    # Existing SHA512 / PBKDF2 / Argon2 hashes are preserved, never rehashed.
    try:
        text = value.decode("ascii")
        parts = text.split("$")
        if parts[0] != "":
            return False
        if parts[1] == "6" and len(parts) == 4:
            salt, digest = parts[2:]
            return (
                len(base64.b64decode(salt, validate=True)) > 0
                and len(base64.b64decode(digest, validate=True)) == 64
            )
        if (
            parts[1] == "7"
            and len(parts) == 5
            and parts[2].isdigit()
            and 1 <= int(parts[2]) <= 10000000
        ):
            salt, digest = parts[3:]
            return (
                len(base64.b64decode(salt, validate=True)) > 0
                and len(base64.b64decode(digest, validate=True)) == 64
            )
        if parts[1] == "argon2id" and len(parts) == 6:
            return bool(
                re.fullmatch(r"v=19", parts[2])
                and re.fullmatch(r"m=\d+,t=\d+,p=\d+", parts[3])
                and re.fullmatch(r"[A-Za-z0-9+/]{8,}", parts[4])
                and re.fullmatch(r"[A-Za-z0-9+/]{16,}", parts[5])
            )
    except (ValueError, UnicodeError, IndexError):
        pass
    return False


def parse_password_file(data: bytes) -> dict[str, bytes]:
    if len(data) > 2 * 1024 * 1024:
        raise AccountError("invalid_file", "The account file exceeds the safety limit.")
    entries: dict[str, bytes] = {}
    if data and not data.endswith(b"\n"):
        raise AccountError(
            "invalid_file",
            "The account file has an incomplete final line; repair it before changing accounts.",
        )
    for line in data.splitlines(keepends=True):
        body = line.rstrip(b"\r\n")
        if body.count(b":") != 1:
            raise AccountError(
                "invalid_file", "The account file is malformed; repair it before changing accounts."
            )
        name, value = body.split(b":")
        try:
            username = validate_username(name.decode("ascii"))
        except (UnicodeError, AccountError):
            raise AccountError(
                "invalid_file", "The account file contains an unsupported account name."
            ) from None
        if username in entries or not _valid_hash(value):
            raise AccountError(
                "invalid_file", "The account file contains duplicate accounts or malformed hashes."
            )
        entries[username] = line
    return entries


@dataclass(frozen=True)
class Snapshot:
    data: bytes
    inode: int
    device: int
    mtime_ns: int
    ctime_ns: int
    mode: int
    uid: int
    gid: int

    @property
    def fingerprint(self) -> tuple:
        return (
            self.inode,
            self.device,
            self.mtime_ns,
            self.ctime_ns,
            self.mode,
            self.uid,
            self.gid,
            hashlib.sha256(self.data).digest(),
        )


def snapshot(path: Path, max_bytes: int = 2 * 1024 * 1024) -> Snapshot:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise AccountError(
                "invalid_file", "The account file must be a regular file with no hard links."
            )
        if before.st_size > max_bytes:
            raise AccountError("invalid_file", "The file exceeds the safety limit.")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(max_bytes + 1)
        after = os.fstat(fd)
        if len(data) > max_bytes or (before.st_mtime_ns, before.st_ctime_ns, before.st_size) != (
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_size,
        ):
            raise AccountError(
                "external_change",
                "The account file changed during the read; try again after the other writer finishes.",
            )
        return Snapshot(
            data,
            before.st_ino,
            before.st_dev,
            before.st_mtime_ns,
            before.st_ctime_ns,
            stat.S_IMODE(before.st_mode),
            before.st_uid,
            before.st_gid,
        )
    finally:
        os.close(fd)


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def file_lock(path: Path, timeout: float = 3.0):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise AccountError("unsafe_lock", "The safety lock has unsafe permissions.")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise AccountError(
                        "busy", "Another account change is running; wait for it to finish."
                    ) from None
                time.sleep(0.025)
        yield
    finally:
        os.close(fd)


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise AccountError(
            "unsafe_backup", "The private data folder has unsafe ownership or permissions."
        )


class PasswordCommand:
    """Adapter is intentionally fail-closed until the pinned tool's stdin contract is proved."""

    def __init__(
        self,
        executable: str = "/usr/bin/mosquitto_passwd",
        algorithm: str = "sha512-pbkdf2",
        timeout: float = 5.0,
        stdin_verified: bool = False,
    ):
        if algorithm not in {"sha512-pbkdf2", "argon2id"}:
            raise ValueError("Unsupported password algorithm")
        self.executable, self.algorithm, self.timeout, self.stdin_verified = (
            executable,
            algorithm,
            timeout,
            stdin_verified,
        )

    def __call__(self, path: Path, action: str, username: str, password: str | None) -> None:
        if action == "delete":
            args = [self.executable, "-D", str(path), username]
            secret_input = None
        else:
            if not self.stdin_verified:
                raise AccountError(
                    "tool_unverified",
                    "The password tool has not passed its private-input compatibility check.",
                )
            args = [self.executable, "-H", self.algorithm, str(path), username]
            secret_input = (password + "\n" + password + "\n").encode("utf-8")
        try:
            result = subprocess.run(
                args,
                input=secret_input,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout,
                check=False,
                shell=False,
                close_fds=True,
            )
            if result.returncode:
                raise AccountError(
                    "command_failed", "The password tool could not complete the change."
                )
        except (OSError, subprocess.TimeoutExpired):
            raise AccountError("command_failed", "The password tool failed or timed out.") from None


class BrokerReloader:
    """PID namespace sharing is not network sharing. Refuse our own PID1."""

    def __init__(
        self, pid: int = 1, broker_uid: int = 1883, proc: Path = Path("/proc"), signaler=None
    ):
        import signal

        self.pid, self.broker_uid, self.proc = pid, broker_uid, proc
        self.signaler = signaler or os.kill
        self.signal = signal.SIGHUP

    def __call__(self) -> None:
        try:
            if self.pid != 1 or self.pid == os.getpid():
                raise ValueError
            root = self.proc / str(self.pid)
            # A broker started as root then dropping UID is non-dumpable: exe readlink
            # is denied to its own UID. Verify readable name + explicit executable argv.
            executable = (root / "comm").read_text().strip()
            command = (root / "cmdline").read_bytes().split(b"\0", 1)[0]
            status = (root / "status").read_text()
            uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
            uids = [int(value) for value in uid_line.split()[1:]]
            if (
                executable != "mosquitto"
                or command not in {b"mosquitto", b"/usr/sbin/mosquitto", b"/usr/bin/mosquitto"}
                or not uids
                or any(value != self.broker_uid for value in uids)
                or os.geteuid() != self.broker_uid
            ):
                raise ValueError
            self.signaler(self.pid, self.signal)
        except (OSError, ValueError, StopIteration):
            raise AccountError(
                "reload_failed",
                "Broker identity or reload could not be verified; no other process was targeted.",
            ) from None


class PasswordStore:
    def __init__(
        self,
        path: Path,
        command: Callable,
        reload: Callable,
        verifier: Callable,
        *,
        broker_uid: int = 1883,
        broker_gid: int = 1883,
        protected: tuple[str, ...] = ("homeassistant", "zigbee2mqtt"),
        lock_timeout: float = 3.0,
    ):
        self.path = Path(path)
        self.command, self.reload, self.verifier = command, reload, verifier
        self.broker_uid, self.broker_gid, self.protected = (
            broker_uid,
            broker_gid,
            frozenset(protected),
        )
        self.lock_timeout = lock_timeout
        self.backups = self.path.parent / ".mqtt-manager-backups"
        self.critical = False

    def accounts(self) -> list[str]:
        return sorted(parse_password_file(snapshot(self.path).data), key=str.casefold)

    def _check_permissions(self, original: Snapshot) -> None:
        if (
            original.uid != self.broker_uid
            or original.gid != self.broker_gid
            or original.mode not in {0o600, 0o640}
            or os.geteuid() != self.broker_uid
        ):
            raise AccountError(
                "unsafe_permissions",
                "The account file must belong to the broker user and group with mode 600 or 640.",
            )

    def _stage(self, data: bytes, original: Snapshot) -> Path:
        fd, name = tempfile.mkstemp(prefix=".mqtt-manager-stage-", dir=self.path.parent)
        path = Path(name)
        try:
            os.fchown(fd, original.uid, original.gid)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                fd = -1
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            return path
        except BaseException:
            if fd >= 0:
                os.close(fd)
            path.unlink(missing_ok=True)
            raise

    def _publish(self, stage: Path, original: Snapshot) -> None:
        fd = os.open(stage, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != original.uid
                or info.st_gid != original.gid
            ):
                raise AccountError("unsafe_stage", "The staged file has unsafe ownership or type.")
            os.fchmod(fd, original.mode)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(stage, self.path)
        fsync_directory(self.path.parent)

    def _backup(self, original: Snapshot) -> None:
        private_directory(self.backups)
        fd, name = tempfile.mkstemp(prefix="backup-", dir=self.backups)
        with os.fdopen(fd, "wb") as stream:
            stream.write(original.data)
            stream.flush()
            os.fsync(stream.fileno())
        fsync_directory(self.backups)
        # Only our own regular 0600 files qualify for retention/deletion.
        candidates = []
        for path in self.backups.glob("backup-*"):
            info = path.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise AccountError("unsafe_backup", "A backup has unsafe ownership or permissions.")
            candidates.append((info.st_mtime_ns, path.name, path))
        for _, _, path in sorted(candidates, reverse=True)[20:]:
            path.unlink()
        fsync_directory(self.backups)

    def blocked(self) -> bool:
        return self.critical or any(
            os.path.lexists(self.backups / name)
            for name in ("RECOVERY_REQUIRED", "TRANSACTION_PENDING")
        )

    def _pending(self) -> None:
        # Persist before publication: interrupted transactions are never trusted baselines.
        fd = os.open(
            self.backups / "TRANSACTION_PENDING",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(
                b"Account transaction interrupted or not yet verified. Consult docs/recovery.md.\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        fsync_directory(self.backups)

    def _clear_pending(self) -> None:
        (self.backups / "TRANSACTION_PENDING").unlink()
        fsync_directory(self.backups)

    def _mark_critical(self) -> None:
        self.critical = True
        try:
            fd = os.open(
                self.backups / "RECOVERY_REQUIRED",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(
                    b"Recovery required. Consult docs/recovery.md before removing this marker.\n"
                )
                stream.flush()
                os.fsync(stream.fileno())
            fsync_directory(self.backups)
        except OSError:
            pass  # In-memory latch still blocks changes; API never hides this failure.

    def mutate(
        self,
        action: str,
        username: str,
        password: str | None = None,
        progress: Callable[[str], None] = lambda _: None,
    ) -> dict:
        if action not in {"add", "change", "delete"}:
            raise AccountError("invalid_action", "Choose add, change or delete.")
        validate_username(username)
        if action != "delete":
            validate_password(password)
            if not getattr(self.verifier, "available", True):
                raise AccountError(
                    "verification_unavailable",
                    "The private-input connection check has not passed its compatibility test; nothing was applied.",
                )
        if action == "delete" and username in self.protected:
            raise AccountError("protected", "This account is protected from removal.")
        stage = None
        with file_lock(self.path.parent / ".mqtt-manager.lock", self.lock_timeout):
            if self.blocked():
                raise CriticalError()
            progress("Checking the account file")
            original = snapshot(self.path)
            self._check_permissions(original)
            before = parse_password_file(original.data)
            if action == "add" and username in before:
                raise AccountError("exists", "That account already exists.")
            if action != "add" and username not in before:
                raise AccountError("missing", "That account does not exist.")
            self._backup(original)
            try:
                stage = self._stage(original.data, original)
                progress("Preparing the account change")
                self.command(stage, action, username, password)
                staged = snapshot(stage)
                after = parse_password_file(staged.data)
                expected = (
                    set(before) | {username}
                    if action == "add"
                    else set(before) - {username}
                    if action == "delete"
                    else set(before)
                )
                if (
                    set(after) != expected
                    or any(
                        after.get(name) != line for name, line in before.items() if name != username
                    )
                    or (action == "change" and after[username] == before[username])
                ):
                    raise AccountError(
                        "unexpected_diff",
                        "The tool changed more than the selected account; nothing was applied.",
                    )
                if action != "delete":
                    expected_prefix = (
                        b"$7$"
                        if getattr(self.command, "algorithm", "sha512-pbkdf2") == "sha512-pbkdf2"
                        else b"$argon2id$"
                    )
                    if not after[username].split(b":", 1)[1].startswith(expected_prefix):
                        raise AccountError(
                            "unexpected_algorithm",
                            "The password tool used an unexpected hash format; nothing was applied.",
                        )
                if snapshot(self.path).fingerprint != original.fingerprint:
                    raise AccountError(
                        "external_change",
                        "Another writer changed the account file; nothing was applied.",
                    )
                progress("Applying and reloading the broker")
                self._pending()
                # Check again after durable journal work narrows the external-writer race.
                if snapshot(self.path).fingerprint != original.fingerprint:
                    self._clear_pending()
                    raise AccountError(
                        "external_change",
                        "Another writer changed the account file; nothing was applied.",
                    )
                # Publication can fail after replace (e.g. directory fsync): detect that below.
                try:
                    self._publish(stage, original)
                    stage = None
                    committed = snapshot(self.path)
                    if committed.data != staged.data or (
                        committed.uid,
                        committed.gid,
                        committed.mode,
                    ) != (original.uid, original.gid, original.mode):
                        raise AccountError(
                            "external_change", "The applied file differs from the staged change."
                        )
                    self.reload()
                    if action != "delete":
                        progress("Checking a fresh connection")
                        if self.verifier(username, password) is not True:
                            raise AccountError(
                                "verification_failed",
                                "The new credentials could not make a fresh connection.",
                            )
                    if snapshot(self.path).fingerprint != committed.fingerprint:
                        raise AccountError(
                            "external_change", "The account file changed during verification."
                        )
                    self._clear_pending()
                except BaseException as failure:
                    try:
                        current = snapshot(self.path)
                    except Exception:
                        self._mark_critical()
                        raise CriticalError() from None
                    if current.fingerprint == original.fingerprint:
                        # Replace failed before any publication; broker still has original.
                        try:
                            self._clear_pending()
                        except OSError:
                            self._mark_critical()
                            raise CriticalError() from None
                        raise AccountError(
                            "apply_failed", "The file could not be replaced. Nothing was applied."
                        ) from None
                    if current.data != staged.data:
                        self._mark_critical()
                        raise CriticalError() from None
                    try:
                        if "committed" in locals() and current.fingerprint != committed.fingerprint:
                            raise AccountError(
                                "external_change", "The applied file was changed externally."
                            )
                        progress("Restoring the previous account file")
                        recovery = self._stage(original.data, original)
                        try:
                            if snapshot(self.path).fingerprint != current.fingerprint:
                                raise AccountError(
                                    "external_change", "The applied file changed during recovery."
                                )
                            self._publish(recovery, original)
                        finally:
                            recovery.unlink(missing_ok=True)
                        restored = snapshot(self.path)
                        if restored.data != original.data or (
                            restored.uid,
                            restored.gid,
                            restored.mode,
                        ) != (original.uid, original.gid, original.mode):
                            raise AccountError(
                                "external_change",
                                "The restored account file could not be verified.",
                            )
                        self.reload()
                        if snapshot(self.path).fingerprint != restored.fingerprint:
                            raise AccountError(
                                "external_change",
                                "The account file changed during recovery reload.",
                            )
                        self._clear_pending()
                    except BaseException:
                        self._mark_critical()
                        raise CriticalError() from None
                    if isinstance(failure, AccountError):
                        raise AccountError(
                            failure.code, failure.message + " The previous file was restored."
                        ) from None
                    raise AccountError(
                        "apply_failed", "The change failed. The previous file was restored."
                    ) from None
                return {
                    "username": username,
                    "action": action,
                    "status": "succeeded",
                    "label": "● Complete",
                    "message": "Account removed and broker reload signalled. Existing connections may remain active."
                    if action == "delete"
                    else "Fresh connection verified. Existing connections using an older password are not disconnected.",
                }
            except AccountError:
                raise
            except Exception:
                raise AccountError(
                    "operation_failed", "The account change failed before it could be applied."
                ) from None
            finally:
                if stage:
                    stage.unlink(missing_ok=True)
