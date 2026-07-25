#!/usr/bin/env bash
# tasklist-view.sh — PLC-native reader for .claude/tasklist.md. Pure bash, jq-free.
# Parses the checkbox tree by STRUCTURE (# phase / ## group / - [c] leaf + indent),
# never by label text (restricted character set + adopter portability; same rule as session_card.py).
# State char: x|X -> done, / -> in-progress, ' ' -> todo, any other -> todo (never crash).
# Modes: default = brief (bar + count + the current step); --tree = full expandable tree.
set -uo pipefail

FILE="${PLC_TASKLIST_FILE:-.claude/tasklist.md}"
MODE="brief"; [ "${1:-}" = "--tree" ] && MODE="tree"

if [ ! -f "$FILE" ]; then
  printf 'no tasklist yet — the guard writes .claude/tasklist.md on first gated edit\n'
  exit 0
fi

# --- parse into parallel arrays -------------------------------------------------
phase=""
declare -a g_name g_done g_tot                 # per-group
declare -a l_group l_state l_text l_indent     # per-leaf (l_group = group index)
gi=-1
while IFS= read -r line || [ -n "$line" ]; do
  if [[ $line == \#\#* ]]; then
    if [[ $line =~ ^##[[:space:]]+(.*)$ ]]; then
      gi=$((gi+1)); g_name[$gi]="${BASH_REMATCH[1]}"; g_done[$gi]=0; g_tot[$gi]=0
    fi
    continue
  fi
  if [[ $line =~ ^#[[:space:]]+(.*)$ ]]; then phase="${BASH_REMATCH[1]}"; continue; fi
  if [[ $line =~ ^([[:space:]]*)-[[:space:]]\[(.)\][[:space:]](.*)$ ]]; then
    ind="${BASH_REMATCH[1]}"; ch="${BASH_REMATCH[2]}"; txt="${BASH_REMATCH[3]}"
    case "$ch" in x|X) st=done;; /) st=prog;; *) st=todo;; esac
    if [ "$gi" -lt 0 ]; then gi=0; g_name[0]=""; g_done[0]=0; g_tot[0]=0; fi
    k=${#l_state[@]}
    l_group[$k]=$gi; l_state[$k]=$st; l_text[$k]="$txt"; l_indent[$k]=${#ind}
    g_tot[$gi]=$(( g_tot[$gi] + 1 ))
    [ "$st" = done ] && g_done[$gi]=$(( g_done[$gi] + 1 ))
  fi
done < "$FILE"

total=0; [ "${l_state+x}" = x ] && total=${#l_state[@]}
done_n=0
if [ "$total" -gt 0 ]; then for st in "${l_state[@]}"; do [ "$st" = done ] && done_n=$((done_n+1)); done; fi

if [ "$total" -eq 0 ]; then
  printf '%s\n\nno tasks in %s\n' "${phase:-tasklist}" "$FILE"; exit 0
fi

bar() { # done total  -> 10-wide filled/empty
  local d=$1 t=$2 w=10 f i=0; f=$(( t>0 ? d*w/t : 0 ))
  while [ $i -lt $w ]; do [ $i -lt $f ] && printf '█' || printf '░'; i=$((i+1)); done
}

# --- header (both modes) --------------------------------------------------------
printf '%s   %s  %d/%d\n' "${phase:-tasklist}" "$(bar "$done_n" "$total")" "$done_n" "$total"

# --- brief mode: the collapsed one-liner ("where we are now") --------------------
if [ "$MODE" = brief ]; then
  for ((k=0; k<total; k++)); do
    if [ "${l_state[$k]}" = prog ]; then
      g=${l_group[$k]}
      printf '▶ now: %s · %s   (/tasklist --tree to expand)\n' "${g_name[$g]}" "${l_text[$k]}"
      exit 0
    fi
  done
  printf '(no step in progress — mark one with - [/];  /tasklist --tree to expand)\n'
  exit 0
fi

# --- tree mode: the full expanded overview --------------------------------------
printf '\n'
seen_current=0
gcur=-1
for ((k=0; k<total; k++)); do
  g=${l_group[$k]}
  if [ "$g" != "$gcur" ]; then
    gcur=$g
    printf '  %s   %d/%d\n' "${g_name[$g]}" "${g_done[$g]}" "${g_tot[$g]}"
  fi
  case "${l_state[$k]}" in done) gl='✓';; prog) gl='▶';; *) gl='○';; esac
  pad=""; d=$(( l_indent[$k] / 2 )); j=0; while [ $j -lt $d ]; do pad="$pad  "; j=$((j+1)); done
  if [ "${l_state[$k]}" = prog ] && [ "$seen_current" -eq 0 ]; then
    seen_current=1
    printf '    %s%s %s   ← here\n' "$pad" "$gl" "${l_text[$k]}"
  else
    printf '    %s%s %s\n' "$pad" "$gl" "${l_text[$k]}"
  fi
done
exit 0
