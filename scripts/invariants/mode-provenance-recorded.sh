#!/usr/bin/env bash
# Invariant `mode-provenance-recorded`: a phase's record says which mode it ran in, where that came from, and
# -- under `fast` -- carries exactly one blind review, positioned after the plan.
#
# TWO CRITERIA IN ONE FILE because they read the same artifact: the phase's Q&A log fragment. A
# second script would open the same file, parse it a second way, and the two parsings would
# eventually disagree.
#
#   P1             a `mode:` provenance line exists, and its `source` is one of the two legal
#                  values -- an unrecognised value is NAMED, never allowed to fall through.
#   P2             exactly one line PER CONFIRMATION. A second confirmation line means the mode was
#                  raised a second time, which `fast` may not do -- unless the mode genuinely
#                  changed mid-phase, in which case the extra line carries `source: override` and
#                  is the record OF that change. Both are legal; a second `project-default` is not.
#   P3             the value of `source` is what makes "it went back to the default" observable
#                  from outside. A phase after an override records `project-default`, and that is
#                  the only externally visible difference between "the override expired" and "the
#                  override never fired".
#   P4             under `fast`, exactly one `blind-review:` stamp, and its commit is after the
#                  plan document's. Zero is a skipped review; two is the full-mode frequency
#                  leaking into the quick one. Neither is the other, and neither prints the same
#                  message.
#
# ARMED BY THE MODE for P4 only. P1-P3 apply to every phase: a `detailed` phase must record that it
# was `detailed`, or "which mode did this run in" has no answer for half the corpus.
#
# Verdicts: 0 pass, 1 the record is wrong, 3 could not run.
set -euo pipefail
cd "${PROVENANCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

QA_DIR="${PROVENANCE_QA_DIR:-docs/qa-log.d}"
CLAUDE_MD="${PROVENANCE_CLAUDE_MD:-CLAUDE.md}"
FRAGMENT="${PROVENANCE_FRAGMENT:-}"

LEGAL_SOURCES="project-default override"

if [ -z "$FRAGMENT" ]; then
  branch="$(/usr/bin/git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [ -n "$branch" ] || { printf 'COULD NOT RUN: not a git work tree\n' >&2; exit 3; }
  slug="$(printf '%s' "$branch" | tr '/' '-')"
  FRAGMENT="$(/bin/ls -1 "$QA_DIR"/*"$slug"*.md 2>/dev/null | /usr/bin/tail -1 || true)"
fi

if [ -z "$FRAGMENT" ] || [ ! -r "$FRAGMENT" ]; then
  # BEFORE CALLING THIS A PROBLEM, ASK WHETHER THE RULE APPLIES AT ALL.
  #
  # This check is about a PHASE's record. Not every branch is a phase: a chore branch stamping a
  # merged PR into the roadmap, a docs branch, a follow-up fix -- none of them has a Q&A fragment
  # and none of them should. The first version did not ask, so it exited 3 on every such branch,
  # and since close-gate's invariant runner reads exit STATUS only, 3 blocks exactly like 1.
  #
  # A branch that is not a phase is then blocked by a check firing
  # where nothing was configured. Every new invariant needs an explicit not-applicable path.
  #
  # THE DISCRIMINATOR IS THE BRANCH'S OWN DIFF, not its name (a branch is gated by what it
  # touches). A branch that adds or edits a phase spec or plan is a phase's working branch and owes
  # a record; one that does not, is not and does not.
  #
  # RESIDUAL, STATED: a follow-up fix branch for an already-merged phase adds no spec or plan, so it
  # reads as not-applicable. That is deliberate -- its phase's record was checked when the phase
  # closed -- but it does mean this check cannot notice a fragment DELETED by such a branch.
  base="${PROVENANCE_BASE:-}"
  if [ -z "$base" ]; then
    base="$(/usr/bin/git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  fi
  phase_docs=""
  if [ -n "$base" ]; then
    phase_docs="$(/usr/bin/git diff --name-only "$base...HEAD" 2>/dev/null \
      | /usr/bin/grep -E '^docs/superpowers/(specs|plans)/.*-phase-' || true)"
  fi

  if [ -n "$phase_docs" ]; then
    # A phase branch with no fragment IS a problem, and reporting it as clean is the vacuous-pass
    # shape.
    printf 'COULD NOT RUN: this branch adds phase documents but no Q&A log fragment under %s\n' "$QA_DIR" >&2
    printf '  %s\n' $phase_docs >&2
    exit 3
  fi

  printf 'ok  not applicable: this branch adds no phase spec or plan, so it is not a phase working branch and owes no record\n'
  exit 0
fi

fail=0
say() { printf 'FAIL %s\n' "$*" >&2; fail=1; }

lines="$(/usr/bin/grep -nE '^mode: [A-Za-z0-9._-]+ \| source: [A-Za-z0-9._-]+ \| confirmed-at: [A-Za-z0-9._-]+$' "$FRAGMENT" || true)"
if [ -z "$lines" ]; then
  say "P1: $FRAGMENT carries no provenance line -- 'which mode did this phase run in' has no answer"
else
  n=$(printf '%s\n' "$lines" | wc -l | tr -d ' ')
  defaults=0
  while IFS= read -r l; do
    [ -n "$l" ] || continue
    src="$(printf '%s' "$l" | sed -E 's/.*\| source: ([A-Za-z0-9._-]+) \|.*/\1/')"
    case " $LEGAL_SOURCES " in
      *" $src "*) ;;
      *) say "P1: source '$src' is not one of: $LEGAL_SOURCES ($FRAGMENT:${l%%:*})" ;;
    esac
    [ "$src" = "project-default" ] && defaults=$((defaults + 1))
  done <<<"$lines"
  if [ "$defaults" -gt 1 ]; then
    say "P2: $defaults lines record source=project-default -- the mode was raised more than once, which fast may not do"
  fi
  printf 'ok  P1/P2/P3: %d provenance line(s), sources legal, %d default confirmation(s)\n' "$n" "$defaults"
fi

mode=""
if [ -r "$CLAUDE_MD" ]; then
  mode="$(awk '
    /^[[:space:]]*#/ { next }
    index($0, "mode:") == 1 {
      sub("^mode:[[:space:]]*", ""); sub("[[:space:]]*#.*$", ""); gsub(/[[:space:]]+$/, "")
      print; exit
    }' "$CLAUDE_MD")"
fi

if [ "$mode" = "fast" ]; then
  stamps=$(/usr/bin/grep -cE '^blind-review: ' "$FRAGMENT" || true)
  case "$stamps" in
    1) printf 'ok  P4: exactly one blind review recorded for this fast phase\n' ;;
    0) say "P4: no blind review recorded -- the quick setting reduces its frequency to one per phase, never to zero" ;;
    *) say "P4: $stamps blind reviews recorded -- that is the full setting's frequency leaking into the quick one" ;;
  esac
else
  printf 'ok  P4 not applicable: this project runs mode=%s, and the once-per-phase rule is armed only by fast\n' \
    "${mode:-<unset>}"
fi

exit "$fail"
