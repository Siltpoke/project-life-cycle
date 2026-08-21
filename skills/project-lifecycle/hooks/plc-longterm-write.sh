#!/usr/bin/env bash
# skills/project-lifecycle/hooks/plc-longterm-write.sh
#
# Write the long-term entries the user TICKED, as a separate act after the choosing.
#
# THIS IS THE SECOND HALF OF THE LOOP. The first half is that the candidates never enter the PR's
# diff, which scripts/invariants/longterm-candidates-not-in-diff.sh enforces. Without this script
# there is no authorised route at all and the feature would just be a prohibition; without the
# invariant, an unticked box is decoration because merging writes the change anyway.
#
# IT REFUSES TO DO NOTHING QUIETLY. Called with no ticked entries it exits non-zero and says so,
# rather than producing an empty commit -- an empty commit here would read, to anyone reviewing the
# history later, exactly like a write that happened.
#
# Brief format, one entry per line, inside the long-term item:
#     - [x] <path> :: <text to append>
#     - [ ] <path> :: <text the user did not tick>
#
# Envelope: bash + git.
#
# Exit codes: 0 wrote and committed, 1 nothing was selected, 2 bad invocation.
set -euo pipefail

die() { printf '%s\n' "$*" >&2; exit "${2:-2}"; }

brief=""
while [ $# -gt 0 ]; do
  case "$1" in
    --brief) [ $# -ge 2 ] || die "--brief needs a path"; brief="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -n "$brief" ] || die "usage: plc-longterm-write.sh --brief <brief.md>"
[ -r "$brief" ] || die "cannot read $brief"

ticked="$(awk '
  /<!-- plc-brief-item: long-term -->/ { inblk = 1; next }
  inblk && /<!-- plc-brief-item: /     { inblk = 0 }
  inblk && /^[[:space:]]*-[[:space:]]*\[[xX]\][[:space:]]*/ {
    sub(/^[[:space:]]*-[[:space:]]*\[[xX]\][[:space:]]*/, "")
    print
  }
' "$brief")"

if [ -z "$ticked" ]; then
  printf 'nothing was selected -- no long-term record is written, and no empty commit is made\n' >&2
  exit 1
fi

written=""
while IFS= read -r entry; do
  [ -n "$entry" ] || continue
  case "$entry" in
    *" :: "*) ;;
    *) die "malformed entry (expected `<path> :: <text>`): $entry" ;;
  esac
  path="${entry%% :: *}"
  text="${entry#* :: }"
  [ -n "$path" ] && [ -n "$text" ] || die "malformed entry: $entry"
  [ -e "$path" ] || die "the entry names a file that does not exist: $path"
  printf -- '- %s\n' "$text" >> "$path"
  written="$written $path"
done <<<"$ticked"

# shellcheck disable=SC2086
git add $written
git commit -q -F - <<EOF
chore: write the long-term entries the user selected

Written as a separate act AFTER the selection, never by merging. Entries the
user left unticked are not here and were never in the branch's diff.

Longterm-write: $(printf '%s\n' "$ticked" | tr '\n' ';')
EOF

printf 'ok  wrote %d selected entr(y|ies) and committed with an authorising trailer\n' \
  "$(printf '%s\n' "$ticked" | wc -l | tr -d ' ')"
