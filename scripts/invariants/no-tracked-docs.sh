#!/usr/bin/env bash
# Invariant: nothing under docs/ is git-tracked.
set -euo pipefail
tracked=$(git ls-files docs/)
if [ -n "$tracked" ]; then
  echo "FAIL no-tracked-docs: tracked file(s) under docs/:"
  echo "$tracked"
  exit 1
fi
echo "PASS no-tracked-docs: docs/ has no tracked files"
