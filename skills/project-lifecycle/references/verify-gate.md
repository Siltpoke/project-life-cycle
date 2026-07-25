# verify-gate — the per-PR "qualified?" artifact contract

The gate (`scripts/verify-gate.sh`, jq-only) VALIDATES artifacts; separate runtimes
PRODUCE them. It reads:

- `.plc/spec.json` (on the PR BASE) — `{ specCommit, acceptanceCriteria: [{ id, text }] }`.
- `.plc/report.json` (working tree) — `{ prHeadSha, providerVendor, providerModel,
  verdict: "QUALIFIED"|"NOT_QUALIFIED", perAc: [{ id, verdict: "met"|"unmet",
  evidence: ["file://…"|"test://…"|"hunk://…"] }], findings: [{ severity, summary, evidence }] }`.
- `.plc/override-<reviewedHeadSha>.json` — `{ reviewedHeadSha, findings: [...], reason }`.

Exit 0 = every deterministic check passed AND (verdict==QUALIFIED OR a matching override
exists). Exit non-zero = block. The LLM verdict never mechanically blocks; the block is the
ABSENCE of the human override when the verdict is not QUALIFIED.

## Invocation

```
PLC_REPO=<repo> bash scripts/verify-gate.sh <BASE_SHA> <HEAD_SHA>
```

- `PLC_REPO` — repo root (default: `git rev-parse --show-toplevel`).
- `PLC_REPORT` — override the report path (default: `$PLC_REPO/.plc/report.json`).
- Exits `0` on all-pass; non-zero if any check fails.

## Checks implemented

1. **Report exists** — `.plc/report.json` must be present at the resolved path.
2. **Report is valid JSON** — parsed with `jq -e .`.
3. **Required top-level fields present** — `prHeadSha`, `providerVendor`, `providerModel`,
   `verdict`, `perAc` (checked with `jq -e 'has("<field>")'`).
4. **SHA binding** — `report.prHeadSha` must equal the `<HEAD_SHA>` argument. This is how the
   gate proves the report was generated FOR this exact commit, not a stale one from an earlier
   push to the same PR.

A commit cannot embed its own hash (writing the hash changes the tree, which changes the
hash), so in practice the report-bearing commit binds `prHeadSha` to an ancestor commit's SHA,
and the gate is invoked with that ancestor SHA as `<HEAD_SHA>` — not necessarily the literal
tip of the branch. Later commits on top (e.g. a bookkeeping "bind report" commit) don't
invalidate the binding as long as the caller passes the SHA the report actually claims.

Later tasks extend the checks run inside the `else` branch of the report-schema block
(spec/AC cross-reference, evidence resolution, override matching, envelope assertions) —
this doc will grow alongside them.

## Envelope regression lock

`scripts/test_verify_gate.py::test_gate_is_jq_only_no_python_or_node` locks the gate's
envelope (bash + git + jq + coreutils only) — it fails if a future edit reaches for
`python3`/`python`/`node`/`npx`. It scans non-comment content only, so the gate's own
explanatory prose about staying jq-only doesn't trip the check it's proving. This test runs
as part of `scripts/test_verify_gate.py`, which is already covered by CI's "Gate + hook unit
tests" step (`python -m pytest scripts/ -q` globs the whole `scripts/` directory) — no
separate CI step is needed for it.

## Making the gate a real merge block (host config, out of the gate script)

On a real PR, `verify-gate.sh <base> <head>` runs as a CI job whose pass/fail becomes a
GitHub **required status check** in branch protection. The code-soundness floor is the
adopter's EXISTING CI sub-checks, each individually required (never one aggregate that can
go green while a sub-check is silently disabled). This gate script provides the qualified?
status; branch protection is what makes it block merge. That config is a host setting, not
part of this jq envelope.
