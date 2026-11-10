# Backend API contract

The approved account screen is served at `/` with external local CSS/JavaScript. The page shell is public; account data and operations require admin sign-in. Final interactive browser checks are still pending; see verification.md.

## Sign-in sequence

1. `GET /auth/csrf`: `{csrf_token}`. Signed private cookie, no-store.
2. `POST /auth/login`: JSON `{username,password}`, exact `Origin: <PUBLIC_ORIGIN>` and `X-CSRF-Token`. Returns `{authenticated:true,csrf_token}` with a rotated token/session nonce.
3. Use the rotated token plus exact Origin on **every** POST/PUT/PATCH/DELETE. Cookie auth is required for all account APIs. Never put passwords/tokens in query strings.
4. `GET /auth/session`: `{authenticated,username,csrf_token}`. `POST /auth/logout` revokes the server-side nonce and clears the cookie.

## Account table

`GET /api/accounts?q=&status=all&sort=username&direction=asc`

- Search matches username and note, case-insensitively, at most 256 characters.
- Status: `all`, `connected`, `disconnected`, `unknown`, `reconnecting` (last one disabled by default unless configured observation criteria are met).
- Sort: `username`, `note`, `status`, `last_seen`; direction `asc`/`desc`. Username ascending is the deliberate default/tie-break.
- Response: `{accounts,total,count,critical,message}`; account fields are `username`, `note`, `protected`, `status`, `status_label`, `connections`, `last_seen` (ISO UTC or null), `last_seen_local` (Melbourne/AEDT display or null), `log_incomplete`, `presence_uncertain`, `source:"log observation"`.
- Shapes/words: `● Connected`, `○ Disconnected`, `○ Unknown`, `◐ Reconnecting`. Show the log-observation explanation; these are not live socket checks. `critical` means account writes are blocked pending recovery. `log_incomplete` reports history coverage, not per-row uncertainty. `presence_uncertain` controls the row warning: fresh tracked connections clear it, but retained timestamps after gaps do not. With incomplete history, the last tracked disconnect cannot exclude unseen parallel sessions, so the warning returns. A reported connection count includes only tracked sessions, not a complete live broker count. Older clients may keep displaying the broader history warning.
- Adding/changing an account proves the credential through a short internal connection, but does **not** configure or connect the device. Reserved `mqtt-manager-check-` connections are excluded from presence and last seen. A new account remains `○ Unknown` with null last seen until a non-verification client event is observed. The page refreshes this list every 15 seconds while signed in with no dialog/operation active.
- Disconnect observation accepts both `Client <id> disconnected.` and `Client <id> [<address>:<port>] disconnected.` formats; no old connected state is retained just because the broker includes its peer address. Current connect/disconnect parsing requires client IDs without whitespace; clients using IDs with spaces are not reliably represented.

## Generated passwords and notes

- `POST /api/passwords/generate`: `{password}`. Cryptographically generated 32-character URL-safe password, never retained in results/cookies. Display it only in the edit/add flow, allow override, never analytics/log/localStorage caching. Add/change submission requires the chosen password; the server does not silently generate one the browser has not received.
- Passwords: 12–256 characters, no control characters. Username: 1–128 ASCII letters/numbers/underscore followed by letters/numbers/dot/underscore/@/hyphen; no leading option or path syntax.
- `PUT /api/accounts/<username>/note`: JSON `{note}`; response `{username,note,message}`. At most 2,000 text characters, empty removes the separate note. Notes are descriptions, never credentials.

## Account operations and progress

`POST /api/operations`: JSON `{action:"add"|"change"|"delete",username,password?,note?}`.

- Password required for add/change. Delete never tests an invented password. Protected-account deletion is refused before scheduling.
- Accepted response: HTTP202 `{id,status:"running",label:"◐ Working",poll_url,poll_after_ms:500}`. Display a working shape/spinner plus returned words. Poll every 500ms until terminal state; no dead form-posts.
- `GET /api/operations/<id>` returns `{id,status,label,message,...}`. Running messages describe checking/preparing/applying/fresh-connect/restoring/note-save stages.
- Terminal status: `succeeded` / `failed` / `critical`. Success includes `username`, `action`, message and optional `warning` for a separate note failure. Failed includes public `error` and message; no password, raw hash, command arguments or traceback.
- One in-flight operation, no waiting queue; another gets busy409. Retention32 public results/15 minutes, initiating-session scoped. Refresh/logout/restart can make a result unavailable; inspect the account list rather than infer failure.
- Account removal or password change does **not** disconnect established clients. Delete only confirms exact file removal and reload signal, not a forced logout or synchronous broker acknowledgment.

## Error and operational contracts

Errors use `{error,message}`. Common HTTP codes: 400 invalid request/account/file, 401 sign-in required, 403 Origin/CSRF, 404 missing/result expired, 409 busy/duplicate/external writer, 413 request too large, 429 abuse limit, 503 critical recovery. Anonymous `/healthz` is **liveness only**, `{status:"ok"}`; it deliberately does not expose broker state.

Bodies <=16KiB, TLS required outside tests, trusted host from configured PUBLIC_ORIGIN, no forwarded-header trust. The CSP allows only same-origin external scripts/styles: use external assets rather than inline script/style. Product templates must escape all account/notes/presence text. UI screenshots and real disposable-broker integration are not covered by synthetic Flask test-client fixtures.
