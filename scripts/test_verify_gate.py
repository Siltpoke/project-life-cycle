"""Self-mutation tests for scripts/verify-gate.sh — the jq per-PR artifact validator.

python here is TEST tooling (subprocess-drives the bash gate against fixture git repos),
NOT the gate's runtime envelope — the gate itself stays jq-only.
Mirrors scripts/test_close_gate_local.py's fixture-git-repo approach.

Invariant for should-block tests: bind report.prHeadSha to the head you pass (via
_perturb_commit) so exactly the target check fires, and assert a check-UNIQUE message
substring — never `returncode != 0` alone (it can pass for the wrong reason, e.g. an
incidental SHA mismatch masking the check actually under test). The sole exception is
test_wrong_sha_report_blocks, which isolates the SHA check on purpose.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[1] / "scripts/verify-gate.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", msg)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _write(repo: Path, rel: str, body: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _run(repo: Path, base: str, head: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(GATE), base, head],
        cwd=repo, capture_output=True, text=True,
        env={"PLC_REPO": str(repo), "PATH": __import__("os").environ["PATH"]},
    )


def _perturb_commit(repo: Path, msg: str) -> str:
    """Commit the current .plc/report.json perturbation, then rebind report.prHeadSha to the
    new commit sha in the WORKING TREE (which is what the gate reads) so ONLY the perturbed
    check fires — never a masking SHA mismatch. Returns the head sha to pass to the gate."""
    h = _commit(repo, msg)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["prHeadSha"] = h
    _write(repo, ".plc/report.json", json.dumps(rep))  # working-tree rebind, gate reads this
    return h


def _mk(tmp_path: Path) -> tuple[Path, str, str]:
    """A repo where every gate check passes. Returns (repo, base_sha, head_sha).

    base commit: .plc/spec.json (AC1) + a source file the report's evidence points at.
    head commit: a valid .plc/report.json bound to the head sha, verdict QUALIFIED.
    """
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _write(repo, "README.md", "hi\n")
    _write(repo, ".plc/spec.json", json.dumps(
        {"specCommit": "x", "acceptanceCriteria": [{"id": "AC1", "text": "does the thing"}]}))
    _write(repo, "scripts/thing.sh", "#!/bin/sh\necho hi\n")
    base = _commit(repo, "spec + source on base")

    report = {
        "prHeadSha": "PLACEHOLDER", "providerVendor": "claude", "providerModel": "opus-4-8",
        "verdict": "QUALIFIED",
        "perAc": [{"id": "AC1", "verdict": "met", "evidence": ["file://scripts/thing.sh"]}],
        "findings": [],
    }
    _write(repo, ".plc/report.json", json.dumps(report))
    _write(repo, "scripts/thing.sh", "#!/bin/sh\necho hi improved\n")
    head = _commit(repo, "feat: the change + report")
    # bind the report to the real head sha now that we know it. NOTE: `head` is
    # deliberately NOT reassigned to the bind-commit's own sha below — a commit
    # cannot self-reference its own hash inside its tree (writing the sha changes
    # the tree, which changes the sha). The bind commit is one more commit ON TOP
    # of `head`; the report's prHeadSha stays bound to `head`, which is what we
    # return so callers' (base, head) pair matches what report.json actually says.
    report["prHeadSha"] = head
    _write(repo, ".plc/report.json", json.dumps(report))
    _commit(repo, "chore: bind report to head")
    return repo, base, head


def test_fully_valid_pr_passes(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    r = _run(repo, base, head)
    assert r.returncode == 0, r.stdout + r.stderr


def test_missing_report_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    (repo / ".plc/report.json").unlink()
    _commit(repo, "chore: drop report")
    r = _run(repo, base, head)
    assert r.returncode != 0
    assert "report.json" in r.stdout


def test_invalid_json_report_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    _write(repo, ".plc/report.json", "{not json")
    _commit(repo, "chore: corrupt report")
    r = _run(repo, base, head)
    assert r.returncode != 0


def test_wrong_sha_report_blocks(tmp_path: Path) -> None:
    # Deliberately NOT using _perturb_commit here: this test isolates the SHA check
    # itself, so we commit-without-rebinding on purpose (prHeadSha stays "deadbeef..."
    # while newhead is the real, different commit sha).
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["prHeadSha"] = "deadbeef" * 5
    _write(repo, ".plc/report.json", json.dumps(rep))
    _commit(repo, "chore: stale sha")
    newhead = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                             capture_output=True, text=True).stdout.strip()
    r = _run(repo, base, newhead)
    assert r.returncode != 0
    assert "prHeadSha" in r.stdout


def test_missing_required_field_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    del rep["providerVendor"]
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: drop vendor")
    r = _run(repo, base, newhead)
    assert r.returncode != 0
    assert "providerVendor" in r.stdout


def test_report_ac_ids_must_equal_base_spec(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["perAc"].append({"id": "AC2", "verdict": "met", "evidence": ["file://scripts/thing.sh"]})
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: extra ac not in spec")
    r = _run(repo, base, newhead)
    assert r.returncode != 0
    assert "AC ids do not equal base spec AC ids" in r.stdout


def test_missing_ac_from_report_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    # spec has AC1+AC2 on base, report covers only AC1
    _write(repo, ".plc/spec.json", json.dumps(
        {"specCommit": "x", "acceptanceCriteria": [{"id": "AC1", "text": "a"}, {"id": "AC2", "text": "b"}]}))
    newbase = _commit(repo, "spec grows AC2")
    rep = json.loads((repo / ".plc/report.json").read_text())
    # force a real working-tree diff (prHeadSha still points at the stale _mk head) so the
    # commit below has content to commit; _perturb_commit rebinds prHeadSha correctly after.
    rep["prHeadSha"] = "stale-placeholder"
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: report still only AC1")
    r = _run(repo, newbase, newhead)
    assert r.returncode != 0
    assert "AC ids do not equal base spec AC ids" in r.stdout


def test_spec_introducing_pr_is_process_only_na(tmp_path: Path) -> None:
    # base has NO .plc/spec.json; head introduces it (+report). R1: gate N/A, not silent pass.
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    _write(repo, "README.md", "hi\n")
    base = _commit(repo, "no spec yet")
    _write(repo, ".plc/spec.json", json.dumps(
        {"specCommit": "x", "acceptanceCriteria": [{"id": "AC1", "text": "a"}]}))
    _write(repo, "scripts/thing.sh", "#!/bin/sh\n")
    rep = {"prHeadSha": "P", "providerVendor": "claude", "providerModel": "m", "verdict": "QUALIFIED",
           "perAc": [{"id": "AC1", "verdict": "met", "evidence": ["file://scripts/thing.sh"]}], "findings": []}
    _write(repo, ".plc/report.json", json.dumps(rep))
    head = _commit(repo, "feat: introduce spec + code")
    rep["prHeadSha"] = head
    _write(repo, ".plc/report.json", json.dumps(rep))
    # NOTE (mirrors _mk): don't reassign `head` to this bind commit's own sha — a commit
    # can't self-reference its own hash inside its tree. `head` stays the "feat" commit sha,
    # which is what report.prHeadSha is bound to and what we pass to _run.
    _commit(repo, "chore: bind report")
    r = _run(repo, base, head)
    assert r.returncode == 0
    assert "N/A" in r.stdout
    assert "process-only" in r.stdout


def test_perac_missing_evidence_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["perAc"][0]["evidence"] = []
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: strip evidence")
    r = _run(repo, base, newhead)
    assert r.returncode != 0
    assert "no evidence" in r.stdout


def test_perac_bad_verdict_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["perAc"][0]["verdict"] = "looks-good"
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: bad verdict")
    r = _run(repo, base, newhead)
    assert r.returncode != 0
    assert "verdict not met/unmet" in r.stdout


def test_untyped_evidence_ref_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["perAc"][0]["evidence"] = ["looks good to me"]
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: string-gamed evidence")
    r = _run(repo, base, newhead)
    assert r.returncode != 0
    assert "not typed" in r.stdout


def test_file_evidence_missing_path_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["perAc"][0]["evidence"] = ["file://scripts/does_not_exist.sh"]
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: dangling file ref")
    r = _run(repo, base, newhead)
    assert r.returncode != 0
    assert "evidence file missing" in r.stdout


def test_perac_evidence_not_array_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["perAc"][0]["evidence"] = "file://scripts/thing.sh"
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: evidence not an array")
    r = _run(repo, base, newhead)
    assert r.returncode != 0
    assert "evidence not an array" in r.stdout


def test_test_and_hunk_refs_type_check_only(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["perAc"][0]["evidence"] = ["test://scripts/test_verify_gate.py::x", "hunk://scripts/thing.sh#L1"]
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _commit(repo, "chore: test+hunk refs")
    r = _run(repo, base, head)
    assert r.returncode == 0, r.stdout


# --- verdict-teeth: override-present-if-not-qualified (AC1, HARD CONSTRAINT) ------------------
# Block = ABSENCE of the human override artifact, never the LLM verdict value by itself.
# QUALIFIED needs no override; anything else (incl. malformed) requires a matching, non-empty
# .plc/override-<reviewedHeadSha>.json. Should-block cases bind prHeadSha via _perturb_commit
# so only the verdict-teeth check fires, and assert the check-unique "requires .plc/override"
# substring from the gate's `bad` message.


def test_not_qualified_without_override_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["verdict"] = "NOT_QUALIFIED"
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: verdict NOT_QUALIFIED")
    r = _run(repo, base, newhead)
    assert r.returncode != 0
    assert "requires .plc/override" in r.stdout


def test_malformed_verdict_requires_override(tmp_path: Path) -> None:
    # Conservative treatment: an unsupported/malformed verdict value (not QUALIFIED, not even
    # a recognized "unqualified" value) still requires a human override artifact.
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["verdict"] = "MAYBE"
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: malformed verdict")
    r = _run(repo, base, newhead)
    assert r.returncode != 0
    assert "requires .plc/override" in r.stdout


def test_override_with_empty_reason_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["verdict"] = "NOT_QUALIFIED"
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: verdict NOT_QUALIFIED")
    # override file is uncommitted — the gate reads the working tree, not git show.
    _write(repo, f".plc/override-{newhead}.json", json.dumps(
        {"reviewedHeadSha": newhead, "findings": ["x"], "reason": ""}))
    r = _run(repo, base, newhead)
    assert r.returncode != 0
    assert "requires .plc/override" in r.stdout


def test_not_qualified_with_matching_override_passes(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["verdict"] = "NOT_QUALIFIED"
    _write(repo, ".plc/report.json", json.dumps(rep))
    h = _perturb_commit(repo, "nq report")  # prHeadSha rebinds to h in the working tree
    _write(repo, f".plc/override-{h}.json", json.dumps(
        {"reviewedHeadSha": h, "findings": ["AC1 evidence weak"], "reason": "shipping behind flag; tracked X1"}))
    r = _run(repo, base, h)
    assert r.returncode == 0, r.stdout


def test_override_findings_not_array_blocks(tmp_path: Path) -> None:
    # jq `.findings | length` also accepts strings (codepoint count) and numbers (abs value),
    # so a non-array truthy `findings` must NOT satisfy the "non-empty findings[] (array)"
    # requirement — else `{"findings": "x"}` (length 1) would wrongly pass the -ge 1 check.
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["verdict"] = "NOT_QUALIFIED"
    _write(repo, ".plc/report.json", json.dumps(rep))
    h = _perturb_commit(repo, "nq report")
    _write(repo, f".plc/override-{h}.json", json.dumps(
        {"reviewedHeadSha": h, "findings": "AC1 weak", "reason": "shipping behind flag; tracked X1"}))
    r = _run(repo, base, h)
    assert r.returncode != 0
    assert "requires .plc/override" in r.stdout


def test_override_findings_empty_array_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["verdict"] = "NOT_QUALIFIED"
    _write(repo, ".plc/report.json", json.dumps(rep))
    h = _perturb_commit(repo, "nq report")
    _write(repo, f".plc/override-{h}.json", json.dumps(
        {"reviewedHeadSha": h, "findings": [], "reason": "shipping behind flag; tracked X1"}))
    r = _run(repo, base, h)
    assert r.returncode != 0
    assert "requires .plc/override" in r.stdout


def test_override_reviewed_sha_mismatch_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["verdict"] = "NOT_QUALIFIED"
    _write(repo, ".plc/report.json", json.dumps(rep))
    h = _perturb_commit(repo, "nq report")
    _write(repo, f".plc/override-{h}.json", json.dumps(
        {"reviewedHeadSha": "deadbeef" * 5, "findings": ["AC1 evidence weak"],
         "reason": "shipping behind flag; tracked X1"}))
    r = _run(repo, base, h)
    assert r.returncode != 0
    assert "requires .plc/override" in r.stdout


# --- override-only-diff bypass (AC1b, R2): resolves the SHA-staleness paradox ------------------
# A NOT_QUALIFIED report is bound (prHeadSha) to a reviewed sha X. A human then pushes ONE
# commit that adds ONLY .plc/override-<X>.json — HEAD moves to Y, but the report correctly
# still says X (nothing about the reviewed code changed). BASE here is "the point already
# gated" (mirrors an incremental re-invocation), so BASE..HEAD isolates exactly that commit —
# same self-reference constraint _mk documents: the "bind" commit records prHeadSha equal to
# its own PARENT sha (a commit can't reference its own hash inside its own tree), so `bound`
# (the bind commit, current HEAD at that point) and `x` (report.prHeadSha's value) are
# deliberately different shas one commit apart.


def test_override_only_diff_bypasses_sha_staleness(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["verdict"] = "NOT_QUALIFIED"
    _write(repo, ".plc/report.json", json.dumps(rep))
    x = _commit(repo, "chore: not-qualified report at X")
    rep["prHeadSha"] = x
    _write(repo, ".plc/report.json", json.dumps(rep))
    bound = _commit(repo, "chore: bind report to X")
    # human adds ONLY the override for X -> head moves to Y; report still (correctly) says X
    _write(repo, f".plc/override-{x}.json", json.dumps(
        {"reviewedHeadSha": x, "findings": ["AC1 weak"], "reason": "accepted; tracked"}))
    y = _commit(repo, "chore: add override only")
    r = _run(repo, bound, y)
    assert r.returncode == 0, r.stdout
    assert "override-only" in r.stdout


def test_override_plus_code_change_is_not_a_bypass(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["verdict"] = "NOT_QUALIFIED"
    _write(repo, ".plc/report.json", json.dumps(rep))
    x = _commit(repo, "chore: nq report")
    rep["prHeadSha"] = x
    _write(repo, ".plc/report.json", json.dumps(rep))
    bound = _commit(repo, "chore: bind")
    # override AND an unrelated code change in the same step -> NOT override-only
    _write(repo, f".plc/override-{x}.json", json.dumps(
        {"reviewedHeadSha": x, "findings": ["x"], "reason": "r"}))
    _write(repo, "scripts/thing.sh", "#!/bin/sh\necho changed again\n")
    y = _commit(repo, "chore: override + code")
    r = _run(repo, bound, y)
    assert r.returncode != 0  # stale report (prHeadSha=x != y) is NOT bypassed
    assert "prHeadSha" in r.stdout


# --- type guards against set -e crash on wrong-typed-but-valid-JSON artifacts (final review) --
# A bare jq command-substitution over valid-JSON-but-wrong-TYPE (or non-JSON) crashes the gate
# under set -euo pipefail: jq exits 5, pipefail propagates, script dies with a raw jq trace,
# NO structured bad()/BLOCK line, remaining checks skipped. These guards make that fail
# CLOSED-and-STRUCTURED instead of CLOSED-and-crashed.


def test_corrupt_base_spec_blocks(tmp_path: Path) -> None:
    # base .plc/spec.json exists but is not valid JSON at all (not just wrong-typed) — the base
    # spec object-type guard must catch this (git show succeeds; jq parse/type check fails).
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    _write(repo, "README.md", "hi\n")
    _write(repo, ".plc/spec.json", "THIS IS NOT JSON {{{")
    _write(repo, "scripts/thing.sh", "#!/bin/sh\necho hi\n")
    base = _commit(repo, "corrupt spec on base")

    report = {
        "prHeadSha": "PLACEHOLDER", "providerVendor": "claude", "providerModel": "opus-4-8",
        "verdict": "QUALIFIED",
        "perAc": [{"id": "AC1", "verdict": "met", "evidence": ["file://scripts/thing.sh"]}],
        "findings": [],
    }
    _write(repo, ".plc/report.json", json.dumps(report))
    head = _commit(repo, "feat: report over corrupt base spec")
    report["prHeadSha"] = head
    _write(repo, ".plc/report.json", json.dumps(report))
    _commit(repo, "chore: bind report to head")

    r = _run(repo, base, head)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "not a JSON object" in r.stdout
    assert "verify-gate BLOCK" in r.stdout  # reached the normal tail — did not crash mid-script


def test_non_object_report_blocks(tmp_path: Path) -> None:
    # report.json is valid JSON but a top-level ARRAY, not an object. jq -e . would pass (any
    # truthy JSON); the object-type guard must catch this before any `.field` read is attempted.
    repo, base, head = _mk(tmp_path)
    _write(repo, ".plc/report.json", json.dumps([1, 2, 3]))
    newhead = _commit(repo, "chore: report is a JSON array")  # no prHeadSha field to rebind
    r = _run(repo, base, newhead)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "report.json is not a JSON object" in r.stdout
    assert "verify-gate BLOCK" in r.stdout


def test_non_array_perac_blocks(tmp_path: Path) -> None:
    # report is a valid object but perAc is a number, not an array. The perAc array-type guard
    # must fire before `.perAc | length` / `.perAc[i]` reads are attempted.
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["perAc"] = 5
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: perAc not an array")
    r = _run(repo, base, newhead)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "perAc is not an array" in r.stdout
    assert "verify-gate BLOCK" in r.stdout


def test_zero_ac_spec_records_na(tmp_path: Path) -> None:
    # base spec is a valid object with acceptanceCriteria: [] — must record N/A, not block.
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    _write(repo, "README.md", "hi\n")
    _write(repo, ".plc/spec.json", json.dumps({"specCommit": "x", "acceptanceCriteria": []}))
    _write(repo, "scripts/thing.sh", "#!/bin/sh\necho hi\n")
    base = _commit(repo, "spec with zero acceptance criteria")

    report = {
        "prHeadSha": "PLACEHOLDER", "providerVendor": "claude", "providerModel": "opus-4-8",
        "verdict": "QUALIFIED", "perAc": [], "findings": [],
    }
    _write(repo, ".plc/report.json", json.dumps(report))
    head = _commit(repo, "feat: report with no ACs to cover")
    report["prHeadSha"] = head
    _write(repo, ".plc/report.json", json.dumps(report))
    _commit(repo, "chore: bind report to head")

    r = _run(repo, base, head)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "N/A" in r.stdout
    assert "no acceptance criteria" in r.stdout


def test_perac_array_of_non_objects_blocks(tmp_path: Path) -> None:
    # perAc passes both prior guards (REPORT_IS_OBJECT, perAc type=="array") but its element
    # is a non-object (a number) — `.id`/`.verdict` field access on that element must not crash.
    repo, base, head = _mk(tmp_path)
    rep = json.loads((repo / ".plc/report.json").read_text())
    rep["perAc"] = [5]
    _write(repo, ".plc/report.json", json.dumps(rep))
    newhead = _perturb_commit(repo, "chore: perAc array of non-objects")
    r = _run(repo, base, newhead)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "verdict not met/unmet" in r.stdout
    assert "verify-gate BLOCK" in r.stdout


def test_base_spec_malformed_ac_elements_blocks(tmp_path: Path) -> None:
    # base spec is a valid object; acceptanceCriteria is a non-empty array of NON-objects
    # (e.g. [5]) — extracting no ids from a non-empty array must BLOCK (malformed spec), not
    # silently N/A like a legitimately-empty acceptanceCriteria: [] does.
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    _write(repo, "README.md", "hi\n")
    _write(repo, ".plc/spec.json", json.dumps({"specCommit": "x", "acceptanceCriteria": [5]}))
    _write(repo, "scripts/thing.sh", "#!/bin/sh\necho hi\n")
    base = _commit(repo, "malformed acceptanceCriteria elements on base")

    report = {
        "prHeadSha": "PLACEHOLDER", "providerVendor": "claude", "providerModel": "opus-4-8",
        "verdict": "QUALIFIED",
        "perAc": [{"id": "AC1", "verdict": "met", "evidence": ["file://scripts/thing.sh"]}],
        "findings": [],
    }
    _write(repo, ".plc/report.json", json.dumps(report))
    head = _commit(repo, "feat: report over malformed base spec")
    report["prHeadSha"] = head
    _write(repo, ".plc/report.json", json.dumps(report))
    _commit(repo, "chore: bind report to head")

    r = _run(repo, base, head)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "none carry an id" in r.stdout
    assert "verify-gate BLOCK" in r.stdout


# --- jq-only envelope lock (AC7) ------------------------------------------------------------
# Regression guard: locks the gate's envelope (bash + git + jq + coreutils) so a future edit
# that reaches for python3/node/npx fails this test instead of silently widening the gate's
# dependency footprint. Only WHOLE-LINE comments (`^\s*#`) are dropped before scanning — the
# gate's own prose about staying jq-only (e.g. its header) legitimately mentions these tokens
# without using them, and a naive substring scan on raw source would false-positive on that
# prose. Trailing/inline `#...` is deliberately left in place: stripping from any space-preceded
# `#` (an earlier version of this test did that) is quote-unaware and would swallow real code
# after a `#` that appears inside a string literal earlier on the same line — e.g.
# `echo "use # to skip" && python3 evil.py` would have `&& python3 evil.py` erased along with
# the string's `#`, producing a false negative on an actual violation. Whole-line-only stripping
# closes that gap while still passing the gate's real whole-line comments and leaving bash's
# `${REF#file://}` parameter expansion (never at start of line) untouched.


def test_gate_is_jq_only_no_python_or_node() -> None:
    src = GATE.read_text(encoding="utf-8")
    code_only = "\n".join(
        "" if re.match(r"^\s*#", line) else line for line in src.splitlines()
    )
    for banned in ("python3", "python ", "node ", "\tnode", "npx "):
        assert banned not in code_only, f"verify-gate.sh must stay jq-only; found: {banned!r}"
    # jq must actually be the tool doing JSON work
    assert "jq " in code_only


# ============================ AC3 — guard potency ============================
# The gate READS diff-guards.json (routed guards, produced by diff-guards.sh) +
# guard-manifest.json (author bindings) + potency-result.json (produced by potency-runner.sh).
# It does NOT re-derive "added" — that is the out-of-envelope producer's job. These tests drive
# the gate's AC3 block against hand-written artifacts; the producers have their own unit tests.

def _hash_object(repo: Path, rel: str) -> str:
    return subprocess.run(["git", "hash-object", rel], cwd=repo,
                          check=True, capture_output=True, text=True).stdout.strip()


def _add_guards(repo: Path, head: str, *, guards: list, manifest: list,
                potency: dict | None = None, potency_head: str | None = None,
                potency_mhash: str | None = None) -> None:
    """Write AC3 artifacts into a valid _mk() repo's working tree, bound to `head`. potency=None
    means 'no potency-result.json file'. Fields default to the consistent (fresh) values so a
    test perturbs only the one it targets."""
    _write(repo, ".plc/diff-guards.json",
           json.dumps({"base": "x", "head": head, "guards": guards}))
    _write(repo, ".plc/guard-manifest.json", json.dumps(manifest))
    mh = potency_mhash if potency_mhash is not None else _hash_object(repo, ".plc/guard-manifest.json")
    if potency is not None:
        potency.setdefault("prHeadSha", potency_head if potency_head is not None else head)
        potency.setdefault("manifestHash", mh)
        potency.setdefault("runId", "r1")
        _write(repo, ".plc/potency-result.json", json.dumps(potency))


def _fixture_entry(gid: str) -> dict:
    return {"guardId": gid, "file": "scripts/thing.sh", "line": 2,
            "firingFixture": "true"}


def test_ac3_routed_guard_without_manifest_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    _add_guards(repo, head, guards=[{"guardId": "scripts/thing.sh:2", "file": "scripts/thing.sh",
                                     "line": 2, "kind": "throw"}], manifest=[])
    r = _run(repo, base, head)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "no .plc/guard-manifest.json entry" in r.stdout


def test_ac3_fixture_bound_potent_guard_passes(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    gid = "scripts/thing.sh:2"
    _add_guards(repo, head, guards=[{"guardId": gid, "kind": "throw"}],
                manifest=[_fixture_entry(gid)],
                potency={"perGuard": [{"guardId": gid, "fixtureResult": "passed",
                                       "neuterResult": "failed"}]})
    r = _run(repo, base, head)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "potent" in r.stdout


def test_ac3_impotent_guard_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    gid = "scripts/thing.sh:2"
    _add_guards(repo, head, guards=[{"guardId": gid, "kind": "throw"}],
                manifest=[_fixture_entry(gid)],
                potency={"perGuard": [{"guardId": gid, "fixtureResult": "passed",
                                       "neuterResult": "passed"}]})  # neuter did NOT break it
    r = _run(repo, base, head)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "impotent" in r.stdout


def test_ac3_missing_potency_coverage_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    gid = "scripts/thing.sh:2"
    _add_guards(repo, head, guards=[{"guardId": gid, "kind": "throw"}],
                manifest=[_fixture_entry(gid)],
                potency={"perGuard": []})  # routed fixture guard absent from potency-result
    r = _run(repo, base, head)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "missing from potency-result" in r.stdout


def test_ac3_valid_waiver_passes(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    gid = "scripts/thing.sh:2"
    _add_guards(repo, head, guards=[{"guardId": gid, "kind": "throw"}],
                manifest=[{"guardId": gid, "waiver": {"reason": "vendored third-party guard",
                                                      "waivedBy": "maintainer"}}])
    r = _run(repo, base, head)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "waived" in r.stdout


def test_ac3_empty_waiver_reason_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    gid = "scripts/thing.sh:2"
    _add_guards(repo, head, guards=[{"guardId": gid, "kind": "throw"}],
                manifest=[{"guardId": gid, "waiver": {"reason": "", "waivedBy": "maintainer"}}])
    r = _run(repo, base, head)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "neither a fixture binding nor a valid waiver" in r.stdout


def test_ac3_no_guards_is_na(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    _add_guards(repo, head, guards=[], manifest=[])
    r = _run(repo, base, head)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no guards added this PR" in r.stdout


def test_ac3_stale_potency_manifest_hash_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    gid = "scripts/thing.sh:2"
    _add_guards(repo, head, guards=[{"guardId": gid, "kind": "throw"}],
                manifest=[_fixture_entry(gid)],
                potency={"perGuard": [{"guardId": gid, "fixtureResult": "passed",
                                       "neuterResult": "failed"}]},
                potency_mhash="deadbeef")  # hash does not match current manifest
    r = _run(repo, base, head)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "manifestHash stale" in r.stdout


def test_ac3_stale_potency_sha_blocks(tmp_path: Path) -> None:
    repo, base, head = _mk(tmp_path)
    gid = "scripts/thing.sh:2"
    _add_guards(repo, head, guards=[{"guardId": gid, "kind": "throw"}],
                manifest=[_fixture_entry(gid)],
                potency={"perGuard": [{"guardId": gid, "fixtureResult": "passed",
                                       "neuterResult": "failed"}]},
                potency_head="deadbeef" * 5)  # potency bound to a different sha
    r = _run(repo, base, head)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "prHeadSha" in r.stdout


def test_ac3_always_failing_fixture_blocks(tmp_path: Path) -> None:
    # AC3.5 is a DELTA: an always-failing fixture (fixtureResult=failed) bound to a dead guard
    # must NOT pass as potent just because its neutered run also failed — no flip is proven.
    repo, base, head = _mk(tmp_path)
    gid = "scripts/thing.sh:2"
    _add_guards(repo, head, guards=[{"guardId": gid, "kind": "throw"}],
                manifest=[_fixture_entry(gid)],
                potency={"perGuard": [{"guardId": gid, "fixtureResult": "failed",
                                       "neuterResult": "failed"}]})
    r = _run(repo, base, head)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "impotent" in r.stdout


def test_ac3_nonobject_guard_element_fails_closed(tmp_path: Path) -> None:
    # HIGH-2: a corrupt diff-guards.json whose .guards holds a non-object must fail CLOSED with a
    # message, never crash the gate under set -e with a raw jq trace.
    repo, base, head = _mk(tmp_path)
    _write(repo, ".plc/diff-guards.json",
           json.dumps({"base": "x", "head": head, "guards": ["not-an-object"]}))
    r = _run(repo, base, head)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "non-object element" in r.stdout
    assert "verify-gate BLOCK" in r.stdout


def test_ac3_nonobject_manifest_element_fails_closed(tmp_path: Path) -> None:
    # HIGH-2: a manifest array holding a non-object must not crash the select(.guardId) read.
    repo, base, head = _mk(tmp_path)
    _add_guards(repo, head, guards=[{"guardId": "scripts/thing.sh:2", "kind": "throw"}],
                manifest=["oops-not-an-object"])
    r = _run(repo, base, head)
    assert r.returncode == 1, r.stdout + r.stderr
    # manifest not a valid array-of-objects → treated as no entry → routed-guard block
    assert "no .plc/guard-manifest.json entry" in r.stdout
    assert "verify-gate BLOCK" in r.stdout


def test_ac3_guardid_with_space_in_path_passes(tmp_path: Path) -> None:
    # MED-1: a guardId whose file part contains a space must still match its potency entry (no
    # word-split false-positive "missing from potency-result").
    repo, base, head = _mk(tmp_path)
    gid = "my dir/thing.sh:2"
    ent = {"guardId": gid, "file": "my dir/thing.sh", "line": 2, "firingFixture": "true"}
    _add_guards(repo, head, guards=[{"guardId": gid, "kind": "throw"}], manifest=[ent],
                potency={"perGuard": [{"guardId": gid, "fixtureResult": "passed",
                                       "neuterResult": "failed"}]})
    r = _run(repo, base, head)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "potent" in r.stdout
