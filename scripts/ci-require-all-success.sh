#!/usr/bin/env bash
# ci-require-all-success.sh — the body of the `all-tests-passed` aggregate gate.
#
# Branch protection can require ONE status check by name. The matrix job `pytest-shard` reports
# under expanded per-leg names a bare required-check name never matches, so the workflow fans
# every CI job into one stable job (`all-tests-passed`) and that job calls this script with each
# dependency's `result`.
#
# It passes only when EVERY argument is exactly `success`. This is stricter than "not failure" on
# purpose: a GitHub required check whose job was `skipped` counts as PASSING, so a dependency that
# silently did not run (a path-skip, a cancelled matrix, an `if:` that evaluated false) must be
# caught here as a NON-pass — otherwise the whole suite could be skipped and the PR still go green.
# `cancelled`, `failure`, and an empty/missing result all fail too.
#
# Called from .github/workflows/validate.yml. Tested by scripts/test_ci_require_all_success.py.
set -u

if [ "$#" -lt 1 ]; then
  # Vacuous guard: zero results is not "everything passed", it is a wiring mistake. A gate that
  # passes when it was handed nothing is the empty-set-is-not-evidence failure this repo has filed.
  echo "::error::ci-require-all-success: no job results were passed — nothing to check is not a pass" >&2
  exit 2
fi

fail=0
for r in "$@"; do
  if [ "$r" != "success" ]; then
    echo "::error::a required job was '${r:-<empty>}' (not success) — a skipped or cancelled job does NOT pass"
    fail=1
  fi
done

if [ "$fail" -eq 0 ]; then
  echo "all required jobs succeeded ($*)"
fi
exit "$fail"
