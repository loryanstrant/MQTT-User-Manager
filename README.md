# MQTT User Manager

**Add MQTT accounts and change their passwords from a private web page.** Keeps Mosquitto's existing password-file authentication rather than migrating accounts.

## What you get

1. One searchable, sortable account table, editable notes and log-observed connection status.
2. Add/change/remove dialogs, generated passwords you can replace/copy, and protected removal of Home Assistant/Zigbee2MQTT accounts.
3. Hashed admin login, short revocable sessions, exact-Origin/CSRF protection and visible operation progress.
4. Private backups, exact unrelated-account preservation, atomic writes, verified fresh logins and rollback; interrupted transactions block further changes.

Password changes/removal **do not disconnect established clients**. Last seen means the last logged connection event, not a live message/keepalive check. Desktop is the approved layout; the table scrolls sideways at narrow widths. No mobile app, broker replacement, ACL migration or Docker socket.

## Current verification and release state

On 10 November 2026, the real image built on PERCEPTOR and ran with UID/GID1883, read-only root, dropped capabilities and shared broker PID namespace. Disposable tests passed actual HTTP add/change/delete, old-password refusal, known-valid deleted credential refusal, unchanged unrelated accounts, private backups, rollback, and first add to an existing empty file without `-c`. Six exact password cases (spaces, quotes/backslash, Unicode) passed private options-file verification. The earlier isolated broker proof showed an established subscriber surviving three reloads without reconnection.

**Not deployed.** The single post-build review fixed delayed password-generation responses and the scratch proxy network connection. Scratch HTTPS now serves the exact fixed product script; 125 Python tests and six synthetic asynchronous UI tests pass, and actual disposable HTTP add/change/delete passes again. Playwright execution still stopped at guarded discovery, so no browser layout/click or screenshot pass is claimed. See [verification receipt](docs/verification.md) and [deployment](docs/deployment.md).

## Test

```sh
devenv
# Activate the environment it prints.
python -m pytest -q --cov=app --cov-report=term-missing
ruff check app tests wsgi.py
node --check app/static/accounts.js
node --test tests/ui_regressions.cjs
docker build -t mqtt-user-manager:local .
```

`test_*.py` fixtures are synthetic and offline. Explicit `tests/prove_broker.py` and `tests/scratch_rig.py up|down` create disposable Docker resources only; the latter requires the scratch admin password privately on stdin. `tests/container_api_proof.py` runs inside that disposable manager, not against production. Never copy production account hashes into tests.

## Run

Read [transaction ADR](docs/adr/0001-safe-password-file-transactions.md), [auth/presence ADR](docs/adr/0002-bounded-api-auth-and-presence.md), [production integration ADR](docs/adr/0003-private-client-and-screen.md) and [recovery](docs/recovery.md).

- Configure an exact HTTPS `PUBLIC_ORIGIN`, private Werkzeug `ADMIN_PASSWORD_HASH`, independent >=32-character `SECRET_KEY` and explicit `MQTT_BROKER_HOST`. Store credentials in shared Vaultwarden and stack secret settings; examples contain no values.
- Password file must exist, be valid/regular/single-link, owned by broker UID/GID1883 and mode600/640. Prepare private manager data directory. The whole config directory mount is required for atomic replacement; logs are read-only.
- Share only the broker PID namespace. Reload checks PID1 `comm`, exact executable argv and all UIDs before same-UID SIGHUP. This works with a root-started broker that drops privileges, where `/proc/1/exe` is not readable. Never mount Docker socket or host PID namespace.
- Run exactly one waitress process (`python wsgi.py`), four HTTP threads, one transaction worker, bounded public results and a lifetime process lock. No queues or multi-process workers.
- The default `FreshConnectVerifier` uses Mosquitto `-o` with private0600 ephemeral options, reserved client IDs, explicit bounded attempts and positive authenticated-CONNECT evidence. It refuses a listener accepting an incorrect password. This does not replace deployment verification of listener authentication policy and endpoint identity.
- Base `eclipse-mosquitto:latest` floats per infrastructure standard. Actual tool compatibility target tested is binary2.1.2; re-run artifact checks on upstream changes. SHA512-PBKDF2 is the tested/default hashing algorithm. Optional Argon2 generation was not successful in the earlier tool image and is not deployment-approved.

Private-input handling keeps secrets out of argv/logs/results/browser storage. Verification on broker port1883 remains within the local Docker network; it is not encrypted transport and must not be extended to untrusted remote networks. Python cannot promise secure erasure of transient process memory.

## Recovery and maintenance

Follow [recovery](docs/recovery.md). Backups are same-filesystem recovery snapshots, not off-host disaster recovery. All external writers must cooperate with `.mqtt-manager.lock`; stop the manager before direct maintenance. A pathname fingerprint cannot eliminate races with uncooperative writers. Mounting the whole broker config directory and sharing broker PIDs are deliberate privileges: the app constrains writes to the account path/stages/backups, but compromise of the app would still have broader directory access.

[API contract](docs/api.md) describes all endpoints. The public home screen contains only a login shell; account APIs require authentication. No passwords in persistent browser storage or retained operation results.
