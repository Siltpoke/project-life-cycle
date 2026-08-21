#!/usr/bin/env bash
# closure-declaration.sh — reads a phase's closure declaration out of its own
# phase documents and prints it as records. It decides NOTHING about pass or fail; the
# verdict for "no declaration at all" belongs to the gate, not here.
#
# Usage: closure-declaration.sh extract <file>...
#
# Prints one TAB-separated record per line, on stdout:
#     closed<TAB><id><TAB><reason-or-hyphen>
#     left-open<TAB><id><TAB><reason>
#     none<TAB>-<TAB>-
# No block found across every file given: prints nothing, exits 0. That is not an error
# here — the gate raises it.
#
# Any malformed input is a NAMED failure on stderr with a non-zero exit, never a silent
# zero. This is the shape scripts/ac-evidence.sh already had to close: a declaration the
# checker cannot read must be a red, not an under-count.
#
# ENVELOPE: bash + sed + awk. NO python3 — scripts/invariants/gate-jq-only-envelope.sh
# fails the build on a violation. Launched by name, never via a bare `bash` (see
# scripts/invariants/named-interpreter.sh).
#
# WHY THE INFO STRING IS EXACT. The opening fence must be ```plc-closes and nothing else.
# `plc-closes-example` is deliberately NOT a match, because awk has no concept of
# fence-nesting depth: an illustrative block wrapped in a wider four-backtick fence is
# still a line in the file.
set -u

PROG="$(basename "$0")"
FENCE_OPEN='^```plc-closes[[:space:]]*$'
FENCE_CLOSE='^```[[:space:]]*$'
# A WRAPPER is the fence a documentation example is nested inside. CommonMark lets you wrap
# a backtick-fenced illustration in either a LONGER backtick fence or a tilde fence, and the
# tilde form is the more idiomatic of the two. The reserved `-example` suffix closes the trap
# only for authors who remember it; skipping wrapper contents closes
# it structurally: otherwise a real `plc-closes` block inside `~~~markdown` is
# read as a genuine declaration.
WRAP_FENCE='^(````+|~~~+)'

die() { printf '%s: %s\n' "$PROG" "$1" >&2; exit 1; }

usage() { printf 'usage: %s extract <file>...\n' "$PROG" >&2; exit 2; }

# ---------------------------------------------------------------------------
# Locate every real block across every file. Emits "path<TAB>openline<TAB>closeline".
# An opening fence with no closing fence is a named failure, not a block that runs to
# end-of-file: silently swallowing the rest of a document is how a declaration would
# absorb unrelated prose and then report it as malformed entries, blaming the wrong line.
# ---------------------------------------------------------------------------
# NOTE: this function is CALLED INSIDE `$( )`, so it runs in a subshell and `die`'s
# `exit 1` would kill only that subshell -- the caller would carry on and exit 0. That is
# the fail-open to avoid: an unreadable file would print its message and then be silently
# skipped. Readability is therefore checked by the caller,
# before the substitution, and nothing in here may exit on the script's behalf.
locate_blocks() {
  local f
  for f in "$@"; do
    awk -v path="$f" -v fo="$FENCE_OPEN" -v fc="$FENCE_CLOSE" -v fw="$WRAP_FENCE" '
      # Wrapper handling comes FIRST: everything between a wrapper open and its close is
      # documentation ABOUT the format, not an instance of it. Without this, a real block
      # nested in `~~~markdown` is read as a genuine declaration.
      $0 ~ fw { inwrap = !inwrap; next }
      inwrap  { next }
      $0 ~ fo { if (inblk) { printf "UNCLOSED\t%s\t%d\n", path, open; exit 1 }
                inblk = 1; open = NR; next }
      inblk && $0 ~ fc { printf "%s\t%d\t%d\n", path, open, NR; inblk = 0; next }
      END { if (inblk) { printf "UNCLOSED\t%s\t%d\n", path, open; exit 1 } }
    ' "$f" || true
  done
}

cmd_extract() {
  [ "$#" -ge 1 ] || usage

  # Readability is checked HERE, in the script's own shell, not inside locate_blocks --
  # see the note on that function. Every file is checked before any is read, so a missing
  # path is reported as itself rather than as "no declaration found".
  local f
  for f in "$@"; do
    # `-f` as well as `-r`, and the order matters for the message. `[ -r ]` alone is TRUE
    # for a readable DIRECTORY, and BWK awk (macOS's /usr/bin/awk) reads a directory
    # as an EMPTY STREAM rather than erroring -- so a directory argument produced exit 0,
    # no output and no message: the silent zero this script's own header forbids.
    [ -e "$f" ] || die "cannot read '$f': no such file"
    [ -f "$f" ] || die "cannot read '$f': not a regular file"
    [ -r "$f" ] || die "cannot read '$f': permission denied"
  done

  local blocks
  blocks="$(locate_blocks "$@")"

  # An unclosed fence is reported before anything else: every later message would be
  # derived from a block whose extent is unknown.
  local unclosed
  unclosed="$(printf '%s\n' "$blocks" | /usr/bin/grep '^UNCLOSED' || true)"
  if [ -n "$unclosed" ]; then
    local p l
    p="$(printf '%s\n' "$unclosed" | head -1 | cut -f2)"
    l="$(printf '%s\n' "$unclosed" | head -1 | cut -f3)"
    die "opening fence \`\`\`plc-closes at $p:$l is never closed"
  fi

  blocks="$(printf '%s\n' "$blocks" | /usr/bin/grep -v '^[[:space:]]*$' || true)"
  local n
  n="$(printf '%s\n' "$blocks" | /usr/bin/grep -c . || true)"

  # No declaration anywhere. Not this script's error to raise.
  [ "$n" -eq 0 ] && return 0

  # Exactly one block across the WHOLE resolved set. Two is an error, never a merge —
  # ambiguity resolved by picking a winner is how a declaration silently loses half its
  # entries. The message names every path and line so the author does not have to hunt.
  if [ "$n" -gt 1 ]; then
    local where
    where="$(printf '%s\n' "$blocks" | awk -F'\t' '{printf "  %s:%d\n", $1, $2}')"
    die "$(printf 'found %d plc-closes blocks; exactly one is allowed across all phase documents:\n%s' "$n" "$where")"
  fi

  local path open close
  path="$(printf '%s\n' "$blocks" | cut -f1)"
  open="$(printf '%s\n' "$blocks" | cut -f2)"
  close="$(printf '%s\n' "$blocks" | cut -f3)"

  parse_body "$path" "$open" "$close"
}

# ---------------------------------------------------------------------------
# Parse the one block's body. Every non-blank line must match a production; anything else
# names itself and its line number.
#
# The reason is STORED, never matched. No code in this feature branches on its content —
# that is the line a text-matching oracle would cross. It exists so a human reading a
# failure can see why, and for no other purpose.
# ---------------------------------------------------------------------------
parse_body() {
  local path="$1" startln="$2" endln="$3"
  # `close` is an awk BUILT-IN function name and cannot be a variable: BSD awk rejects the
  # program outright. The rename to startln/endln is not style. It is also why these -v
  # names must be kept in step with the locals above -- an earlier revision renamed only
  # the locals, leaving `-v startln` unset, so every line fell outside the range, the
  # parser printed ZERO records and exited 0. That is indistinguishable from "this file has
  # no block", which is a legitimate outcome, so nothing would have complained.
  awk -v path="$path" -v startln="$startln" -v endln="$endln" '
    function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return s }
    # Strip the optional separator between id and reason. Both the em dash and a double
    # hyphen are accepted: references/close-gate.md writes one, keyboards produce the other, and a format
    # that rejects the reason for its punctuation would be teaching authors to omit it.
    function dereason(s) { s = trim(s); sub(/^(--|—)[[:space:]]*/, "", s); return trim(s) }
    NR <= startln || NR >= endln { next }
    { line = trim($0) }
    line == "" { next }
    {
      if (line ~ /^closes:[[:space:]]*none[[:space:]]*$/) { seen_none = 1; nrec++; print "none\t-\t-"; next }
      if (line ~ /^(closed|left-open):[[:space:]]*[A-Za-z][A-Za-z0-9._-]*([[:space:]].*)?$/) {
        kind = line; sub(/:.*$/, "", kind)
        rest = line; sub(/^[^:]*:[[:space:]]*/, "", rest)
        id = rest; sub(/[[:space:]].*$/, "", id)
        reason = dereason(substr(rest, length(id) + 1))
        # A left-open entry with no reason is malformed. A statement of deliberate
        # non-action with no stated reason is indistinguishable from having forgotten —
        # which is the defect this declaration exists to prevent.
        if (kind == "left-open" && reason == "") {
          printf "%s: %s:%d declares `left-open: %s` with no reason; a deliberate non-closure must say why\n", "closure-declaration.sh", path, NR, id > "/dev/stderr"
          bad = 1; next
        }
        # A TAB inside the reason would silently corrupt the record format, which is
        # TAB-separated: a downstream `cut -f3` sees four fields where the contract promises
        # three. Rejected rather than escaped -- escaping would silently rewrite text the
        # format promises to carry verbatim, and a reason is the one field a human reads.
        #
        # NO APOSTROPHES ANYWHERE IN THIS awk PROGRAM. It is a single-quoted shell string,
        # so one apostrophe in a comment closes it and every line after is parsed as shell.
        # That happened here and produced `syntax error near unexpected token`.
        if (index(reason, "\t") > 0) {
          printf "%s: %s:%d has a TAB inside its reason; the record format is TAB-separated, so use spaces\n", "closure-declaration.sh", path, NR > "/dev/stderr"
          bad = 1; next
        }
        if (id in kindof && kindof[id] != kind) {
          printf "%s: %s:%d names `%s` as %s, but it is already declared %s in the same block\n", "closure-declaration.sh", path, NR, id, kind, kindof[id] > "/dev/stderr"
          bad = 1; next
        }
        kindof[id] = kind
        nrec++
        printf "%s\t%s\t%s\n", kind, id, (reason == "" ? "-" : reason)
        next
      }
      printf "%s: %s:%d is not a declaration entry: %s\n", "closure-declaration.sh", path, NR, line > "/dev/stderr"
      bad = 1
    }
    END {
      # `closes: none` says this phase closed nothing. Mixing it with entries that name
      # ids is a contradiction, not a union, and a parser that quietly took the union
      # would let a typo delete the claim. This script enforces that on top of
      # the grammar itself.
      if (seen_none && nrec > 1) {
        printf "%s: %s:%d-%d mixes `closes: none` with entries that name ids; it must stand alone\n", "closure-declaration.sh", path, startln, endln > "/dev/stderr"
        bad = 1
      }
      if (bad) exit 1
    }
  ' "$path"
}

# ---------------------------------------------------------------------------
# reconcile.
#
# Compares the declaration against TWO sources and fails in EITHER direction:
#   - an id declared `closed:` whose ledger state is not `closed`
#   - a closure line THIS BRANCH ADDED whose id the declaration names under neither key
#
# The second direction is the one that matters. Without it, a
# phase closing three ids and declaring two leaves the third in the ledger, undeclared, and
# indistinguishable from a legitimate historical backfill.
# Scoping to THIS BRANCH is what lets both halves hold at once:
# historical backfills predate any current base and stay silent.
#
# Ledger state is read by shelling out to the deriver, never re-derived. A second computation
# of the same thing is a copy, and a copied guard drifts.
# ---------------------------------------------------------------------------
cmd_reconcile() {
  local ledger="" deriver="" rc=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --ledger)  ledger="$2";  shift 2 ;;
      --deriver) deriver="$2"; shift 2 ;;
      --) shift; break ;;
      -*) die "unknown option '$1'" ;;
      *) break ;;
    esac
  done
  [ -n "$ledger" ]  || die "reconcile: --ledger is required"
  [ -n "$deriver" ] || die "reconcile: --deriver is required"
  [ "$#" -ge 1 ]    || die "reconcile: at least one phase document is required"
  [ -r "$ledger" ]  || die "reconcile: cannot read ledger '$ledger'"
  [ -x "$deriver" ] || [ -r "$deriver" ] || die "reconcile: cannot read deriver '$deriver'"

  local decl
  decl="$(cmd_extract "$@")" || return 1

  # Absent declaration is NOT this subcommand's verdict either; the gate raises it.
  # Reconcile answers only "do the declaration and the ledger agree".
  local states added
  states="$("$deriver" --states 2>/dev/null || true)"

  local base_f added_f split
  base_f="$(mktemp)"; added_f="$(mktemp)"
  # shellcheck disable=SC1090
  . "$(dirname "$0")/lib/closure-log-added.sh" 2>/dev/null \
    || { rm -f "$base_f" "$added_f"; die "reconcile: helper scripts/lib/closure-log-added.sh is missing or unreadable"; }
  command -v closure_log_split >/dev/null 2>&1 \
    || { rm -f "$base_f" "$added_f"; die "reconcile: helper did not define closure_log_split"; }
  split="$(closure_log_split "$ledger" "$base_f" "$added_f")"
  added="$(closure_log_added_ids "$added_f")"
  rm -f "$base_f" "$added_f"

  # --- direction 1: every declared closure must exist in the ledger ---------------------------
  local kind id state
  while IFS="$(printf '\t')" read -r kind id _; do
    [ -n "${kind:-}" ] || continue
    case "$kind" in
      closed)
        state="$(printf '%s\n' "$states" | awk -F'\t' -v k="$id" '$1 == k { print $2; exit }')"
        case "$state" in
          closed*) printf 'ok        %s declared closed and the ledger agrees\n' "$id" ;;
          "")      printf 'FAIL      %s is declared closed but has NO event in %s — append one (see %s)\n' "$id" "$ledger" "$deriver"; rc=1 ;;
          *)       printf 'FAIL      %s is declared closed but the ledger last says "%s"\n' "$id" "$state"; rc=1 ;;
        esac
        ;;
      left-open)
        # Exempt by construction, not by a special case: a deliberate non-closure makes no
        # claim about the ledger, so there is nothing to reconcile.
        printf 'ok        %s declared left-open; no ledger event required\n' "$id"
        ;;
      none)
        printf 'ok        this phase declares it closed nothing\n'
        ;;
    esac
  done <<EOF
$decl
EOF

  # --- direction 2: every closure THIS BRANCH ADDED must be declared --------------------------
  local a
  for a in $added; do
    if printf '%s\n' "$decl" | awk -F'\t' -v k="$a" '$2 == k { found = 1 } END { exit !found }'; then
      printf 'ok        %s was added to the ledger and the declaration names it\n' "$a"
    else
      printf 'FAIL      %s was added to %s by this branch but the declaration names it under neither `closed:` nor `left-open:`\n' "$a" "$ledger"
      rc=1
    fi
  done

  return "$rc"
}

case "${1:-}" in
  extract)   shift; cmd_extract "$@" ;;
  reconcile) shift; cmd_reconcile "$@" ;;
  ""|-h|--help) usage ;;
  *) die "unknown subcommand '$1' (expected: extract, reconcile)" ;;
esac
