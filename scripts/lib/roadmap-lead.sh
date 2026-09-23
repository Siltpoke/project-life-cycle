# roadmap-lead.sh (p42) — the ONE reader of a mainline row's name and lead widths.
#
# Sourced by scripts/gen-roadmap-lead-baseline.sh and by
# scripts/invariants/roadmap-lead-length.sh. The generator and the guard MUST measure
# identically or the baseline is a comparison between two different rulers -- the
# encoder-divergence class this repo has paid for, and the reason p36's block grammar lives
# in one file too.
#
# WHAT A "LEAD" IS, defined here because the definition is the feature.
# The `what` cell of a mainline row routinely runs to hundreds of characters. It is not
# formless: it already opens with a sentence and then continues. Measured on this repo when
# the rule was written -- first sentence median 78 columns, p75 136, max 450, while the whole
# cell has median 953. So the lead EXISTS; nothing marked where it ended.
#
# The lead is the text before the first of `。` (ideographic full stop), `. ` (a full stop and
# a space, so `v1.1` is not a sentence end) or `<br>` (this document's own line break). If none
# occurs, the lead is the whole cell -- which is the honest reading: a cell with no sentence
# break is all lead.
#
# WIDTH IS DISPLAY COLUMNS, not characters, via scripts/lib/eaw-ranges.jq -- the same ruler
# p36 uses for step lines. A bound in characters would let a Chinese row be twice as wide as
# an English one for the same number.
#
# Envelope: bash + jq + awk + cksum.

# roadmap_lead_rows <roadmap> <eaw-lib-dir>
#   Emits: <name-digest><TAB><name-cols><TAB><lead-cols><TAB><name prefix>
roadmap_lead_rows() {
  _rl_map="$1"
  _rl_lib="$2"

  awk '
    index($0, "## \360\237\233\243") == 1 { inmain = 1; next }
    inmain && substr($0, 1, 3) == "## " { inmain = 0 }
    !inmain { next }
    {
      t = $0; sub(/^[ \t]+/, "", t)
      if (substr(t, 1, 1) != "|") next
      if (t ~ /^\|[-: |]+\|?$/) { seensep = 1; next }
      if (!seensep) next
      n = split(t, c, "|")
      if (n < 5) next
      name = c[2]; gsub(/^[ \t]+|[ \t]+$/, "", name)
      what = c[3]; gsub(/^[ \t]+|[ \t]+$/, "", what)
      if (name == "") next
      printf "%s\t%s\n", name, what
    }
  ' "$_rl_map" | while IFS="$(printf '\t')" read -r _rl_name _rl_what; do
    [ -n "${_rl_name:-}" ] || continue

    # The lead: text before the first sentence end. Done in awk rather than in a shell
    # parameter expansion so the three markers are one expression a reader can check.
    _rl_lead="$(printf '%s' "$_rl_what" | awk '
      {
        s = $0
        best = length(s) + 1
        for (i = 1; i <= 3; i++) {
          m = (i == 1) ? index(s, "\343\200\202") : (i == 2 ? index(s, ". ") : index(s, "<br>"))
          if (m > 0 && m < best) best = m
        }
        print substr(s, 1, best - 1)
      }')"

    _rl_ncols="$(printf '%s' "$_rl_name" | jq -Rr "include \"eaw-ranges\" {search:\"$_rl_lib\"}; dispwidth")"
    _rl_lcols="$(printf '%s' "$_rl_lead" | jq -Rr "include \"eaw-ranges\" {search:\"$_rl_lib\"}; dispwidth")"
    # cksum, not a cryptographic hash: this identifies a row for a human-managed baseline, it
    # does not defend against anyone. Bounded to the envelope this repo allows.
    _rl_key="$(printf '%s' "$_rl_name" | cksum | awk '{print $1}')"
    # The prefix is for a person reading the file. It is NOT part of the key -- truncating it
    # differently later must not silently re-pin every row.
    #
    # TRUNCATED WITH jq, NOT `cut -c`. Measured: `cut -c1-48` cut by BYTES here, because this
    # guard runs with a minimal environment and no UTF-8 locale, so it sliced a multi-byte
    # character in half and wrote INVALID UTF-8 into a tracked file. jq is UTF-8 native and is
    # already inside this envelope. A generated artifact that is not valid text is worse than a
    # missing one: everything downstream reads it and only some things complain.
    # THE HUMAN COLUMN CARRIES BACKLOG IDS AND NOTHING ELSE. It is not free text, and that
    # is not tidiness -- the SAME field failed three separate ways before it was narrowed to
    # this, each time because it copied arbitrary prose out of a document the CJK rule exempts
    # into a tracked file it does not:
    #   1. `cut -c1-48` sliced a multi-byte character in half (no UTF-8 locale under the
    #      guard's minimal environment) and wrote INVALID UTF-8.
    #   2. Chinese row names then made the whole file refuse to ship -- `.claude/` is on no
    #      exemption list.
    #   3. The ASCII skeleton still carried the PR links out of the row names, which spell a
    #      project identifier the gate bans. Blocked on push, again.
    # A backlog id can do none of those and identifies a row better than a prose fragment. A
    # row with no id gets an empty column and is found by its digest, which is the key anyway.
    #
    # It is NOT part of the key, so narrowing it cannot silently re-pin every row.
    # `|| true` is load-bearing under `set -o pipefail`: grep exits 1 when a row carries no
    # backlog id -- one row does -- which killed the generator MID-FILE on its first run. It
    # printed 26 of 52 rows and exited 1; a caller that only checked the row count it got back
    # would have pinned half the table and called it a baseline.
    _rl_pref="$(printf '%s' "$_rl_name" | { grep -oE 'B[0-9]+(\.[0-9]+)?' || true; } | head -4 | tr '\n' ' ' | sed 's/ $//')"

    printf '%s\t%s\t%s\t%s\n' "$_rl_key" "$_rl_ncols" "$_rl_lcols" "$_rl_pref"
  done
}
