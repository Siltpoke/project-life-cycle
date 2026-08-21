#!/usr/bin/env bash
# skills/project-lifecycle/hooks/plc-verify-stage.sh
#
# Dispatch ONE verification stage and write its own report. Running one must not run the others.
#
# WHY THIS EXISTS AT ALL (the negative constraint the design carries for a later
# feature). Under the compressed setting all the verification stages are carried out by a single
# reviewer agent, back to back. The tempting shortcut is to fold their instructions into the
# implementer's prompt and call it "two agents" -- and that shortcut DESTROYS the stages as
# addressable units. A later feature that wants to expose them as commands a user types would find
# nothing left to expose. So: the compressed setting changes WHO does the work and HOW MANY agents
# are dispatched. It never changes WHETHER a stage runs, and every stage stays individually
# dispatchable with a report of its own.
#
# THIS FILE NAMES NO STAGE. The legal set comes out of the dispatch block in references/mode.md, the
# same way the resolver takes its keys from the expansion block. scripts/test_mode_surfaces.py greps
# this file for every declared stage name and requires zero hits: a hardcoded list here would agree
# with the document today and drift from it silently tomorrow.
#
# Envelope: bash + jq only.
#
# Exit codes:
#   0  the named stage ran and its report was written
#   1  bad invocation, or the report could not be written
#   2  the named stage is not in the declared set -- named, never guessed
#   3  the dispatch block is missing or malformed: nothing can be concluded
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAP="${PLC_MODE_DOC:-$HERE/../references/mode.md}"

die() { printf '%s\n' "$*" >&2; exit "${2:-1}"; }

[ $# -ge 1 ] || die "usage: plc-verify-stage.sh <stage> [--out DIR]"
want="$1"; shift
out="."
while [ $# -gt 0 ]; do
  case "$1" in
    --out) [ $# -ge 2 ] || die "--out needs a directory"; out="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -r "$MAP" ] || die "cannot read the mode document: $MAP" 3

if ! block="$(awk '
  /<!-- plc-dispatch:begin -->/ { inblk = 1; next }
  /<!-- plc-dispatch:end -->/   { inblk = 0; next }
  inblk && /^```json$/          { infence = 1; fences++; next }
  inblk && /^```$/              { infence = 0; next }
  inblk && infence              { print }
  END                           { if (fences != 1) exit 9 }
' "$MAP")"; then
  die "the mode document must hold exactly one fenced dispatch block: $MAP" 3
fi
jq -e . >/dev/null 2>&1 <<<"$block" || die "the dispatch block is not valid json: $MAP" 3

declared="$(jq -r '.stages[]?' <<<"$block")"
[ -n "$declared" ] || die "the dispatch block declares no stages: $MAP" 3

known=0
while IFS= read -r s; do
  [ "$s" = "$want" ] && known=1
done <<<"$declared"
if [ "$known" != 1 ]; then
  die "unknown verification stage: $want (declared: $(printf '%s' "$declared" | tr '\n' ' '))" 2
fi

[ -d "$out" ] || die "output directory does not exist: $out"
report="$out/$want-report.md"

# The report is created for the named stage ONLY. Nothing here touches a sibling stage's path, and
# the test that matters asserts the siblings are absent afterwards rather than that this line is
# correct -- an assertion about the file system, not about the code.
{
  printf '# %s report\n\n' "$want"
  printf -- '- dispatched: %s\n' "$want"
  printf -- '- dispatched-alone: yes\n'
  printf -- '- findings: (to be filled by the agent that runs this stage)\n'
} > "$report"

printf 'ok  %s dispatched alone; report at %s\n' "$want" "$report"
