#!/usr/bin/env bash
# potency-runner.sh — out-of-envelope producer of potency-result.json (verify-gate AC3 / R4).
# For each guard-manifest.json entry that declares a firingFixture, prove the guard is POTENT:
#   fixtureResult = run the fixture with the guard intact  (a potent guard → fixture passes)
#   neuterResult  = neuter the guard, re-run the fixture    (a potent guard → fixture now FAILS)
# A guard whose fixture still passes after neutering is impotent — the jq gate blocks on it.
# Emits { prHeadSha, manifestHash, runId, perGuard:[{guardId,fixtureResult,neuterResult}] }.
# (manifestHash is a `git hash-object` content hash — see the MHASH note below for why not sha256.)
# Out-of-envelope (bash + jq + the fixture's own toolchain); verify-gate.sh stays jq-only.
#
# Usage: potency-runner.sh --head <sha> --manifest <path> --out <path> [--diff-guards <path|->]
set -euo pipefail

die() { echo "potency-runner: $*" >&2; exit 1; }

HEAD="" MANIFEST="" OUT="" DIFFGUARDS="-"
while [ $# -gt 0 ]; do
  case "$1" in
    --head|--manifest|--out|--diff-guards)
      [ $# -ge 2 ] || die "flag $1 needs a value"
      case "$1" in
        --head) HEAD="$2" ;; --manifest) MANIFEST="$2" ;;
        --out) OUT="$2" ;; --diff-guards) DIFFGUARDS="$2" ;;
      esac
      shift 2 ;;
    *) die "unknown flag: $1" ;;
  esac
done
[ -n "$HEAD" ]     || die "missing --head"
[ -n "$MANIFEST" ] || die "missing --manifest"
[ -n "$OUT" ]      || die "missing --out"
[ -f "$MANIFEST" ] || die "manifest not found: $MANIFEST"
jq -e 'type=="array"' "$MANIFEST" >/dev/null 2>&1 || die "manifest is not a JSON array: $MANIFEST"

# Content hash via `git hash-object` — deterministic pure-content hash the jq-only gate can
# recompute identically WITHOUT a non-envelope interpreter (shasum is perl on macOS;
# sha256sum is absent there). git is already in the gate's envelope.
MHASH="$(git hash-object "$MANIFEST")" || die "git hash-object failed on $MANIFEST"
RUNID="${EPOCHSECONDS:-0}-$$-${RANDOM:-0}"

# A neuter step MUTATES a real source file in place. If anything between backup and restore fails
# under set -euo pipefail (a bad neuterCmd, disk-full, an interrupted CI job) the file would be
# left permanently neutered + the backup leaked. One EXIT trap makes the restore unconditional —
# it fires no matter which guard below trips. CUR_* are cleared after each clean restore so the
# trap never double-restores. This matters more for an unattended periodic run than for a one-shot PR.
CUR_FILE="" CUR_BAK="" TMP=""
cleanup() {
  [ -n "$CUR_BAK" ] && [ -f "$CUR_BAK" ] && [ -n "$CUR_FILE" ] && cp "$CUR_BAK" "$CUR_FILE" 2>/dev/null
  [ -n "$CUR_BAK" ] && rm -f "$CUR_BAK"
  [ -n "$TMP" ] && rm -f "$TMP"
  return 0
}
trap cleanup EXIT

# result of running a fixture command: passed (exit 0) / errored (127 = toolchain missing) / failed.
# NOTE (trust boundary): run_fixture and the neuter step execute `bash -c "$cmd"` on strings taken
# from the committed guard-manifest.json. This is the same trust level as "the PR's own test suite
# runs in CI" — NOT a new injection surface — PROVIDED this runner only ever runs in an ephemeral
# CI sandbox against a reviewed/mergeable branch, never a maintainer's persistent local checkout and
# never auto-triggered on an unreviewed fork PR. any unattended runner MUST preserve that boundary.
run_fixture() {
  local cmd="$1" rc=0
  bash -c "$cmd" >/dev/null 2>&1 || rc=$?
  if [ "$rc" -eq 0 ]; then echo passed
  elif [ "$rc" -eq 127 ]; then echo errored
  else echo failed; fi
}

PERGUARD='[]'
COUNT="$(jq 'length' "$MANIFEST")"
i=0
while [ "$i" -lt "$COUNT" ]; do
  ENTRY="$(jq -c ".[$i]" "$MANIFEST")"
  GID="$(printf '%s' "$ENTRY" | jq -r '.guardId // empty')"
  FIX="$(printf '%s' "$ENTRY" | jq -r '.firingFixture // empty')"
  FILE="$(printf '%s' "$ENTRY" | jq -r '.file // empty')"
  LINE="$(printf '%s' "$ENTRY" | jq -r '.line // empty')"
  NEUTER="$(printf '%s' "$ENTRY" | jq -r '.neuterCmd // empty')"
  # Waiver entries (no firingFixture) are the gate's concern, not the runner's — skip.
  if [ -z "$FIX" ]; then i=$((i+1)); continue; fi
  [ -n "$GID" ] || die "manifest entry $i has firingFixture but no guardId"

  FRES="$(run_fixture "$FIX")"

  # neuter → re-run → restore. Default neuter = blank the guard's line (best-effort; a manifest
  # author overrides via neuterCmd for multi-line / structured guards).
  NRES="errored"
  if [ -n "$FILE" ] && [ -f "$FILE" ]; then
    CUR_FILE="$FILE"; CUR_BAK="$(mktemp)"; cp "$FILE" "$CUR_BAK"   # trap now guards the restore
    if [ -n "$NEUTER" ]; then
      bash -c "$NEUTER" >/dev/null 2>&1 || true
    elif [ -n "$LINE" ]; then
      sed -i.sedbak "${LINE}s/.*//" "$FILE" && rm -f "$FILE.sedbak"
    fi
    NRES="$(run_fixture "$FIX")"
    cp "$CUR_BAK" "$FILE"                                          # restore
    # clean any backup an author's neuterCmd left behind (e.g. `sed -i.bak`) so it can't be
    # accidentally committed, then close the neuter window (trap must not double-restore).
    rm -f "$CUR_BAK" "$FILE.bak" "$FILE.sedbak" "$FILE.orig" 2>/dev/null || true
    CUR_FILE=""; CUR_BAK=""
  fi

  PERGUARD="$(printf '%s' "$PERGUARD" | jq \
    --arg g "$GID" --arg f "$FRES" --arg n "$NRES" \
    '. + [{guardId:$g, fixtureResult:$f, neuterResult:$n}]')"
  i=$((i+1))
done

TMP="$(mktemp)"   # cleaned by the EXIT trap installed above
jq -n --arg head "$HEAD" --arg mhash "$MHASH" --arg run "$RUNID" --argjson pg "$PERGUARD" \
  '{prHeadSha:$head, manifestHash:$mhash, runId:$run, perGuard:$pg}' > "$TMP"
mkdir -p "$(dirname "$OUT")"
mv "$TMP" "$OUT"
echo "potency-runner: proved $(printf '%s' "$PERGUARD" | jq 'length') guard(s) → $OUT"
