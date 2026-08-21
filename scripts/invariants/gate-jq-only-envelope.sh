#!/usr/bin/env bash
# Invariant: the close gate's own dependency envelope stays jq-only --
# no `python3` -- across a DECLARED SET of files, with every exemption written down and a
# completeness assertion so the set cannot silently fall behind the directory.
#
# WHY. This is a hard rule: the gate is a drop-in for other people's
# repos, and every interpreter it reaches for is one more thing an adopter must already have.
# `scripts/close-gate.sh`'s header states the envelope ("bash + git + jq + coreutils only") and
# `scripts/validate.py` is explicitly NOT in it -- it is the VALIDATOR the manifest's declared
# `test_command` runs, not the gate. That distinction is the point: this invariant is about what
# the gate itself needs to start, never about what an adopter's declared test command shells out
# to. `gen-test-evidence.sh` resolving a manifest `test_command` that happens to say `python3` is
# therefore correct behaviour and is deliberately NOT a failure here.
#
# WHY IT COVERS THE WHOLE DIRECTORY. A scan of a few files by name would cover none of the
# scripts in `scripts/invariants/` -- every one of which runs INSIDE the gate, more literally
# part of its envelope than `gen-test-evidence.sh`. Under such a list, a
# `PLANTED=$(python3 -c "print(1)")` appended to `changelog-one-heading-per-category.sh` would leave this
# checker at exit 0 with only ok rows, none of them the planted file, and every invariant header
# saying "Envelope: bash + grep + awk" would be a claim wider than its mechanism.
#
# THE SHAPE OF THE EXEMPTIONS. A naive whole-directory scan is red against three files,
# and none of those three INVOKES anything -- they carry the token as DATA: matcher regexes,
# failure-message strings, one line of prose, and context-floor-envelope.sh's self-coverage assertion, which plants
# `python3 -c "pass"` on purpose. A checker that bans a token cannot lexically scan its own family,
# because sibling checkers necessarily spell that token in their source. Hence EXEMPTIONS -- and
# because an exemption is a hole, three things guard it: each carries a written reason (below), the
# completeness assertion proves nothing escaped both sets, and each exemption must prove it is
# STILL NEEDED (a file that no longer contains the token loses its exemption, loudly).
#
# THE RULE, stated exactly, because a naive `grep -c python3 == 0` fails on today's clean tree.
# The declared files legitimately WRITE ABOUT python3 (close-gate.sh's header carries the envelope statement
# itself). A line is read as EXECUTABLE unless the `python...` token sits in a shell comment, where
# "comment" is approximated the way POSIX sh actually defines it: a `#` at the start of the line
# or preceded by whitespace begins one. The line is truncated there, and only the surviving code
# is searched for `(^|non-word)python[0-9]*` -- which also catches `/usr/bin/python3`,
# `.venv/bin/python` and `env python3`, since `/` and space are non-word characters.
#
# WHAT THIS WOULD MISS (all lexical, all named rather than implied):
#   * obfuscation -- `PY="pyth"; ${PY}on3 x`, `$INTERP x`, `exec "$(command -v python3)"`. The
#     token never appears contiguously in the source bytes, so no grep of any shape sees it.
#     Deliberate evasion is not the threat; DRIFT is, and drift arrives spelled out.
#   * delegation -- a declared file calling a helper script that itself runs python3. Only the
#     declared files are read; a helper is covered only by being declared.
#   * a `#` inside a quoted string that swallows a REAL invocation to its right, e.g.
#     `eval "echo '#' ; python3 x"`. The truncation rule is per-line and quote-blind.
#   * the manifest. A manifest `test_command` such as `python3 scripts/validate.py` is the
#     validator, above, and out of scope by design.
#   * THE THREE EXEMPT FILES, by construction. Their reasons are below; that is the cost of being
#     able to check the rest at all.
#
# WHAT THIS WOULD FALSELY FLAG:
#   * `python3` inside a string or heredoc that is not a command -- `echo "no python3 here"` reads
#     as executable, because the truncation rule only understands comments, not quoting. The cost
#     is accepted: the false direction is a loud, one-line, trivially-fixed failure (move the
#     sentence into a comment), whereas the alternative -- teaching this a shell quoting model --
#     is a parser, in a file whose whole value is being grep that runs in milliseconds.
#   * a variable named `python3_note=...` -- same class, same cost.
#   * an UNTRACKED scratch `.sh` left in `scripts/invariants/`. The completeness assertion reads
#     the FILESYSTEM, not `git ls-files`, so a stray file is a failure. That is intended -- a local
#     run would execute it, so it is inside the envelope in every sense that matters -- and the
#     message says how to resolve it.
#
# SCOPE OF THE MARKDOWN HALF. `references/close-gate.md` is a DOCUMENT: its prose, its `json`
# example (`.venv/bin/python -m pytest`, an adopter's test command) and its `## Self-test`
# block (which really does run `python3 -c` to build oversized fixtures) may all say python3
# legitimately. Only the ONE fenced block under `## Portable gate script` -- the bytes an adopter
# copies out and runs as their gate -- is in scope. The block is located by that heading + the
# next fence pair rather than by line numbers, and a locator that finds nothing, or finds an
# EMPTY block, is a hard FAIL rather than a vacuous pass (an empty span compares equal to an
# empty span, so a comparison of two of them passes while checking nothing).
#
# THE FIXTURE ROOT IS AN ARGUMENT, NEVER AN ENVIRONMENT VARIABLE. `scan_set` takes the root it
# scans as a parameter and the self-coverage assertion calls it IN-PROCESS. The hooks-side envelope check
# shows why: a design that lets any ambient environment relocate the scan, or one that
# gates that behind a SECOND variable, can be steered from outside -- and a changelog check hits
# the same class with `PLC_CHANGELOG_PATH`, where an environment variable can point a
# gate at a README and produce a green check over a file nobody meant to check. An environment
# variable is not a capability.
#
# Envelope: bash + grep + awk. No python3 -- an invariant that needed one to prove nothing needs
# one would be self-refuting. This file cannot assert that about ITSELF by scanning (it is exempt,
# necessarily), so the honest substitute is the still-needed check below plus the pytest row.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The repo root is an OPTIONAL EXPLICIT ARGUMENT, defaulting to the derivation from this file's own
# location. It is an argument and never an environment variable, for the reason spelled out in the
# header. It exists because deriving the root from `$0` means a COPY of this script -- which is what
# every mutation test is -- silently resolves the root to wherever the copy was written, scans
# nothing, and fails for a reason that has nothing to do with the mutation -- a red that could
# be read as "the assertion works".
#
# Trust boundary, stated: a decoy root would make this scan a tree that is not the repo. That is
# accepted deliberately -- the only invocation that matters is the
# one written into the tracked `.claude/close-gate.json`, visible in every diff, and
# `scripts/test_gate_envelope.py` asserts that invocation passes NO arguments. Building a decoy
# that survives is also strictly harder here: it must carry every declared file clean, every
# exempt file still holding the token, and a `close-gate.md` with a locatable fenced gate.
REPO_ROOT="${1:-$(cd "$HERE/../.." && pwd)}"

# --- the declared set: whole-file targets, repo-relative, ONE PER LINE, written out by hand.
# A hand-written list rather than a glob, deliberately: a glob removes the stale-list risk
# and adds two -- a script nobody meant to gate joins the envelope silently, and the exemption list
# is STILL a hand-written list, so the staleness only moves. The completeness assertion below gives
# the declared list the glob's one real benefit (nothing can be forgotten) while keeping every
# entry a deliberate act.
# Order is load-bearing only in that close-gate.sh and gen-test-evidence.sh lead and the markdown
# case trails, so those rows keep a stable relative order.
DECLARED="
scripts/close-gate.sh
scripts/gen-test-evidence.sh
scripts/invariants/changelog-one-heading-per-category.sh
scripts/invariants/ledger-contract-sync.sh
scripts/invariants/manifest-version-sync.sh
scripts/invariants/no-hook-state-tracked.sh
scripts/invariants/no-icloud-conflict-copies.sh
scripts/backlog-closures.sh
scripts/invariants/backlog-closure-log.sh
scripts/invariants/backlog-no-title-markers.sh
scripts/invariants/gate-abort-is-not-success.sh
scripts/invariants/unreleased-survives-drain.sh
scripts/invariants/preimage-invisible-to-rollover.sh
scripts/invariants/guide-map-covers-references.sh
scripts/invariants/tasklist-never-tracked.sh
scripts/invariants/close-gate-wiring.sh
scripts/retention-drain.sh
scripts/ac-evidence.sh
scripts/ac-baseline.sh
scripts/invariants/close-gate-doc-has-check.sh
scripts/invariants/adopter-doc-ships-ac-scripts.sh
scripts/invariants/acquire-shape-and-steal-oracle.sh
scripts/invariants/stage-registry-bindings.sh
scripts/invariants/link-check-reaches-deep.sh
scripts/invariants/skip-baseline-matches.sh
scripts/skip-baseline.sh
scripts/ledger-append.sh
scripts/ledger-run.sh
scripts/invariants/lychee-pin-single-source.sh
scripts/invariants/session-card-no-network.sh
scripts/invariants/ci-status-never-tracked.sh
scripts/invariants/mode-map-single-block.sh
scripts/invariants/mode-skip-marker-template.sh
scripts/invariants/longterm-candidates-not-in-diff.sh
scripts/invariants/fast-keeps-the-net.sh
scripts/invariants/mode-provenance-recorded.sh
scripts/invariants/careful-paths-single-block.sh
scripts/invariants/careful-reason-has-no-inference-words.sh
scripts/invariants/careful-check-reads-worktree.sh
scripts/invariants/careful-boundary-text-present.sh
"

# --- the exemption table. One line per file: `<path>|<reason>`. A bare name in a list is
# indistinguishable from an oversight; a reason is a decision a reader can evaluate. The reason
# lives HERE and not as a marker inside the exempt file, deliberately: a `# envelope-exempt:`
# comment would let any future file grant itself an exemption in one line with nothing reviewing
# it, whereas an edit here lands in the diff a reviewer is already reading.
EXEMPT="
scripts/invariants/gate-jq-only-envelope.sh|this file -- its matcher regex and every one of its failure strings necessarily spell the token it bans
scripts/invariants/context-floor-envelope.sh|same shape, plus its self-coverage assertion which PLANTS a python invocation into a fixture on purpose
scripts/invariants/named-interpreter.sh|one line of prose naming python3 as explicitly OUT of that check's shell-only scope
"

MD="skills/project-lifecycle/references/close-gate.md"
MD_ANCHOR='^## Portable gate script'
INV_DIR="scripts/invariants"

# Print `NR: line` for every line in [s,e] whose CODE (comment truncated per the rule above)
# invokes a python interpreter.
scan() {
  awk -v s="$2" -v e="$3" '
    NR < s || NR > e { next }
    {
      code = $0
      sub(/^[[:space:]]*#.*$/, "", code)
      sub(/[[:space:]]#.*$/, "", code)
      if (code ~ /(^|[^[:alnum:]_])python[0-9]*/) print NR ": " $0
    }
  ' "$1"
}

# --- scan_set <root>: run every check over the declared set rooted at <root>.
#
# A FUNCTION taking the root as an ARGUMENT, not a re-invocation of this script and not an
# environment variable. The self-coverage assertion below needs to run this against a fixture tree
# in-process; see the header for why an environment-variable design can be defeated.
# Returns 0 when the whole set is clean, 1 otherwise. Prints one row per target.
scan_set() {
  local root="$1"
  local rc=0 f reason hits n_decl=0

  report() {  # label, hits
    if [ -n "$2" ]; then
      echo "FAIL gate-jq-only-envelope: $1 invokes a python interpreter"
      printf '%s\n' "$2"
      echo "  -> the gate's envelope is bash + git + jq + coreutils only (stated in the header of"
      echo "     scripts/close-gate.sh). Redesign the step in jq, or -- if this line only TALKS"
      echo "     about python3 -- move it into a comment."
      rc=1
    else
      echo "ok gate-jq-only-envelope: $1 invokes no python interpreter"
    fi
  }

  # --- empty-set guard. An empty declared list scans nothing, prints nothing but the trailing
  # assertions, and is indistinguishable from a clean repository.
  for f in $DECLARED; do n_decl=$((n_decl + 1)); done
  if [ "$n_decl" -eq 0 ]; then
    echo "FAIL gate-jq-only-envelope: the declared set is EMPTY -- a scan over nothing is not a pass"
    return 1
  fi

  for f in $DECLARED; do
    if [ ! -r "$root/$f" ]; then
      echo "FAIL gate-jq-only-envelope: $f missing or unreadable"
      rc=1
      continue
    fi
    report "$f" "$(scan "$root/$f" 1 "$(grep -c '' "$root/$f")")"
  done

  # --- the embedded gate: locate the fenced block under the anchor heading.
  if [ ! -r "$root/$MD" ]; then
    echo "FAIL gate-jq-only-envelope: $MD missing or unreadable"
    return 1
  fi

  local RANGE MD_START MD_END MD_INFO
  RANGE="$(awk -v anchor="$MD_ANCHOR" '
    $0 ~ anchor { seen = 1; next }
    seen && /^```/ {
      if (open == 0) { open = NR; info = $0 }
      else { print (open + 1) " " (NR - 1) " " info; exit }
    }
  ' "$root/$MD")"

  if [ -z "$RANGE" ]; then
    echo "FAIL gate-jq-only-envelope: cannot locate the embedded gate in $MD"
    echo "  -> expected a fenced block after a heading matching '$MD_ANCHOR'. If the document was"
    echo "     restructured, this invariant's locator is stale and must be re-anchored -- do NOT"
    echo "     delete the check, an unfindable gate is not an unchecked one."
    return 1
  fi

  # shellcheck disable=SC2086
  set -- $RANGE
  MD_START="$1"; MD_END="$2"; MD_INFO="$3"

  if [ "$MD_START" -gt "$MD_END" ]; then
    echo "FAIL gate-jq-only-envelope: the embedded gate block in $MD is EMPTY (lines $MD_START-$MD_END)"
    echo "  -> an empty range would scan nothing and pass, which is the failure this guard exists"
    echo "     to make impossible."
    return 1
  fi

  if [ "$MD_INFO" != '```bash' ]; then
    echo "FAIL gate-jq-only-envelope: the embedded gate's fence is '$MD_INFO', expected '\`\`\`bash'"
    echo "  -> the located block is not the shell gate; re-anchor rather than widen."
    return 1
  fi

  report "$MD (embedded gate, lines $MD_START-$MD_END)" \
    "$(scan "$root/$MD" "$MD_START" "$MD_END")"

  # --- each exemption must still be NEEDED. A file that no longer contains the token it was
  # exempted for would sit exempt forever, quietly unscanned; here it turns red and gets deleted.
  # Stated limit: this asks about the CODE-visible token, so an exempt file that moves its only
  # mention into a comment goes red while being genuinely fine. Accepted -- loud, on a file the
  # author is already editing.
  # NOTE, because the two loops look like they should behave alike and do not: `IFS='|'` means this
  # read does NOT strip leading whitespace, where `for f in $DECLARED` above does. Indenting an
  # EXEMPT entry therefore breaks it -- loudly (the path stops being readable AND stops matching the
  # completeness check), which is survivable, but it is a real asymmetry rather than an oversight.
  while IFS='|' read -r f reason; do
    [ -n "$f" ] || continue
    if [ ! -r "$root/$f" ]; then
      echo "FAIL gate-jq-only-envelope: exempt file $f missing or unreadable"
      rc=1
      continue
    fi
    hits="$(scan "$root/$f" 1 "$(grep -c '' "$root/$f")")"
    if [ -z "$hits" ]; then
      echo "FAIL gate-jq-only-envelope: $f is EXEMPT but no longer contains the token"
      echo "  -> the exemption has expired. Delete its line from EXEMPT and move the file into"
      echo "     DECLARED, so it is scanned like every other file."
      rc=1
    else
      echo "ok gate-jq-only-envelope: $f exempt, still needed ($reason)"
    fi
  done <<EOF
$(printf '%s\n' "$EXEMPT" | grep -v '^[[:space:]]*$')
EOF

  # --- completeness: every .sh in the invariants directory is in exactly one of the two sets.
  # This is the stale-list risk the hooks-side envelope check NAMES and does not close. Reads the
  # FILESYSTEM rather than `git ls-files`: a fixture directory is not a repo, and a git-based
  # listing would make this assertion exercise different code from the real run.
  local found=0 base rel known
  for path in "$root/$INV_DIR"/*.sh; do
    [ -e "$path" ] || continue
    found=$((found + 1))
    base="$(basename "$path")"
    rel="$INV_DIR/$base"
    known=0
    for f in $DECLARED; do [ "$f" = "$rel" ] && known=1; done
    # STRING equality, never a grep. A `grep -q "^$rel|"` here would interpolate a
    # filename into a BASIC REGULAR EXPRESSION -- so a `.` in the name is a wildcard. Then a
    # real, undeclared, unexempted `probe.v2.sh` sitting in
    # this directory would match an EXEMPT line reading `probeXv2.sh`, the "is in neither set" row would never
    # fire, and the whole run would exit 0. That is a FALSE PASS in the one mechanism this check exists
    # to provide. The declared loop one line up is exact too; the two agree.
    while IFS='|' read -r ef _; do
      [ "$ef" = "$rel" ] && known=1
    done <<EOF
$(printf '%s\n' "$EXEMPT" | grep -v '^[[:space:]]*$')
EOF
    if [ "$known" -eq 0 ]; then
      echo "FAIL gate-jq-only-envelope: $rel is in neither the declared set nor the exemptions"
      echo "  -> it runs inside the gate, so it is inside the envelope. Resolve it one of three"
      echo "     ways: add it to DECLARED (it is scanned), add it to EXEMPT with a written reason"
      echo "     (it is not), or move it out of $INV_DIR if it is a scratch file."
      rc=1
    fi
  done
  # UNREACHABLE BY ANY FIXTURE, and said so rather than left to look tested: most of the
  # DECLARED files live in this very directory, so a root whose $INV_DIR is empty fails the
  # "missing or unreadable" rows long before arriving here -- an empty
  # fixture root produces those rows and never this one. It stays because the day the declared set
  # stops including a file from this directory is the day it becomes reachable, and a vacuous pass
  # over an empty directory looks exactly like a covered one (a guard no fixture can
  # reach needs naming, not a comment claiming coverage).
  if [ "$found" -eq 0 ]; then
    echo "FAIL gate-jq-only-envelope: no .sh found in $INV_DIR -- a completeness check over an"
    echo "  empty directory passes vacuously and looks exactly like a covered one"
    rc=1
  fi

  return "$rc"
}

# --- build_fixture <src-root> <dst-root>: copy the WHOLE set (declared + exempt + the markdown)
# preserving relative paths. The whole set, never one substituted file: with the rest defaulting to
# the real ones an unrelated real defect can produce the red, and a red that is not attributable to
# the plant proves nothing.
# The invariants directory in the fixture holds EXACTLY the declared + exempt files, so the
# completeness assertion stays green there and cannot confound the plant's red.
build_fixture() {
  local src="$1" dst="$2" f
  for f in $DECLARED $MD; do
    mkdir -p "$dst/$(dirname "$f")" || return 1
    cp "$src/$f" "$dst/$f" || return 1
  done
  while IFS='|' read -r f _; do
    [ -n "$f" ] || continue
    mkdir -p "$dst/$(dirname "$f")" || return 1
    cp "$src/$f" "$dst/$f" || return 1
  done <<EOF
$(printf '%s\n' "$EXEMPT" | grep -v '^[[:space:]]*$')
EOF
  return 0
}

# --- self-coverage. Proves this checker actually OPENED each declared file,
# rather than merely listing it: for EACH declared file, plant a python invocation in exactly that
# one copy of a full fixture set and require a red that NAMES it. Plus an all-clean control run
# over the same fixture shape, because a red that appears with nothing planted is not evidence.
#
# Without this, a declared entry that is never read looks identical to a declared entry that is
# read and clean.
self_coverage() {
  local src="$1" rc=0 planted tmp out frc
  for planted in $DECLARED; do
    tmp="$(mktemp -d)" || { echo "FAIL gate-jq-only-envelope SELF-COVERAGE: mktemp -d failed"; return 1; }
    if ! build_fixture "$src" "$tmp"; then
      echo "FAIL gate-jq-only-envelope SELF-COVERAGE: could not build the fixture set"
      rm -rf "$tmp"; return 1
    fi
    printf '\nPLANTED=$(python3 -c "pass")\n' >> "$tmp/$planted"
    out="$(scan_set "$tmp" 2>&1)"; frc=$?
    if [ "$frc" -eq 0 ]; then
      echo "FAIL gate-jq-only-envelope SELF-COVERAGE: a python invocation planted in $planted did"
      echo "  not turn the scan red -- that file is DECLARED but never actually read."
      rc=1
    elif ! printf '%s\n' "$out" | grep -qF "FAIL gate-jq-only-envelope: $planted invokes"; then
      echo "FAIL gate-jq-only-envelope SELF-COVERAGE: the scan went red with $planted planted, but"
      echo "  the failure does not name that file -- the red is not attributable to the plant."
      rc=1
    fi
    rm -rf "$tmp"
  done

  # --- the control. Same fixture shape, nothing planted, must be green.
  tmp="$(mktemp -d)" || { echo "FAIL gate-jq-only-envelope SELF-COVERAGE: mktemp -d failed"; return 1; }
  if ! build_fixture "$src" "$tmp"; then
    echo "FAIL gate-jq-only-envelope SELF-COVERAGE: could not build the control fixture"
    rm -rf "$tmp"; return 1
  fi
  out="$(scan_set "$tmp" 2>&1)"; frc=$?
  rm -rf "$tmp"
  if [ "$frc" -ne 0 ]; then
    echo "FAIL gate-jq-only-envelope SELF-COVERAGE: the all-clean control fixture went RED, so the"
    echo "  per-file reds above are not attributable to their plants."
    printf '%s\n' "$out"
    rc=1
  fi

  if [ "$rc" -eq 0 ]; then
    local n=0 f
    for f in $DECLARED; do n=$((n + 1)); done
    echo "ok gate-jq-only-envelope SELF-COVERAGE: each of the $n declared files was proven readable"
    echo "   by this scan (planted individually, red each time, named each time; clean control green)"
  fi
  return "$rc"
}

scan_set "$REPO_ROOT"; RC=$?
self_coverage "$REPO_ROOT" || RC=1
exit "$RC"
