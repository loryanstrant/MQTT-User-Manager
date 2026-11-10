# ADR-0003: Private client proof and approved account screen

- Status: implemented; production release awaiting visual/deployment gates
- Date:2026-11-10

## Decision

Preserve approved single-table desktop screen with always-visible actions, search, column sort and editable notes. Narrow width keeps a bounded horizontally scrollable table as explicitly approved; no phone app/parity. Native dialogs bound height, labelled controls, textContent for server-derived strings, shapes plus words, sequential500ms progress polling, no password browser persistence. Unknown operation outcomes block mutation controls in the page; refresh requires inspecting account/recovery state, not blindly replaying.

Wire production `FreshConnectVerifier` to actual Mosquitto2.1.2 `-o` private0600 ephemeral UTF-8 options. Password never enters argv, stdout/log/result output or persistent client config. Require rc0 plus explicit CONNACK0; refuse a listener accepting random incorrect credential. Bound total retry deadline8s and individual process1.5s. Exclude reserved verification IDs from presence. Local Docker-network port1883 is not encrypted; don't use across untrusted networks.

Root-started/droppriv Mosquitto is non-dumpable to sameUID for `/proc/1/exe`. Use readable `comm`, exact executable argv and all UID fields, refuse ownPID1, then sameUID SIGHUP. Verified actual reloader in isolated production-like root-started broker; signal delivery is not synchronous acknowledgment.

## Limits and evidence

Exact whitespace/quotes/backslash/Unicode options roundtrip tested on real2.1.2 client; reverify on upstream changes. Incorrect-credential refusal guards anonymous/fallback false positives but does not prove endpoint identity, every policy or encrypted transport. Deployment must verify exact listener/password-file configuration. Uncooperative-writer race and password-change existing-session continuity remain as documented in ADR0001.

Real HTTP container integration and rollback passed;125 Python tests passed. The single post-build review added six synthetic asynchronous UI regressions, fixed stale password-generation replies with revision guards and cleared submitted password references on every exit. Scratch HTTPS reachability and exact served product script now pass using a second interface on the disposable manager; broker isolation is retained. Browser execution still fails at guarded discovery, so no interactive/layout pass or production deployment is claimed. Approval images are proposals only. See docs/verification.md. No broker restart authorised.
