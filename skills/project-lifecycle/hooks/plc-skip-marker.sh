#!/usr/bin/env bash
# skills/project-lifecycle/hooks/plc-skip-marker.sh
#
# Emit the two lines that stand in for a step the current mode did not run.
#
# THE TEMPLATE IS HERE AND NOWHERE ELSE, and neither line may be written by a model.
#
# Line 1 is machine-read. Its whole purpose is to make "which phases skipped which steps"
# COUNTABLE -- a hand-written variant is a row nobody ever counts, and the first consumer is the
# pre-merge brief's third item, which counts skipped steps straight off these markers rather than
# keeping a second list that would drift.
#
# Line 2 answers "why is this blank" for a human. It is English, like the rest of the skill's files;
# the plain-language rendering happens in conversation.
#
# The sentence says "set `mode: detailed`" unconditionally. `detailed` never skips a step, so a
# marker cannot legitimately carry mode=detailed and there is no self-contradicting case to cover.
#
# Envelope: bash only. No jq, no python3 -- there is nothing here to parse.
set -euo pipefail

if [ $# -ne 3 ]; then
  printf 'usage: plc-skip-marker.sh <step-id> <mode> <phase>\n' >&2
  printf '  step-id  the step that did not run, e.g. second-agent\n' >&2
  printf '  mode     the mode in effect, e.g. fast\n' >&2
  printf '  phase    the phase token, e.g. p1\n' >&2
  exit 1
fi

for arg in "$1" "$2" "$3"; do
  case "$arg" in
    "" ) printf 'plc-skip-marker.sh: empty argument -- a marker with a blank field is uncountable\n' >&2; exit 1 ;;
    *[!A-Za-z0-9._-]* ) printf 'plc-skip-marker.sh: %s contains a character the fixed format cannot carry\n' "$arg" >&2; exit 1 ;;
  esac
done

printf '<!-- plc-mode-skip: %s | mode=%s | phase=%s -->\n' "$1" "$2" "$3"
printf '_Not run under the %s mode. To fill it in: set `mode: detailed` and re-run this step._\n' "$2"
