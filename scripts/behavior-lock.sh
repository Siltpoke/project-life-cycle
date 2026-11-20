#!/usr/bin/env bash
# the Behavior Lock registry: parser, carrier resolution, and graduation.
#
# The registry (.claude/behavior-lock.tsv) is the live behavior-contract: one row per
# behavior a change is actively preserving, fixing, or adding, each bound to the test that
# proves it. Modeled on the closure-ledger triad (scripts/backlog-closures.sh) -- a pinned
# TSV, a validate/derive-only parser, and an invariant guard -- with two deliberate
# differences, both recorded in the design plan:
#
#   1. NOT append-only. The closure ledger enforces a byte-prefix; graduation (a behavior
#      leaving the list once a permanent test pins it) removes rows, so that is dropped.
#      The invariant enforces grammar + carrier-resolves only.
#   2. Its own id namespace BL-<n>, separate from backlog B<n> (which owns 400+ ids) and
#      from phase-scoped AC ids.
#
# Format: 5 tab-separated columns, `#` is a comment, the file ends with a newline.
#   id  class  behavior  carrier  why
#
# id       : ^BL-[0-9]+$
# class    : PRESERVE | FIX | NEW
# behavior : non-empty
# carrier  : non-empty, not `-`; `path` or `path::testname`
# why      : non-empty
#
# jq-only envelope: no jq and no python3 in this file or anything it calls (CLAUDE.md).

set -uo pipefail

LOG="${PLC_BEHAVIOR_LOCK:-.claude/behavior-lock.tsv}"
GRAD="${PLC_BEHAVIOR_LOCK_GRADUATED:-.claude/behavior-lock-graduated.tsv}"

CLASSES="PRESERVE FIX NEW"

die() { printf 'behavior-lock: %s\n' "$1" >&2; exit "${2:-2}"; }

# ---------------------------------------------------------------------------------------------
# line-level validation
# ---------------------------------------------------------------------------------------------

# check_line <line> -- prints the reason and returns 1 on failure; prints nothing on success.
check_line() {
  local line="$1" ncol id cls beh car why
  case "$line" in ''|'#'*) return 0 ;; esac

  ncol="$(printf '%s' "$line" | awk -F'\t' '{print NF}')"
  if [ "$ncol" != 5 ]; then
    printf 'not 5 tab-separated columns (%s): %s\n' "$ncol" "$line"; return 1
  fi

  id="$(printf '%s' "$line" | cut -f1)"
  cls="$(printf '%s' "$line" | cut -f2)"
  beh="$(printf '%s' "$line" | cut -f3)"
  car="$(printf '%s' "$line" | cut -f4)"
  why="$(printf '%s' "$line" | cut -f5)"

  printf '%s' "$id" | grep -qE '^BL-[0-9]+$' \
    || { printf 'bad id shape "%s" (want BL-<n>): %s\n' "$id" "$line"; return 1; }
  case " $CLASSES " in *" $cls "*) ;; *) printf 'bad class "%s" (want PRESERVE|FIX|NEW): %s\n' "$cls" "$line"; return 1 ;; esac
  [ -n "$beh" ] || { printf 'empty behavior: %s\n' "$line"; return 1; }
  if [ -z "$car" ] || [ "$car" = "-" ]; then
    printf 'empty carrier (every behavior must name the test that proves it): %s\n' "$line"; return 1
  fi
  [ -n "$why" ] || { printf 'empty why: %s\n' "$line"; return 1; }
  return 0
}

# ---------------------------------------------------------------------------------------------
# carrier resolution
# ---------------------------------------------------------------------------------------------

# resolve <carrier> [root] -- exit 0 iff the carrier resolves to a real test.
#   `path`           -> that file exists under root.
#   `path::name`     -> that file exists AND `name` appears in it as a whole word.
# A carrier that names a test which does not exist is the whole failure this guards: a row
# can claim a test proves a behavior while nothing does.
resolve() {
  local carrier="$1" root="${2:-.}" path name
  case "$carrier" in
    *"::"*)
      path="${carrier%%::*}"
      name="${carrier#*::}"
      ;;
    *)
      path="$carrier"
      name=""
      ;;
  esac
  [ -n "$path" ] || return 1
  [ -f "$root/$path" ] || return 1
  if [ -n "$name" ]; then
    grep -qwF -- "$name" "$root/$path" || return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------------------------
# graduation -- move a row out of the live registry into the cold archive
# ---------------------------------------------------------------------------------------------

# graduate <id> [file] [gradfile] -- remove id's row from the live registry and append it to
# the graduated archive. git history is the real trail; the archive keeps a flat readable one.
graduate() {
  local id="$1" f="${2:-$LOG}" g="${3:-$GRAD}" row tmp
  [ -f "$f" ] || die "no registry at $f" 2
  row="$(grep -v '^#' "$f" | awk -F'\t' -v id="$id" '$1==id{print; found=1} END{exit !found}')" \
    || die "no live row for $id" 1
  printf '%s\n' "$row" >> "$g"
  tmp="$(mktemp)"
  awk -F'\t' -v id="$id" '/^#/{print; next} $1==id{next} {print}' "$f" > "$tmp"
  mv "$tmp" "$f"
}

# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------

usage() {
  cat >&2 <<'USAGE'
usage: behavior-lock.sh <mode>
  --check-line             read one row on stdin, validate it (exit 1 on a bad row)
  --check-file [FILE]      validate every row of the registry
  --list-ids [FILE]        every id in the registry
  --carriers [FILE]        every id and its carrier, tab-separated
  --resolve CARRIER [ROOT] exit 0 iff the carrier resolves to a real test under ROOT
  --graduate ID [FILE] [GRADFILE]  move id's row to the graduated archive
USAGE
  exit 64
}

[ $# -ge 1 ] || usage

case "$1" in
  --check-line)
    # `read` returns non-zero at EOF on a final line with no trailing newline, but still
    # assigns the partial content -- so init and ignore its status rather than `|| line=""`,
    # which would blank exactly that last unterminated row.
    line=""
    IFS= read -r line || true
    if ! msg="$(check_line "$line")"; then printf 'behavior-lock: %s\n' "$msg" >&2; exit 1; fi
    ;;

  --check-file)
    f="${2:-$LOG}"
    [ -f "$f" ] || die "no such registry: $f" 2
    rc=0; n=0
    while IFS= read -r line; do
      case "$line" in ''|'#'*) continue ;; esac
      n=$((n + 1))
      if ! msg="$(check_line "$line")"; then printf 'behavior-lock: %s\n' "$msg" >&2; rc=1; fi
    done < "$f"
    printf 'checked %s behavior row(s)\n' "$n"
    exit $rc
    ;;

  --list-ids)
    f="${2:-$LOG}"
    [ -f "$f" ] || exit 0
    grep -v '^#' "$f" | cut -f1 | grep -v '^$' | sort -u
    ;;

  --carriers)
    f="${2:-$LOG}"
    [ -f "$f" ] || exit 0
    grep -v '^#' "$f" | awk -F'\t' 'NF>=4 && $1!=""{print $1 "\t" $4}'
    ;;

  --resolve)
    [ $# -ge 2 ] || usage
    if resolve "$2" "${3:-.}"; then exit 0; else exit 1; fi
    ;;

  --graduate)
    [ $# -ge 2 ] || usage
    graduate "$2" "${3:-$LOG}" "${4:-$GRAD}"
    ;;

  *) usage ;;
esac
