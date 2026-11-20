"""AC suite M5 brownfield behavior-baseline on intake.

The archaeology brownfield pass (references/archaeology.md) gains a seventh artifact: a behavior
baseline. On intake of an existing repo the documented step seeds PRESERVE rows into
.claude/behavior-lock.tsv for ONLY the critical surfaces whose carrier resolves, records a `before`
baseline via scripts/behavior-baseline.sh, and routes critical surfaces with no resolving carrier to
the adoption-snapshot "Coverage gaps" (never a row). No new script: the step is documented commands
over the existing behavior-lock.sh + behavior-baseline.sh, and the seeded rows are watched by M1's
behavior-lock-carriers-resolve invariant.

This suite exercises that documented command path on a fixture brownfield repo, and pins the doc
contract so the Artifact-set table cannot silently drift back to six.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
README* / CHANGELOG.md / GUIDE*.

The self-coverage case (test_AC4...) plants a dangling carrier and REQUIRES the carrier-resolve
invariant go red -- a guard that cannot fail on its own target is vacuous.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCK = REPO / "scripts" / "behavior-lock.sh"
BASELINE = REPO / "scripts" / "behavior-baseline.sh"
INV = REPO / "scripts" / "invariants" / "behavior-lock-carriers-resolve.sh"
ARCHAEOLOGY_MD = REPO / "skills" / "project-lifecycle" / "references" / "archaeology.md"

LOCK_HEADER = "# id\tclass\tbehavior\tcarrier\twhy\n"


# --------------------------------------------------------------------------------------------
# helpers -- model a brownfield intake: a repo dir with a .claude/ the pass writes drafts into
# --------------------------------------------------------------------------------------------

def brownfield(tmp_path: Path) -> Path:
    """An existing repo that is adopting PLC: it already has a test suite, no .claude registry yet."""
    (tmp_path / ".claude").mkdir()
    # a critical behavior the repo already proves with a test
    (tmp_path / "test_orders.py").write_text(
        "def test_total_includes_tax():\n    assert 1 + 1 == 2\n", encoding="utf-8"
    )
    return tmp_path


def seed_row(repo: Path, id_: str, behavior: str, carrier: str, why: str) -> None:
    """The documented step: append a PRESERVE row to the adopted repo's registry."""
    reg = repo / ".claude" / "behavior-lock.tsv"
    if not reg.exists():
        reg.write_text(LOCK_HEADER, encoding="utf-8")
    with reg.open("a", encoding="utf-8") as fh:
        fh.write("\t".join([id_, "PRESERVE", behavior, carrier, why]) + "\n")


def resolves(repo: Path, carrier: str) -> bool:
    """The documented gate on whether a surface becomes a row: does its carrier resolve?"""
    r = subprocess.run(
        ["/bin/bash", str(LOCK), "--resolve", carrier, str(repo)],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def record_baseline(repo: Path, id_: str, state: str, exit_code: str, cmd: str, env: str):
    r = subprocess.run(
        ["/bin/bash", str(BASELINE), "--record", id_, state, exit_code, cmd, env],
        capture_output=True, text=True,
        env={**os.environ, "PLC_BEHAVIOR_BASELINE": str(repo / ".claude" / "behavior-baseline.tsv"),
             "PLC_BEHAVIOR_LOCK": str(repo / ".claude" / "behavior-lock.tsv")},
    )
    return r


def baseline_get(repo: Path, id_: str, state: str) -> str:
    r = subprocess.run(
        ["/bin/bash", str(BASELINE), "--get", id_, state],
        capture_output=True, text=True,
        env={**os.environ, "PLC_BEHAVIOR_BASELINE": str(repo / ".claude" / "behavior-baseline.tsv")},
    )
    return r.stdout.strip()


def carriers_resolve(repo: Path) -> subprocess.CompletedProcess:
    """M1's hard-fail invariant, driven over the adopted repo's registry with an empty base so
    every seeded row counts as touched (the pass seeds them, so they are all new on intake)."""
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
# AC1 -- the doc contract: the seventh artifact is documented and cannot drift back to six
# --------------------------------------------------------------------------------------------

def test_AC1_archaeology_md_documents_the_seventh_artifact():
    # This is the ONLY coupling between the doc and this test suite: the cases below model the
    # command path, but whether archaeology.md actually documents that path (and its routing rules)
    # is pinned here, on NEW prose this phase introduces -- not on strings that pre-existed it.
    text = ARCHAEOLOGY_MD.read_text(encoding="utf-8")
    # the Artifact set table now has a 7th row
    assert "| 7 |" in text, "the Artifact set table must grow to a 7th row (the behavior baseline)"
    # a dedicated section documents the step as commands over the two existing scripts
    assert "## Behavior baseline" in text, "a 'Behavior baseline' section must document the step"
    assert "behavior-lock.sh" in text and "behavior-baseline.sh" in text, (
        "the baseline step must be documented as commands over the two existing M1 scripts"
    )
    assert "--resolve" in text, "the step must document the carrier-resolve command"
    # the routing rules, asserted on NEW prose (not the pre-existing '## Coverage gaps' heading):
    # (a) a carrier that does NOT resolve -> no row;
    assert "seed NO row" in text, "the resolve-fails branch must route to Coverage gaps, not a row"
    # (b) a carrier that resolves but FAILS -> not a PRESERVE (pass->pass), also no row.
    assert "The carrier fails" in text, (
        "the carrier-resolves-but-fails branch must be documented (a failing behavior is not PRESERVE)"
    )


# --------------------------------------------------------------------------------------------
# AC2 -- a critical surface WITH a resolving carrier becomes a row + a recorded baseline
# --------------------------------------------------------------------------------------------

def test_AC2_resolving_carrier_becomes_a_row_and_records_a_baseline(tmp_path):
    repo = brownfield(tmp_path)
    carrier = "test_orders.py::test_total_includes_tax"
    assert resolves(repo, carrier), "the carrier for a tested behavior must resolve"

    seed_row(repo, "BL-1", "order total includes tax", carrier, "core billing behavior on intake")
    # the baseline records the CARRIER's own exit (not the whole suite's) -- per behavior, exit 0
    r = record_baseline(repo, "BL-1", "before", "0",
                        "pytest test_orders.py::test_total_includes_tax", "py3/local")
    assert r.returncode == 0, r.stdout + r.stderr

    # the carrier-resolve invariant is green over the adopted repo
    inv = carriers_resolve(repo)
    assert inv.returncode == 0, inv.stdout + inv.stderr
    # the baseline is retrievable (the characterization record, exit 0 for a PRESERVE before)
    assert baseline_get(repo, "BL-1", "before") == "0"


# --------------------------------------------------------------------------------------------
# AC3 -- a critical surface with NO resolving carrier is a Coverage gap, never a row
# --------------------------------------------------------------------------------------------

def test_AC3_untested_surface_is_not_seeded_as_a_row(tmp_path):
    repo = brownfield(tmp_path)
    # a critical surface the pass found, but nothing tests it
    untested = "payments.py::refund_is_idempotent"
    assert not resolves(repo, untested), "an untested surface's carrier must NOT resolve"

    # the documented rule: do NOT seed a row for it (route to Coverage gaps instead).
    # Following the rule leaves the registry empty of it, so the invariant stays green:
    seed_row(repo, "BL-1", "order total includes tax",
             "test_orders.py::test_total_includes_tax", "tested surface")
    inv = carriers_resolve(repo)
    assert inv.returncode == 0, inv.stdout + inv.stderr

    # negative control -- WHY the rule exists: had the pass wrongly seeded the untested surface,
    # the adopter's first close-gate would have gone red on the dangling carrier.
    seed_row(repo, "BL-2", "refund is idempotent", untested, "WRONGLY seeded untested surface")
    bad = carriers_resolve(repo)
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert "BL-2" in bad.stdout


# --------------------------------------------------------------------------------------------
# AC4 -- the manual demo, automated: break a seeded carrier -> red; revert -> green
# --------------------------------------------------------------------------------------------

def test_AC4_breaking_a_seeded_carrier_reds_then_revert_greens(tmp_path):
    repo = brownfield(tmp_path)
    carrier = "test_orders.py::test_total_includes_tax"
    seed_row(repo, "BL-1", "order total includes tax", carrier, "core billing behavior on intake")
    assert carriers_resolve(repo).returncode == 0

    # deliberately break the behavior's proof: the test is renamed away
    (repo / "test_orders.py").write_text(
        "def test_renamed_away():\n    assert True\n", encoding="utf-8"
    )
    red = carriers_resolve(repo)
    assert red.returncode == 1, red.stdout + red.stderr
    assert "BL-1" in red.stdout

    # revert -> green again
    (repo / "test_orders.py").write_text(
        "def test_total_includes_tax():\n    assert 1 + 1 == 2\n", encoding="utf-8"
    )
    assert carriers_resolve(repo).returncode == 0


# --------------------------------------------------------------------------------------------
# AC6 -- the baseline is the characterization record (id/state/exit/cmd/env/date), na allowed
# --------------------------------------------------------------------------------------------

def test_AC6_baseline_is_the_characterization_record(tmp_path):
    repo = brownfield(tmp_path)
    seed_row(repo, "BL-1", "order total includes tax",
             "test_orders.py::test_total_includes_tax", "tested surface")
    record_baseline(repo, "BL-1", "before", "0", "pytest test_orders.py", "py3/local")
    tsv = (repo / ".claude" / "behavior-baseline.tsv").read_text(encoding="utf-8")
    line = [ln for ln in tsv.splitlines() if ln.startswith("BL-1\t")][0]
    cols = line.split("\t")
    assert len(cols) == 6, "the baseline record has 6 columns: id/state/exit/cmd/env/date"
    assert cols[:5] == ["BL-1", "before", "0", "pytest test_orders.py", "py3/local"]

    # `na` is accepted where a would-be NEW behavior has no test yet (a brownfield surface a
    # characterization test will be written for).
    r = record_baseline(repo, "BL-1", "before", "na", "no test yet", "py3/local")
    assert r.returncode == 0, r.stdout + r.stderr
