# ADR-0002: Bounded progress, private admin access, and honest observations

- Status: accepted for backend implementation
- Date: 2026-11-10

## Decision

The initial deliverable is backend-only. Product Jinja2 templates/CSS belong to the parent and require preview approval. The backend exposes JSON with shapes plus words and sorting/filtering. A screen must poll an accepted operation every 500 ms and show its progress words; it must not wait on a long blocking form response.

Run exactly **one application process**, using the provided waitress entry point. It handles four request threads and a single transaction thread, with **no operation queue**. The task result store holds at most 32 public results for 15 minutes, scoped to the initiating session nonce. Active work cannot be evicted. A second operation gets a busy response. Individual command/lock/verification stages have explicit bounds; do not introduce unbounded injectable production adapters. Process interruption is addressed by the persisted transaction marker, not by pretending the in-memory task continues.

Admin login uses a Werkzeug scrypt/PBKDF2 password hash, a mandatory private >=32-character session key, 30-minute Secure/HttpOnly/SameSite=Strict cookies, rotated CSRF, exact configured Origin on **all writes including login**, trusted host validation, and bounded rate limiting. A bounded server-side nonce registry revokes copied cookies on logout, expires after 30 minutes, and invalidates on process restart. Admin password hash version invalidates prior sessions. All API/write responses are no-store. Bodies are capped at 16 KiB; waitress adds connection/header/body/idle bounds. No proxy header is trusted. Behind a reverse proxy, login abuse limits intentionally apply to the proxy address and a global counter; this can temporarily block legitimate login during abuse, rather than allowing spoofed forwarded addresses. LAN/WireGuard and HTTPS ingress are deployment requirements, not app-granted bypasses.

Presence is only **log observation**. Parse bounded epoch/ISO connect/disconnect lines keyed by client ID and username; support multiple client sessions per username. Internal `mqtt-manager-check-` IDs are reserved/excluded from activity. Rotation, truncation/copytruncate regrowth, missing logs, restart messages, unobserved users and bounded-scan loss produce unknown/incomplete states where evidence is insufficient. Never invent keepalive activity or infer device absence from elapsed time. No periodic reconnect heuristic unless explicitly enabled by count/window and observed disconnect/connect events. Unknown state is not a disconnection; reset reconnect history whenever rotation, truncation, skipped log bytes, missing logs or session tracking overflow loses continuity. Last seen means the last observed event, with raw epoch as source and Melbourne-local display derived separately. Local logs without timezone use the configured timezone and are ambiguous at DST transitions; prefer epoch timestamps in broker configuration.

## Limits

- The app cannot prove a client is still connected now from an old log. `● Connected` means an observed connect not yet contradicted in the available log stream; the screen must retain the log-observation explanation.
- Only the configured current log file is scanned, not an unbounded rotation archive. On rotation, existing sessions become unknown until fresh evidence. Missing usernames in disconnect lines cannot recover a lost client mapping.
- Client-ID reuse follows ordered log events; a late disconnect without generation metadata cannot reliably distinguish an old connection from the replacement. Do not represent this as live socket truth.
- Tracking and reads are capped (1 MiB per scan; 10,000 clients/accounts). Incomplete flags are public. The password file and notes are capped at 2 MiB. Product templates must HTML-escape all usernames/notes/log-derived fields.
- Polling results are ephemeral and never contain the supplied/generated password. Reloading or signing out means check the account list; do not assume a task failed because polling disappeared.
- UI visual QA and disposable-broker integration remain parent work. Offline unit/integration fixtures are not deployment evidence.
