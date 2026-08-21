"""The stage registry as data, and the invariant that keeps its bindings honest.

The registry is the reader's denominator: "every registry stage gets exactly one row in every run",
so `len(stages)` has to mean something. Two things can quietly make it meaningless — a binding that
points at a variable nobody kept, and a registry that parses while declaring nothing — and both are
failures here rather than silent passes.

The obvious mutant is "rename one gate-check identifier -> invariant red". Building it found
a defect in the invariant itself, which is why there are two: `grep -F RUN_JOURNAL` still matches
`RUN_JOURNAL_RENAMED`, so the FIRST version of the checker reported nothing when its own probe
renamed that way. Half of all renames extend the old name.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
INVARIANT = Path(os.environ.get("PLC_STAGE_REGISTRY_IMPL", SCRIPTS / "invariants/stage-registry-bindings.sh"))
REGISTRY = ROOT / ".claude/stage-registry.json"
GATE = SCRIPTS / "close-gate.sh"

# The stage table. Written out here rather than read from the registry: a test that reads its
# expectation out of its subject cannot notice a stage going missing.
EXPECTED_STAGES = {
    "intent_gate", "qa_log", "user_story", "spec", "crosscheck_a", "plan", "crosscheck_b",
    "journal", "test_evidence", "invariants", "product_diff", "close_gate_task",
    "cross_family_review", "smoke", "changelog", "spec_doc", "plan_doc", "roadmap_row",
    "independent_review", "close_gate_phase",
}


def _run(registry: Path, gate: Path, impl: Path = INVARIANT):
    return subprocess.run(
        ["/bin/bash", str(impl), str(registry), str(gate)],
        capture_output=True, text=True, check=False,
    )


def _registry() -> dict:
    return json.loads(REGISTRY.read_text())


def _write(tmp_path: Path, data: dict, name: str = "registry.json") -> Path:
    target = tmp_path / name
    target.write_text(json.dumps(data, indent=2))
    return target


def _gate_copy(tmp_path: Path, old: str, new: str, name: str = "gate.sh") -> Path:
    text = GATE.read_text()
    assert old in text, f"{old!r} is not in close-gate.sh — this fixture is stale"
    target = tmp_path / name
    target.write_text(text.replace(old, new))
    return target


# ---------------------------------------------------------------------------
# The registry itself
# ---------------------------------------------------------------------------
def test_registry_declares_exactly_the_stages_the_spec_named(tmp_path: Path) -> None:
    stages = {s["stage_id"] for s in _registry()["stages"]}
    assert stages == EXPECTED_STAGES, f"missing {EXPECTED_STAGES - stages}, unexpected {stages - EXPECTED_STAGES}"


def test_no_binding_names_a_check_number(tmp_path: Path) -> None:
    """The registry binds to identifiers, never to ordinal positions. A binding like `5` or
    `check5` would still be found in close-gate.sh by any matcher and would rot the moment the gate
    renumbers — which it has done twice (9 after the 1..8 table, then 9b after 9)."""
    for stage in _registry()["stages"]:
        binding = stage["gate_check"]
        if binding is None:
            continue
        assert not any(ch.isdigit() for ch in binding), (
            f"{stage['stage_id']} binds {binding!r}, which carries a number"
        )
        assert binding.isupper() or "_" in binding, f"{stage['stage_id']} binds {binding!r}"


def test_every_stage_with_a_deterministic_writer_binds_or_says_why(tmp_path: Path) -> None:
    """The `none` rows are the point of the registry — they are exactly the stages that can
    silently not happen. This asserts they are declared as null rather than omitted, because an
    omitted field and a null one read the same to a careless jq filter and only one of them is a
    decision."""
    for stage in _registry()["stages"]:
        assert "writer" in stage and "gate_check" in stage, stage["stage_id"]
    unwritten = [s["stage_id"] for s in _registry()["stages"] if s["writer"] is None]
    assert unwritten, "a registry where every stage has a writer is not describing this repo"


def test_available_from_is_dated_and_its_provenance_is_stated(tmp_path: Path) -> None:
    for stage in _registry()["stages"]:
        date = stage["available_from"]
        assert len(date) == 10 and date[4] == date[7] == "-", f"{stage['stage_id']}: {date}"
        basis = stage["available_from_basis"]
        assert basis, stage["stage_id"]
        assert basis == "repo-start" or basis.startswith("measured:"), (
            f"{stage['stage_id']}: basis must be `repo-start` or `measured: <how>`, got {basis!r}"
        )
    # cross_family_review is dated by its script: review evidence cannot exist before the script
    # does, whenever a repo arms `second-agent-family`.
    cfr = next(s for s in _registry()["stages"] if s["stage_id"] == "cross_family_review")
    assert cfr["available_from"] == "2026-07-24", cfr


def test_the_real_registry_and_the_real_gate_agree(tmp_path: Path) -> None:
    result = _run(REGISTRY, GATE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "self-coverage confirmed" in result.stdout


# ---------------------------------------------------------------------------
# The rename mutant, in both rename shapes
# ---------------------------------------------------------------------------
def test_a_renamed_gate_identifier_reds_the_invariant(tmp_path: Path) -> None:
    gate = _gate_copy(tmp_path, "RUN_JOURNAL", "PLANTED_GONE")
    result = _run(REGISTRY, gate)
    assert result.returncode != 0, result.stdout
    assert "gate_check RUN_JOURNAL is bound by the registry" in result.stdout


def test_a_gate_identifier_renamed_by_EXTENSION_also_reds(tmp_path: Path) -> None:
    """The half a substring matcher cannot see. This is not hypothetical: the first version of the
    invariant used `grep -F` and its own self-coverage probe renamed exactly this way, so the check
    reported nothing and the probe is what caught it."""
    gate = _gate_copy(tmp_path, "RUN_JOURNAL", "RUN_JOURNAL_RENAMED", name="extended.sh")
    result = _run(REGISTRY, gate)
    assert result.returncode != 0, result.stdout
    assert "gate_check RUN_JOURNAL is bound by the registry" in result.stdout


def test_mutant_substring_matcher_fails_its_own_self_coverage(tmp_path: Path) -> None:
    """And the mutant on the fix. Put `grep -qF` back and the invariant must refuse to pass at all
    — not because a binding is broken, but because it can no longer show that it could notice."""
    text = INVARIANT.read_text()
    old = '    grep -qE "(^|[^A-Za-z0-9_])${id}([^A-Za-z0-9_]|\\$)" "$gate" ||'
    assert text.count(old) == 1, "mutation target is stale"
    mutant = tmp_path / "substring.sh"
    mutant.write_text(text.replace(old, '    grep -qF -- "$id" "$gate" ||'))
    result = _run(REGISTRY, GATE, impl=mutant)
    assert result.returncode != 0, result.stdout
    assert "self-coverage FAILED" in result.stdout


# ---------------------------------------------------------------------------
# Shape failures — each one is a way the denominator could go quietly wrong
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda d: d.update(stages=[]), "declares no stages"),
        (lambda d: d["stages"].append(dict(d["stages"][0])), "duplicate stage_id"),
        (lambda d: d["stages"][0].pop("mandated_when"), "no mandated_when"),
        (lambda d: d["stages"][0].pop("writer"), "no writer field"),
        (lambda d: d["stages"][0].pop("gate_check"), "no gate_check field"),
        (lambda d: d["stages"][0].update(available_from="July"), "available_from must be YYYY-MM-DD"),
        (lambda d: d["stages"][0].update(available_from_basis=""), "available_from_basis is empty"),
        (
            lambda d: [s.update(gate_check=None) for s in d["stages"]],
            "no stage binds a gate_check",
        ),
        (
            lambda d: d["stages"][7].update(gate_check="RUN.*"),
            "is not a shell identifier",
        ),
    ],
)
def test_a_malformed_registry_is_a_failure_not_a_vacuous_pass(tmp_path, mutate, expected) -> None:
    data = _registry()
    mutate(data)
    registry = _write(tmp_path, data)
    result = _run(registry, GATE)
    assert result.returncode != 0, f"accepted: {result.stdout}"
    assert expected in result.stdout, result.stdout


def test_an_unreadable_registry_is_reported_rather_than_skipped(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    result = _run(missing, GATE)
    assert result.returncode != 0
    assert "unreadable" in result.stdout

    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    result = _run(broken, GATE)
    assert result.returncode != 0
    assert "not valid JSON" in result.stdout


def test_the_invariant_is_declared_in_the_gate_manifest() -> None:
    """A checker nothing runs is the same shape as a guard that never checks."""
    manifest = json.loads((ROOT / ".claude/close-gate.json").read_text())
    names = {i["name"] for i in manifest["invariants"]}
    assert "stage-registry-bindings" in names, sorted(names)
