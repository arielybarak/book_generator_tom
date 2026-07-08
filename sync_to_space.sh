#!/usr/bin/env bash
# Sync the library + config from the main repo into the HF Space submodule.
#
# The HF Space (hf_space/) must be self-contained, so it vendors a COPY of src/
# and config.yaml. Run this after changing any src/ module or config.yaml that
# the app uses, then commit + push from inside hf_space/ to redeploy.
#
# Usage:  ./sync_to_space.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPACE="$ROOT/hf_space"

if [ ! -d "$SPACE" ]; then
    echo "error: $SPACE not found (is the hf_space submodule checked out?)" >&2
    exit 1
fi

# src/ → hf_space/src/  (mirror; --delete removes files dropped from src/; skip caches)
rsync -a --delete --exclude='__pycache__' "$ROOT/src/" "$SPACE/src/"

# config.yaml → hf_space/config.yaml
cp "$ROOT/config.yaml" "$SPACE/config.yaml"

echo "Synced src/ and config.yaml → hf_space/"
echo "Next: cd hf_space && git add -A && git commit -m 'sync' && git push"
