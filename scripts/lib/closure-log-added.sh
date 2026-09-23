# closure-log-added.sh — the ONE computation of "which closure-log lines did this
# branch add". Sourced, never executed; it defines functions and nothing else.
#
# WHY THIS FILE EXISTS. Two callers now need the same answer:
#   - scripts/invariants/backlog-closure-log.sh, which validates every added line
#   - scripts/closure-declaration.sh reconcile, which asks whether every added closure was
#     declared by the phase that added it
# A second computation of the same thing is a copy, and a copied guard drifts, so the
# extraction is the point, not a convenience.
#
# WHAT IT DELIBERATELY DOES NOT DO. It does not verify that the log is an append-only byte
# prefix of its base -- criterion 4 stays in the invariant, where it already lives and is
# already tested. A caller that uses the added set WITHOUT that check (reconcile does) is
# relying on the invariant to red the same gate run, because check 8 runs unconditionally in
# every mode. That reliance is stated here rather than assumed.
#
# NO APOSTROPHES INSIDE ANY awk PROGRAM BELOW. A single-quoted shell string ends at the
# first one and every line after is then parsed as shell: one apostrophe in
# a comment can turn a green suite red, with no test failing for the reason it names.

# closure_log_split <log> <base_out> <added_out>
#   Materialises the merge-base version of <log> into <base_out> and the lines added since
#   into <added_out>. Prints "<base_ref><TAB><base_len>" on stdout.
#   A log that is new on this branch yields an empty base, so every line counts as added.
closure_log_split() {
  _cls_log="$1"; _cls_base="$2"; _cls_added="$3"

  # THE BASE IS origin/main, WITH LOCAL main ONLY AS A FALLBACK, and that order is a fix
  # rather than a preference. This used to read `git merge-base HEAD main`, and a local `main`
  # ref goes stale the moment you work from a worktree or stop checking main out -- which is
  # the normal way this repo is used. Measured at p36 close: local `main` sat four merged PRs
  # behind `origin/main`, so three ids closed by OTHER phases were counted
  # as "added by this branch" and the gate demanded this phase declare them. A silently wrong
  # BASE makes a correct check ask a wrong question, and the answer looks like the author
  # forgot something.
  #
  # Every other base in this repo already resolves against origin/main (see
  # scripts/invariants/roadmap-station-blocks-placement.sh, which says so in as many words).
  # The fallback keeps a clone with no remote working -- including this feature's own test
  # fixtures, which build a repo that has `main` and no `origin`.
  _cls_ref="$(git merge-base HEAD origin/main 2>/dev/null || true)"
  [ -n "$_cls_ref" ] || _cls_ref="$(git merge-base HEAD main 2>/dev/null || true)"
  if [ -n "$_cls_ref" ] && git cat-file -e "$_cls_ref:$_cls_log" 2>/dev/null; then
    git show "$_cls_ref:$_cls_log" > "$_cls_base"
  else
    : > "$_cls_base"
  fi

  # One-time normalisation of a base that predates criterion 0, so an already-committed
  # missing newline cannot permanently block every future append.
  if [ -s "$_cls_base" ] && [ "$(tail -c1 "$_cls_base" | od -An -c | tr -d ' ')" != '\n' ]; then
    printf '\n' >> "$_cls_base"
  fi

  _cls_len="$(wc -c < "$_cls_base" | tr -d ' ')"
  # A caller must not compare with `head -c 0`: BSD head treats a zero count as an ERROR,
  # prints nothing, and that empty output checksums equal to the empty base -- so a check
  # written that way passes BECAUSE it failed. The guard for that lives with criterion 4 in
  # the invariant, which is why the length is returned rather than hidden.
  tail -c "+$((_cls_len + 1))" "$_cls_log" > "$_cls_added"

  printf '%s\t%s\n' "$_cls_ref" "$_cls_len"
}

# closure_log_added_ids <added_file>
#   Prints one id per line for every added CLOSURE event, deduplicated in first-seen order.
#
#   THE ALLOW-LIST IS DELIBERATE AND IT REPLACED A DENY-LIST. The first version
#   skipped only `ref-amend` and treated every other event alike, which meant a branch that
#   merely REOPENED an id was forced to declare it -- under `closed:` (false) or `left-open:`
#   (semantically wrong; nothing was left open, it was actively reopened). The criterion this
#   serves says `a closure line this phase ADDS`, and a reopen is not a closure line. Over-firing
#   never let anything slip, but it demanded a declaration no shipped document explained.
#
#   `partial` IS in the set: it is a closure that did not finish the whole entry, and a phase
#   that adds one has changed what the backlog says about that id.
closure_log_added_ids() {
  awk -F'\t' '
    /^#/       { next }
    /^[ \t]*$/ { next }
    $2 != "closed" && $2 != "partial" { next }
    !seen[$1]++ { print $1 }
  ' "$1"
}
