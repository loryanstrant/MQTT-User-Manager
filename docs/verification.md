# Verification receipt — 10 November 2026

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

## Review outcome

Bounded consultant review identified unknown-result unlock, password serialization and listener-policy proof concerns. Page keeps mutation controls blocked on unknown result rather than enabling Save after timeout; exact serialization tested with actual client; verifier refuses an incorrectly accepted random password. Polling is sequential. Endpoint policy/identity and refresh/cross-tab behavior still need deployment/browser checks. The consultant opinion was not execution evidence.
