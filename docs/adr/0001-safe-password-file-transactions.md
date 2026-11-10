# ADR-0001: Preserve the password file; prove changes before reporting success

- Status: accepted for backend implementation; deployment mechanics await parent validation
- Date: 2026-11-10

## Decision

Use Flask/Jinja2/waitress and the broker-compatible upstream Mosquitto password tool, not a home-grown hash implementation. The command and fresh-connect verifier are injectable. Until their private-input contracts are proved, production defaults refuse to operate. The intended compatibility target is Mosquitto **binary 2.1.2**, not an assumed `eclipse-mosquitto:2.1.2` tag: the parent reported that tag unavailable. The final image choice must be verified separately and commented beside any pin.

A transaction acquires `.mqtt-manager.lock` with an acquisition deadline, holds it through command, reload, verification, and rollback, then:

1. Snapshot a regular, single-link, bounded password file; validate every name and supported hash. Require broker ownership and mode 600/640. Preserve unrelated lines byte-for-byte, including existing supported hash formats. Existing CRLF records are accepted and must remain byte-for-byte unchanged for unrelated users; an incomplete final line is rejected.
2. Save a 0600 snapshot in the 0700 `.mqtt-manager-backups` directory. Keep the newest 20 regular, safe backups.
3. Stage in the same directory at mode 600, run the upstream tool without a shell and with bounded time, and validate exact account count/set and immutable unrelated lines. The target's format must match `MQTT_HASH_ALGO` (default `sha512-pbkdf2`).
4. Compare the original fingerprint (bytes, identity, timestamps, ownership, mode). Persist and sync `TRANSACTION_PENDING`, compare again, set the original stage mode, sync the file, atomically replace, and sync the directory. Read back the applied contents and metadata.
5. Verify broker PID1 identity and same UID before SIGHUP. Add/change require a bounded fresh-CONNECT proof with the supplied password. Delete reports exact removal plus **reload signal**, not confirmed reload completion or forced logout. Parent separately verifies a disposable known-valid credential is denied after deletion.
6. On reload/verification/publication failure, restore the exact snapshot and signal reload again. Recheck the applied fingerprint after preparing recovery, verify restored bytes/ownership/mode, and check the restored fingerprint after rollback reload before clearing the journal. Refuse to overwrite an externally changed applied file. Failure or refusal of rollback creates `RECOVERY_REQUIRED`. Interrupted transactions leave `TRANSACTION_PENDING`. Either marker blocks new changes across restarts; recovery is explicit, not guessed.

## Consequences and boundaries

- **All external writers must cooperate with the same lock.** A last fingerprint check cannot atomically compare-and-swap an arbitrary POSIX pathname against an uncooperative writer. The narrow check-to-replace race remains. Do not use editors or direct password-tool writes while this manager runs. Stop the manager before non-cooperating maintenance.
- Password changes/removal do **not** disconnect already connected clients. Existing sessions may continue until disconnected or the broker's own policies act. This is not instant revocation.
- A successful `kill(SIGHUP)` is a delivered signal, not a broker reload acknowledgment. Fresh-CONNECT verification is stronger proof for add/change; no arbitrary wrong password is used as deletion evidence.
- Old plaintext passwords are neither known nor retained, so rollback verifies file restoration and reload signalling, not a fresh connect with the previous password.
- Generated passwords appear in a single uncached response. The browser sends the chosen password for the transaction; it never appears in signed sessions, polling results, logs, backups, or command arguments. Process memory necessarily contains the supplied secret during hashing/verification and cannot promise secure erasure in Python.
- Notes are a separate atomic JSON store. Note failure after account success reports a warning; do not pretend the account was rolled back. Notes may contain descriptions, never credentials.
- SHA512/PBKDF2/Argon2 hash parsing is strict and bounded. Unsupported formats/names stop account edits for explicit repair rather than silently deleting unknown entries.
- No Docker socket, Docker API, live fleet discovery, production credentials, or guessed device descriptions in the app.
