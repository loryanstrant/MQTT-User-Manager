# Backend handoff — 2026-11-10

## Source

Exact scratch worktree: `/data/sessions/8fab1fe60f30/wt`.

Import: `app/`, `tests/`, `wsgi.py`, `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `.gitignore`, `.env.example`, `Dockerfile`, `compose.example.yaml`, `README.md`, `AGENTS.md`, `CHANGELOG.md`, and `docs/`.

Do **not** import `.mcp.json`, `_IMAGES/`, `_CONSULTANT/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, or Python caches. This session has no local Git repository, commit, branch or PR. Parent owns import/review into the now-created private repository. No production changes, live fleet reads, containers or deployment occurred in this backend session.

## Test receipts

Offline synthetic gate with CPython3.12.16:

```text
ruff check app tests wsgi.py
All checks passed!

/data/venvs/mqtt-user-manager-scratch/bin/python -m pytest -q --cov=app --cov-report=term-missing
114 passed in 2.84s
app total: 901 statements, 76 missed, 92% coverage
```

Coverage is not a claim every branch was exercised. Production startup/actual broker tools/container and additional filesystem-race branches still require the parent's artifact/integration checks. Test fixtures inject synthetic hash generation, reload and verifier callbacks; tests do not call Mosquitto or a live broker. Recovery, external writers, permissions, lock serialization, rollback failures, durable markers, CSRF/Origin, copied-session revocation, generated-secret non-retention, bounded tasks/results, notes, rotation/copytruncate/partial logs, FIFO rejection and multi-session evidence are exercised.

The independent consultant review (bounded design review, not source execution) informed the durable pending marker, server-side nonce revocation, internal-verification exclusion, and documented uncooperative-writer/async-reload limits. Its suggestions were independently evaluated rather than treated as verified results.

## One post-handoff review pass

Reviewed the entire backend, tests, API/recovery ADRs and container examples directly: this scratch folder has no Git baseline, so committed/uncommitted diffs and the Git-range impact sweep were unavailable. Code-graph discovery failed with a guarded RuntimeError; no bypass or retry was used. The review skill's checklist was applied; its PR-only no-edit restriction does not apply to this explicit own-code fix request.

- Fixed rollback publication/reload uncertainty: recheck the current fingerprint after preparing recovery; verify restored bytes, ownership and mode; compare restored fingerprint after reload before clearing pending. Synthetic external content/metadata changes during rollback reload now retain both recovery markers; an edit during recovery preparation remains untouched.
- Fixed expired-session capacity lockout and permitted replacement of the initiating session at capacity. Truly full active-session capacity still refuses a new sign-in.
- Made opt-in reconnect evidence continuous: unknown state is not an observed disconnect; skipped scans, missing logs and session overflow clear prior reconnect counts. Rotation/truncation already reset them.
- Added nine regression cases. Before fixes, eight failed and the active-capacity control passed; after fixes the entire gate passed. Two bounded consultant calls tried to disprove the findings. Rollback was confirmed; session permanence and reconnect severity were narrowed, not treated as unconditional claims. Consultant opinions were then grounded by synthetic execution.

Deferred unchanged: the parent's actual client/broker/container compatibility proof and UI checks. The documented narrow pathname check-to-replace race with writers ignoring the lock remains; all direct maintenance must stop the manager. No second review pass was run, no live service was accessed, and no deployment is claimed.

## Parent remaining work

1. Prove and wire a bounded private-config Mosquitto fresh-CONNECT verifier. It must use reserved `mqtt-manager-check-` client IDs, positive authenticated-CONNECT evidence (not mere subscribe timeout or generic success), private0600 ephemeral config, no password argv/log/result exposure, and retry until a short deadline for async reload. Current default verifier `available=False` refuses add/change **before any publication**. Inject a proved callable via `create_app(services={"verifier": ...})`, or replace production default explicitly.
2. Build/inspect the Dockerfile example; parent measured `eclipse-mosquitto:latest` binary2.1.2 and non-TTY stdin hashing. No exact2.1.2 tag/digest pin is shipped. Check empty existing password-file add without `-c`, binary paths, package availability, PID1/UID1883 signalling, mount semantics and actual broker config. The backend never targets itself as PID1. The app requires directory mounts for atomic replacement.
3. Real disposable-broker sequence: known-valid credential accepts; change new credential accepts/old rejects; remove formerly valid credential rejects; existing connected synthetic session continuity warning proven. No arbitrary bad password deletion proof. Verify backup hashes/metadata privately, unchanged unrelated accounts and rollback reload behavior. Existing connections aren't forcibly revoked.
4. Import/review all source and run the test gate in the actual private branch. Add the parent-approved product templates/CSS and perform actual desktop/phone interactive checks. No product UI exists in this backend handoff.

## Interfaces

See `docs/api.md`. Factory `create_app(config=None, services=None)` exposes extensions `accounts`, `notes`, `presence`, `operations`, `limiter`, `valid_sessions` and a production lifetime process lock. All mutations require exact configured Origin and CSRF; sign-in rotates token. Account operations return202 plus500ms polling. No queue; public result32/15min retention; initiating-session scope. User-visible success/critical/connection states contain shapes and words.

## Important limits

All other writers must cooperate with `.mqtt-manager.lock`; POSIX pathname replacement is not an atomic compare-and-swap against an uncooperative editor. Stop manager for direct maintenance. Durable pending/critical markers require explicit recovery; the manager does not auto-trust a partially completed change. Password changes/removals do not force connected devices offline. Signal delivery is not synchronous reload acknowledgment. Presence is log observation only. Notes are separately atomic and can produce a warning after account success. Python cannot promise secure erasure of transient plaintext from process memory.
