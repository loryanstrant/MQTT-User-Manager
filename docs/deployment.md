# Deployment guide

**Deploy the manager separately from an existing broker.** Do not recreate or restart a shared broker merely to add this web page.

## Manager-only deployment

Use `compose.production.yaml` as a parameterized example. Supply the verified manager image, existing broker container name/network, config and log directories, private manager data directory and exact HTTPS origin. Confirm the resolved Compose file contains only the manager. Protect deployment secrets; do not print resolved secret-bearing configuration into logs.

- Run as the broker UID/GID (the image defaults to 1883:1883), with read-only root, dropped capabilities, no-new-privileges, private bounded tmpfs and resource limits.
- Share the broker's container PID namespace, **not** host PIDs or the Docker socket. Verify PID 1 is the broker, with the expected command and UID. After broker replacement, redeploy the manager deliberately to join its new PID namespace.
- Join the broker network and name it explicitly through `MQTT_BROKER_HOST`; PID sharing does not share localhost/networking.
- Mount the complete writable broker config directory for same-directory atomic replacement; mount logs read-only and manager data privately. Password file must exist, be regular/single-link, broker-owned, mode 600/640 and valid. Protect a metadata/content backup before any intentional ownership correction.
- Bind HTTP to loopback and place a TLS reverse proxy in front of it. Allow ingress only on the intended trusted network. Set `PUBLIC_ORIGIN` to that exact HTTPS address. Do not weaken Origin, host validation, cookies or CSP to accommodate a bad proxy setup.

Keep credentials in a secret manager or protected runtime environment. The admin password uses a Werkzeug scrypt/PBKDF2 hash; session key must be independent and at least 32 characters. Do not store plaintext credentials in examples, build arguments or image layers.

## Broker prerequisites

Confirm the selected listener has `allow_anonymous false` and uses the exact mounted password file. The tested/default hash algorithm is SHA512-PBKDF2. Enable connection/disconnection logging to the configured file with epoch timestamps where possible; give the manager read access without write access. Configure bounded log rotation externally. The manager scans only the current file, up to 1 MiB per scan.

Check actual Mosquitto client/password-tool compatibility in the final image. The integration target tested is binary 2.1.2; a matching versioned image tag is not assumed. Password hashing uses non-batch newline-delimited stdin, without `-c` on existing files. Connection proof uses private 0600 ephemeral `-o` options and positive CONNACK evidence with bounded retries. Never put passwords in argv.

The broker can remain connected to existing clients across password-file reloads; verify this with a disposable subscriber in your environment. Updates do not force disconnect. Plan separately for revocation of an already connected device.

## Release gate

1. Run pinned offline Python, lint and JavaScript gates; record the exact source revision and test results.
2. Build and inspect the real image; verify its source revision, user, tools and safety settings after pulling it on the destination.
3. Run disposable container tests: add, change/new accepts/old rejects, delete/previously-valid rejects, unchanged unrelated lines, private snapshots, exact rollback and an established session surviving reloads.
4. Verify the actual HTTPS page, auth refusal when anonymous, login, table search/sort, notes and operation polling. Exercise desktop and narrow width with synthetic data for publication screenshots.
5. Before production writes, protect the broker baseline and coordinate all other writers. Test only an explicitly approved disposable account. Privately compare unrelated credentials, broker identity/restart count and existing-client observations afterwards.

A green unit suite or liveness HTTP 200 is not proof of broker readiness, final image compatibility or browser behaviour. Shared service restarts need separate explicit approval with their impact. A deployment intended solely as a restart is not a workaround for that requirement.

## Maintenance

Follow [recovery](recovery.md). External writers must cooperate with the same lock or stop the manager. A pathname fingerprint cannot eliminate a race with an uncooperative writer. Run one application process and bounded tasks; no multi-worker replicas. Save private integration receipts outside public documentation and use only synthetic accounts in screenshots and tests.
