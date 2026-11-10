# MQTT-User-Manager engineering rules

Read README.md, docs/api.md, and both ADRs before editing. Read whole source files; do not infer behavior from fragments. Follow dev-standards core/infrastructure/secrets/generic/ux.

- No Docker socket or Docker/host management APIs in the app. Same-UID broker PID namespace signalling only after identity verification. Broker network host is explicitly `mosquitto`, not localhost.
- Never log password/command arguments, raw hashes/config values, request bodies or exception tracebacks from command/client adapters. Public exceptions are deliberately sanitized. Fixtures are synthetic only.
- Preserve unrelated password-file lines exactly. Keep strict validation, same-directory private stages, lock, protected newest20 backups, file/directory fsync, atomic replacement, external fingerprint, persistent interrupted/critical latches and rollback tests together.
- All external writers must cooperate with the lock; stop the manager for direct maintenance. Password updates do not force disconnect existing clients. Never claim arbitrary bad-password rejection proves deletion.
- Run one waitress application process, bounded tasks and polling. Keep prod/fleet reads/writes out of tests. Real compatibility/integration proof belongs to the parent/deployer and must be recorded separately from unit-test success.
- New UI requires preview approval and real desktop/phone visual checks. Product templates/CSS are present; never treat design previews or API markup tests as browser verification. Shapes plus words, sortable/searchable lists and progress polling are mandatory. No Test credential button.
- No commit to main; private Gitea PR when the final repository is available. Current branch is not deployed or released; read docs/verification.md and docs/deployment.md for gates.

## Test gate

Persistent scratch venv: `/data/venvs/mqtt-user-manager-scratch/bin/python -m pytest -q --cov=app`.
In a real git worktree, use `devenv` with pinned requirements-dev.txt, then `python -m pytest -q --cov=app` and `ruff check app tests wsgi.py`.
