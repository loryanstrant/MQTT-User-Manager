# Verification receipt

## Presence diagnosis and fix — 11 November 2026

- Read-only METROPLEX checks at approximately 07:54 AEDT: manager can read the correctly mounted broker log; both containers are running with unchanged start times and zero restarts. The current log has one successful internal verifier connection and no non-verifier device connections for each of `living-room-tv`, `bedroom-tv` and `garage-tv`. Blank device last seen is therefore expected, not a failed account addition. The current log is not an unlimited connection archive.
- Reproduced a separate tracker defect: deployed disconnect parser ignores bracketed peer addresses, leaving observed sessions connected. Thirteen new synthetic cases failed before the fix. Fixed bounded optional-address parsing; 138 Python tests pass with 92% app coverage, ruff/JavaScript syntax/diff checks pass, and all six existing synthetic page regressions pass. Independent bounded consultant review reported no blocking issue; it did not execute tests.
- Actual log-format read-only comparison: old regex matches zero of 11,158 candidate disconnect events; corrected regex matches 11,155. The three remaining events have whitespace-containing client IDs, which both existing connect/disconnect tracking exclude. That pre-existing limitation is not fixed here. No live log or password material was copied into tests.
- Corrected parser was exercised in a separate temporary Python process inside the existing manager, reading logs only; the running application was not patched or restarted. Internal verifier exclusion remains intact. This source fix is not deployed yet. No authenticated account mutation, broker reload/restart or connected-client disruption occurred during diagnosis. Browser verification remains as previously deferred; no screen markup or JavaScript changed.

## Initial verification — 10 November 2026

## Proven in this session

- Full imported backend source, tests, API/recovery docs and ADRs reviewed. Child handoff accepted and archived; its114 synthetic tests passed independently after import.
- Expanded suite:125 tests passed, app92% coverage. Ruff and JavaScript syntax checks passed. Coverage does not prove all behavior. No browser test runs in pytest.
- Docker image built and booted on live-verified PERCEPTOR. UID/GID1883, read-only root, dropped capabilities, bounded tmpfs; Alpine tools and Melbourne zone available.
- Actual HTTP inside disposable manager: sign-in, unauthenticated API refusal, template served, add/change/delete; old password rejected, deleted previously-valid password rejected, unrelated file lines unchanged and existing account fresh login accepted. Private backup files retained, live account mode0640. Receipt `_IMAGES/mqtt-container-api-proof.json` in session c204b6db2dbf (scratch, not committed).
- Forced actual verifier failure restored exact original bytes/mode, reloaded and cleared pending. First add to existing empty file succeeded without creation flag. Six password cases with leading/trailing/interior spaces, quotes/backslash/hash, Unicode and all-spaces passed the exact private-options adapter on disposable broker2.1.2.

Earlier saved mechanics proof: add/change/remove across three reloads, established synthetic subscriber received every message with only one CONNACK, broker identity unchanged, unrelated hash unchanged and file0640. Saved `_IMAGES/mqtt-mechanics-proof.json`; recovered full proof code before relying on it. No production credential material was copied.

## Not verified / not deployed

Playwright `browser_run_code_unsafe` failed at guarded discovery on this turn; no navigate, login, click or screenshot execution is claimed and the uncertain call was not replayed. The scratch HTTPS proxy answered502 because it could not reach the manager's isolated network from Rufus network namespace. Direct inside-container HTTP is **not** proof the page is browser reachable or correctly laid out.

No built-screen screenshots. The approved saved images remain **design previews only**. Desktop and380px interaction/layout checks, clipboard behavior, cross-tab/refresh unknown-outcome handling and browser network-error tests remain required.

Production Mosquitto identity, image, StartedAt and restart count matched before/after this work. Only read-only live checks ran. Password file remains root:1883 mode0640, config directory1883:1883; manager currently requires broker-owned file, so provisioning must intentionally resolve this without weakening checks. No new production account, route, secret stack binding, image push or stack deployment occurred.

## Single post-build review — 10 November 2026

Read the complete committed diff and all changed source/tests/docs; no uncommitted changes existed at entry. Applied the review/verify checklist, including the impact sweep (19 Python files parsed, none unparsed). Its capped symbol/consumer lists and non-Python files were covered by direct full-file reading. Code-graph execution failed at guarded discovery, not a proved absence of an index.

- Confirmed and fixed delayed generated-password replies repopulating cleared fields or replacing a newer password choice. Revision guards invalidate on manual input, clearing/dismissal, overlapping generation and operation start; stale errors are ignored. Submitted payload password references clear in `finally`, including unknown start outcomes. Bounded independent consultant opinion was grounded by synthetic execution, not treated as a test result.
- Six complete-product-script synthetic DOM/async regressions failed before the fix and pass after it: cancel/Escape/pagehide, manual override, out-of-order replies, reopened dialog/stale errors, unknown-operation clearing/locking, and closed/note editor refusal. These are not browser layout evidence. Run `node --test tests/ui_regressions.cjs`.
- Full offline gate:125 Python tests,92% app coverage, ruff clean and JavaScript syntax clean. Rebuilt image `e8b23b562458` ran the actual disposable HTTP add/change/delete proof again, refusing old and deleted known-valid credentials, preserving every unrelated line and mode0640; receipt `_IMAGES/mqtt-post-review-api-proof.json` in session c204b6db2dbf.
- Fixed scratch network path: Rufus already reserves8700–8719, so a separate publication failed before proxy start. The disposable manager now joins the verified Rufus preview network in addition to its broker network; its broker remains isolated and neither exposes a host port. A scratch Caddy process sharing Rufus's existing preview namespace serves the manager by network name. HTTPS liveness and byte-for-byte served fixed `accounts.js` passed. No shared Caddy route/config changed.
- Playwright execution again failed at guarded discovery before navigation. No login, interaction, screenshots, clipboard, cross-tab/refresh or layout execution is claimed, and the uncertain call was not replayed. All disposable containers, network, volume and local credential/env files were removed. Production was not accessed or changed during this review.

Deferred unchanged: real desktop/380px browser checks, production ownership provisioning, CI/registry artifact and broker-preserving deployment. The documented uncooperative-writer race remains an explicit maintenance constraint, not silently weakened. No second review pass was run.

## Earlier build review outcome

Bounded consultant review identified unknown-result unlock, password serialization and listener-policy proof concerns. Page keeps mutation controls blocked on unknown result rather than enabling Save after timeout; exact serialization tested with actual client; verifier refuses an incorrectly accepted random password. Polling is sequential. Endpoint policy/identity and refresh/cross-tab behavior still need deployment/browser checks. The consultant opinion was not execution evidence.
