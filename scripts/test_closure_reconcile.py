"""Tests for `closure-declaration.sh reconcile` — the declaration against the closure ledger.

**The asymmetry these cases pin, and why it is not a fallout.** A closure line that
existed BEFORE this branch and that no phase declared is silent (case 7) — those are
historical backfills, and demanding declarations for them would make adopting this
feature a retroactive audit. A closure line THIS BRANCH ADDED and did not declare is a
failure (case 5). Without case 5 the check misses the exact defect it exists to
fix: a phase closing three ids and declaring two leaves the third indistinguishable from a
backfill.

**Every case runs inside a throwaway git repo**, because "which lines did THIS BRANCH add"
is a question only git can answer. The fixture carries the real dependency set — the
script, its helper, and a stub deriver — because of what happens when
it does not: the helper source failed, the function was undefined, and the gate RETURNED 0.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "closure-declaration.sh"
HELPER = REPO / "scripts" / "lib" / "closure-log-added.sh"
FENCE = "`" * 3

HEADER = "# closure log\n"
BASE_LINES = (
    "B1001\tclosed\tcompleted\t2026-01-02\t-\n"
    "B1002\tclosed\tcompleted\t2026-01-05\t#31\n"
    "B1003\tclosed\tcompleted\t2026-01-05\t#31\n"
)

# A stub deriver, faithful to the real one's OUTPUT CONTRACT (`id<TAB>state (reason)`)
# rather than to its implementation, and derived from the same file the real one reads.
# An unfaithful stub lets a whole suite agree on a fabricated shape.
DERIVER = r"""#!/usr/bin/env bash
set -u
[ "${1:-}" = "--states" ] || exit 2
awk -F'\t' '
  /^#/ { next }
  /^[ \t]*$/ { next }
  $2 == "ref-amend" { next }
  { st[$1] = $2 " (" $3 ")" }
  END { for (k in st) printf "%s\t%s\n", k, st[k] }
' "$(dirname "$0")/../.claude/backlog-closures.tsv"
"""


def block(*lines: str) -> str:
    return "\n".join([f"{FENCE}plc-closes", *lines, FENCE, ""])


def make_repo(tmp_path: Path, *, base: str, added: str, doc_body: str) -> Path:
    d = tmp_path / "repo"
    (d / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (d / ".claude").mkdir(parents=True, exist_ok=True)
    (d / "docs").mkdir(parents=True, exist_ok=True)
    shutil.copy(SCRIPT, d / "scripts" / SCRIPT.name)
    shutil.copy(HELPER, d / "scripts" / "lib" / HELPER.name)

    deriver = d / "scripts" / "backlog-closures.sh"
    deriver.write_text(DERIVER, encoding="utf-8")
    deriver.chmod(0o755)

    log = d / ".claude" / "backlog-closures.tsv"
    log.write_text(HEADER + base, encoding="utf-8")

    def git(*a: str) -> None:
        subprocess.run(["git", *a], cwd=d, capture_output=True, check=False)

    git("init", "-q")
    git("symbolic-ref", "HEAD", "refs/heads/main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("add", "-A")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "feat")

    (d / "docs" / "spec.md").write_text(doc_body, encoding="utf-8")
    if added:
        log.write_text(HEADER + base + added, encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "branch work")
    return d


def reconcile(d: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "/bin/bash",
            "scripts/closure-declaration.sh",
            "reconcile",
            "--ledger",
            ".claude/backlog-closures.tsv",
            "--deriver",
            "scripts/backlog-closures.sh",
            "docs/spec.md",
        ],
        cwd=d,
        capture_output=True,
        text=True,
    )


# ------------------------------------------------------------------- case 1
def test_case1_declared_closed_and_ledger_agrees(tmp_path: Path) -> None:
    d = make_repo(
        tmp_path,
        base=BASE_LINES,
        added="B1007\tclosed\tcompleted\t2026-01-24\tpending\n",
        doc_body=block("closed: B1007"),
    )
    p = reconcile(d)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "B1007" in p.stdout


# ------------------------------------------------------------------- case 2
def test_case2_declared_closed_with_no_ledger_event(tmp_path: Path) -> None:
    """AC2. The carrier of the coarse mutant."""
    d = make_repo(tmp_path, base=BASE_LINES, added="", doc_body=block("closed: B1007"))
    p = reconcile(d)
    assert p.returncode != 0
    assert "FAIL" in p.stdout, "the verdict marker itself, not just the id"
    assert "B1007" in p.stdout and "NO event" in p.stdout, p.stdout
    # The REMEDIATION clause, asserted because a clause nobody checks can be deleted silently.
    # Without this line, removing the clause from the script's message
    # (`— append one (see …)`) leaves every row green. A `why` that describes an
    # assertion the test does not make is a false claim about coverage.
    assert "append one" in p.stdout, p.stdout


# ------------------------------------------------------------------- case 3
def test_case3_declared_closed_but_last_event_is_reopen(tmp_path: Path) -> None:
    """`last state-bearing event`, not `any event`. The carrier of the FINE mutant."""
    d = make_repo(
        tmp_path,
        base=BASE_LINES + "B1004\tclosed\tcompleted\t2026-01-11\t#32\n",
        added="B1004\treopen\t-\t2026-01-24\t-\n",
        doc_body=block("closed: B1004"),
    )
    p = reconcile(d)
    assert p.returncode != 0
    # `FAIL` is asserted FIRST and deliberately: a mutant that accepted the state and
    # echoed it back printed `reopen` too, so grepping only for the state name passed
    # against a broken implementation. Found by the fine mutant, not by reading.
    assert "FAIL" in p.stdout, "the verdict marker itself, not just the echoed state"
    assert "B1004" in p.stdout and "reopen" in p.stdout, p.stdout


# ------------------------------------------------------------------- case 4
def test_case4_left_open_needs_no_ledger_event(tmp_path: Path) -> None:
    """AC4, the exemption — by construction, not by a special case."""
    d = make_repo(
        tmp_path,
        base=BASE_LINES,
        added="",
        doc_body=block("left-open: B1005 — the fix is outside this fence"),
    )
    p = reconcile(d)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "B1005" in p.stdout and "no ledger event required" in p.stdout


# ------------------------------------------------------------------- case 5
def test_case5_added_closure_not_declared_is_a_failure(tmp_path: Path) -> None:
    """AC8, and the reason this check is bidirectional at all."""
    d = make_repo(
        tmp_path,
        base=BASE_LINES,
        added=(
            "B1007\tclosed\tcompleted\t2026-01-24\tpending\n"
            "B1008\tclosed\tcompleted\t2026-01-24\tpending\n"
        ),
        doc_body=block("closed: B1007"),
    )
    p = reconcile(d)
    assert p.returncode != 0
    assert "B1008" in p.stdout and "neither" in p.stdout, p.stdout


# ------------------------------------------------------------------- case 6
def test_case6_added_closure_declared_left_open_is_enough(tmp_path: Path) -> None:
    """Declaring is what AC8 requires, not closing."""
    d = make_repo(
        tmp_path,
        base=BASE_LINES,
        added="B1008\tclosed\tcompleted\t2026-01-24\tpending\n",
        doc_body=block("closed: B1008", "left-open: B1005 — out of fence"),
    )
    p = reconcile(d)
    assert p.returncode == 0, p.stdout + p.stderr


# ------------------------------------------------------------------- case 7
def test_case7_historical_backfills_stay_green(tmp_path: Path) -> None:
    """AC6's stated purpose, preserved."""
    d = make_repo(tmp_path, base=BASE_LINES, added="", doc_body=block("closes: none"))
    p = reconcile(d)
    assert p.returncode == 0, p.stdout + p.stderr
    for old in ("B1001", "B1002", "B1003"):
        assert old not in p.stdout, f"{old} predates the branch and must not be mentioned"


# ------------------------------------------------------------------- case 8
def test_case8_ref_amend_is_not_a_state_bearing_event(tmp_path: Path) -> None:
    d = make_repo(
        tmp_path,
        base=BASE_LINES,
        added="B1002\tref-amend\t-\t2026-01-24\t#31\n",
        doc_body=block("closes: none"),
    )
    p = reconcile(d)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "B1002" not in p.stdout, p.stdout


# ------------------------------------------------------------------- case 9
def test_case9_two_left_open_entries_are_both_named(tmp_path: Path) -> None:
    """AC4's named regression fixture: two deliberate non-closures in one block."""
    d = make_repo(
        tmp_path,
        base=BASE_LINES,
        added="",
        doc_body=block(
            "left-open: B1005 — only a reproduction shipped, not the fix",
            "left-open: B1006 — the follow-up is tracked separately",
        ),
    )
    p = reconcile(d)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "B1005" in p.stdout and "B1006" in p.stdout


# ------------------------------------------------------------------ case 10
def test_case10_unmentioned_open_ids_are_not_this_phases_business(tmp_path: Path) -> None:
    """The pair that makes case 9 mean something: the SAME ledger with the two ids simply
    not mentioned also passes — which is why case 9 asserts they were NAMED, not merely
    that the run was green."""
    d = make_repo(tmp_path, base=BASE_LINES, added="", doc_body=block("closes: none"))
    p = reconcile(d)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "B1005" not in p.stdout and "B1006" not in p.stdout


# ------------------------------------------------------------- guard rails
def test_missing_helper_is_a_named_failure(tmp_path: Path) -> None:
    """Measured: what a missing helper does when nothing checks is that the source
    failed, the function was undefined, and the caller RETURNED 0."""
    d = make_repo(tmp_path, base=BASE_LINES, added="", doc_body=block("closes: none"))
    (d / "scripts" / "lib" / HELPER.name).unlink()
    p = reconcile(d)
    assert p.returncode != 0
    assert "helper" in p.stderr, p.stderr


def test_malformed_declaration_stops_before_reconciling(tmp_path: Path) -> None:
    d = make_repo(tmp_path, base=BASE_LINES, added="", doc_body=block("wat"))
    p = reconcile(d)
    assert p.returncode != 0
    assert "not a declaration entry" in p.stderr, p.stderr


def test_none_verdict_is_reported_not_silent(tmp_path: Path) -> None:
    """SURVIVED MUTANT. Emptying the `none` verdict branch left all three
    suites green: every case exercising `closes: none` asserted only exit 0 and the ABSENCE
    of ids, so a silent no-op was indistinguishable from a real pass. A verdict nobody reads
    is a verdict nobody would notice going missing."""
    d = make_repo(tmp_path, base=BASE_LINES, added="", doc_body=block("closes: none"))
    p = reconcile(d)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "closed nothing" in p.stdout, p.stdout


def test_reopen_alone_does_not_demand_a_declaration(tmp_path: Path) -> None:
    """AC8 says `a closure line this phase ADDS`. The first
    implementation used a deny-list (skip only `ref-amend`), so a branch that merely REOPENED
    an id was forced to declare it -- under `closed:` (false) or `left-open:` (nothing was
    left open; it was actively reopened). No shipped document explained that demand."""
    d = make_repo(
        tmp_path,
        base=BASE_LINES + "B1004\tclosed\tcompleted\t2026-01-11\t#32\n",
        added="B1004\treopen\t-\t2026-01-24\t-\n",
        doc_body=block("closes: none"),
    )
    p = reconcile(d)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "B1004" not in p.stdout, p.stdout


def test_partial_closure_does_demand_a_declaration(tmp_path: Path) -> None:
    """The other side of the allow-list, so it pins a CHOICE and not just an exclusion:
    `partial` is a closure that did not finish the whole entry, and a phase that adds one has
    changed what the backlog says about that id."""
    d = make_repo(
        tmp_path,
        base=BASE_LINES,
        added="B1008\tpartial\tcompleted\t2026-01-24\tpending\n",
        doc_body=block("closes: none"),
    )
    p = reconcile(d)
    assert p.returncode != 0
    assert "B1008" in p.stdout, p.stdout
