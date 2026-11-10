# Recovery: account edits are blocked

**Keep account edits blocked until you have checked the broker and restored a trusted file.** Removing a marker is not recovery by itself.

## What the warning means

`TRANSACTION_PENDING` means the manager stopped during a transaction, or could not durably mark completion. `RECOVERY_REQUIRED` means automatic recovery failed or was refused because the live file changed externally. Either can mean a file change happened without a proven fresh connection/reload. The web account list is not proof the broker is using that file.

1. Stop the **manager only** through the stack's supported controls. Do not restart the shared broker as an automatic repair. A live broker restart/reload requires the separately approved operational procedure; existing device connections may be affected.
2. Protect a copy of the current password file, the markers, and `.mqtt-manager-backups/` before doing anything else. These contain sensitive password hashes: broker UID/GID, password-file mode 600/640, backups directory 700 and backup files 600. Never print their contents, hashes, or values to chat/logs.
3. Inspect the most recent retained snapshot locally and compare it to the current file **without exposing raw values**. The snapshot was taken before the pending operation. Confirm the selected file parses, has unique usernames, expected account count and only the intended account difference. Preserve any legitimate external writer's change; do not overwrite it by assumption. Newest backup is not automatically best if an administrator changed the file externally.
4. Restore the selected trusted file with a same-directory private stage, correct broker UID/GID and original mode, file fsync, atomic replace, directory fsync. Use a reviewed recovery script/procedure; do not copy over the live file in place. Reload with a verified broker identity and same-UID SIGHUP, and prove a fresh connection using a **disposable known-valid credential** under the approved broker procedure. For removal, confirm that the credential which just worked is denied. Do not use an arbitrary bad password as removal evidence. Existing connections are not forced offline by password-file changes.
5. Only after recovery is proved, remove the marker(s), sync their directory, and start the manager. Confirm there is no critical warning and the expected account list is served. Keep all evidence private. If proof fails, keep the marker(s) and escalate; do not repeatedly resubmit account changes.

## Ordinary failures

- **Another change is running:** wait for its polling result; the manager has no queue.
- **Another writer changed the file:** the manager leaves that writer's file untouched if detected before publication. All writers must use `.mqtt-manager.lock`; stop the manager for non-cooperating maintenance.
- **File/name/hash/ownership invalid:** repair intentionally offline, not by weakening validation. The manager requires the file owned by the broker UID/GID, mode 600 or 640, no symbolic/hard links, complete final line, supported hash formats, and bounded size.
- **Fresh connection failed, previous file restored:** the manager restores the exact bytes and signals reload again. It does not retain an old plaintext password, so it cannot fresh-connect with the old credential. Verify service behavior through the separately approved operational process before retrying.
- **Account succeeded but note failed:** the account remains successfully changed. Repair the separate notes JSON and re-save the description. Notes must be private 600 and a bounded unique-key string mapping.
- **Polling unavailable after refresh/restart/logout:** check the account list. Public task results expire after 15 minutes and are scoped to the initiating sign-in; a missing result is not proof that an operation failed.
- **Connection status unknown:** check log availability/rotation/permissions. Do not invent device presence from keepalive time. Last seen is the last observed log event only.

## Backups and operational constraints

Backups are on the same filesystem as the password file, not off-host disaster recovery. An interrupted transaction blocks further mutations before new snapshots/pruning; its preceding backup therefore remains retained. Back up the broker configuration separately through the approved host backup system.

Run one application process. Do not use multi-worker gunicorn, several manager replicas, or direct uncoordinated writes. The durable journal blocks interrupted operations; it does not eliminate the POSIX check-to-replace race against writers which ignore the lock. The account mount must be the **whole writable config directory**, not an individual file bind mount: atomic replacement of a single bind-mounted file will fail or leave stale mount identities.
