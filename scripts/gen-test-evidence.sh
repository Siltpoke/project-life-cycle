#!/usr/bin/env bash
# gen-test-evidence.sh — safe runner for THIS repo's test-evidence file.
#
# Usage: gen-test-evidence.sh <task|phase>
# Run from the repo root (same cwd assumption the declared test_command already makes).
#
# Replaces the manual incantation `{ close-gate.sh evidence-header; <test_command>; } | tee
# <file>`: `tee` exits with ITS OWN status, so a FAILING
# validator still writes a green-looking evidence file — the exact hazard this script exists to
# close. Runs under `set -o pipefail` (both here and on the inner `bash -c`, since a fresh `bash
# -c` child does not inherit the parent's shell options) so the validator's real exit status
# survives the pipe, and writes to a TEMP FILE first: the real evidence file is only overwritten
# on SUCCESS, so a failing run leaves a pre-existing good evidence file completely untouched —
# never an empty or truncated one.
#
# The declared command is obtained from `close-gate.sh test-command` — the
# ONE place that value is read from the manifest, printed raw and UNRESOLVED. This script is the
# one that resolves BOTH placeholders the declared command can carry — `{EVIDENCE_FILE}` and
# `{SET}` — using bash parameter expansion (`${var//pat/repl}`), never
# `sed` — see close-gate.sh's row-7 comment for why `sed`'s delimiter/backreference model is
# unsafe for a path substitution like this one.
#
# TEST-ONLY: set PLC_GEN_TEST_EVIDENCE_CMD_OVERRIDE to run a different command instead of the
# manifest's declared test_command, so the refusal-on-failure can be demonstrated with a
# deliberately failing command WITHOUT mutating .claude/close-gate.json. Never set this for a
# real evidence run — the shipped evidence file must come from the real declared command.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$HERE/close-gate.sh"
M=".claude/close-gate.json"

SET_MODE="${1:?usage: gen-test-evidence.sh <task|phase>}"
case "$SET_MODE" in
  task|phase) ;;
  *) echo "✗ set mode must be 'task' or 'phase' — got '$SET_MODE'"; exit 1 ;;
esac

[ -f "$M" ] || { echo "✗ missing manifest $M"; exit 1; }
EV="$(jq -r '.test_evidence // empty' "$M" 2>/dev/null)"
[ -n "$EV" ] || { echo "✗ manifest has no test_evidence path declared"; exit 1; }

if [ -n "${PLC_GEN_TEST_EVIDENCE_CMD_OVERRIDE:-}" ]; then
  EVCMD_TMPL="$PLC_GEN_TEST_EVIDENCE_CMD_OVERRIDE"
else
  EVCMD_TMPL="$(/bin/bash "$GATE" test-command)"
fi
[ -n "$EVCMD_TMPL" ] || { echo "✗ no test_command to run (declared value is empty)"; exit 1; }

# Report a genuine mkdir failure (permissions/quota) here, at its real cause, rather than
# swallowing it and deferring to a less informative downstream error (e.g. `tee` failing to
# open a file in a directory that was never created, several steps later and unrelated-looking).
EV_DIR="$(dirname "$EV")"
if ! MKDIR_ERR="$(mkdir -p "$EV_DIR" 2>&1)"; then
  echo "✗ could not create evidence directory $EV_DIR: ${MKDIR_ERR:-mkdir failed (permissions or quota?)}"
  exit 1
fi

# Same directory as the real evidence file, so the final `mv` is a same-filesystem rename —
# atomic, and never leaves the destination half-written.
TMP="$(mktemp "${EV}.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

EVCMD="${EVCMD_TMPL//\{EVIDENCE_FILE\}/$TMP}"
# `{SET}`: resolved to this run's mode HERE, by substitution, same as
# `{EVIDENCE_FILE}` above — not via an env var, which would be public API once shipped.
EVCMD="${EVCMD//\{SET\}/$SET_MODE}"

set +e
/bin/bash -o pipefail -c "$EVCMD"
RC=$?
set -e

if [ "$RC" -eq 0 ]; then
  # A zero exit status is not the same claim as "an artifact the gate could accept", and the two
  # guards below are the two measured places they come apart. Both destroy VALID state while
  # printing a ✓ — neither can buy a green (row 7 rejects both afterwards), so what is at stake is
  # the adopter's last good evidence file plus a success message that means its opposite.
  #
  # Read the first line with `read`, not `head -n1 | grep`: under `-o pipefail` a `grep -q` that
  # matches exits before `head` finishes writing, `head` takes SIGPIPE, and the pipeline's status
  # is 141, so a match reads as a failure.
  # `case` needs no external command and no regex dialect.
  if [ ! -s "$TMP" ]; then
    echo "✗ gen-test-evidence: the command exited 0 but wrote nothing to {EVIDENCE_FILE} — $EV left unchanged. The declared test_command must write THROUGH the {EVIDENCE_FILE} placeholder (a runner that writes to its own report file instead produces exactly this)."
    exit 1
  fi
  IFS= read -r FIRSTLINE < "$TMP" || FIRSTLINE=""
  case "$FIRSTLINE" in
    '# plc-gate-evidence inputs=EMPTY-'*)
      # `evidence-header` emits an EMPTY-* sentinel INSTEAD of a digest, and exits 0, when the
      # manifest's test_evidence_inputs matched no tracked file. That is deliberate on the gate's
      # side (it has a dedicated row-7 branch that rejects this header loudly rather than
      # fingerprinting nothing) — the producer just had no matching refusal. Scoped to this
      # sentinel prefix, which covers both spellings in circulation
      # (…-no-gate-relevant-paths-matched here, …-no-test-evidence-inputs-matched in the ported
      # copy), and NOT to "the header is missing": an adopter who never opted into fingerprint
      # mode declares no test_evidence_inputs, calls no evidence-header, and their headerless
      # evidence must keep working.
      echo "✗ gen-test-evidence: the evidence header fingerprints nothing — the manifest's test_evidence_inputs matched no tracked files, so the gate will reject this file. $EV left unchanged. Fix the globs in $M (or \`git add\` the paths they name), then re-run."
      exit 1
      ;;
  esac
  mv -f "$TMP" "$EV"
  trap - EXIT
  echo "✓ evidence written: $EV (set=$SET_MODE)"
  exit 0
else
  echo "✗ gen-test-evidence: command exited $RC — evidence NOT written; $EV left unchanged"
  exit "$RC"
fi
