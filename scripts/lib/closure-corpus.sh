# closure-corpus.sh (the station-plan work) — what "the corpus" means, defined once.
#
# Sourced by closed-step-refs-resolve.sh and station-state-consistency.sh. Both need the
# same set of documents, and two definitions of a scope drift apart silently: one guard
# would start checking a smaller world than the other while both kept printing ✓.
#
# WHY THE ARCHIVE IS IN SCOPE, and it is the whole reason this is corpus-wide rather than
# live-only. `scripts/retention-drain.sh` moves `docs/superpowers/specs/` wholesale into
# `docs/archive/working/`, and closure declarations live in those specs. A deriver that read
# only live documents would make every station's position REVERSE at the moment of an
# archive run, with nothing having happened in the project at all (the closure design). Scanning
# from `docs/` covers both by containment; the archive is named here anyway, because a later
# reader narrowing this glob needs to meet the reason rather than infer it.
#
# Envelope: bash + coreutils + grep. No python3, no jq needed here.

# closure_corpus_files [root]
#   Prints one path per line for every document carrying a real `plc-closes` opening fence.
#   No matches prints nothing and returns 0 — an empty corpus is a legal state, and it is
#   the CALLER's job to say so out loud rather than let a silent pass stand in for it.
closure_corpus_files() {
  local root="${1:-docs}"
  [ -d "$root" ] || return 0
  # -exec ... {} + rather than a pipe into xargs: with no matches, find simply never execs,
  # whereas xargs on this platform will run grep with no file arguments and read stdin.
  find "$root" -type f -name '*.md' \
    -exec grep -lE '^```plc-closes[[:space:]]*$' {} + 2>/dev/null | sort
}

# closure_step_records <extractor> <file>...
#   Prints `token<TAB>source` for every `closed-step:` entry that names an actual step,
#   dropping the `none` sentinel (which asserts that no step was closed and therefore has
#   nothing to resolve). Returns non-zero if the extractor did.
#
#   The extractor is passed in rather than located here so a test can point at a copy.
closure_step_records() {
  local extractor="$1"; shift
  [ "$#" -ge 1 ] || return 0
  local out rc=0
  out="$(/bin/bash "$extractor" extract --corpus "$@")" || rc=$?
  [ "$rc" -eq 0 ] || return "$rc"
  printf '%s\n' "$out" | awk -F'\t' '$1 == "closed-step" && $2 != "none" { print $2 "\t" $4 }'
}
