#!/usr/bin/env bash
# Assert that every expected adopter-only branch was reached in a capture file: "expected ⊆
# reached", NOT strict set equality -- unrelated extra content in the capture does not fail this
# (by design). The oracle is
# NOT absence-of-error: a run that errors nowhere and reaches nothing is exactly the failure
# this fixture exists to catch, and an EMPTY expected-set file is the same failure one layer up -- it would
# make this comparator trivially pass while asserting nothing, so a missing, unreadable, or
# all-blank expected-set file is itself a FAIL.
#
# bash 3.2.57 note (the /bin/bash macOS ships): which array expansion is actually unsafe under
# `set -u`, measured, not assumed:
#   $ /bin/bash -c 'set -euo pipefail; a=(); echo "${#a[@]}"'          ->  0    (fine)
#   $ /bin/bash -c 'set -euo pipefail; a=(); printf "%s\n" "${a[@]}"'  ->  a[@]: unbound variable
# LENGTH expansion ("${#arr[@]}") of an empty array is fine under `set -u`; ELEMENT expansion
# ("${arr[@]}") is the unsafe form. Array code that expands elements only
# inside `if [ "${#missing[@]}" -ne 0 ]` -- i.e. only on the branch where the array is already
# known non-empty -- would NOT break on the happy path. The counter +
# accumulating-string form below is used anyway, not because the array would fail, but
# because it removes the whole class of "which expansion form is safe here" mistakes rather than
# relying on getting the guard right every time.
set -euo pipefail
CAPTURE="$1"; EXPECTED="$2"
[ -r "$CAPTURE" ]  || { echo "FAIL: capture unreadable: $CAPTURE"; exit 2; }
[ -r "$EXPECTED" ] || { echo "FAIL: expected-set unreadable: $EXPECTED"; exit 2; }

total=0
reached=0
missing_count=0
missing_list=""
while IFS= read -r line || [ -n "$line" ]; do
  [ -n "$line" ] || continue
  total=$(( total + 1 ))
  if /usr/bin/grep -qF -- "$line" "$CAPTURE"; then
    reached=$(( reached + 1 ))
    echo "  reached: $line"
  else
    missing_count=$(( missing_count + 1 ))
    missing_list="${missing_list}  ${line}
"
  fi
done < "$EXPECTED"

if [ "$total" -eq 0 ]; then
  echo "FAIL: expected-set is empty (0 non-blank lines in $EXPECTED)"
  echo "  an empty expected set asserts nothing and must never read as success"
  exit 1
fi

echo "reached $reached/$total adopter-only branches"
if [ "$missing_count" -ne 0 ]; then
  echo "FAIL: these adopter-only branches were NOT reached:"
  printf '%s' "$missing_list"
  echo "  A run that silently skips them has not exercised the adopter path."
  exit 1
fi
echo "ok: every adopter-only branch was exercised"
