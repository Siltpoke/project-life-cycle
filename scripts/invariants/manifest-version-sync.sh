#!/usr/bin/env bash
# Invariant: the 3 SemVer plugin manifests carry an identical .version (a partial
# release bump is the failure this catches). Antigravity (version-less) + codex
# (own X.Y.Z+codex.<stamp> scheme) are deliberately out of the synced set.
set -euo pipefail
vers=""
for d in .claude-plugin .qoder-plugin .codebuddy-plugin; do
  if [ ! -r "$d/plugin.json" ]; then
    echo "FAIL manifest-version-sync: missing/unreadable $d/plugin.json"
    exit 1
  fi
  # `|| v=__ERROR__` keeps set -e from aborting on malformed JSON (jq non-zero);
  # 2>/dev/null hides jq's raw stderr so the verdict line is the only output.
  v=$(jq -r '.version // "null"' "$d/plugin.json" 2>/dev/null) || v="__ERROR__"
  if [ "$v" = "__ERROR__" ]; then
    echo "FAIL manifest-version-sync: $d/plugin.json is not valid JSON"
    exit 1
  fi
  if [ "$v" = "null" ] || [ -z "$v" ]; then
    echo "FAIL manifest-version-sync: $d/plugin.json has no .version"
    exit 1
  fi
  vers="${vers}${v}"$'\n'
done
uniq_vers=$(printf '%s' "$vers" | sort -u)
n=$(printf '%s' "$uniq_vers" | grep -c . || true)
if [ "$n" -ne 1 ]; then
  echo "FAIL manifest-version-sync: the 3 manifests' versions diverge:"
  echo "$uniq_vers"
  exit 1
fi
echo "PASS manifest-version-sync: all 3 manifests at $uniq_vers"
