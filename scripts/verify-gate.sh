#!/usr/bin/env bash
# verify-gate.sh — per-PR "qualified?" artifact VALIDATOR (Half A). Envelope: bash + git + jq
# + coreutils. NO non-jq interpreters (AC7). Reads artifacts other runtimes produce; never runs an
# LLM or a test. Exit 0 = qualified-to-merge (deterministic conjunction); non-zero = block.
#
# TRUST BOUNDARY (AC9): this gate TRUSTS the CI-regenerated producer
# artifacts it reads (report.json, potency-result.json, and, where a liveness layer is
# built — quarantine.json / canary-result.json). It is STALENESS-resistant (SHA-binding defeats a
# stale or copied artifact) but NOT forgery-resistant: a hand-crafted artifact (e.g. a fabricated
# QUALIFIED report, or a quarantine.json with a backend's entry deleted) is not detected here.
# Forgery-resistance belongs to a CI-ATTESTATION layer the adopter owns (a trusted CI identity as
# the sole writer of these artifacts / OIDC / signed provenance) — never this portable jq gate.
#
# Usage: verify-gate.sh <BASE_SHA> <HEAD_SHA>
#   PLC_REPO   repo root (default: git rev-parse --show-toplevel)
#   PLC_REPORT report path (default: $PLC_REPO/.plc/report.json)
set -euo pipefail

REPO="${PLC_REPO:-$(git rev-parse --show-toplevel)}"
BASE="${1:?usage: verify-gate.sh <BASE_SHA> <HEAD_SHA>}"
HEAD="${2:?usage: verify-gate.sh <BASE_SHA> <HEAD_SHA>}"
PLCDIR="$REPO/.plc"
REPORT="${PLC_REPORT:-$PLCDIR/report.json}"

# --- override-only-diff bypass detection (AC1b, R2) ----------------------------------------
# Resolves the SHA-staleness paradox: a NOT_QUALIFIED report is bound (prHeadSha) to a
# reviewed sha X. A human then pushes a commit that adds ONLY .plc/override-<X>.json — HEAD
# moves to Y, but the report still says X (still correct: nothing about the reviewed code
# changed). If BASE..HEAD contains EXACTLY one changed file — an ADDED .plc/override-<sha>.json
# whose reviewedHeadSha equals the (stale) report.prHeadSha — we re-evaluate the prior report
# against that override WITHOUT requiring a fresh head-bound report and WITHOUT re-invoking
# any provider. Any deviation (0 or >=2 changed files, non-A status, wrong path, sha mismatch,
# missing/invalid report) leaves BYPASS=0 and the normal SHA-binding check applies.
BYPASS=0
CH="$(git -C "$REPO" diff --name-status "$BASE" "$HEAD" 2>/dev/null || true)"
LINES="$(printf '%s\n' "$CH" | grep -c . || true)"
if [ "$LINES" = "1" ]; then
  ST="$(printf '%s' "$CH" | awk '{print $1}')"
  PN="$(printf '%s' "$CH" | awk '{print $2}')"
  if [ "$ST" = "A" ] && [[ "$PN" =~ ^\.plc/override-[0-9a-f]+\.json$ ]] \
     && [ -f "$REPORT" ] && jq -e . "$REPORT" >/dev/null 2>&1 \
     && [ -f "$REPO/$PN" ] && jq -e . "$REPO/$PN" >/dev/null 2>&1; then
    OVR_RS="$(jq -r '.reviewedHeadSha // empty' "$REPO/$PN" 2>/dev/null || echo '')"
    REP_RS="$(jq -r '.prHeadSha // empty' "$REPORT" 2>/dev/null || echo '')"
    [ -n "$OVR_RS" ] && [ "$OVR_RS" = "$REP_RS" ] && BYPASS=1
  fi
fi

fail=0
bad() { echo "✗ $1"; fail=1; }
ok()  { echo "✓ $1"; }
na()  { echo "◻ N/A — $1 (recorded)"; }   # explicit non-qualified-but-not-blocked path

# --- report existence + schema + SHA binding (AC2, part) ----------------------------------
# REPORT_IS_OBJECT is computed once and reused by every later block that reads into the report
# (requirements floor, per-AC verdicts, verdict-teeth) so a valid-JSON-but-wrong-type artifact
# (e.g. a top-level array) can never reach an unguarded `.field` jq read downstream — it fails
# CLOSED here, structurally, instead of crashing set -e later with a raw jq trace.
REPORT_IS_OBJECT=0
if [ -f "$REPORT" ] && jq -e 'type=="object"' "$REPORT" >/dev/null 2>&1; then
  REPORT_IS_OBJECT=1
fi

if [ ! -f "$REPORT" ]; then
  bad "report.json missing at .plc/report.json"
elif ! jq -e . "$REPORT" >/dev/null 2>&1; then
  bad "report.json is not valid JSON"
elif [ "$REPORT_IS_OBJECT" -ne 1 ]; then
  bad "report.json is not a JSON object"
else
  RHEAD="$(jq -r '.prHeadSha // empty' "$REPORT")"
  for f in prHeadSha providerVendor providerModel verdict perAc; do
    jq -e "has(\"$f\")" "$REPORT" >/dev/null 2>&1 || bad "report missing field: $f"
  done
  if [ "$RHEAD" = "$HEAD" ]; then
    ok "report bound to PR head"
  elif [ "$BYPASS" = "1" ]; then
    ok "override-only diff — re-evaluating prior report at $RHEAD without re-running provider"
  else
    bad "report.prHeadSha ($RHEAD) != PR head ($HEAD)"
  fi
fi

# --- requirements floor: report AC-ids == base spec AC-ids, else N/A (AC4, R1) ------------
if SPEC_JSON="$(git -C "$REPO" show "$BASE:.plc/spec.json" 2>/dev/null)"; then
  if ! printf '%s' "$SPEC_JSON" | jq -e 'type=="object"' >/dev/null 2>&1; then
    bad "base .plc/spec.json is not a JSON object"
  else
    AC_COUNT="$(printf '%s' "$SPEC_JSON" | jq '.acceptanceCriteria | if type=="array" then length else 0 end' 2>/dev/null || echo 0)"
    SPEC_IDS="$(printf '%s' "$SPEC_JSON" | jq -r '.acceptanceCriteria[]? | .id? // empty' 2>/dev/null | sort)"
    if [ "$AC_COUNT" -eq 0 ]; then
      na "base .plc/spec.json has no acceptance criteria — gate N/A"
    elif [ -z "$SPEC_IDS" ]; then
      bad "base .plc/spec.json acceptanceCriteria has entries but none carry an id"
    elif [ "$REPORT_IS_OBJECT" -eq 1 ]; then
      REPORT_IDS="$(jq -r '.perAc[]? | .id? // empty' "$REPORT" | sort)"
      if [ "$SPEC_IDS" = "$REPORT_IDS" ]; then
        ok "requirements floor: report covers exactly the base spec AC ids"
      else
        bad "report perAc AC ids do not equal base spec AC ids"
      fi
    fi
  fi
else
  na "no .plc/spec.json on base — spec-introducing / process-only PR — gate N/A"
fi

# --- per-AC verdict + typed, existence-checked evidence (AC2, R3) --------------------------
if [ "$REPORT_IS_OBJECT" -eq 1 ]; then
  PATYPE="$(jq -r '.perAc | type' "$REPORT" 2>/dev/null || echo missing)"
  if [ "$PATYPE" != "array" ]; then
    bad "report perAc is not an array"
  else
    N="$(jq '.perAc | length' "$REPORT")"
    i=0
    while [ "$i" -lt "$N" ]; do
      V="$(jq -r ".perAc[$i] | .verdict? // empty" "$REPORT")"
      case "$V" in
        met|unmet) : ;;
        *) bad "perAc[$i] verdict not met/unmet: '$V'" ;;
      esac
      ETYPE="$(jq -r ".perAc[$i].evidence | type" "$REPORT" 2>/dev/null || echo missing)"
      if [ "$ETYPE" != "array" ]; then
        bad "perAc[$i] evidence not an array"
      else
        EC="$(jq ".perAc[$i].evidence | length" "$REPORT" 2>/dev/null || echo 0)"
        if [ "$EC" -lt 1 ]; then
          bad "perAc[$i] has no evidence"
        else
          j=0
          while [ "$j" -lt "$EC" ]; do
            REF="$(jq -r ".perAc[$i].evidence[$j]" "$REPORT")"
            case "$REF" in
              file://*) P="${REF#file://}"
                        [ -e "$REPO/$P" ] || bad "perAc[$i] evidence file missing: $P" ;;
              test://*|hunk://*) : ;;  # existence proven out-of-envelope; type is enough here
              *) bad "perAc[$i] evidence ref not typed (file://|test://|hunk://): '$REF'" ;;
            esac
            j=$((j+1))
          done
        fi
      fi
      i=$((i+1))
    done
  fi
fi

# --- verdict-teeth: override-present-if-not-qualified (AC1, HARD CONSTRAINT) ---------------
# Key off the human OVERRIDE ARTIFACT, never the LLM verdict value. The block is the ABSENCE
# of the override, not the verdict's value or correctness — an LLM verdict alone can never
# mechanically block a merge. Malformed/unsupported verdict values are treated conservatively
# (same as any non-QUALIFIED value): an override is required.
if [ "$REPORT_IS_OBJECT" -eq 1 ]; then
  VERDICT="$(jq -r '.verdict // "MALFORMED"' "$REPORT" 2>/dev/null || echo MALFORMED)"
  if [ "$VERDICT" = "QUALIFIED" ]; then
    ok "advisory verdict QUALIFIED — no override required"
  else
    OVR="$PLCDIR/override-$RHEAD.json"
    if [ -f "$OVR" ] && jq -e . "$OVR" >/dev/null 2>&1 \
       && [ "$(jq -r '.reviewedHeadSha // empty' "$OVR" 2>/dev/null || echo '')" = "$RHEAD" ] \
       && [ "$(jq -r '.findings | type' "$OVR" 2>/dev/null || echo bad)" = "array" ] \
       && [ "$(jq '.findings | length' "$OVR" 2>/dev/null || echo 0)" -ge 1 ] \
       && [ -n "$(jq -r '.reason // empty' "$OVR" 2>/dev/null || echo '')" ]; then
      ok "verdict $VERDICT dispositioned by override-$RHEAD.json"
    else
      bad "verdict $VERDICT requires .plc/override-$RHEAD.json (reviewedHeadSha=$RHEAD, findings[]>=1, non-empty reason)"
    fi
  fi
fi

# --- AC3: guard potency — a routed guard needs a manifest fixture-proof or an audited waiver --
# The gate READS diff-guards.json (routed guards, produced by diff-guards.sh out-of-envelope) +
# guard-manifest.json (author bindings) + potency-result.json (produced by potency-runner.sh).
# It does NOT re-derive "added" (that is the producer's job). Every routed guard must be
# either fixture-proven potent (its neutered fixture FAILS) or waived with an audited reason.
DG="$PLCDIR/diff-guards.json"
MAN="$PLCDIR/guard-manifest.json"
POT="$PLCDIR/potency-result.json"
if [ ! -f "$DG" ] || ! jq -e 'type=="object"' "$DG" >/dev/null 2>&1; then
  na "no diff-guards.json — no guard-routing recorded this PR"
else
  DG_HEAD="$(jq -r '.head // empty' "$DG")"
  NG="$(jq '.guards | if type=="array" then length else -1 end' "$DG" 2>/dev/null || echo -1)"
  if [ "$DG_HEAD" != "$HEAD" ]; then
    bad "diff-guards.json head ($DG_HEAD) != PR head ($HEAD)"
  elif [ "$NG" -lt 0 ]; then
    bad "diff-guards.json .guards is not an array"
  elif [ "$NG" -eq 0 ]; then
    na "no guards added this PR — guard-potency check N/A"
  elif ! jq -e '.guards | all(.[]?; type=="object")' "$DG" >/dev/null 2>&1; then
    # Every later `.guards[i].guardId` read assumes an object element. A non-object element
    # (corrupt/hand-crafted artifact) would otherwise make an unguarded `.guardId` jq read
    # abort the whole gate under set -e with a raw trace — fail CLOSED here instead.
    bad "diff-guards.json .guards has a non-object element"
  else
    # MAN must be an array of OBJECTS before any select(.guardId) — a non-object element would
    # crash the select under set -e (same defect class as the report-object guard above).
    MAN_IS_ARRAY=0
    [ -f "$MAN" ] && jq -e 'type=="array" and all(.[]?; type=="object")' "$MAN" >/dev/null 2>&1 && MAN_IS_ARRAY=1
    NEED_POTENCY=0
    ROUTED_FIXTURE_IDS=""   # newline-delimited (guardId is file:line; a path may contain spaces)
    gi=0
    while [ "$gi" -lt "$NG" ]; do
      GID="$(jq -r ".guards[$gi].guardId // empty" "$DG")"
      ENTRY=""
      [ "$MAN_IS_ARRAY" -eq 1 ] && ENTRY="$(jq -c --arg g "$GID" 'map(select(.guardId==$g)) | .[0] // empty' "$MAN")"
      if [ -z "$ENTRY" ] || [ "$ENTRY" = "null" ]; then
        bad "routed guard $GID has no .plc/guard-manifest.json entry (add a fixture binding or a waiver)"
      else
        FIX="$(printf '%s' "$ENTRY" | jq -r '.firingFixture // empty')"
        WR_REASON="$(printf '%s' "$ENTRY" | jq -r '.waiver.reason // empty')"
        WR_BY="$(printf '%s' "$ENTRY" | jq -r '.waiver.waivedBy // empty')"
        if [ -n "$FIX" ]; then
          NEED_POTENCY=1
          ROUTED_FIXTURE_IDS="$ROUTED_FIXTURE_IDS$GID
"
        elif [ -n "$WR_REASON" ] && [ -n "$WR_BY" ]; then
          ok "routed guard $GID waived ($WR_REASON — $WR_BY)"
        else
          bad "routed guard $GID manifest entry is neither a fixture binding nor a valid waiver (reason+waivedBy)"
        fi
      fi
      gi=$((gi+1))
    done
    if [ "$NEED_POTENCY" -eq 1 ]; then
      if [ ! -f "$POT" ] || ! jq -e 'type=="object"' "$POT" >/dev/null 2>&1; then
        bad "routed fixture-bound guards need .plc/potency-result.json (absent or not an object)"
      elif ! jq -e '(.perGuard // []) | all(.[]?; type=="object")' "$POT" >/dev/null 2>&1; then
        bad "potency-result.json perGuard has a non-object element"
      else
        P_HEAD="$(jq -r '.prHeadSha // empty' "$POT")"
        P_MH="$(jq -r '.manifestHash // empty' "$POT")"
        MH_NOW="$(git -C "$REPO" hash-object "$MAN" 2>/dev/null || echo '')"
        if [ "$P_HEAD" != "$HEAD" ]; then
          bad "potency-result.json prHeadSha ($P_HEAD) != PR head ($HEAD)"
        elif [ -z "$MH_NOW" ] || [ "$P_MH" != "$MH_NOW" ]; then
          bad "potency-result.json manifestHash stale (does not match current guard-manifest.json)"
        else
          # newline-delimited iteration (a guardId's file part may contain spaces). Here-string,
          # NOT a pipe: a `... | while` runs the loop in a subshell where bad()'s fail=1 is lost.
          while IFS= read -r GID; do
            [ -n "$GID" ] || continue
            PG="$(jq -c --arg g "$GID" '.perGuard // [] | map(select(.guardId==$g)) | .[0] // empty' "$POT")"
            if [ -z "$PG" ] || [ "$PG" = "null" ]; then
              bad "routed guard $GID missing from potency-result.json (no potency proof)"
            else
              # Potency is the DELTA, not the neuter half alone: the intact fixture must PASS
              # (baseline) AND the neutered fixture must FAIL. Checking only neuterResult==failed
              # accepts an always-failing fixture bound to a dead guard as "potent" (fixtureResult
              # failed → neuterResult failed → no flip proven). Both halves are producer-OBSERVED
              # results, so requiring the conjunction stays consistent with the producer-observed-results invariant.
              FRES="$(printf '%s' "$PG" | jq -r '.fixtureResult // empty')"
              NRES="$(printf '%s' "$PG" | jq -r '.neuterResult // empty')"
              if [ "$FRES" = "passed" ] && [ "$NRES" = "failed" ]; then
                ok "guard $GID potent (intact fixture passes; neutering breaks it)"
              else
                bad "guard $GID is impotent: need fixtureResult=passed + neuterResult=failed (got fixtureResult=$FRES, neuterResult=$NRES)"
              fi
            fi
          done <<EOF
$ROUTED_FIXTURE_IDS
EOF
        fi
      fi
    fi
  fi
fi

[ "$fail" -eq 0 ] && { echo "✓ verify-gate PASS"; exit 0; } || { echo "✗ verify-gate BLOCK"; exit 1; }
