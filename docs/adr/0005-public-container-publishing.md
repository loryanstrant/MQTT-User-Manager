# ADR-0005: Publish the tested public image through GitHub

- Status: implemented; first live publication and public pull await reviewed merge
- Date: 2026-11-11

## Decision

Publish containers through the public GitHub repository to `ghcr.io/loryanstrant/mqtt-user-manager`. This workflow is the only `.github` file allowed through the clean canonical snapshot exporter. It runs on public `main` pushes or manual main dispatch, never against unreviewed pull-request code with package-write credentials. Public source has no private canonical ancestry.

Run pinned offline dependencies and existing Python/lint/JavaScript gates first. Build a Linux AMD64 image once, load it locally, and exercise that exact image before registry login or upload. The explicit smoke script creates randomly named disposable containers with no external network, host mounts, broker PID namespace or published ports. Generated test credentials stay in private temporary files/stdin and are removed. Verify process UID, read-only root, explicit client binaries, liveness, exact served asset hashes, anonymous account refusal, login, wrong-Origin mutation refusal and revoked-cookie logout. It never contacts production and makes no live broker compatibility claim.

Only the publish job receives `packages: write`, using GitHub's automatic `GITHUB_TOKEN`; checkout keeps no credential helper state. Pin executable third-party actions to resolved commit revisions. Add public OCI source/revision/license labels and push the exact tested image first as `sha-<full-public-commit>`, then as `latest`. Serialize main publishes and check the current public main tip immediately before promotion so stale manual reruns do not roll back the moving tag. The revision and latest uploads are not atomic: a revision may already be available when latest fails. Record each outcome in the job summary and inspect registry state before any manual rerun; an upload failure is not automatically replayed.

## Boundaries

- The canonical snapshot token needs permission to update the one public workflow file. It is not exposed to GitHub Actions, image layers or public source.
- GHCR package visibility/access must be checked separately after first publication. A public repository does not prove an anonymous image pull works. An existing unlinked package may need explicit Actions access.
- The first upload, remote digest, source labels and anonymous pull require live verification after merge. A local build or green offline workflow contract test is not upload evidence.
- Only Linux AMD64 is built/tested. ARM images and provenance attestations are not claimed. Broker integration and deployment remain separate approval/verification gates.
- Latest tracks successful public snapshots; revision tags support exact-artifact deployment. No automatic fleet deployment or broker restart is introduced.
