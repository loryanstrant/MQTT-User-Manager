# Verification boundaries

**Offline tests, disposable broker proof and browser checks answer different questions.** Do not treat one as evidence for another.

## Offline gate

Use pinned `requirements-dev.txt`, then run:

```sh
python -m pytest -q --cov=app --cov-report=term-missing
ruff check app tests wsgi.py
node --check app/static/accounts.js
node --test tests/ui_regressions.cjs
```

All `test_*.py` fixtures are synthetic. They cover strict file validation, preserved unrelated lines, atomic publication, locking, recovery latches, refused rollback over external changes, private adapters, authentication/session/CSRF, bounded tasks and log-evidence loss. Synthetic JavaScript tests cover stale password-generation responses and unknown operation outcomes. Coverage is not proof that every branch or browser state was exercised.

## Disposable integration evidence

The initial implementation was exercised with an actual container and Mosquitto binary 2.1.2: HTTP login/add/change/remove, fresh credential checks, rejection of an old password and a known-valid deleted credential, preservation of unrelated lines, private snapshots, exact rollback and first add to an existing empty file. Whitespace, quotes, backslash and Unicode passwords passed the private-options adapter. A synthetic established subscriber received messages through three reloads without reconnecting.

These results are not a universal compatibility guarantee: rerun on the final upstream image and selected listener. `tests/prove_broker.py`, `tests/scratch_rig.py` and `tests/container_api_proof.py` are explicit disposable Docker scripts, never a production test gate. Do not copy real password hashes into them. Supply scratch secrets privately and clean up every resource and local credential file.

## Presence evidence

The tracker handles plain and address-bearing IPv4/IPv6 disconnects and multiple sessions per account. Internal `mqtt-manager-check-` clients do not count as device presence. Log rotation/truncation, missing files, skipped scan bytes and memory limits invalidate continuity; old timestamps may remain but do not prove present connectivity.

`log_incomplete` reports whole-history coverage. `presence_uncertain` reports whether the row should carry an evidence warning. A fresh tracked connection can clear that warning without claiming all history was recovered or that the reported count includes unseen parallel sessions. After the last tracked disconnect with incomplete history, the warning returns. Client IDs containing whitespace are not reliably represented by the current parser.

## Browser and production boundaries

Initial browser automation did not execute successfully. A maintainer subsequently confirmed the deployed page worked and created accounts; broker logs and file comparisons confirmed accepted fresh credentials and unchanged pre-existing account lines. This manual production evidence is not an automated desktop/narrow screenshot or exhaustive existing-client continuity check.

Publication screenshots must show the actual running product. The maintainer requested real-system captures on 2026-11-11: redact private deployment identifiers, usernames and notes without fabricating states, and never capture exposed passwords. Label redaction explicitly. Design previews must be labelled as proposals and must not be used as README product screenshots. Verify login/list/search/sort/no-match/notes/add/change/remove and relevant error states at desktop and narrow width before claiming interactive browser coverage.
