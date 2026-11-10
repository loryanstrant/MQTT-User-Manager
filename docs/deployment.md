# Deployment checkpoint

**You explicitly approved merge/deployment without agent visual QA on 10 November 2026 at 23:57 AEDT and will test the page yourself.** Browser verification remains unverified, not passed. Restarting Mosquitto is not approved.

## Approved deployment path

Deploy a separate `mqtt-users` Dockhand stack using `compose.production.yaml`, with the existing `mosquitto_default` external network and `pid: container:Mosquitto`. The broker stack is not edited or deployed; this avoids image/config drift recreating the broker. Bind the manager port only to loopback for METROPLEX's host-network Caddy. Check the resolved compose contains only the manager before deploying with pull/build/force-recreate disabled.

Publish a source-revision-labelled, commit-addressed image manually for this initial deployment and verify the pulled image on METROPLEX. Automated CI publishing is deferred; it is not silently claimed to exist. The existing offline release gate remains required.

Back up the root-owned password file privately, verify exact bytes and mode, and change only its UID to 1883 (GID1883/mode0640 unchanged). Retain the protected pre-provision snapshot and broker identity/log baseline. There is no account creation or reload during provisioning. Production add/change/delete tests are deferred to your page test; no existing credential is rotated.

DNS and HTTPS routing must still go through AdGuard/CaddyUI. If named MCP access fails at guarded discovery, leave routing pending rather than bypass the registry or directly modify Caddy. A running manager without its HTTPS route is a partial deployment, not a usable page.

Broker replacement/restart later requires a deliberate manager redeploy to rejoin its new PID namespace; do not restart the broker for this deployment.

## Verified current facts

Read-only checks on10 November2026: Dockhand environment5 METROPLEX, stack/service key `mosquitto`, container `Mosquitto` running, zero restarts. Account file `/home/docker/Mosquitto/config/passwords` root:1883 mode0640, directory1883:1883. Broker PID1 `/usr/sbin/mosquitto`, all UIDs1883; `comm` and `cmdline` readable, `exe` link denied. Port8090 unoccupied at check time. Re-check before deploying.

Admin credential created in Vaultwarden organisation Strant Family, collection LS Development, item **MQTT User Manager - admin**. Browser/test credential must use that item's placeholder, not Rufus's unrelated test login. Production runtime gets hash/session secret through Dockhand secret variables; values never enter repo/compose/transcript. No provider binding has occurred.

## Earlier checkpoint (before the manual-testing approval)

1. Restore named Playwright execution through supported wiring; do not bypass registry on guarded failure. The scratch HTTPS network path and exact served script passed in the single post-build review, but the browser call failed before navigation. Start the disposable rig again and exercise login/list/search/sort/no-match/notes/add/change/remove, desktop1440 and narrow380. Save screenshots in `_IMAGES/`; design previews and synthetic JavaScript tests are not built-screen QA.
2. Verify active Gitea runner/build conventions, add tested CI/image workflow and publish commit-addressed image. Prove METROPLEX pull of that exact artifact. Draft PR is not a release.
3. Resolve existing root-owned account file intentionally: protected metadata/content backup on METROPLEX, broker-owned1883:1883 with mode unchanged and private byte comparison. Current manager refuses root ownership; don't give it root/chown capability or remove its safety check to avoid provisioning. This prerequisite was not applied.
4. Privately retrieve/update existing Dockhand compose, keeping broker service untouched. Add `mqtt-users`/`MQTT-Users`, `pid:service:mosquitto`, port8090 to8080, full config-directory mount, log read-only, private data directory, read-only root/tmpfs/no-new-privileges/cap_dropALL and secret-backed settings. Configure `MQTT_PASSWORD_FILE=/mosquitto/config/passwords`. No Docker socket. Inspect dry-run/equivalent proof: existing broker image/config hash drift could cause recreation even with `forceRecreate:false`; flags alone do not prove safety. Prefer service-scoped supported deploy; if unavailable stop rather than experiment on prod. No stack-wide image pull.
5. Through AdGuard/CaddyUI only, provide `mqtt-users.strant.casa` with LAN/WireGuard access and HTTPS on METROPLEX's verified Caddy. Then create/change/remove only a disposable test account through page and prove fresh logins; compare every existing account line privately, broker ID/image/StartedAt, and client log baseline including HA/Z2M/SolarEdge/ESPHome/monitoring. Ask for visible page confirmation. Keep observation gaps honest; naturally periodic connections are not automatically regression failures.

Any necessary shared-service restart requires a separate explicit OK naming impact before action. Current scratch network error is not a reason to restart the production broker or Caddy. No public exposure, no existing credential rotation, no dynamic-security migration.
