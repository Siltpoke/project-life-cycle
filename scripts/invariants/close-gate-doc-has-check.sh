#!/usr/bin/env bash
# Invariant: the SHIPPED adopter contract carries the ac-oracle-binding check and its bound.
#
# The check must be present in `references/close-gate.md` -- the document an adopter
# materializes their gate from -- not only in this repository's own gate. Those are two separate
# acts: wiring this repo's `scripts/close-gate.sh` and writing the contract. Only one of them is
# forced by anything, and the unforced one drifts (guide-map-covers-references.sh's header
# describes references drifting out of a map that called
# itself "every").
#
# The disclaimer is the second half and is NOT decoration. A green ac-oracle-binding row says a criterion
# HAS an oracle; it says nothing about whether that oracle is any good, and an exclusion survives on
# its condition, not on its reasoning. An adopter who copies the check without the bound ships a row
# that claims more than the mechanism can deliver.
#
# BOTH CHECKLISTS, and the second is the one that would have drifted: `ac-oracle-binding` runs in
# task mode on every push and in phase mode at close. A contract naming it under `phase-done` only
# would describe a gate the adopter does not have.
#
# SCOPE, stated rather than left to be discovered:
#   * PRESENCE of the literal check name inside each checklist's own line range, and PRESENCE of the
#     two disclaimer sentences anywhere in the document. It does not read the prose around them --
#     a description can be wrong in ways no mechanism can see, and pretending otherwise would be the
#     same over-claim this check exists to stop.
#   * The disclaimer sentences are matched with `grep -F`, byte for byte. That is deliberate: the
#     value here is that the WORDING survives, so a paraphrase must red. `scripts/ac-evidence.sh`
#     holds the same two strings as `DISCLAIMER_1`/`DISCLAIMER_2`; if you reword one, reword both.
#
# Checklist bounds come from the HEADINGS, never a line count -- a count goes stale on the next edit,
# the same way a line-number citation does.
#
# jq-only envelope: no python3 here or in anything it calls.

set -uo pipefail

NAME="close-gate-doc-has-check"

# The subject is an ARGUMENT, never fd 0. git feeds the pre-push hook a ref line on stdin; a check
# that read stdin would scan that ref line, find no document in it, and pass -- measured once
# already in this directory (backlog-no-title-markers.sh's header).
#
# The argument is a ROOT, not the file, so the tests can build a throwaway tree under `tmp_path` and
# mutate THAT. An earlier shape had them mutate the tracked file and restore it in a `finally`: a
# SIGKILL or a `pytest -x` interrupt between the two would have left the shipped adopter contract
# saying `REMOVED`.
ROOT="${1:-.}"
DOC="$ROOT/skills/project-lifecycle/references/close-gate.md"

CHECK="ac-oracle-binding"
DISCLAIMER_1="this proves each criterion HAS an oracle. It never proves the oracle is correct,"
DISCLAIMER_2="and an exclusion self-destructs only when its condition fails, never when its reasoning was wrong."

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

[ -f "$DOC" ] || fail "$DOC not found (subject must exist; an absent contract is not a pass)"

# --- the two checklists, bounded by their own headings --------------------------
# Enter at `### \`<mode>\``, leave at the next `##`-or-deeper heading. Anything between is that
# checklist's text.
section() {
  awk -v want="$1" '
    /^#{2,}[[:space:]]/ {
      # A heading. Are we entering the one we want, or leaving the one we had?
      if (inside) { inside = 0 }
      if (index($0, "`" want "`") > 0) { inside = 1 }
      next
    }
    inside { print }
  ' "$DOC"
}

rc=0
found_any=0

for mode in task-done phase-done; do
  body="$(section "$mode")"
  if [ -z "$body" ]; then
    # An empty extraction means the document's shape changed under this parser, not that the
    # checklist is clean. Passing here would be a vacuous pass.
    printf 'FAIL %s: extracted ZERO lines for the `%s` checklist -- the document layout changed and this parser no longer reads it (a vacuous pass is not a pass)\n' "$NAME" "$mode"
    rc=1
    continue
  fi
  found_any=1
  # A checklist ROW whose SUBJECT is the check -- not a mention of it anywhere in the section.
  # Measured while writing this: the `user-story.md` row in `task-done` explains itself by pointing
  # at "the `ac-oracle-binding` row below", so a plain `grep -F` over the section stayed green with
  # the actual row deleted. That is this repo's use-vs-mention class, reproduced inside the guard
  # written to stop the contract from drifting.
  # The subject must END at the check name. A prefix match is satisfied by a row renamed to
  # `ac-oracle-binding-disabled` -- measured on a throwaway copy, the invariant stayed green with the
  # real row gone. The boundary is a backtick, a space, or end-of-line; nothing else may follow.
  if printf '%s\n' "$body" | grep -qE '^- \[ \] *`?'"$CHECK"'(`| |$)'; then
    :
  else
    printf 'FAIL %s: the `%s` checklist has no row whose subject is `%s` -- an adopter materializing their gate from this document would not have the check. (A mention inside another row does not count; the row must start `- [ ] `%s``.)\n' "$NAME" "$mode" "$CHECK" "$CHECK"
    rc=1
  fi
done

[ "$found_any" -eq 1 ] || fail "neither checklist was readable in $DOC -- refusing to report on an empty set"

# --- the bound the check does not exceed ----------------------------------------
n=1
for sentence in "$DISCLAIMER_1" "$DISCLAIMER_2"; do
  if grep -qF -- "$sentence" "$DOC"; then
    :
  else
    printf 'FAIL %s: disclaimer sentence %d is missing or reworded. Expected verbatim:\n    %s\n' "$NAME" "$n" "$sentence"
    printf '    (without it the row claims more than the mechanism proves. The same two\n'
    printf '    strings live in scripts/ac-evidence.sh as DISCLAIMER_1/DISCLAIMER_2; reword both or neither.)\n'
    rc=1
  fi
  n=$((n + 1))
done

[ "$rc" -eq 0 ] || exit 1

pass "both checklists name \`$CHECK\`, and both disclaimer sentences are present verbatim"
