#!/usr/bin/env bash
# Run only with trusted canonical main; never force-push private history.
set -euo pipefail
set +x
: "${PUBLIC_GITHUB_TOKEN:?Provide the publication credential through CI secrets}"
: "${PUBLICATION_SCRATCH:?Provide a disposable worktree-relative scratch directory}"
repo=$(git rev-parse --show-toplevel)
revision=$(git rev-parse HEAD)
case "$PUBLICATION_SCRATCH" in /*|*..*) echo 'Use a worktree-relative scratch directory' >&2; exit 1;; esac
scratch="$repo/$PUBLICATION_SCRATCH"
if test -e "$scratch"; then echo 'Publication scratch must not already exist' >&2; exit 1; fi
umask 077
mkdir -p "$scratch"
trap 'rm -rf -- "$scratch"' EXIT
python3 "$repo/scripts/public_snapshot.py" "$scratch/export" --repo "$repo" --revision "$revision"
cat > "$scratch/askpass" <<'ASKPASS'
#!/bin/sh
case "$1" in *Username*) printf '%s\n' 'x-access-token';; *Password*) printf '%s\n' "$PUBLIC_GITHUB_TOKEN";; *) exit 1;; esac
ASKPASS
chmod 700 "$scratch/askpass"
export GIT_ASKPASS="$scratch/askpass" GIT_TERMINAL_PROMPT=0
target=https://github.com/loryanstrant/MQTT-User-Manager.git
# A local-only target permits end-to-end offline proof, never alternate network hosts.
if test -n "${PUBLICATION_OFFLINE_TEST_TARGET:-}"; then
    case "$PUBLICATION_OFFLINE_TEST_TARGET" in "$repo"/*) ;; *) echo 'Offline target must be inside the test repository' >&2; exit 1;; esac
    test -d "$PUBLICATION_OFFLINE_TEST_TARGET" || exit 1
    target="$PUBLICATION_OFFLINE_TEST_TARGET"
fi
# Suppress adapter output: credentials must never enter error or command logs.
if ! git -c credential.helper= clone --quiet --single-branch --branch main \
    "$target" "$scratch/public" \
    >"$scratch/transport.log" 2>&1; then echo 'Public clone failed; transport output withheld' >&2; exit 1; fi
if ! cmp -s "$scratch/export/LICENSE" "$scratch/public/LICENSE"; then
    echo 'Public license differs; review before publication' >&2; exit 1
fi
# Only replace the public working tree, retaining its existing public .git history.
find "$scratch/public" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf -- {} +
cp -a "$scratch/export/." "$scratch/public/"
git -C "$scratch/public" add -A
if git -C "$scratch/public" diff --cached --quiet; then echo 'Public snapshot already current'; exit 0; fi
git -C "$scratch/public" -c user.name='Project publisher' \
    -c user.email='publisher@users.noreply.github.com' commit --quiet \
    -m "Publish clean source snapshot ${revision:0:12}"
# Plain push fails on races; no forced update, branch pruning or private refs.
if ! git -C "$scratch/public" -c credential.helper= push --quiet origin HEAD:main \
    >"$scratch/transport.log" 2>&1; then echo 'Public push failed; transport output withheld' >&2; exit 1; fi
echo 'Published clean public snapshot'
