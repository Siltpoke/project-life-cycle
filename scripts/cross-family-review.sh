#!/usr/bin/env bash
# cross-family-review.sh — cross-family blind-2nd-agent adapter.
#
# Runs the brainstorm's blind 2nd agent on a DIFFERENT CLI family (codex) for
# genuine lineage diversity. Armed-optional: this script is invoked ONLY when
# `second-agent-family: foreign:codex` is armed. Every failure path degrades to
# `status:fallback` in the envelope — the caller then runs today's same-family
# subagent — so a foreign reviewer that is missing, unauthed, slow, or broken never
# corrupts the brainstorm.
#
# IT DOES NOT ALWAYS EXIT 0, and that is a deliberate BREAKING change. The old contract
# said it did, which meant a chained caller could not tell "a review came back" from
# "no review happened" without parsing the envelope, and `runner && next-step` ran the
# next step either way. See emit() for the three codes and what each one asks of you.
#
# Trust boundary: `-s read-only` is a FILESYSTEM sandbox, NOT privacy isolation.
# The caller must pass a SYNTHESIZED decision packet (question + options +
# research), never raw workspace access, and must have taken arm-time consent
# for cross-provider data flow. See references/cross-family-review.md.
#
# Usage: cross-family-review.sh --family codex --packet <file> --out <file> [--timeout 120]
#          [--schema <file>] [--require <field>] [--payload-key <name>]
#
# The three optional flags exist so a SECOND caller can reuse these four gates instead of
# copying them. They all default to the brainstorm decision contract this script was built for, so
# an invocation that omits them is byte-identical to before. The alternative was a second script
# with its own copy of the gates, and a copied guard drifts.
#   --schema       the JSON Schema handed to the foreign CLI (default: the decision packet schema)
#   --require      the field gate 4 insists on, i.e. the one that proves a real answer came back
#   --payload-key  the name the payload takes in the emitted envelope
#
# Emits <out>, key-disjoint by arm — the key that is ABSENT is the discriminator:
#   succeeded: {"engine","status":"succeeded",<payload-key>: <payload>}
#   fallback:  {"engine","status":"fallback","fallback_reason":"<reason>"}
#   status ∈ {succeeded, fallback}
#   fallback_reason ∈ {unsupported-family, not-installed, not-authed,
#                      spawn-failed, quota-exhausted, unparseable, empty-answer, timed-out}
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA="${SCRIPT_DIR}/cross-family-review.schema.json"
REQUIRE="independent_pick"
PAYLOAD_KEY="pick"

FAMILY="" PACKET="" OUT="" TIMEOUT="120"
while [ $# -gt 0 ]; do
  case "$1" in
    --family)      FAMILY="$2";      shift 2;;
    --packet)      PACKET="$2";      shift 2;;
    --out)         OUT="$2";         shift 2;;
    --timeout)     TIMEOUT="$2";     shift 2;;
    --schema)      SCHEMA="$2";      shift 2;;
    --require)     REQUIRE="$2";     shift 2;;
    --payload-key) PAYLOAD_KEY="$2"; shift 2;;
    *) shift;;
  esac
done
# A schema path that does not exist would reach codex as a broken --output-schema and come back
# as `spawn-failed`, i.e. a caller typo would be indistinguishable from a foreign CLI that is
# down. Named at the point of use instead.
[ -r "$SCHEMA" ] || { echo "FATAL: --schema '$SCHEMA' is missing or unreadable" >&2; exit 2; }

# Emit a result JSON to --out (atomic) and exit with the code that describes what
# happened. $1=status $2=reason $3=pick-file(optional)
#
# EXIT CODES — the rule is about the CALLER, not about severity:
#   0  a real answer came back and is in --out
#   2  the invocation itself was wrong (an unreadable --schema; an unsupported family)
#   3  the invocation was right and no answer came back — a legitimate fallback
#   1  the answer could not be WRITTEN (see below); not "no answer", but "not stored"
#
# `unsupported-family` exits 2, not 3. The envelope still says status:"fallback", so
# every caller that reads the envelope behaves identically either way; the only thing
# exit 2 breaks is an `&&` chain, and a mis-typed --family is exactly the case where an
# `&&` chain SHOULD break. Calling a configuration typo "the foreign reviewer had no
# answer" points the diagnostic at the wrong actor.
#
# THE ENVELOPE IS A DISCRIMINATED UNION: the two arms are KEY-DISJOINT. The success arm
# carries no `fallback_reason` key at all; the fallback arm carries no payload key at
# all. Arm membership is readable from key presence, and no envelope exists in which the
# payload slot is present-but-meaningless.
#
# Its honest weight, stated here so no one counts it as more than it is: a consumer
# reading `.review` in jq still gets `null` on a fallback envelope, because jq cannot
# tell absent from null on a path read. Key-disjointness buys existing consumers almost
# nothing — it is a human-reading, debugging and schema-hygiene improvement. WHAT MAKES
# A CONSUMER SAFE IS THE EXIT CODE ABOVE, not this.
emit() {
  local status="$1" reason="$2" pickfile="${3:-}"
  local tmp="${OUT}.tmp.$$" rc
  if [ "$status" = "succeeded" ] && [ -n "$pickfile" ]; then
    rc=0
    jq -n --slurpfile pick "$pickfile" --arg k "$PAYLOAD_KEY" \
      '{engine:"foreign:codex", status:"succeeded"} + {($k): $pick[0]}' > "$tmp" || exit 1
  else
    case "$reason" in
      unsupported-family) rc=2;;
      *)                  rc=3;;
    esac
    jq -n --arg r "$reason" \
      '{engine:"foreign:codex", status:"fallback", fallback_reason:$r}' > "$tmp" || exit 1
  fi
  # Writing the envelope is part of the signal contract. Without these guards a
  # full or read-only disk gives a successful-looking exit 0 with no trustworthy
  # envelope on disk -- a claim wider than its mechanism. Exit 1,
  # not 3: an answer DID come back, it just could not be stored, and a caller told "no
  # answer" would retry the foreign reviewer for nothing.
  #
  # NAMED LIMITS, both measured rather than predicted:
  #
  # 1. THE TWO WRITE GUARDS ARE MUTUALLY REDUNDANT under the only fixture that can
  #    reach them (an unwritable --out directory), so NEITHER IS INDIVIDUALLY
  #    KILLABLE. Measured: removing the `> "$tmp"` guard alone leaves the run green
  #    because `mv` then fails on a temp file that was never created and this guard
  #    fires; removing this guard alone leaves it green because the write already
  #    failed; removing BOTH turns the fixture red. The matrix therefore counts the envelope's
  #    write half as ONE killable unit, not two. The redundancy is kept deliberately —
  #    defence in depth is worth more here than a tidier kill count.
  #
  # 2. `mv -f <tmp> <an existing directory>` exits 0 on this platform: the envelope
  #    lands INSIDE the directory instead of at --out, and no exit code says so. That
  #    failure mode is not reachable by any fixture in this suite and ships as a
  #    deliberately un-oracled line, named here so the next reader sees a decision
  #    rather than an oversight.
  mv -f "$tmp" "$OUT" || exit 1

  # Mirror the envelope into the lifecycle ledger, and MAP it rather than re-deriving
  # it. The envelope above is already this script's judgement about whether the foreign reviewer
  # ran; computing a second opinion here would be two mechanisms for one fact, and they would
  # drift. `succeeded` is an observation, `fallback` is an observation that it did NOT happen --
  # both are things this script watched, so both are `observed:true` and neither is an
  # agent-authored claim.
  #
  # FAIL-OPEN, ALWAYS. Every failure below is swallowed. A stage whose record never got
  # written reads as claimed/unknown in /plc-status -- never observed, and never a failure of this
  # script, whose exit code belongs to the REVIEW and not to the bookkeeping about it.
  ledger_mirror "$status" "$reason" || true

  exit "$rc"
}

ledger_mirror() {
  local status="$1" reason="$2"
  [ "${PLC_LEDGER:-1}" = "1" ] || return 0
  local here emitter runner run_id ledger now attempt
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  emitter="$here/ledger-append.sh"; runner="$here/ledger-run.sh"
  [ -r "$emitter" ] && [ -r "$runner" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  local root; root="$(git -C "$here" rev-parse --show-toplevel 2>/dev/null)" || return 0
  run_id="$(/bin/bash "$runner" run-id --phase "${PLC_PHASE:-nophase}" 2>/dev/null)" || return 0
  [ -n "$run_id" ] || return 0
  ledger="$(/bin/bash "$runner" ledger-path "$run_id" --repo-root "$root" --owner-pid $$ 2>/dev/null)" || return 0
  # Same as close-gate.sh: a refusal from `next-attempt` means the ledger could not be read well
  # enough to allocate an id, so the mirror row is SKIPPED rather than written on a guess. Missing
  # renders claimed/unknown; a duplicate attempt id is silent and permanent.
  if ! attempt="$(/bin/bash "$runner" next-attempt "$ledger" cross_family_review 2>/dev/null)" \
     || [ -z "$attempt" ]; then
    return 0
  fi
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  set -- append --file "$ledger" --run-id "$run_id" \
    --repo-id "$(git -C "$root" rev-list --max-parents=0 HEAD 2>/dev/null | head -1)" \
    --phase "${PLC_PHASE:-nophase}" --stage-id cross_family_review --attempt-id "$attempt" \
    --type stage_observation --observed true --observer cross-family-review.sh \
    --started-at "$now" --completed-at "$now"
  if [ "$status" = "succeeded" ]; then
    set -- "$@" --status done
  else
    # A fallback is a FAILED stage, not an absent one: the script ran, the foreign reviewer did
    # not, and the reason it did not is the most useful thing anyone will ever read off this row.
    set -- "$@" --status failed --attribute "fallback_reason=${reason:-unstated}"
  fi
  /bin/bash "$emitter" "$@" >/dev/null 2>&1 || true
  return 0
}

# --- Gate 0: family supported (only codex is BUILT; others are design-only) ---
[ "$FAMILY" = "codex" ] || emit fallback "unsupported-family"

# --- Gate 1: binary installed + not a project-local shim -------------------
BIN="${CODEX_BIN:-codex}"
RESOLVED="$(command -v "$BIN" 2>/dev/null || true)"
[ -n "$RESOLVED" ] && [ -x "$RESOLVED" ] || emit fallback "not-installed"
# Reject a binary resolved from inside the current git repo tree (shim spoofing).
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
case "$RESOLVED" in
  "$REPO_ROOT"/*) [ -n "$REPO_ROOT" ] && emit fallback "not-installed";;
esac

# --- Gate 2: authed (noninteractive probe) ---------------------------------
# codex writes auth status to STDERR (verified codex-cli 0.143.0: "Logged in using
# ChatGPT" on stderr, exit 0). The old `2>/dev/null` discarded stderr, so the probe
# always saw empty stdout and ALWAYS fell back not-authed — cross-family never fired
# even when authed. Merge stderr in (`2>&1`) and match the authed-POSITIVE phrase
# ("logged in using|as"); "Not logged in" lacks that tail, so an unknown/negative
# output degrades to not-authed (safe same-family fallback), never a false authed.
if ! "$RESOLVED" login status </dev/null 2>&1 | grep -qiE "logged in (using|as)"; then
  emit fallback "not-authed"
fi

# --- Gate 3: spawn (read-only, ephemeral, noninteractive, wall-clock cap) ---
LASTMSG="$(mktemp)"
# THE ENGINE'S DIAGNOSTIC IS KEPT, because the old code threw it away and then
# guessed. stderr went to /dev/null and every non-zero exit was called `spawn-failed`.
#
# MEASURED: the runner reported
# {"status":"fallback","fallback_reason":"spawn-failed"} and the real cause was
# `ERROR: You've hit your usage limit. ... try again later.` on stderr,
# exit 1, with the binary on PATH, logged in, and the process having run to completion.
# Nothing about the spawn failed. The fallback was right; the reason it gave was not --
# and it points the maintainer at the process, the sandbox and the arguments while the
# actual remedy is to wait for the limit to reset. An earlier defect had the same shape: the auth probe read
# stdout where codex writes stderr, so it ALWAYS fell back `not-authed`.
ENGINE_ERR="$(mktemp)"
trap 'rm -f "$LASTMSG" "$ENGINE_ERR"' EXIT
timeout "$TIMEOUT" "$RESOLVED" exec --json --ephemeral -s read-only --skip-git-repo-check \
  --output-schema "$SCHEMA" -o "$LASTMSG" - < "$PACKET" >/dev/null 2>"$ENGINE_ERR"
rc=$?
[ "$rc" -eq 124 ] && emit fallback "timed-out"
if [ "$rc" -ne 0 ]; then
  # ONE pattern, and it is the one that was measured. Case-insensitive, substring, no
  # anchoring: the sentence carries a reset timestamp that differs every time, so anchoring
  # on the whole line would classify exactly one outage.
  #
  # DELIBERATELY NARROW, and the narrowness is the honest part. Quota exhaustion is not
  # uniform -- a second shape has been observed, `exit 0` with NO output,
  # which is indistinguishable from `empty-answer` by construction and is left to gate 4.
  # Guessing at further wordings would be a claim wider than the measurement. Anything this
  # cannot classify stays `spawn-failed`, where it is now a true statement rather than a
  # default dressed as a diagnosis.
  #
  # `grep -q` inside an `if`: a non-match exits 1, and this script's `emit` path must be
  # reached rather than skipped.
  if grep -qi 'usage limit' "$ENGINE_ERR" 2>/dev/null; then
    emit fallback "quota-exhausted"
  fi
  emit fallback "spawn-failed"
fi

# --- Gate 4: output parseable, field present, and the field has CONTENT ----
# Three questions, asked separately and in this order, because they have different
# answers and conflating them is how a blank answer got reported as a review.
#
# Do NOT collapse these into one predicate and split the reason classes on jq's exit
# code: real jq exits 4 on an empty file, 5 on malformed input, and 5 again on a
# top-level array, so an exit-code split silently reclassifies an empty -o file. This
# design never classifies by exit code — only by WHICH STEP failed.

# A. Did anything parse at all?
jq -e . "$LASTMSG" >/dev/null 2>&1 || emit fallback "unparseable"

# B. Is the required field present and usable? UNTOUCHED on purpose. This is the
# original gate, and leaving it in front of the new predicate is what keeps `false`
# falling back. An emptiness rewrite that replaced this line would stringify `false`
# to "false", call it non-empty, and start ACCEPTING it — un-fixing a case that
# already works, with no existing assertion noticing. Absent / null / false all land
# here and keep the `unparseable` reason word they have today.
# `.[$f]` is a LITERAL key lookup, not a path traversal: `--require a.b` asks for the
# key named "a.b", matching how emit() writes `{($k): …}`. Pinned by a fixture.
jq -e --arg f "$REQUIRE" '.[$f]? // empty' "$LASTMSG" >/dev/null 2>&1 \
  || emit fallback "unparseable"

# C. Does that field carry content? Emptiness is defined PER TYPE — never length in
# the abstract, never "looks wrong". The polarity is load-bearing and is stated so the
# next reader cannot flip it by accident: THE EXPRESSION IS TRUE IFF THE ANSWER IS
# NON-EMPTY, and any non-zero jq exit is a fallback. Written the other way round
# ("true means empty"), malformed input would fail-open into a reported review.
# `0` is not empty and stays passing — a numeric verdict where a string was expected is
# a schema complaint, and a schema option was deliberately not added. Named, not overlooked.
jq -e --arg f "$REQUIRE" '
  .[$f] as $v
  | if   ($v|type) == "string" then ($v | gsub("\\s"; "")) != ""
    elif ($v|type) == "array"  then ($v | length) > 0
    elif ($v|type) == "object" then ($v | keys | length) > 0
    else true
    end
' "$LASTMSG" >/dev/null 2>&1 || emit fallback "empty-answer"

emit succeeded "" "$LASTMSG"
