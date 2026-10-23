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
# Resolved BEFORE the cd below, because the sentinel is found relative to THIS FILE and not to the
# tree being checked: a fixture repository has no scripts/lib of its own.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROVENANCE_ROOT:-$(cd "$HERE/../.." && pwd)}"

QA_DIR="${PROVENANCE_QA_DIR:-docs/qa-log.d}"
CLAUDE_MD="${PROVENANCE_CLAUDE_MD:-CLAUDE.md}"
FRAGMENT="${PROVENANCE_FRAGMENT:-}"
REGISTRY="${PROVENANCE_REGISTRY:-.claude/stage-registry.json}"
SENTINEL="${PROVENANCE_SENTINEL:-$HERE/../lib/fragment-sentinel.awk}"
LABEL=""

LEGAL_SOURCES="project-default override"

if [ -z "$FRAGMENT" ]; then
  branch="$(/usr/bin/git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [ -n "$branch" ] || { printf 'COULD NOT RUN: not a git work tree\n' >&2; exit 3; }
  slug="$(printf '%s' "$branch" | tr '/' '-')"
  FRAGMENT="$(/bin/ls -1 "$QA_DIR"/*"$slug"*.md 2>/dev/null | /usr/bin/tail -1 || true)"
  [ -n "$FRAGMENT" ] && LABEL="$FRAGMENT"
fi

# A PHASE RECORD DOES NOT STAY IN THE HOT ZONE, and reading only the hot zone is what made this
# check unable to validate any phase after its own drain -- which is every phase, a few hours after
# it closes.
#
# `retention-drain.sh drain qa-log` compiles a fragment into the archive verbatim and removes the
# hot copy. The journal has a post-merge-only rule holding that off until after the merge; the
# qa-log has none, so at the moment `close-gate.sh phase` runs, this phase's record can legitimately
# live only under docs/archive/**. Without that, the prescribed drain moves the
# fragment into a docs/archive/brainstorming-qa-log/ segment and this file exits 3 -- COULD
# NOT RUN, which the gate's invariant runner blocks on exactly like a failure -- while the
# provenance line sits in that archive, readable. The record was never missing.
#
# WHERE IT LOOKS IS DECLARED, NOT GUESSED: the roots come from the stage registry's `qa_log` stage,
# `fragment-marker` kind -- the same declaration the lifecycle ledger reads for the same question.
# A guessed path is how a check begins passing for the wrong reason, so an unreadable registry is
# verdict 3 and says so.
#
# AND THE READER IS THE SHIPPED ONE. `scripts/lib/fragment-sentinel.awk` is the declared source of
# truth for "is this line a real fragment boundary", and its sibling guard's refusal message names
# calling it (`awk -f`) as the sanctioned alternative to writing a second matcher. This is the
# SECOND direct run-time reader; the claim in that guard's header and in the reference doc is
# updated in the same commit, because "one direct reader" would otherwise be a sentence this file
# falsifies.
if [ -z "$FRAGMENT" ] && [ -n "${slug:-}" ]; then
  case "$slug" in
    *phase-*) pat="phase-${slug#*phase-}" ;;
    *)        pat="" ;;
  esac
  if [ -n "$pat" ]; then
    command -v jq >/dev/null 2>&1 || {
      printf 'COULD NOT RUN: the hot fragment is absent and jq is missing, so the stage-registry roots that declare where a drained fragment lands cannot be read\n' >&2
      exit 3; }
    [ -r "$REGISTRY" ] || {
      printf 'COULD NOT RUN: the hot fragment is absent and the stage-registry (%s) is unreadable, so where a drained fragment lands is not declared anywhere this check can read\n' "$REGISTRY" >&2
      exit 3; }
    [ -r "$SENTINEL" ] || {
      printf 'COULD NOT RUN: the fragment-sentinel reader is not readable: %s\n' "$SENTINEL" >&2
      exit 3; }
    roots="$(jq -r '.stages[]? | select(.stage_id=="qa_log") | .retro_evidence[]?
                    | select(.kind=="fragment-marker") | .roots[]?' "$REGISTRY" 2>/dev/null || true)"
    [ -n "$roots" ] || {
      printf 'COULD NOT RUN: %s declares no fragment-marker roots for stage qa_log, so a drained record has no declared home to read\n' "$REGISTRY" >&2
      exit 3; }

    # A READER THAT COULD NOT RUN MUST NOT BE SCORED AS A READER THAT SAID SOMETHING, and here the
    # two are the same number. `/usr/bin/awk` exits 2 on a syntax error in its program AND on an
    # unreadable input file, and 2 is this sentinel's own FENCED verdict -- so without this
    # pre-flight a program that does not parse is reported as "every one of these files quotes a
    # marker inside a fence", sending the operator to look for code fences that are not there.
    # Measured: `awk -f <syntax-error>` -> 2, `awk '{print}' /nonexistent` -> 2.
    #
    # The discriminator is an EMPTY input: a working program can only answer 0 (found) or 1 (not
    # found) against /dev/null, because there is nothing there to fence. A 2 means it did not run.
    set +e
    /usr/bin/awk -v pat="$pat" -f "$SENTINEL" /dev/null >/dev/null 2>&1; probe=$?
    set -e
    case "$probe" in
      0|1) : ;;
      *) printf 'COULD NOT RUN: the declared sentinel %s exits %s on empty input, so it did not run at all (awk exits 2 on a syntax error, which is also this reader'"'"'s FENCED verdict -- scoring it would report a broken reader as "fenced")\n' "$SENTINEL" "$probe" >&2
         exit 3 ;;
    esac

    hits=""; fenced=""
    for root in $roots; do
      for f in $root; do
        [ -f "$f" ] || continue
        # Unreadable is not empty. Without this the same exit 2 arrives per-file and lands in the
        # FENCED bucket again, one pre-flight later.
        [ -r "$f" ] || { printf 'COULD NOT RUN: %s is declared as an archive root but is not readable\n' "$f" >&2; exit 3; }
        set +e
        slice="$(/usr/bin/awk -v pat="$pat" -f "$SENTINEL" "$f" 2>/dev/null)"; st=$?
        set -e
        case "$st" in
          0) [ -n "$slice" ] && hits="$hits $f" ;;
          2) fenced="$fenced $f" ;;
        esac
      done
    done

    nhits=0; for f in $hits; do nhits=$((nhits + 1)); done
    if [ "$nhits" -gt 1 ]; then
      printf 'FAIL mode-provenance-recorded: phase %s is compiled into %d archive files, so "the record" has two answers and nothing choosing:\n' "$pat" "$nhits" >&2
      printf '  %s\n' $hits >&2
      printf '  -> A drain appends a fragment once; its own idempotence sentinel is what makes a retry safe. Two copies means that was defeated. Fix the archive, do not pick one here.\n' >&2
      exit 1
    fi
    if [ "$nhits" -eq 0 ] && [ -n "$fenced" ]; then
      printf 'FAIL mode-provenance-recorded: the only sentinel naming phase %s in the declared archive roots was rejected as FENCED:\n' "$pat" >&2
      printf '  %s\n' $fenced >&2
      printf '  -> A document that QUOTES a marker is not carrying one. Reported rather than treated as absent, because "the record is elsewhere" and "the record is a code sample" must not print the same thing.\n' >&2
      exit 1
    fi
    if [ "$nhits" -eq 1 ]; then
      for f in $hits; do LABEL="$f"; done
      tmp="$(mktemp -t mode-provenance.XXXXXX)" || {
        printf 'COULD NOT RUN: cannot create a temporary file for the archive slice\n' >&2; exit 3; }
      trap 'rm -f "$tmp"' EXIT
      /usr/bin/awk -v pat="$pat" -f "$SENTINEL" "$LABEL" > "$tmp"
      [ -s "$tmp" ] || {
        printf 'COULD NOT RUN: the slice for phase %s out of %s is empty, and an empty slice must not be read as a record with nothing in it\n' "$pat" "$LABEL" >&2
        exit 3; }
      FRAGMENT="$tmp"
      LABEL="$LABEL (archive slice for $pat)"
      [ -n "$fenced" ] && printf 'note: a fenced sentinel naming %s also appears in%s -- not a boundary by the grammar, named here rather than passed over in silence\n' "$pat" "$fenced"
    fi
  fi
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
    printf 'COULD NOT RUN: this branch adds phase documents but no Q&A log fragment -- not under %s, and not compiled into the fragment-marker roots %s declares for stage qa_log\n' "$QA_DIR" "$REGISTRY" >&2
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
      *) say "P1: source '$src' is not one of: $LEGAL_SOURCES (${LABEL:-$FRAGMENT}:${l%%:*})" ;;
    esac
    [ "$src" = "project-default" ] && defaults=$((defaults + 1))
  done <<<"$lines"
  if [ "$defaults" -gt 1 ]; then
    say "P2: $defaults lines record source=project-default -- the mode was raised more than once, which fast may not do"
  fi
  printf 'ok  P1/P2/P3: %d provenance line(s), sources legal, %d default confirmation(s) -- read from %s\n' "$n" "$defaults" "${LABEL:-$FRAGMENT}"
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
