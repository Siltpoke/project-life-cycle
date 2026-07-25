#!/usr/bin/env bash
# Invariant: no git-tracked iCloud " 2" conflict copies (a recurring corruption
# seen on iCloud-synced checkouts — the daemon spawns ' 2' duplicates that corrupt
# refs/objects/index). grep exits 1 on no-match; `|| true` keeps set -e from aborting.
set -euo pipefail
hits=$(git ls-files | grep -E ' 2(\.| |/|$)' || true)
if [ -n "$hits" ]; then
  echo "FAIL no-icloud-conflict-copies: tracked ' 2' conflict copies:"
  echo "$hits"
  exit 1
fi
echo "PASS no-icloud-conflict-copies: no tracked ' 2' conflict copies"
