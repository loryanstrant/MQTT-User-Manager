"""Private atomic notes; never infer descriptions from fleet names."""

import json
import os
import tempfile
from pathlib import Path

from .passwd import AccountError, file_lock, fsync_directory, snapshot, validate_username


def validate_note(note):
    if (
        not isinstance(note, str)
        or len(note) > 2000
        or any(ord(c) < 32 and c not in "\n\t" for c in note)
    ):
        raise AccountError("invalid_note", "Notes must be text of at most 2,000 characters.")
    return note


class NotesStore:
    def __init__(self, path: Path, lock_timeout=3.0):
        self.path = Path(path)
        self.lock_timeout = lock_timeout

    def read(self):
        try:
            original = snapshot(self.path, max_bytes=2 * 1024 * 1024)
        except FileNotFoundError:
            return {}
        if original.uid != os.geteuid() or original.mode != 0o600:
            raise AccountError(
                "unsafe_notes", "The notes file must be private and owned by the manager."
            )
        try:

            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError
                    result[key] = value
                return result

            data = json.loads(original.data, object_pairs_hook=unique)
            if not isinstance(data, dict) or len(data) > 10000:
                raise ValueError
            for name, note in data.items():
                validate_username(name)
                validate_note(note)
            return data
        except (ValueError, UnicodeError, AccountError):
            raise AccountError(
                "invalid_notes", "The notes file is malformed; repair it before changing notes."
            ) from None

    def set(self, username, note):
        validate_username(username)
        validate_note(note)
        stage = None
        with file_lock(self.path.parent / ".notes.lock", self.lock_timeout):
            original = snapshot(self.path) if self.path.exists() else None
            data = self.read()
            if note:
                data[username] = note
            else:
                data.pop(username, None)
            encoded = (json.dumps(data, ensure_ascii=True, sort_keys=True) + "\n").encode()
            if len(encoded) > 2 * 1024 * 1024 or len(data) > 10000:
                raise AccountError("notes_full", "The notes safety limit has been reached.")
            try:
                fd, name = tempfile.mkstemp(prefix=".notes-stage-", dir=self.path.parent)
                stage = Path(name)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                current = snapshot(self.path) if self.path.exists() else None
                if (current.fingerprint if current else None) != (
                    original.fingerprint if original else None
                ):
                    raise AccountError(
                        "external_change", "Another writer changed the notes; nothing was applied."
                    )
                os.replace(stage, self.path)
                stage = None
                fsync_directory(self.path.parent)
            finally:
                if stage:
                    stage.unlink(missing_ok=True)
