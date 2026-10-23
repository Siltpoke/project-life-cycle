#!/usr/bin/env bash
# Invariant: no backlog HEADING carries a closure marker.
#
# State lives in `.claude/backlog-closures.tsv` and is derived from it. A heading that still says
# `✅ DONE` is a second, hand-maintained copy of that state sitting one line above the entry --
# and a second copy is exactly what the log replaces. Left unguarded it grows back: the next
# person closing something writes the word where they have always written it, the index quietly
# disagrees with the log, and the reader has no way to tell which one is stale.
#
# Only MARKER SHAPES are banned: the ✅ glyph, and DONE / CLOSED / MERGED in ALL CAPS. Prose is
# not. Case-normalising would red a heading reading "hold this until the drain is done", so the
# check is deliberately case-SENSITIVE, and that tolerance is itself pinned by a test.
#
# What it does NOT do, stated here rather than discovered later: it says nothing about whether an
# entry is really closed. That could only be decided by reading the heading -- an untrustworthy
# heuristic -- so a gate resting on it would certify the heuristic against
# itself. Closure lives in the log; this only stops the log's job being duplicated in prose.
#
# jq-only envelope: no python3 here or in anything it calls.

set -uo pipefail

NAME="backlog-no-title-markers"
F="docs/BACKLOG.md"

# Character-safe truncation for the FAIL diagnostic below. Sourced, not reimplemented:
# this repository already has one correct implementation and a second would be a second thing to
# keep right. Still jq-only -- `utf8-text.sh` is pure bash and calls no python3.
. "$(dirname "${BASH_SOURCE[0]}")/../utf8-text.sh"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

# The subject is an ARGUMENT, never whatever happens to be on fd 0.
#
# The first version took a piped stdin as the subject, so that a test could hand it one heading.
# That made the guard DEAD in the only place it runs automatically: git feeds the `pre-push` hook
# a line of `<local ref> <local sha> <remote ref> <remote sha>` on stdin, at the time nothing in
# the chain down to `close-gate.sh` redirected fd 0, and so the guard cheerfully scanned git's ref line,
# found no `## B` heading in it, and passed -- while a heading carrying `✅ DONE` sat
# unread in the file it exists to guard. Measured end to end, not reasoned:
#
#   $ printf 'refs/heads/x sha refs/heads/x sha\n' | bash scripts/invariants/...
#   PASS ...                                   # with a real marker sitting in docs/BACKLOG.md
#   $ bash scripts/invariants/...              # same tree, no pipe
#   FAIL ... <line>:## B<n> — ✅ DONE <date> ...
#
# It also silently DRAINED the pre-push hook's stdin, so any future reader of those ref lines
# would have got nothing. A guard whose subject comes from an ambient channel checks whatever the
# caller happened to be holding; this one now checks what it was told to check, or the ledger.
#
# UPDATE: the pre-push chain the hook installer injects now redirects fd 0
# from /dev/null, so on THAT path git's ref lines no longer reach this far. The measurement above
# is history rather than a live reading -- and the RULE it justifies is unchanged and still right,
# because the redirect is one caller's behaviour and a guard must not depend on any caller's. Left
# standing rather than deleted: the next person to "simplify" the subject back onto fd 0 needs to
# be able to read why it was moved off it.
SRC="${1:-}"
if [ -n "$SRC" ]; then
  [ -f "$SRC" ] || fail "no such file: $SRC"
else
  # WHY THIS BRANCH SPEAKS: silence would be indistinguishable from a guard that ran and found
  # nothing. That reason is unchanged. The REASON IT GIVES had to change.
  #
  # It used to say absent docs/ is the normal state on every other clone, because
  # `docs/` WAS gitignored and the tracked count WAS 0 -- true when written, retired by p39.
  # Measured: `git ls-files docs/` returns a non-empty list. So an absent `docs/BACKLOG.md` now
  # means a broken or partial tree, NOT a fresh clone, and the message must not hand the reader
  # a reason that stopped being true. The old sentence is quoted here rather than deleted,
  # because the next person to wonder why this branch exists needs to be able to read it.
  #
  # The verdict is deliberately still `pass`: this guard's job is closure markers in headings,
  # and "the file I check is missing" is not a finding about headings. Whether an absent
  # `docs/BACKLOG.md` should fail SOMETHING is a real question and it belongs to whatever owns
  # tree completeness, not here.
  [ -f "$F" ] || pass "$F is not present in this tree — nothing to check. NOTE: this file is tracked, so an absent copy means a partial or broken tree rather than a fresh clone"
  SRC="$F"
fi

OFFENDERS="$(grep -nE '^## B' "$SRC" | grep -E '✅|[^A-Za-z](DONE|CLOSED|MERGED)([^A-Za-z]|$)' || true)"

if [ -n "$OFFENDERS" ]; then
  printf 'FAIL %s: %s heading(s) still carry a closure marker. State is derived from\n' \
         "$NAME" "$(printf '%s\n' "$OFFENDERS" | grep -c '')" >&2
  printf '%s: .claude/backlog-closures.tsv — append an event there and delete the words here.\n' "$NAME" >&2
  # CHARACTERS, not bytes, and one line at a time.
  #
  # This was `cut -c1-140`, and `cut -c` counts BYTES under GNU coreutils in EVERY locale -- the
  # finding `scripts/utf8-text.sh` exists for (p39: a generator sliced a CJK row mid-character
  # and rewrote a backlog file as invalid UTF-8, reported by
  # CI). `$OFFENDERS` is derived from heading PROSE, and this file's own header says prose is a
  # legal subject, so non-ASCII input is expected rather than exceptional. Measured: under
  # `LC_ALL=C` a CJK heading came out of this line with a dangling \351 lead byte -- mojibake in
  # the terminal.
  #
  # It does NOT reproduce on a macOS shell, where BSD `cut -c` is character-aware in a
  # UTF-8 locale, so the first measurement here said the bug was absent. `LC_ALL=C` is the
  # portable oracle; the test pins it.
  #
  # Per line, because `plc_utf8_head` takes one string and `$OFFENDERS` holds one row per
  # offending heading. The bound stays 140 -- now 140 characters -- because the reason for a
  # bound is unchanged: this can hold every offending heading in a large file.
  while IFS= read -r _line; do
    printf '%s\n' "$(plc_utf8_head "$_line" 140)" >&2
  done <<EOF_OFFENDERS
$OFFENDERS
EOF_OFFENDERS
  fail "closure markers found in $SRC"
fi

pass "no closure markers in any heading of $SRC"
