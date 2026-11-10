# MQTT-User-Manager engineering rules

Read README.md, docs/api.md, and all ADRs before editing. Read whole source files; do not infer behavior from fragments. Preserve the security, test and UI requirements below.

- No Docker socket or Docker/host management APIs in the app. Same-UID broker PID namespace signalling only after identity verification. Broker network host is explicitly `mosquitto`, not localhost.
- Never log password/command arguments, raw hashes/config values, request bodies or exception tracebacks from command/client adapters. Public exceptions are deliberately sanitized. Fixtures are synthetic only.
- Preserve unrelated password-file lines exactly. Keep strict validation, same-directory private stages, lock, protected newest20 backups, file/directory fsync, atomic replacement, external fingerprint, persistent interrupted/critical latches and rollback tests together.
- All external writers must cooperate with the lock; stop the manager for direct maintenance. Password updates do not force disconnect existing clients. Never claim arbitrary bad-password rejection proves deletion.
- Run one waitress application process, bounded tasks and polling. Keep prod/fleet reads/writes out of tests. Real compatibility/integration proof belongs to the deployer and must be recorded separately from unit-test success.
- New UI requires preview approval and real desktop/phone visual checks. Product templates/CSS are present; never treat design previews or API markup tests as browser verification. Shapes plus words, sortable/searchable lists and progress polling are mandatory. No Test credential button.
- No commit to main; review changes in the canonical repository before publication. A branch is not a deployed artifact; read docs/verification.md and docs/deployment.md for gates.

## Test gate

Use a virtual environment with pinned `requirements-dev.txt`, then run `python -m pytest -q --cov=app`, `ruff check app tests wsgi.py`, `node --check app/static/accounts.js` and `node --test tests/ui_regressions.cjs`. Docker integration scripts are explicit and disposable; never target a live broker.
