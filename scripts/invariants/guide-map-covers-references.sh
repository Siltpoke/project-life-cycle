#!/usr/bin/env bash
# Invariant: GUIDE.md's "Repository map" lists every references/*.md, and nothing else.
#
# The map opens by calling itself "the full annotated layout of this repo — every skill
# reference, hook, command, and root artifact". Without a check it drifts:
# references get added and never reach the map, so the word
# "every" was false and the reader looking for `retention.md` or `verify-gate.md` found
# nothing and had no way to tell absence-from-the-map from absence-from-the-repo.
#
# It drifted for exactly one reason: nothing checked it. Adding a reference and updating
# a hand-written tree are two separate acts, and only one of them is forced.
#
# BOTH DIRECTIONS, and the second is not decoration:
#   missing  — a file on disk that the map never names (the drift that happened)
#   phantom  — a name in the map with no file behind it (what a rename leaves behind,
#              and it reads to a user exactly like a broken link)
#
# SCOPE, stated rather than left to be discovered:
#   * Only the `references/` subtree of the map. The map also draws `hooks/`, `commands/`
#     and root artifacts; those have their own churn and their own arguments, and widening
#     this check to them without measuring them first is how a guard becomes a thing people
#     route around. Deliberately narrow, deliberately said so.
#   * Only `.md`. Non-markdown files under references/ (none today) are not judged.
#   * It checks PRESENCE, never the description text next to a name. A one-line note can be
#     stale in ways no mechanism can see, and pretending otherwise would be the same
#     over-claim this check exists to stop.
#
# The subtree is bounded by INDENTATION, not by a hard-coded line count: it starts at the
# `references/` node and ends at the first line that is neither blank nor indented — i.e.
# the next top-level entry. A count would go stale on the next edit, the same way a line-number
# citation does.
#
# jq-only envelope: no python3 here or in anything it calls.

set -uo pipefail

NAME="guide-map-covers-references"

# Subjects are ARGUMENTS, never fd 0. git feeds the pre-push hook a ref line on stdin and, when
# this was written, nothing down the chain redirected it — so a check that read stdin would
# silently scan that ref line, find no map in it, and pass; a failure mode already measured once
# in this directory (backlog-no-title-markers.sh, whose header records it).
# (The injected chain now carries a `</dev/null`, so that particular path no longer
# carries the ref lines here. The rule stands unchanged: it must not depend on what any caller
# happens to do with fd 0.)
GUIDE="${1:-GUIDE.md}"
REFDIR="${2:-skills/project-lifecycle/references}"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

[ -f "$GUIDE" ] || fail "$GUIDE not found (subject must exist; an absent map is not a pass)"
[ -d "$REFDIR" ] || fail "$REFDIR not found (subject must exist; an absent tree is not a pass)"

# --- names the map lists under references/ -------------------------------------
listed=$(awk '
  # Enter at the references/ node of the tree.
  /^[^ ].*references\/$/ || /references\/$/ { inref = 1; next }
  inref {
    # Leave at the first non-blank, non-indented line: the next top-level entry.
    if ($0 !~ /^[[:space:]]/ && $0 !~ /^$/) { inref = 0; next }
    # A leaf is `├── name.md` or `└── name.md`, at any indent.
    if (match($0, /(├──|└──)[[:space:]]+[A-Za-z0-9._-]+\.md/)) {
      leaf = substr($0, RSTART, RLENGTH)
      sub(/^(├──|└──)[[:space:]]+/, "", leaf)
      print leaf
    }
  }
' "$GUIDE" | sort -u)

ondisk=$(find "$REFDIR" -maxdepth 1 -name '*.md' -type f -exec basename {} \; 2>/dev/null | sort -u)

# An empty extraction means the map's shape changed under the parser, not that the tree is
# clean. Passing here would be a vacuous pass.
[ -n "$listed" ] || fail "extracted ZERO names from $GUIDE's references/ subtree — the map's layout changed and this parser no longer reads it (a vacuous pass is not a pass)"
[ -n "$ondisk" ] || fail "found ZERO .md files in $REFDIR — refusing to compare against an empty set"

missing=$(comm -13 <(printf '%s\n' "$listed") <(printf '%s\n' "$ondisk"))
phantom=$(comm -23 <(printf '%s\n' "$listed") <(printf '%s\n' "$ondisk"))

rc=0
if [ -n "$missing" ]; then
  printf 'FAIL %s: %s reference(s) on disk that the map never names:\n' "$NAME" "$(printf '%s\n' "$missing" | grep -c .)"
  printf '%s\n' "$missing" | sed 's|^|    |'
  rc=1
fi
if [ -n "$phantom" ]; then
  printf 'FAIL %s: %s name(s) in the map with no file behind them:\n' "$NAME" "$(printf '%s\n' "$phantom" | grep -c .)"
  printf '%s\n' "$phantom" | sed 's|^|    |'
  rc=1
fi
[ "$rc" -eq 0 ] || exit 1

pass "$(printf '%s\n' "$ondisk" | grep -c .) reference(s) on disk, all named by the map, no phantoms"
