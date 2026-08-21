#!/usr/bin/env bash
# skills/project-lifecycle/hooks/plc-careful-write.sh
#
# Write the user's tick-box answer back into CLAUDE.md as a `careful-paths:` key.
#
# WHY THIS IS A SCRIPT AND NOT AN INSTRUCTION. Written as an instruction, the whole chain --
# render the tick-boxes, take a
# selection, save it, never ask again -- has no mechanism behind it. An acceptance assertion of
# "the key is present" is met by a key the test itself wrote, and an implementation that does nothing at
# all passes every check. Making the write a separate callable act is what turns "did it happen"
# into a question a mutant can answer.
#
# Reads the chosen paths from stdin, one per line, or from --paths.
#
# Envelope: bash only. No `mapfile` -- macOS still ships bash 3.2.
#
# Exit codes, and each distinction is load-bearing:
#   0  written, or already correct (idempotent -- running twice leaves the file byte-identical)
#   1  bad invocation
#   2  the key already has a value and it differs: REFUSED. A user's own declaration is never
#      silently rewritten by a tool that proposed the alternatives.
#   3  nothing was chosen: nothing is written, and that is a legal outcome, not an error
set -euo pipefail

die() { printf '%s\n' "$*" >&2; exit "${2:-1}"; }

claude_md="" paths_arg="" force_key="careful-paths"
while [ $# -gt 0 ]; do
  case "$1" in
    --claude-md) [ $# -ge 2 ] || die "--claude-md needs a path"; claude_md="$2"; shift 2 ;;
    --paths)     [ $# -ge 2 ] || die "--paths needs a value";    paths_arg="$2"; shift 2 ;;
    --key)       [ $# -ge 2 ] || die "--key needs a value";      force_key="$2"; shift 2 ;;
    -h|--help)   printf 'usage: plc-careful-write.sh --claude-md PATH [--paths "a,b"]  (else reads stdin)\n'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -n "$claude_md" ] || die "usage: plc-careful-write.sh --claude-md PATH [--paths \"a,b\"]"
[ -f "$claude_md" ] || die "cannot read $claude_md"

if [ -n "$paths_arg" ]; then
  chosen="$(printf '%s' "$paths_arg" | tr ',' '\n')"
else
  chosen="$(cat)"
fi
chosen="$(printf '%s\n' "$chosen" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d')"

if [ -z "$chosen" ]; then
  # The user ticked nothing. That is a real answer and it is allowed -- see the third hard
  # constraint on the suggester. Writing an empty key would be indistinguishable from a
  # half-finished run, so nothing is written and the caller is told which case this is.
  printf 'nothing-chosen\tno careful-paths written; the user marked nothing\n'
  exit 3
fi

value="$(printf '%s' "$chosen" | paste -sd, - | sed 's/,/, /g')"

# An existing declaration is the user's, not ours.
existing="$(awk -v k="$force_key" '
  /^[[:space:]]*#/ { next }
  index($0, k ":") == 1 { sub("^" k ":[[:space:]]*", ""); sub("[[:space:]]*#.*$", ""); print; exit }
' "$claude_md")"

if [ -n "$existing" ]; then
  if [ "$existing" = "$value" ]; then
    # IDEMPOTENT. Running twice must leave the file byte-identical, or a re-run quietly grows a
    # duplicate key and the reader of CLAUDE.md gets two answers to one question.
    printf 'unchanged\t%s: %s\n' "$force_key" "$value"
    exit 0
  fi
  printf 'refused\t%s already declares: %s\n' "$force_key" "$existing" >&2
  exit 2
fi

printf '%s: %s\n' "$force_key" "$value" >>"$claude_md"
printf 'written\t%s: %s\n' "$force_key" "$value"
