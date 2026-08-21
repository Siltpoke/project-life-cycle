#!/usr/bin/env bash
# Invariant `fast-keeps-the-net`: `fast` does not switch off a single safety net.
#
# FOUR ASSERTIONS, and each one is structural rather than a promise in prose, because a promise is
# what the presets already are.
#
#   N1             the deterministic gate NEVER READS the approval-timing key. Not "reads it and
#                  ignores it" -- does not read it. `pr-boundary` therefore cannot switch the gate
#                  off, by construction rather than by intention.
#   N2             the shipped contract's net-delete teeth fire off the `Archetype:` trailer, and
#                  the mode document defines `silent` as INFER AND APPLY, DO NOT ASK. Read as "do
#                  not classify" the trailer stops being written and the teeth go quiet with
#                  nothing reporting it.
#   N3             the fast preset's smoke value is the one the mode document documents as
#                  "checklist non-blocking, automation still runs and still gates" -- and the
#                  document says so in those words.
#   N4            no preset sets a value that the document lists as disabling a net.
#
# WHAT IT CANNOT DO, said rather than implied: it reads declarations and code shape. It does not run
# a phase. Whether a real fast run actually dispatches the automated smoke is unmeasured here and
# unmeasurable here.
#
# Verdicts: 0 pass, 1 a net is reachable-off, 3 could not run.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Overridable so each assertion can be shown to RED against a fixture. The three files it really
# reads are shipped product files, so a RED is demonstrated on a fixture copy rather than by editing
# them in place -- and a guard nobody has seen fail is a guard nobody has run.
GATE="${NET_GATE:-scripts/close-gate.sh}"
CONTRACT="${NET_CONTRACT:-skills/project-lifecycle/references/close-gate.md}"
MODE_DOC="${NET_MODE_DOC:-skills/project-lifecycle/references/mode.md}"

for f in "$GATE" "$CONTRACT" "$MODE_DOC"; do
  [ -r "$f" ] || { printf 'COULD NOT RUN: %s is not readable\n' "$f" >&2; exit 3; }
done

fail=0
say() { printf 'FAIL %s\n' "$*" >&2; fail=1; }

# --- N1: the gate does not branch on the approval-timing key -------------------------------------
# Comments are allowed to mention it -- the contract explains the key at length. What may not exist
# is a line where the token participates in a test, a case, or an assignment.
branchy="$(/usr/bin/grep -nE 'pr-boundary|per-task' "$GATE" | /usr/bin/grep -vE ':[[:space:]]*#' || true)"
if [ -n "$branchy" ]; then
  say "N1: the deterministic gate appears to branch on the approval-timing key:"
  printf '%s\n' "$branchy" | sed 's/^/    /' >&2
fi

# --- N2: the net-delete teeth are trailer-driven, and `silent` still writes the trailer ----------
/usr/bin/grep -qF 'Archetype:[[:space:]]*sweep' "$CONTRACT" \
  || say "N2: the shipped contract no longer matches an 'Archetype: sweep' trailer"

flat="$(tr '\n' ' ' < "$MODE_DOC")"
case "$flat" in
  *"infer and apply, do not ask"*) ;;
  *) say "N2: the mode document no longer defines the silent archetype value as infer-and-apply" ;;
esac
case "$flat" in
  *"It does **not** mean *do not"*) ;;
  *) say "N2: the mode document dropped the warning against reading silent as do-not-classify" ;;
esac

# --- N3: the automated smoke still runs and still gates ------------------------------------------
case "$flat" in
  *"Track B runs automatically **and is a gate item**"*) ;;
  *) say "N3: the mode document no longer states that the automated smoke is a gate item" ;;
esac
case "$flat" in
  *'not equal to not doing smoke'*|*'not** mean "no smoke"'*|*'does not mean "no smoke"'*|*'Treating `smoke-mode: self` as "no smoke"'*) ;;
  *) say "N3: the mode document dropped the warning against reading the self smoke value as no-smoke" ;;
esac

# --- N4: no preset disables a net -----------------------------------------------------------------
block="$(awk '
  /<!-- plc-mode-map:begin -->/ { inblk = 1; next }
  /<!-- plc-mode-map:end -->/   { inblk = 0; next }
  inblk && /^```json$/          { infence = 1; next }
  inblk && /^```$/              { infence = 0; next }
  inblk && infence              { print }
' "$MODE_DOC")"
jq -e . >/dev/null 2>&1 <<<"$block" || { printf 'COULD NOT RUN: the expansion map is unreadable\n' >&2; exit 3; }

# `off` and `none` are the two shapes a disabling value takes across this skill's keys. A preset is
# not allowed to carry either: turning something off has to be an explicit act by the project, never
# a side effect of picking a mode.
offenders="$(jq -r '.presets | to_entries[] | .key as $m | .value | to_entries[]
  | select(.value == "off" or .value == "none")
  | "\($m): \(.key)=\(.value)"' <<<"$block")"
if [ -n "$offenders" ]; then
  say "N4: a preset switches something off, which a preset may never do:"
  printf '%s\n' "$offenders" | sed 's/^/    /' >&2
fi

[ "$fail" = 0 ] || exit 1
printf 'ok  fast keeps the net: gate does not read the approval-timing key; teeth are trailer-driven; automated smoke still gates; no preset carries a disabling value\n'
