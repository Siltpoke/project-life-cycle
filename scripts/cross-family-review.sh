#!/usr/bin/env bash
# cross-family-review.sh — cross-family blind-2nd-agent adapter.
#
# Runs the brainstorm's blind 2nd agent on a DIFFERENT CLI family (codex) for
# genuine lineage diversity. Armed-optional: this script is invoked ONLY when
# `second-agent-family: foreign:codex` is armed. It is FAIL-SAFE — every failure
# path degrades to `status:fallback` (the caller then runs today's same-family
# subagent) and the script ALWAYS exits 0. A foreign reviewer that is missing,
# unauthed, slow, or broken must never block or corrupt the brainstorm.
#
# Trust boundary: `-s read-only` is a FILESYSTEM sandbox, NOT privacy isolation.
# The caller must pass a SYNTHESIZED decision packet (question + options +
# research), never raw workspace access, and must have taken arm-time consent
# for cross-provider data flow. See references/cross-family-review.md.
#
# Usage: cross-family-review.sh --family codex --packet <file> --out <file> [--timeout 120]
# Emits <out>: {"engine","status","pick"|null,"fallback_reason"|null}
#   status ∈ {succeeded, fallback}
#   fallback_reason ∈ {unsupported-family, not-installed, not-authed,
#                      spawn-failed, unparseable, timed-out}
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA="${SCRIPT_DIR}/cross-family-review.schema.json"

FAMILY="" PACKET="" OUT="" TIMEOUT="120"
while [ $# -gt 0 ]; do
  case "$1" in
    --family)  FAMILY="$2";  shift 2;;
    --packet)  PACKET="$2";  shift 2;;
    --out)     OUT="$2";     shift 2;;
    --timeout) TIMEOUT="$2"; shift 2;;
    *) shift;;
  esac
done

# Emit a result JSON to --out (atomic) and exit 0. $1=status $2=reason $3=pick-file(optional)
emit() {
  local status="$1" reason="$2" pickfile="${3:-}"
  local tmp="${OUT}.tmp.$$"
  if [ "$status" = "succeeded" ] && [ -n "$pickfile" ]; then
    jq -n --slurpfile pick "$pickfile" \
      '{engine:"foreign:codex", status:"succeeded", pick:$pick[0], fallback_reason:null}' > "$tmp"
  else
    jq -n --arg r "$reason" \
      '{engine:"foreign:codex", status:"fallback", pick:null, fallback_reason:$r}' > "$tmp"
  fi
  mv -f "$tmp" "$OUT"
  exit 0
}

# --- Gate 0: family supported (only codex is BUILT; others are design-only) ---
[ "$FAMILY" = "codex" ] || emit fallback "unsupported-family"

# --- Gate 1: binary installed + not a project-local shim -------------------
BIN="${CODEX_BIN:-codex}"
RESOLVED="$(command -v "$BIN" 2>/dev/null || true)"
[ -n "$RESOLVED" ] && [ -x "$RESOLVED" ] || emit fallback "not-installed"
# Reject a binary resolved from inside the current git repo tree (shim spoofing).
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
case "$RESOLVED" in
  "$REPO_ROOT"/*) [ -n "$REPO_ROOT" ] && emit fallback "not-installed";;
esac

# --- Gate 2: authed (noninteractive probe) ---------------------------------
# codex writes auth status to STDERR (verified codex-cli 0.143.0: "Logged in using
# ChatGPT" on stderr, exit 0). The old `2>/dev/null` discarded stderr, so the probe
# always saw empty stdout and ALWAYS fell back not-authed — cross-family never fired
# even when authed. Merge stderr in (`2>&1`) and match the authed-POSITIVE phrase
# ("logged in using|as"); "Not logged in" lacks that tail, so an unknown/negative
# output degrades to not-authed (safe same-family fallback), never a false authed.
if ! "$RESOLVED" login status </dev/null 2>&1 | grep -qiE "logged in (using|as)"; then
  emit fallback "not-authed"
fi

# --- Gate 3: spawn (read-only, ephemeral, noninteractive, wall-clock cap) ---
LASTMSG="$(mktemp)"
trap 'rm -f "$LASTMSG"' EXIT
timeout "$TIMEOUT" "$RESOLVED" exec --json --ephemeral -s read-only --skip-git-repo-check \
  --output-schema "$SCHEMA" -o "$LASTMSG" - < "$PACKET" >/dev/null 2>&1
rc=$?
[ "$rc" -eq 124 ] && emit fallback "timed-out"
[ "$rc" -ne 0 ] && emit fallback "spawn-failed"

# --- Gate 4: output parseable + has the required pick field ----------------
if ! jq -e '.independent_pick? // empty' "$LASTMSG" >/dev/null 2>&1; then
  emit fallback "unparseable"
fi

emit succeeded "" "$LASTMSG"
