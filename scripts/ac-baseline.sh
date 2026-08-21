#!/bin/bash
# scripts/ac-baseline.sh -- the two named actions on the AC baseline, and its guard digest.
#
# Asymmetry is the point: REMOVAL is automatic and happens at phase close, ADDITION
# requires this tool. A hand-edited entry leaves the guard stale and the gate fails naming it.
#
# The guard is a DIGEST, not a signature. There is no secret, so anyone can recompute it by hand and
# bless new debt as old debt. That is the intended design -- adding must be an explicit, named
# ACTION, not impossible -- and this tool never claims to be tamper-proof. What a reviewer cannot
# tell from a green gate is `ac-baseline.sh add` from a hand-edit plus a recompute; that residual is
# stated here rather than papered over.
#
# Envelope: bash + jq + git ONLY. Hashing is `git hash-object`, NOT `shasum` -- shasum is a perl
# script on macOS and would widen that envelope; `git hash-object` is content-addressed and
# already inside it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
die() { printf '%s\n' "$*" >&2; exit 1; }

sha() { git hash-object --stdin; }
guard_of() { jq -S -c '.criteria' "$1" | sha; }

# Digest of a criterion's FULL declaration, or empty when this story does not declare it (which is
# the normal case for a cross-phase id). The empty case is guarded EXPLICITLY: piping nothing into a
# hasher yields the hash of the empty string, which is non-empty, so a cross-phase entry would get a
# bogus digest instead of null and then lose its baseline protection on the next run for no reason.
declaration_digest() {
  local story="$1" id="$2" text
  [ -n "$story" ] && [ -r "$story" ] || return 1
  text="$("$HERE/ac-evidence.sh" declaration-text "$story" "$id" 2>/dev/null)" || return 1
  [ -n "$text" ] || return 1
  printf '%s' "$text" | sha
}

cmd_init() {
  local f="$1"
  [ -e "$f" ] && die "refusing to overwrite an existing baseline: $f"
  printf '{\n  "criteria": [],\n  "guard": ""\n}\n' > "$f"
  jq --arg g "$(guard_of "$f")" '.guard = $g' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
}

cmd_verify() {
  local f="$1" want have
  jq -e . "$f" >/dev/null 2>&1 || die "baseline is unreadable or not valid JSON: $f"
  want="$(jq -r '.guard // ""' "$f")"
  have="$(guard_of "$f")"
  [ "$want" = "$have" ] && return 0
  printf 'baseline guard is STALE -- an entry was added or edited without `ac-baseline.sh add`.\n' >&2
  jq -r '.criteria[] | select(.action != "scripts/ac-baseline.sh add") | "  suspect entry: \(.id) (action: \(.action))"' "$f" >&2
  printf '  expected guard %s, the file says %s\n' "$have" "$want" >&2
  return 1
}

cmd_add() {
  local f="$1" id="$2" why="$3" story="${4:-}" digest d
  # Verify BEFORE mutating. The other order would recompute the guard over a set that also holds a
  # hand-added entry, laundering it in the same run.
  cmd_verify "$f" || die "refusing to add on top of a stale guard -- resolve that first"
  digest="null"
  if [ -n "$story" ] && d="$(declaration_digest "$story" "$id")" && [ -n "$d" ]; then
    digest="\"$d\""
  fi
  jq --arg id "$id" --arg why "$why" --arg d "$(date -u +%Y-%m-%d)" --argjson dg "$digest" \
     '.criteria += [{id: $id, digest: $dg, added: $d, action: "scripts/ac-baseline.sh add", why: $why}]' \
     "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  jq --arg g "$(guard_of "$f")" '.guard = $g' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
}

cmd_prune() {
  local f="$1" ev="$2" id removed=0
  cmd_verify "$f" || die "refusing to prune on a stale guard -- that would launder a hand-added entry"
  jq -e . "$ev" >/dev/null 2>&1 || die "evidence file is unreadable: $ev"
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    if jq -e --arg id "$id" '.criteria[]? | select(.id == $id)' "$ev" >/dev/null 2>&1; then
      printf 'baseline: removed %s -- it now has an evidence row\n' "$id"
      jq --arg id "$id" '.criteria |= map(select(.id != $id))' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
      removed=1
    fi
  done < <(jq -r '.criteria[].id' "$f")
  if [ "$removed" = 1 ]; then
    jq --arg g "$(guard_of "$f")" '.guard = $g' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  fi
  return 0
}

FILE=".claude/ac-baseline.json"; STORY=""; EV=""; WHY=""; HAVE_WHY=0
SUB="${1:-}"; shift || true
POS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --file)     FILE="$2"; shift 2 ;;
    --story)    STORY="$2"; shift 2 ;;
    --evidence) EV="$2"; shift 2 ;;
    --why)      WHY="$2"; HAVE_WHY=1; shift 2 ;;
    -*)         die "unknown option $1" ;;
    *)          POS[${#POS[@]}]="$1"; shift ;;
  esac
done

case "$SUB" in
  init)   cmd_init "$FILE" ;;
  verify) cmd_verify "$FILE" ;;
  add)
    [ "${#POS[@]}" -ge 1 ] || die "add requires a criterion id"
    [ "$HAVE_WHY" = 1 ] && [ -n "$WHY" ] || die "add requires --why <reason>: an entry with no stated reason is the rot this baseline exists to make visible"
    cmd_add "$FILE" "${POS[0]}" "$WHY" "$STORY"
    ;;
  prune)
    [ -n "$EV" ] || die "prune requires --evidence <path>"
    cmd_prune "$FILE" "$EV"
    ;;
  *) die "usage: ac-baseline.sh init|verify|add <id> --why <reason>|prune --evidence <path> [--file F] [--story S]" ;;
esac
