# ADR-0004: Publish clean snapshots without private history

- Status: accepted for implementation
- Date: 2026-11-11

## Decision

Keep the maintainer's canonical history private. Publish only allowlisted, cleaned current files as new commits on the existing public GitHub `main` history. Do not configure a full-history push mirror, force-push, prune public branches/tags or export canonical `.git` metadata. Preserve the existing public MIT license exactly and stop if it differs.

Publication runs only from canonical `main`, after a reviewed merge, or an explicit main-only manual workflow dispatch. Export the committed tree, not dirty working files. Keep internal workflow/scripts and publication audit fixtures private. Product, docs, generic examples and ordinary tests are public. Reject symlinks/special entries, known private deployment markers and common private-key/token markers before writing any export. This gate is not an exhaustive secret scanner: review remains required, especially for images and metadata.

Use a repository CI secret for GitHub access, never a credential URL, app setting or committed value. Disable git credential helpers for public transport; provide the token through an ephemeral askpass helper and environment. Suppress transport output, stop on license divergence or non-fast-forward races, and remove the disposable publication directory on exit. Do not retry uncertain pushes automatically.

## Consequences

- Public commits have different identifiers and contain no private source ancestry. A generic source-revision prefix identifies each snapshot without copying private commit messages or metadata.
- Only reviewed main snapshots are published; feature branches and canonical tags are not mirrored. GitHub remains a publication target, not the code-review/merge location.
- Public-source cleanup does not remove private historical details from the canonical repository. Those remain private by design.
- Publication screenshots must be actual running-product captures, not design previews. On 2026-11-11 the maintainer explicitly requested captures from the real deployed system instead of synthetic accounts. Redact private account names, notes, deployment addresses and identifiers without inventing states or replacing data with samples; label the redaction. Never capture exposed passwords. Browser verification and release/deployment are separate gates.
- Only `.github/workflows/container.yml` is additionally allowlisted for public container publishing. Other workflows and all private publication machinery remain excluded.
- Publication validation selects Python 3.12 explicitly to match the verified pinned development dependencies, rather than relying on the runner's default Python.
- Disable the workflow or remove its repository secret to stop automatic publication. Use the least-privileged repository-scoped credential available; an existing broader credential should be replaced with a dedicated token when one is provisioned.
