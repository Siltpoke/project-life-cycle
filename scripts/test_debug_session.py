"""AC suite M5 behavior-locked debugging session.

The find-bug/audit entry is a debugging SESSION you enter when stuck, not a
proactive bug-scan. references/debug-session.md threads two things diagnose-loop lacks onto the existing
8-phase debug discipline: (1) lock the NEIGHBORS first -- seed PRESERVE rows via M1 behavior-lock.sh +
behavior-baseline.sh for the behaviors around the bug that currently pass, so the fix is proven not to
regress them; (2) tier incidental findings via findings-tier.md. The bug itself is a FIX row (fail->pass).
Entry is an intent-gate OFFER on a bug problem-class (offer-first, never auto-start). No new script, no
new guard: the seeded rows are watched by M1's behavior-lock-carriers-resolve invariant.

This suite exercises the documented command path on a fixture repo, and pins the doc contract so the
session's shape (and the gate's offer-not-auto) cannot silently drift.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside README* / CHANGELOG.md /
GUIDE*.

The correctness case (test_AC3...) breaks a locked neighbor and REQUIRES the carrier-resolve invariant go
red -- a guard that cannot fail on its own target is vacuous.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCK = REPO / "scripts" / "behavior-lock.sh"
BASELINE = REPO / "scripts" / "behavior-baseline.sh"
INV = REPO / "scripts" / "invariants" / "behavior-lock-carriers-resolve.sh"
REFS = REPO / "skills" / "project-lifecycle" / "references"
DEBUG_SESSION_MD = REFS / "debug-session.md"
INTENT_GATE_MD = REFS / "intent-gate.md"
SKILL_MD = REPO / "skills" / "project-lifecycle" / "SKILL.md"

LOCK_HEADER = "# id\tclass\tbehavior\tcarrier\twhy\n"


# --------------------------------------------------------------------------------------------
# helpers -- a repo mid-debug: it has tests for the neighbors and a failing repro for the bug
# --------------------------------------------------------------------------------------------

def repo_with_bug(tmp_path: Path) -> Path:
    (tmp_path / ".claude").mkdir()
    # a neighbor behavior that currently passes (must stay pass->pass through the fix)
    # and a repro for the bug under investigation (its carrier exists so the FIX row resolves)
    (tmp_path / "test_orders.py").write_text(
        "def test_total_includes_tax():\n    assert 1 + 1 == 2\n"
        "def test_discount_repro():\n    assert True\n",
        encoding="utf-8",
    )
    return tmp_path


def seed_row(repo: Path, id_: str, cls: str, behavior: str, carrier: str, why: str) -> None:
    reg = repo / ".claude" / "behavior-lock.tsv"
    if not reg.exists():
        reg.write_text(LOCK_HEADER, encoding="utf-8")
    with reg.open("a", encoding="utf-8") as fh:
        fh.write("\t".join([id_, cls, behavior, carrier, why]) + "\n")


def resolves(repo: Path, carrier: str) -> bool:
    r = subprocess.run(
        ["/bin/bash", str(LOCK), "--resolve", carrier, str(repo)],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def _baseline_env(repo: Path) -> dict:
    return {**os.environ,
            "PLC_BEHAVIOR_BASELINE": str(repo / ".claude" / "behavior-baseline.tsv"),
            "PLC_BEHAVIOR_LOCK": str(repo / ".claude" / "behavior-lock.tsv")}


def record_baseline(repo: Path, id_: str, state: str, exit_code: str, cmd: str, env: str):
    return subprocess.run(
        ["/bin/bash", str(BASELINE), "--record", id_, state, exit_code, cmd, env],
        capture_output=True, text=True, env=_baseline_env(repo),
    )


def check_transition(repo: Path, id_: str, cls: str = "") -> subprocess.CompletedProcess:
    argv = ["/bin/bash", str(BASELINE), "--check-transition", id_]
    if cls:
        argv.append(cls)
    return subprocess.run(argv, capture_output=True, text=True, env=_baseline_env(repo))


def carriers_resolve(repo: Path) -> subprocess.CompletedProcess:
    empty_base = repo / ".claude" / ".empty-base"
    empty_base.write_text("", encoding="utf-8")
    return subprocess.run(
        ["/bin/bash", str(INV)],
        capture_output=True, text=True, cwd=REPO,
        env={**os.environ,
             "PLC_BEHAVIOR_LOCK": str(repo / ".claude" / "behavior-lock.tsv"),
             "PLC_BEHAVIOR_LOCK_ROOT": str(repo),
             "PLC_BEHAVIOR_LOCK_BASE": str(empty_base)},
    )


# --------------------------------------------------------------------------------------------
# AC1 -- the doc contract: the session, its four steps, and the gate's offer-not-auto
# --------------------------------------------------------------------------------------------

def test_AC1_debug_session_is_documented_as_commands_over_existing_pieces():
    text = DEBUG_SESSION_MD.read_text(encoding="utf-8")
    # step 1: lock the NEIGHBORS, and BEFORE the diagnose loop -- the ordering is the whole point
    assert "Lock the neighbors" in text, "step 1 must document locking the surrounding behaviors first"
    assert "before you poke" in text, "the neighbor lock must come BEFORE the diagnose loop"
    # points INTO the reused pieces (reuse, not restate)
    assert "behavior-lock.sh" in text and "behavior-baseline.sh" in text, (
        "the lock step must be documented as commands over the two M1 scripts"
    )
    assert "diagnose-loop.md" in text, "root-cause must point at diagnose-loop, not restate its 8 phases"
    assert "findings-tier.md" in text, "incidental findings must route to findings-tier"
    assert "no new script" in text, "the session must state it adds no new script"
    # the bug is a FIX row (before = failing = non-zero); neighbors are PRESERVE
    assert "FIX" in text and "PRESERVE" in text, "the bug is a FIX row, neighbors are PRESERVE rows"
    assert "non-zero" in text, "the FIX row's `before` baseline must be documented as the failing exit"
    # step 4: the prove command AND the honest boundary -- the doc must NOT over-claim that
    # carrier-resolve catches a still-present-but-failing neighbor (review HIGH). carrier-resolve gates
    # EXISTENCE (removed/renamed); the pass->fail check is agent-run, not wired into any gate.
    assert "--check-transition" in text, "the prove step must document the transition-check command"
    assert "removed or renamed" in text, (
        "carrier-resolve's gated guarantee is carrier EXISTENCE (removed/renamed), not green-ness"
    )
    assert "not wired into any gate" in text, (
        "the doc must state the pass->fail check is agent-run, NOT a gate -- no over-claim"
    )


def test_AC1_gate_offer_is_documented_offer_not_auto():
    # The offer lives in SKILL.md's front-door bug handling + debug-session.md -- NOT in the
    # `mode: detailed`-frozen intent-gate.md (the [B] design call: editing the frozen gate file would
    # force a mode-baseline bump; SKILL.md, which the agent reads, specifies the gate's behavior just as
    # well). So the assertions target where the offer actually lives.
    skill = SKILL_MD.read_text(encoding="utf-8")
    assert "behavior-locked debug session" in skill, "SKILL.md's bug seam must offer the session"
    assert "offer-not-auto" in skill, "the offer must be documented as offer-not-auto-start"
    ds = DEBUG_SESSION_MD.read_text(encoding="utf-8")
    assert "never auto-starts it" in ds, (
        "debug-session.md must state the gate offers the session and never auto-starts it"
    )


def test_AC1_skill_md_registers_the_reference():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "references/debug-session.md" in text, (
        "SKILL.md must name references/debug-session.md (validate.py check #6 + discoverability)"
    )
    # pin the two bug-SEAM edits, not just the filename -- the filename also appears in the reference
    # index line, so a filename-only check passes even if both seams are reverted (review finding).
    assert "run the loop inside the" in text, "the execute-step bug seam must offer the session"
    # the situation->action quick-reference was relocated: quick-reference TABLE out of the always-injected SKILL.md
    # into references/quick-reference.md (load-on-demand). The 'Bug appears mid-phase' row -- a routing
    # index into the two always-injected seams, which remain in SKILL.md -- moved with the table. The
    # behavioral offer is still guaranteed by the two seams asserted against SKILL.md above; this third
    # assertion tracks the row to its new home rather than dropping it, keeping the seam pinned.
    quick_ref = (REFS / "quick-reference.md").read_text(encoding="utf-8")
    assert "On a gate-flagged bug the user accepted" in quick_ref, (
        "the 'Bug appears mid-phase' quick-reference row must offer the session "
        "(relocated to references/quick-reference.md)"
    )


# --------------------------------------------------------------------------------------------
# AC2 -- the transitions: a FIX bug fail->pass and a PRESERVE neighbor pass->pass, both accepted
# --------------------------------------------------------------------------------------------

def test_AC2_fix_fail_to_pass_and_neighbor_pass_to_pass(tmp_path):
    repo = repo_with_bug(tmp_path)
    neighbor = "test_orders.py::test_total_includes_tax"
    bug = "test_orders.py::test_discount_repro"
    assert resolves(repo, neighbor) and resolves(repo, bug), "both carriers must resolve"

    # lock the neighbor (PRESERVE, before 0) and the bug (FIX, before = fail = non-zero)
    seed_row(repo, "BL-1", "PRESERVE", "order total includes tax", neighbor, "neighbor of the bug")
    seed_row(repo, "BL-2", "FIX", "discount applies once", bug, "the bug under investigation")
    assert record_baseline(repo, "BL-1", "before", "0", "pytest " + neighbor, "py3").returncode == 0
    assert record_baseline(repo, "BL-2", "before", "1", "pytest " + bug, "py3").returncode == 0

    # after the fix: both pass
    record_baseline(repo, "BL-1", "after", "0", "pytest " + neighbor, "py3")
    record_baseline(repo, "BL-2", "after", "0", "pytest " + bug, "py3")

    fix = check_transition(repo, "BL-2", "FIX")
    assert fix.returncode == 0, "a FIX row that went fail->pass must be accepted\n" + fix.stdout + fix.stderr
    pres = check_transition(repo, "BL-1", "PRESERVE")
    assert pres.returncode == 0, "the PRESERVE neighbor must be pass->pass\n" + pres.stdout + pres.stderr

    inv = carriers_resolve(repo)
    assert inv.returncode == 0, inv.stdout + inv.stderr


# --------------------------------------------------------------------------------------------
# AC3 -- the correctness property + proof bar: a fix that breaks a locked neighbor goes red
# --------------------------------------------------------------------------------------------

def test_AC3_fix_breaking_a_locked_neighbor_reds_then_revert_greens(tmp_path):
    repo = repo_with_bug(tmp_path)
    neighbor = "test_orders.py::test_total_includes_tax"
    control = "test_orders.py::test_discount_repro"  # an untouched neighbor -- negative control
    seed_row(repo, "BL-1", "PRESERVE", "order total includes tax", neighbor, "neighbor of the bug")
    seed_row(repo, "BL-3", "PRESERVE", "discount repro present", control, "untouched control")
    record_baseline(repo, "BL-1", "before", "0", "pytest " + neighbor, "py3")
    assert carriers_resolve(repo).returncode == 0

    # the fix "breaks" the neighbor: its carrier is renamed away (control carrier stays)
    (repo / "test_orders.py").write_text(
        "def test_renamed_away():\n    assert True\n"
        "def test_discount_repro():\n    assert True\n",
        encoding="utf-8",
    )
    red = carriers_resolve(repo)
    assert red.returncode == 1, "breaking a locked neighbor's carrier must red\n" + red.stdout + red.stderr
    assert "BL-1" in red.stdout
    assert "BL-3" not in red.stdout, "the untouched control neighbor must NOT red (negative control)"

    # baseline-level detection too: the neighbor is no longer pass->pass
    record_baseline(repo, "BL-1", "after", "1", "pytest " + neighbor, "py3")
    assert check_transition(repo, "BL-1", "PRESERVE").returncode == 1, (
        "a PRESERVE neighbor that went pass->fail must be flagged"
    )

    # revert -> green again
    (repo / "test_orders.py").write_text(
        "def test_total_includes_tax():\n    assert 1 + 1 == 2\n"
        "def test_discount_repro():\n    assert True\n",
        encoding="utf-8",
    )
    assert carriers_resolve(repo).returncode == 0


# --------------------------------------------------------------------------------------------
# AC4 -- incidental findings route to findings-tier; an untested neighbor is a gap, not a row
# --------------------------------------------------------------------------------------------

def test_AC4_incidental_findings_route_to_tiers_and_untested_neighbor_is_a_gap(tmp_path):
    text = DEBUG_SESSION_MD.read_text(encoding="utf-8")
    # the tiers are reused by pointer, not restated -- the S1/S2/S3 vocabulary lives in findings-tier.md
    assert "S1" in text and "S2" in text and "S3" in text, (
        "incidental findings must be tiered S1/S2/S3 (pointing at findings-tier.md)"
    )
    assert "Coverage gap" in text, (
        "a neighbor with no resolving carrier must route to a Coverage gap, never a dangling row"
    )

    # and the rule holds mechanically on a fixture: an untested neighbor seeded as a row would red
    repo = repo_with_bug(tmp_path)
    untested = "payments.py::refund_is_idempotent"
    assert not resolves(repo, untested), "an untested neighbor's carrier must NOT resolve"
    seed_row(repo, "BL-9", "PRESERVE", "refund idempotent", untested, "WRONGLY seeded untested neighbor")
    bad = carriers_resolve(repo)
    assert bad.returncode == 1 and "BL-9" in bad.stdout, "a dangling neighbor row reds -- why it is a gap"
