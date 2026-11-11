# MQTT User Manager

![MQTT User Manager icon](app/static/icon.png)

**Create MQTT accounts and change their passwords from a private web page.** Keep Mosquitto's existing password-file authentication instead of migrating accounts or replacing the broker.

## Features

- Searchable, sortable account table with editable device notes and log-observed connection status.
- Add, change-password and remove dialogs; strong generated passwords you can override and copy.
- Hashed administrator login, revocable 30-minute sessions, Origin/CSRF checks and visible operation progress.
- Strict password-file validation, exact unrelated-account preservation, private backups, atomic updates and rollback.
- JSON API for tools using the same authenticated session and operation-polling contract as the page.

**Password changes and removal do not disconnect established clients.** Last seen is the last observed connection event, not the last message or a live device check. The desktop table scrolls sideways on narrow screens. No mobile app, Docker socket, broker replacement or ACL migration is required.

## Getting started

1. Read the [deployment guide](docs/deployment.md) and [security/recovery constraints](docs/recovery.md).
2. Build locally with `docker build -t mqtt-user-manager:local .`, or, after confirming the [first GHCR publication](docs/deployment.md#container-registry), pull `ghcr.io/loryanstrant/mqtt-user-manager:latest`. Set `MQTT_MANAGER_IMAGE` to the chosen image for the manager-only example.
3. Configure an exact HTTPS `PUBLIC_ORIGIN`, private Werkzeug `ADMIN_PASSWORD_HASH`, independent session key of at least 32 characters and explicit broker hostname. See [.env.example](.env.example).
4. Prepare the broker-owned password file and private data directory; mount the **whole config directory**, read-only logs and the broker PID namespace. [compose.production.yaml](compose.production.yaml) is a manager-only example; [compose.example.yaml](compose.example.yaml) includes a disposable broker example.
5. Provide HTTPS on a trusted private network, sign in, and prove a disposable account change before using it with real devices.

Store credentials in a secret manager or protected deployment configuration, never in this repository. Keep HTTP bound to loopback unless another private ingress arrangement has been explicitly secured. The broker must require password authentication on the configured listener. The manager's local Docker-network verification is unencrypted and must not cross an untrusted network.

## API

See [the API contract](docs/api.md) for cookie sign-in, CSRF, sorting/filtering and add/change/remove operations. Writes return an operation ID: poll until completion rather than treating an HTTP 202 as success. There are no dedicated API keys or per-tool permissions; integrations currently have administrator access through an expiring session.

## Connection evidence

The manager observes a bounded current log, not all rotated history. The table shows the observed connection status and last-seen time without a repeated incomplete-log warning on each row. Missing history can leave connections unknown even when an earlier last-seen timestamp is retained. Internal credential checks never count as device activity. API clients can still distinguish incomplete history from row-level uncertainty.

## Test

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q --cov=app --cov-report=term-missing
ruff check app tests wsgi.py
node --check app/static/accounts.js
node --test tests/ui_regressions.cjs
```

Tests named `test_*.py` use synthetic offline fixtures. Explicit Docker integration scripts create disposable resources only; they must never receive production password files. See [verification](docs/verification.md) for the distinction between unit, container and browser proof.

## Safety and maintenance

Run one waitress application process, not multiple replicas or workers. All password-file writers must cooperate with `.mqtt-manager.lock`; stop the manager before direct maintenance. Interrupted or failed recovery transactions block further changes until explicit recovery. Same-filesystem backups are recovery snapshots, not disaster recovery.

The manager verifies broker identity and UID before sending SIGHUP, then proves new credentials using a fresh authenticated connection. Deletion confirms exact file removal plus reload signalling, not forced logout. A compromised manager would still have access to the mounted config directory and shared broker PID namespace; these are deliberate privileges.

The upstream image floats at `eclipse-mosquitto:latest`; tested client-tool compatibility is Mosquitto binary 2.1.2. Re-run private-input and container tests on upstream changes. SHA512-PBKDF2 is the tested default; optional Argon2 generation is not integration-approved. Python cannot promise secure erasure of transient secret memory.

## Container publishing

GitHub Actions tests each public `main` snapshot, builds a Linux AMD64 image and runs a network-isolated container smoke check before publishing that exact image to GHCR. It publishes `ghcr.io/loryanstrant/mqtt-user-manager:latest` and a `sha-<full-public-commit>` tag. The image's source/revision labels refer to the public GitHub snapshot, not private history. ARM images are not currently built or verified.

The smoke check verifies startup, bundled client tools, exact served assets, administrator sign-in, access protection and logout with temporary generated credentials. It never contacts a live broker; disposable broker integration and deployment verification remain separate gates. See [deployment](docs/deployment.md#container-registry) for package visibility and first-publication setup.

## Project

[GitHub](https://github.com/loryanstrant/MQTT-User-Manager) is the public project page. Contributions are reviewed in the maintainer's canonical repository; GitHub is a one-way publication target. See the [MIT license](LICENSE).
