#!/usr/bin/env bash
# Invariant: a close-gate run that ABORTS half-way must not report success.
#
# WHY THIS IS RUN, NOT GREPPED. The obvious guard is to grep close-gate.sh for
# `GATE_VERDICT_REACHED` and call it wired. That checks the string is PRESENT, not that the
# behaviour HOLDS -- the "a literal marker cannot tell use from mention" failure.
# So this invariant takes the real gate, injects a real abort, and
# asserts the real exit code.
#
# WHAT WAS ACTUALLY BROKEN, so a future reader does not "simplify" the fix away. On bash 3.2.57
# an abort from `set -u` enters the EXIT trap with `$?` ALREADY 0. Observed:
#
#     old gate + unbound variable -> script exit 0, and the marker recorded `exit=0`
#     new gate + unbound variable -> script exit 90, marker `exit=90`
#
# Both halves mattered: the pre-push hook reads the exit code, and anything reading
# `.claude/.gate-runs/last-run` read a SUCCESS for a run that never reached a verdict. The
# repair that suggests itself -- ending the trap with `exit "$_gec"` -- does NOT work, because
# `_gec` is already 0; that was measured before it was discarded.
#
# NO RECURSION, AND THAT IS ASSERTED RATHER THAN ASSUMED. The probe copy aborts immediately
# after the trap is armed, long before the gate reaches its `invariants[]` step, so it cannot
# re-enter this script. If someone later moves the injection point past the invariant runner,
# the "produced no output" assertion below fails loudly instead of forking bombs.
set -euo pipefail

GATE="scripts/close-gate.sh"
[ -r "$GATE" ] || { echo "FAIL gate-abort-is-not-success: cannot read $GATE"; exit 1; }

# Locate the trap line by CONTENT, never by a hard-coded number -- a line number would rot on
# the next edit above it.
trap_line="$(grep -n 'trap .*write_gate_marker' "$GATE" | head -1 | cut -d: -f1)"
case "$trap_line" in
  ''|*[!0-9]*)
    echo "FAIL gate-abort-is-not-success: could not locate the EXIT trap line in $GATE"
    echo "     (the guard could not find what it guards, which is a failure, not a pass)"
    exit 1 ;;
esac

probe="$(mktemp)"
cleanup() { rm -f "$probe"; }
trap cleanup EXIT

# Inject an unbound-variable reference on the line straight after the trap: the abort therefore
# happens with the trap armed and before any check has run.
awk -v L="$trap_line" 'NR==L{print; print ": \"$__GATE_ABORT_INVARIANT_PROBE\""; next} {print}' \
  "$GATE" > "$probe"

# The injection must actually be there. An awk that silently matched nothing would leave a
# pristine gate that passes for the wrong reason -- the "mutant did not take" class.
grep -q '__GATE_ABORT_INVARIANT_PROBE' "$probe" || {
  echo "FAIL gate-abort-is-not-success: the probe injection did not take"
  exit 1
}

out="$(/bin/bash "$probe" task "${PHASE:-probe}" 2>&1)" && rc=0 || rc=$?

if [ "$rc" -eq 0 ]; then
  echo "FAIL gate-abort-is-not-success: a gate that aborted mid-run exited 0"
  echo "     The EXIT trap reports whatever its last command returned, and on"
  echo "     bash(3.2) an abort reaches the trap with \$? already 0. The pre-push hook reads"
  echo "     only this exit code, so a half-run gate is indistinguishable from a passing one."
  exit 1
fi

# A half-run gate must not masquerade as a JUDGED failure either: exit 1 means "the gate ran and
# said no". 90 is this project's existing vocabulary for "did not reach its own summary".
if [ "$rc" -ne 90 ]; then
  echo "FAIL gate-abort-is-not-success: an aborted gate exited $rc, expected 90"
  echo "     (non-zero is necessary but not sufficient -- 1 would read as a judged FAIL)"
  exit 1
fi

# It must not have printed a verdict, which is what proves the run really was cut short rather
# than having quietly completed and returned 90 for some other reason.
if printf '%s' "$out" | grep -qE 'close-gate (PASS|FAIL)'; then
  echo "FAIL gate-abort-is-not-success: the aborted run printed a verdict line"
  exit 1
fi

echo "PASS gate-abort-is-not-success: an aborted gate exits 90 with no verdict line (not 0, not 1)"
