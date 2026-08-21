#!/usr/bin/env bash
# skills/project-lifecycle/hooks/plc-careful-suggest.sh
#
# Read THIS project's own directory structure and propose places that may want careful handling.
# Prints one tab-separated row per candidate: <path>\t<reason>, sorted. Prints a single honest line
# and exits 0 when it has nothing to propose -- inventing candidates to look useful is a defect,
# not a fallback.
#
# THREE HARD CONSTRAINTS, each of which is what makes this machine-decidable at all:
#   1. every proposed path really exists here -- checked, never assumed
#   2. every proposal states WHY, and the why is a FACT the reader can check and overrule
#   3. proposing nothing is a legal outcome, said out loud
#
# THE REASON MAY ONLY STATE WHAT WAS OBSERVED. "this directory contains a file whose name matches
# 'password'" is permitted. "this looks like it handles sensitive data" is not: the first is a fact
# the reader can overrule, the second asks them to trust a judgement nothing made.
#
# NO WORD IS WRITTEN IN THIS FILE. The vocabulary lives in the single data block in
# references/careful-paths.md, plus whatever the project adds via its own key.
#
# Envelope: bash + jq + git only. No python3. No `mapfile` -- macOS still ships bash 3.2.
#
# Exit codes:
#   0  ran; candidates printed, or the no-candidates line
#   1  bad invocation
#   3  the data block is missing, malformed, or not exactly one
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DEFAULT="$HERE/../references/careful-paths.md"

die() { printf '%s\n' "$*" >&2; exit "${2:-1}"; }

claude_md="" data="$DATA_DEFAULT" repo="."
while [ $# -gt 0 ]; do
  case "$1" in
    --claude-md) [ $# -ge 2 ] || die "--claude-md needs a path"; claude_md="$2"; shift 2 ;;
    --data)      [ $# -ge 2 ] || die "--data needs a path";      data="$2";      shift 2 ;;
    --repo)      [ $# -ge 2 ] || die "--repo needs a path";      repo="$2";      shift 2 ;;
    -h|--help)
      printf 'usage: plc-careful-suggest.sh --repo PATH [--claude-md PATH] [--data PATH]\n'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -d "$repo" ] || die "cannot read the project: $repo"
[ -r "$data" ] || die "cannot read the careful-paths data: $data" 3

if ! block="$(awk '
  /<!-- plc-careful-data:begin -->/ { inblk = 1; next }
  /<!-- plc-careful-data:end -->/   { inblk = 0; next }
  inblk && /^```json$/              { infence = 1; fences++; next }
  inblk && /^```$/                  { infence = 0; next }
  inblk && infence                  { print }
  END                               { if (fences != 1) exit 9 }
' "$data")"; then
  die "the careful-paths data must hold exactly one fenced json block: $data" 3
fi
jq -e . >/dev/null 2>&1 <<<"$block" || die "the careful-paths data block is not valid json" 3

WORDS="$(jq -r '.words[]' <<<"$block")"

# The project may add its own names. The shipped list is never edited by a project -- that is what
# keeps "PLC ships no per-project knowledge" true while still letting a project be specific.
if [ -n "$claude_md" ] && [ -r "$claude_md" ]; then
  extra_key="$(jq -r '.extra_words_key' <<<"$block")"
  extra="$(awk -v k="$extra_key" '
    /^[[:space:]]*#/ { next }
    index($0, k ":") == 1 { sub("^" k ":[[:space:]]*", ""); sub("[[:space:]]*#.*$", ""); print; exit }
  ' "$claude_md")"
  if [ -n "$extra" ]; then
    extra="$(printf '%s' "$extra" | tr ',' '\n' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d')"
    WORDS="$WORDS
$extra"
  fi
fi

# Directories git knows about, deepest name first so the reason can point at the directory rather
# than at one file inside it. Untracked-but-not-ignored is included: a project being set up for the
# first time may have committed almost nothing yet.
dirs_and_files() {
  git -C "$repo" ls-files --cached --others --exclude-standard -z 2>/dev/null | tr '\0' '\n' | sed '/^$/d'
}

ALL="$(dirs_and_files)"
[ -n "$ALL" ] || {
  printf 'no-candidates\tI could not see anywhere that obviously needs care. Mark it yourself.\n'
  exit 0
}

# MATCHING IS BYTE-WISE AND CASE-INSENSITIVE OVER ASCII, and that limit is stated rather than
# dressed up. The shipped vocabulary is ASCII, so it matches inside a path containing accented
# characters regardless of whether the filesystem stored them composed (NFC) or decomposed (NFD) --
# the accents are not what is being matched. A NON-ASCII word added by a project is a different
# matter: it is compared byte for byte, so it must be written in the same normalisation form the
# filesystem uses. Normalising here would need a dependency this envelope does not carry, and
# claiming a normalisation that is not performed is worse than naming the limit.
lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

# EVERY SEGMENT OF THE PATH IS MATCHED, not just the final one. Comparing
# only the basename, `src/auth/session.ts` would match nothing -- the directory literally named
# `auth` would be invisible, and a directory named after what it holds is the single most likely way a
# project marks this out. Tests whose file names happen to match as well would not notice.
hits=""
while IFS= read -r path; do
  [ -n "$path" ] || continue
  while IFS= read -r word; do
    [ -n "$word" ] || continue
    lw="$(lower "$word")"

    # Walk the path from the shallowest segment outward, so a match on a directory proposes that
    # directory rather than the file that happens to sit under it.
    #
    # WHAT GETS PROPOSED, in all four shapes -- measured, because the ranking is easy to misread as
    # inverted:
    #
    #   src/auth/handler.ts  word=auth   -> src/auth/  "this directory's name contains auth"
    #   src/lib/login.ts     word=login  -> src/lib/   "this directory contains a file whose ..."
    #   src/auth/login.ts    both        -> src/auth/  the DIRECT evidence wins (rank 0 beats 1)
    #   login.ts             word=login  -> login.ts   "this file's name contains login"
    #
    # A directory is what a person marks, so a matching FILE proposes its directory and carries
    # rank 1; a matching DIRECTORY NAME is direct evidence and carries rank 0. When one path
    # matches both ways, rank decides, and the reader sees the stronger of two true sentences.
    prefix="" matched=""
    remaining="$path"
    while [ -n "$remaining" ]; do
      seg="${remaining%%/*}"
      case "$(lower "$seg")" in
        *"$lw"*) matched="$seg"; break ;;
      esac
      case "$remaining" in
        */*) prefix="$prefix$seg/"; remaining="${remaining#*/}" ;;
        *)   remaining="" ;;
      esac
    done
    [ -n "$matched" ] || continue

    # `rank` decides which reason survives deduplication when one path matches several ways. 0 is
    # the direct evidence -- the thing's own name -- and it must win: measured, `src/auth/` was
    # first reported as "contains a file whose name contains \"session\"" because that row happened
    # to sort earlier, which is a true sentence and the weaker of the two available ones.
    if [ "$prefix$matched" = "$path" ]; then
      rank=0
      target="$path"
      reason="this file's name contains \"$word\""
    else
      rank=0
      target="$prefix$matched/"
      reason="this directory's name contains \"$word\""
    fi
    # A directory whose own name matches nothing, but which holds a file that does, is proposed as
    # the directory with the file named as the evidence.
    case "$target" in
      "$path")
        d="$(dirname "$path")"
        if [ "$d" != "." ]; then
          rank=1
          target="$d/"
          reason="this directory contains a file whose name contains \"$word\""
        fi
        ;;
    esac

    # CONSTRAINT 1, enforced here and not assumed: a proposal pointing at something that is not on
    # disk is a defect. `target` is derived from a real entry, so this can only fail if the tree
    # changed under us -- which is exactly when a silent wrong answer would be worst.
    [ -e "$repo/${target%/}" ] || continue
    hits+="$target"$'\t'"$rank"$'\t'"$reason"$'\n'
  done <<<"$WORDS"
done <<<"$ALL"

if [ -z "$hits" ]; then
  # CONSTRAINT 3. Not an error, not silence, and not a manufactured suggestion.
  printf 'no-candidates\tI could not see anywhere that obviously needs care. Mark it yourself.\n'
  exit 0
fi

# One row per path. Sorted by path, then by rank so the direct evidence wins, then by reason so the
# result is deterministic; the rank column is dropped before printing -- it is a sort key, not
# something the reader needs.
printf '%s' "$hits" | LC_ALL=C sort -u -t$'\t' -k1,1 -k2,2 -k3,3 |
  awk -F'\t' '!seen[$1]++ { printf "%s\t%s\n", $1, $3 }'
