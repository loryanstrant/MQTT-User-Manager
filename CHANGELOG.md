# Changelog

## Unreleased — 2026-11-11

- Remove the repeated “Incomplete log evidence” line from account rows at the maintainer’s request; keep observed connection status, last-seen values and API evidence flags unchanged. The single review also removes stale explanatory copy that promised an incomplete-log warning, with a page-shell regression retaining the shared observation guidance.

- Cover disposable-container cleanup after timeouts, refuse stale-main promotion to latest, and report partial registry publication explicitly with offline regression tests.

- Add a public GitHub Actions workflow that runs offline gates, builds a Linux AMD64 container, exercises startup/auth/assets with generated private test credentials in a network-isolated disposable container, then uploads that exact image to GHCR with source-revision and latest tags.
- Allowlist only the public container workflow in clean snapshots, keeping other workflow files and canonical publishing history private. Document first-upload package visibility and workflow-file credential permissions.
- Use maintainer-approved real-system screenshots for publication with private names, notes and identifiers redacted rather than substituted with synthetic data; actual captures remain pending browser access.

- Select Python 3.12 explicitly for public publication validation so pinned test dependencies match the verified development runtime.

- Add the account-to-devices icon, multi-size favicon and labelled official GitHub-mark header link.
- Publish allowlisted clean snapshots to GitHub after canonical main changes; private commit history is never mirrored. Publication requires a dedicated runtime secret and rejects private markers.

- Add per-account evidence uncertainty separately from incomplete log history. Fresh tracked connections clear the row warning; lost-history timestamps and untracked possible sessions remain qualified.
- Replace private deployment references with generic setup and verification documentation, parameterize the disposable preview harness, and preserve the project’s existing MIT license.

- Fix log-observed disconnects when the broker includes a bracketed peer address, including IPv4/IPv6, so closed sessions no longer remain connected and last seen advances correctly. Preserve shared-user sessions and internal-verifier exclusion; credential creation is not device activity.

## Initial implementation — 2026-11-10

- Quote the production tmpfs option string so Compose parses one mount; the initial deploy refused the unquoted flow-list before container creation.

- Record explicit manual browser-testing approval and a separate Dockhand production stack that cannot recreate the shared broker; initial image publication is manual, with automated CI deferred.

- Add offline-tested backend account add/change/remove with exact file validation, preserved unrelated hashes, private newest20 snapshots, atomic publication, reload verification hooks and rollback.
- Block interrupted or failed recovery transactions with persistent markers, including refused rollback over external edits; verify restored contents/metadata and fingerprint through rollback reload.
- Reclaim expired sign-ins before capacity checks and reset reconnect evidence when log coverage is lost.
- Add hashed admin login, revocable bounded sessions, CSRF/Origin checks, strict cookies, request/rate limits, secure no-cache responses and bounded operation polling.
- Add separate atomic notes and bounded log-observed presence across shared usernames, multiple client sessions, rotation/truncation and missing evidence. Internal verification clients do not invent device activity.
- Add approved searchable/sortable account screen, bounded dialogs, notes, generated/copyable passwords and sequential progress polling; unknown outcomes keep page mutations blocked.
- Wire real private-options fresh-CONNECT verifier with incorrect-password refusal, bounded retries and no secret argv. Verify root-started/droppriv broker identity using readable comm/argv/UID rather than denied exe link.
- Build and run image with real disposable HTTP add/change/remove, rollback and exact password round-trip checks; expand offline tests to125.
- In the single post-build review, invalidate stale generated-password replies after cancel/Escape/pagehide, manual edits, overlapping requests and save; clear payload password references on failed operation requests. Six synthetic JavaScript regressions pass.
- Repair disposable preview reachability using a second manager interface on the verified configured preview network; keep its broker isolated. Exact fixed script served through HTTPS and actual disposable API proof pass again. Guarded Playwright execution still fails, so visual QA and production deployment remain pending. No production restart is claimed.
