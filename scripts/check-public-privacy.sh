#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUDITOR="$ROOT/scripts/audit_public_repo.py"
BLOCKLIST=""

cleanup() {
  if [ -n "$BLOCKLIST" ]; then
    rm -f "$BLOCKLIST"
  fi
}
trap cleanup EXIT

args=(--repo "$ROOT")
if [ -n "${PUBLIC_PRIVACY_BLOCKLIST_B64:-}" ]; then
  BLOCKLIST="$(mktemp "${TMPDIR:-/tmp}/public-privacy.XXXXXX")"
  chmod 600 "$BLOCKLIST"
  if ! python3 -c \
    'import base64, os, sys; sys.stdout.buffer.write(base64.b64decode(os.environ["PUBLIC_PRIVACY_BLOCKLIST_B64"], validate=True))' \
    > "$BLOCKLIST"
  then
    echo "privacy gate could not decode PUBLIC_PRIVACY_BLOCKLIST_B64" >&2
    exit 2
  fi
  args+=(--blocklist "$BLOCKLIST")
fi

python3 "$AUDITOR" "${args[@]}"
