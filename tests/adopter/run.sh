#!/usr/bin/env bash
# Run the close gate the way an ADOPTER runs it: from a repository that has none of this
# repo's own surfaces. Captures to a FILE, never through a pipe -- a token printed inside a
# subshell or a `| tee` chain can vanish from the collected output while the harness still
# exits 0.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${PLC_ADOPTER_OUT:-${TMPDIR:-/tmp}/plc-adopter-run.txt}"

docker build -q -t plc-adopter-fixture "$HERE" >/dev/null
docker run --rm -v "$REPO:/src:ro" -v "$HERE:/fixture:ro" plc-adopter-fixture \
  /bin/bash -c '
    set -euo pipefail
    # An EMPTY repository. No docs/, no .claude/, no .git/hooks/pre-push.
    mkdir -p /work/adopter && cd /work/adopter
    git init -q . && git config user.email a@a && git config user.name a
    git commit -q --allow-empty -m "initial"

    # THE MANIFEST PATH IS HARDCODED. close-gate.sh sets M=".claude/close-gate.json" and
    # reads no env override, so the fabricated manifest goes where the gate actually looks.
    mkdir -p .claude src docs/specs docs/plans docs/journal.d
    cp /fixture/fabricated/close-gate.json .claude/close-gate.json
    cp -r /src/scripts ./scripts

    # THE GATE NEEDS origin/main TO EXIST. close-gate.sh computes
    # `git merge-base origin/main HEAD` and exits 1 when it resolves to empty. A fresh
    # `git init` has no remote at all, so the gate would die there -- before reaching a
    # single one of the adopter-only branches this fixture exists to observe. scripts/local-ci.sh
    # already solves exactly this (it fetches origin/main into its clone); the same idea,
    # spelled for a repo with no upstream: point the ref at the pre-phase commit, which is
    # what a real adopter branching off main would have.
    git branch -q -M main
    git update-ref refs/remotes/origin/main HEAD

    git checkout -q -b feat/phase-1.0-adopter
    echo "adopter" > src/thing.txt
    printf "# spec\n" > docs/specs/2026-01-01-phase-1.0-design.md
    printf "# plan\n" > docs/plans/2026-01-01-phase-1.0.md
    # A COMPLETE minimal adopter, not a half-built one: the CHANGELOG, the ROADMAP row, the
    # journal FACT fields and the evidence file are all supplied, so whatever the gate still says
    # is about the PRODUCT, not about a gap in this fixture.
    printf "## FACT\n\n- **Decision:** ship the adopter phase\n- **Why:** to exercise the gate\n- **Backing:** this fixture\n\n### Plan deviations\n\nnone\n" > docs/journal.d/2026-01-01-adopter.md
    printf "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- the adopter phase\n" > CHANGELOG.md
    printf "# Roadmap\n\n| PR | batch | what | why | eta |\n|---|---|---|---|---|\n| phase 1.0 adopter | - | - | - | - |\n" > docs/ROADMAP.md
    # NOT swallowed. gen-test-evidence.sh is a script an adopter runs, so WHY it failed is part of
    # the result; masking it with a stub would fail the gate later for a misleading reason.
    # `cmd; echo $?` is NOT set -e-safe: under `set -euo pipefail` the script dies on cmd and the
    # echo never runs, so the capture would end before the gate ran at all. An `if` observes a
    # failure instead of being killed by it.
    # STAGE BEFORE GENERATING EVIDENCE. With the work still untracked,
    # gen-test-evidence.sh refuses with "the evidence header fingerprints nothing -- the
    # manifest'"'"'s test_evidence_inputs matched no tracked files". The declared globs are not
    # wrong; the ORDER is. evidence_digest() fingerprints `git ls-files -- <pathspec>`, which
    # lists TRACKED paths only, so a brand-new adopter file is invisible to it until it is
    # staged -- and an adopter'"'"'s FIRST phase is all brand-new files, which is exactly the shape
    # this fixture exists to stand in for. With
    # src/thing.txt untracked `git ls-files -- src` returns 0 rows, staged it returns 1, and the
    # bare `src` pathspec matches the subtree exactly as `src/*` does. The refusal message names
    # this fix itself ("or `git add` the paths they name").
    # Staging here and committing below cannot move the fingerprint:
    # evidence_digest hashes working-tree CONTENT, not the index entry.
    git add -A
    echo "=== gen-test-evidence (adopter path) ==="
    if /bin/bash scripts/gen-test-evidence.sh phase; then
      echo "ADOPTER-EVIDENCE-EXIT=0"
    else
      echo "ADOPTER-EVIDENCE-EXIT=$?"
    fi
    git add -A && git commit -q -m "feat: adopter phase"

    echo "=== close-gate ==="
    # The verdict is CAPTURED, not discarded: swallowing it with `|| true` would let a
    # `✗ close-gate FAIL` verdict sit beside a fixture that printed "ok" and exited 0.
    # `cmd; echo $?` IS NOT A CAPTURE under `set -euo pipefail` -- the shell dies on the
    # non-zero cmd and the echo never runs. That matters here because the gate is EXPECTED
    # to exit non-zero, so that form would abort the container script right here, before the
    # exit code is ever printed.
    if /bin/bash scripts/close-gate.sh phase 1.0; then
      echo "ADOPTER-GATE-EXIT=0"
    else
      echo "ADOPTER-GATE-EXIT=$?"
    fi
    echo "=== end ==="
    echo "this fixture does not exercise /init-harness"
  ' > "$OUT" 2>&1

echo "captured -> $OUT"

# A counted absence of coverage that NAMES THE ARTIFACT RESPONSIBLE, rather than a bare total.
# It lives in its own script so the wording is assertable;
# scripts/test_not_covered_line.py is the guard, and the ban on the words
# skip/ok/pass is part of it.
/bin/bash "$HERE/print-not-covered.sh" "$HERE/skip-baseline.txt"

# BOTH oracles run, and only then one exit status. Under `set -e` a failing compare-reached.sh
# would kill this script before the verdict was ever compared, so a run that also produced a new
# untriaged ✗ row would report the branch mismatch alone -- the more interesting half hidden
# behind the less interesting one. `|| rc=1` RECORDS a failure and still propagates it; it is not
# a `|| true`.
#
# The two oracles are deliberately different shapes: reached is a SUBSET check (did we get to the
# adopter-only branches at all), verdict is SET EQUALITY (is the gate's answer still exactly the
# one we triaged). Neither implies the other -- every branch can be reached by a run whose gate
# aborted, and the verdict can match while a branch silently stopped being exercised.
rc=0
/bin/bash "$HERE/compare-reached.sh" "$OUT" "$HERE/expected-branches.txt" || rc=1
/bin/bash "$HERE/compare-verdict.sh" "$OUT" "$HERE/expected-verdict.txt" || rc=1
exit "$rc"
