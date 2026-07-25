"""The canonical close-gate bash lives inside references/close-gate.md.
These tests extract it and actually run it — nothing else in this repo does."""
import os
import subprocess
import time
from pathlib import Path

import pytest

from close_gate_lib import extract_gate_script, make_fixture_repo, run_gate

GATE_MD = Path(__file__).resolve().parents[1] / "skills/project-lifecycle/references/close-gate.md"


@pytest.fixture(scope="module")
def gate_script() -> str:
    return extract_gate_script(GATE_MD)


def test_extracts_a_runnable_bash_script(gate_script: str) -> None:
    assert gate_script.startswith("#!/usr/bin/env bash")
    assert 'MODE="${1:?' in gate_script


def test_gate_fails_without_a_manifest(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, manifest=None, files={"README.md": "hi\n"})
    result = run_gate(repo, gate_script, "task")
    assert result.returncode == 1
    assert "missing .claude/close-gate.json" in result.stdout


MANIFEST = {
    "test_command": "true",
    "retention": {
        "journal_dir": "docs/journal.d",
        "archive_dir": "docs/archive",
        "count_caps": {"specs": 2, "plans": 2, "docs_total": 5},
    },
}


def _docs(n: int, prefix: str) -> dict[str, str]:
    return {f"docs/superpowers/{prefix}/{i:02d}-x.md": "x\n" for i in range(n)}


def test_count_row_is_quiet_when_under_cap(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, MANIFEST, _docs(2, "specs"))
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert "count: docs/superpowers/specs" not in result.stdout


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, check=True, capture_output=True)


# The canonical FACT-entry bullet form the phase-done gate now greps for (Task: FACT-entry
# enforcement) — matches what journals written under this schema actually write, per
# references/journal-schema.md §"The FACT entry". Appended to fixture journal content in every
# helper below whose tests assert phase mode reaches a clean PASS — without it, the new FACT
# check hard-fails every one of them (that failure is the RED proof the check is non-vacuous).
_FACT_BLOCK = (
    "\n## FACT — fixture distill\n"
    "- **Date:** 2026-01-01\n"
    "- **Decision:** x\n"
    "- **Why:** x\n"
    "- **Backing:** x — measured in y\n"
    "- **Rejected:** x\n"
    "- **Source:** deadbeef:docs/superpowers/specs/x.md\n"
)


def _make_otherwise_passing_phase_fixture(tmp_path: Path, spec_count: int) -> Path:
    """Built so a count-cap overage is the sole thing keeping the gate from a clean run — the
    only honest way to prove the count row is warn-only rather than accidentally-quiet because
    something unrelated already failed the gate.

    Genuinely satisfied (real artifact / real diff):
      - journal touched this phase (docs/journal.d/2026-01-01-x.md is committed on the SECOND commit)
      - CHANGELOG [Unreleased] touched / ROADMAP touched (both files committed on the SECOND commit)
      - fresh test-evidence (.claude/.last-test-run written >1s after the second commit)

    Explicitly SKIPPED, each printing a visible `⊘ <key> not configured in manifest` row that is
    neither a ✓ nor silence. Before that fix these four printed a VACUOUS ✓:
    the absent manifest key produced an empty glob pattern and `compgen -G ""` exits 0, so the gate
    reported a pass for artifacts nobody had said where to look for. That is now impossible:
      - user-story.md + spec doc (`phase_docs_glob` absent)
      - plan doc (`plan_glob` absent)
      - handoff doc (`handoff_glob` absent)
      - acceptance tests (`acceptance_glob` absent)

    A ⊘ row does not flip `fail` (it is a visible skip, not a hard failure — see the gate's req_glob
    comment for why), so the gate still reaches rc 0 here and the count row remains the only thing
    under test — but nothing in this fixture is silently passing as a ✓ any more.

    Skipped entirely, no row printed either way: the Track A/B smoke checks, gated on
    `user_visible` which is absent here (the whole smoke block never runs).

    `make_fixture_repo` commits once with origin/main == HEAD (see close_gate_lib docstring), so
    the diff-range checks (CHANGELOG / ROADMAP / journal touched) need a SECOND commit here to
    have anything to see."""
    manifest = {
        "test_command": "true",
        "test_evidence": ".claude/.last-test-run",
        # NOTE: the manifest "journal" (monolith fallback) key is deliberately ABSENT. It used to
        # be set here purely to dodge a gate defect — the journal-touched alternation `^($JD/|$journal)`
        # gained an empty branch when the key was unset, and BSD/macOS grep (unlike GNU) errors
        # "empty (sub)expression" on that. a later fix made the gate build the alternation only
        # from configured branches, so leaving the key out is now the stronger fixture: it keeps
        # that fix honest instead of papering over it.
        "retention": {
            "journal_dir": "docs/journal.d",
            "archive_dir": "docs/archive",
            "count_caps": {"specs": 2, "plans": 2, "docs_total": 5},
        },
    }
    # no top-level user-story.md: with phase_docs_glob absent the user-story check is now a ⊘
    # skip row, so such a file would be dead fixture weight implying a pass it no longer causes
    files = _docs(spec_count, "specs")
    repo = make_fixture_repo(tmp_path, manifest, files)
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n- x\n", encoding="utf-8")
    (repo / "docs/ROADMAP.md").write_text(
        # must NAME the phase: the ROADMAP row is content-checked, not touch-checked
        "- [x] phase 1.0 — fixture row\n", encoding="utf-8"
    )
    (repo / "docs/journal.d").mkdir(parents=True, exist_ok=True)
    (repo / "docs/journal.d/2026-01-01-x.md").write_text(
        "## t\n**Plan deviations:** none\n" + _FACT_BLOCK, encoding="utf-8"
    )
    _commit(repo, "docs: wrap-up artifacts for gate fixture")
    # macOS ships bash 3.2, whose `-nt` file-test compares mtimes at whole-SECOND granularity
    # (confirmed empirically: two files 0.2s apart in the same wall-clock second both compare
    # NOT_NEWER). A sub-second sleep here is flaky roughly half the time depending on where the
    # commit lands in its second. Sleep past a full second boundary so `$EV -nt .git/HEAD` is
    # deterministic regardless of macOS's default shell.
    time.sleep(1.1)
    (repo / ".claude/.last-test-run").write_text("ok\n", encoding="utf-8")
    return repo


def test_count_row_warns_over_cap_but_does_not_fail(tmp_path: Path, gate_script: str) -> None:
    repo = _make_otherwise_passing_phase_fixture(tmp_path, spec_count=3)
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert "⚠ count: docs/superpowers/specs 3 files (cap 2)" in result.stdout
    assert result.returncode == 0, "count rows are warn-only in phase mode"


def test_docs_total_row_warns_over_cap(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, MANIFEST, _docs(6, "specs"))
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert "⚠ count: docs/**/*.md 6 files (cap 5)" in result.stdout


def test_screenshots_are_never_counted(tmp_path: Path, gate_script: str) -> None:
    """`count_md`'s `-not -path '*/screenshots/*'` clause must be the ONLY thing keeping a
    real `.md` file under `docs/pr-drafts/screenshots/` out of the docs_total count — a `.png`
    fixture proves nothing here, since `find ... -name '*.md'` already excludes any `.png`
    regardless of the path clause (deleting the clause would still pass a `.png`-only fixture).

    So: one non-screenshot spec `.md` (counts either way) + one screenshot `.md` (must be
    excluded), with `docs_total` cap set to exactly the non-screenshot count. specs/plans caps
    are exempted so the docs_total row is the only count check that can fire — isolates the
    assertion to the exclusion clause instead of an unrelated cap tripping. With the clause
    intact: count stays at cap (1), no warning. With the clause removed (verified against a
    scratch copy of the gate, not committed): count is 2 > cap 1, and the warning fires —
    proving this test actually exercises the exclusion, unlike the `.png` version."""
    manifest = {
        "test_command": "true",
        "retention": {
            "journal_dir": "docs/journal.d",
            "archive_dir": "docs/archive",
            "count_caps": {"specs": "none", "plans": "none", "docs_total": 1},
        },
    }
    files = _docs(1, "specs") | {"docs/pr-drafts/screenshots/notes.md": "load-bearing md, not a screenshot\n"}
    repo = make_fixture_repo(tmp_path, manifest, files)
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert "⚠ count: docs/**/*.md" not in result.stdout


def test_count_cap_none_exempts(tmp_path: Path, gate_script: str) -> None:
    manifest = {
        "test_command": "true",
        "retention": {"count_caps": {"specs": "none", "plans": 2, "docs_total": 0}},
    }
    repo = make_fixture_repo(tmp_path, manifest, _docs(9, "specs"))
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert "count: docs/superpowers/specs" not in result.stdout


# --- cc()'s absent-key default (reincarnated for counts) ---
#
# `cc() { jq -r ".retention.count_caps.$1 // empty" "$M"; }` used to yield empty on an absent
# key, and `count_row`'s `case "$3" in ""|none|0) return 0 ;; esac` then returned SILENTLY — no
# row, no warn, no ⊘. RED (pre-fix): a fixture with count_caps entirely absent and specs over
# the documented-but-unenforced default of 10 reached `── close-gate PASS`, zero output, rc=0.
# The fix gives `cc()` a real default (mirrors hot_caps' `cap_val`), so an absent key now still
# compares against a real number instead of vanishing.


def test_count_caps_absent_is_not_a_silent_pass_in_phase_mode(tmp_path: Path, gate_script: str) -> None:
    manifest = {
        "test_command": "true",
        # retention block present (journal_dir needed for other rows to resolve cleanly) but
        # count_caps itself is entirely ABSENT — the exact gap that fix closed for req_glob and
        # this branch's own count code reintroduced.
        "retention": {"journal_dir": "docs/journal.d", "archive_dir": "docs/archive"},
    }
    repo = make_fixture_repo(tmp_path, manifest, _docs(11, "specs"))
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert "⚠ count: docs/superpowers/specs 11 files (cap 10)" in result.stdout, (
        f"count_caps absent must fall back to the documented default (specs=10), not vanish "
        f"silently:\n{result.stdout}"
    )


def test_count_caps_entirely_absent_from_manifest_also_defaults(tmp_path: Path, gate_script: str) -> None:
    """Stronger RED case: no `retention` block at all (not even journal_dir/archive_dir) — jq's
    null-safe chaining must still resolve `cc()`'s default rather than erroring or vanishing."""
    manifest = {"test_command": "true"}
    repo = make_fixture_repo(tmp_path, manifest, _docs(11, "specs"))
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert "⚠ count: docs/superpowers/specs 11 files (cap 10)" in result.stdout, result.stdout


def test_milestone_mode_blocks_over_default_count_cap_when_count_caps_absent(
    tmp_path: Path, gate_script: str
) -> None:
    """The blocking half of the same defect: at milestone close an absent count_caps used to
    mean the count axis — this branch's entire reason for existing — was silently disabled
    project-wide. Required-artifact keys are configured so the required-artifact check can't be
    what fails this; only the now-defaulted count row can."""
    manifest = {
        "test_command": "true",
        "phase_docs_glob": "docs/superpowers/specs/*-phase-{PHASE}-*",
        "plan_glob": "docs/superpowers/plans/*-phase-{PHASE}-*",
        "acceptance_glob": "tests/acceptance/**/*phase-{PHASE}*",
        "retention": {"journal_dir": "docs/journal.d", "archive_dir": "docs/archive"},
    }
    repo = make_fixture_repo(tmp_path, manifest, _docs(11, "specs"))
    result = run_gate(repo, gate_script, "milestone", "1.0")
    assert result.returncode == 1, f"absent count_caps must not disable the milestone block:\n{result.stdout}"
    assert "count: docs/superpowers/specs 11 files (cap 10)" in result.stdout


# --- docs_total must exclude the archive, or archiving can never clear it ---


def test_archive_working_clears_the_docs_total_count(tmp_path: Path, gate_script: str) -> None:
    """RED against the pre-fix gate: `count_md docs` had no `-not -path` clause for
    retention.archive_dir, so moving over-cap docs into the archive — exactly what the gate's
    own `⚠`/`✗` message tells you to run — left `docs_total` unchanged. That makes `milestone`
    a permanent block with no reachable remedy once a repo crosses the cap (short of deleting
    docs, which the user forbade, or raising the cap, which disables the gate). This test
    fails against the pre-fix `count_md` because the archived files are still found under
    `docs/archive/working/**` and counted right back in."""
    manifest = {
        "test_command": "true",
        "retention": {
            "journal_dir": "docs/journal.d",
            "archive_dir": "docs/archive",
            "count_caps": {"specs": "none", "plans": "none", "docs_total": 5},
        },
    }
    files = _docs(6, "specs")  # 6 > cap 5
    repo = make_fixture_repo(tmp_path, manifest, files)
    before = run_gate(repo, gate_script, "phase", "1.0")
    assert "⚠ count: docs/**/*.md 6 files (cap 5)" in before.stdout, before.stdout

    drain = Path(__file__).resolve().parent / "retention-drain.sh"
    for i in range(6):
        src = f"docs/superpowers/specs/{i:02d}-x.md"
        result = subprocess.run(
            ["bash", str(drain), "archive-working", src],
            cwd=repo, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert not (repo / src).exists()

    after = run_gate(repo, gate_script, "phase", "1.0")
    assert "count: docs/**/*.md" not in after.stdout, (
        f"docs_total must exclude retention.archive_dir so archiving is a reachable remedy:\n{after.stdout}"
    )


# --- three pre-existing gate defects, exposed by the coverage the suite added ---


def test_defect_a_absent_phase_docs_glob_is_not_a_silent_pass(tmp_path: Path, gate_script: str) -> None:
    """`compgen -G ""` exits 0, so an ABSENT phase_docs_glob key used to print a
    naked ✓ for the 'spec doc' bad()-tier check — a pass for an artifact nobody said where to
    look for. After the fix the row must be visibly neither a ✓ nor silence."""
    manifest = {"test_command": "true"}
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    result = run_gate(repo, gate_script, "phase", "1.0")
    spec_lines = [line for line in result.stdout.splitlines() if "spec doc" in line]
    assert spec_lines, f"expected a 'spec doc' row in gate output:\n{result.stdout}"
    assert not any(line.startswith("✓") for line in spec_lines), (
        "phase_docs_glob is absent from the manifest — the gate must not print a checkmark "
        f"for an artifact nobody configured a location for: {spec_lines}"
    )


def test_defect_b_absent_journal_key_detects_a_real_touch_without_grep_crash(
    tmp_path: Path, gate_script: str
) -> None:
    """BSD grep errors ('empty (sub)expression', exit 2) on the alternation
    `^(docs/journal.d/|)` built when manifest 'journal' is unset. Under the old code this
    silently resolved to the bad() branch even when the journal fragment dir WAS genuinely
    touched in the phase's commit range — a false negative baked into the crash. The fixed
    gate must build the alternation only from configured branches, never crash, and correctly
    detect a real touch."""
    manifest = {
        "test_command": "true",
        "retention": {"journal_dir": "docs/journal.d"},
    }
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    (repo / "docs/journal.d").mkdir(parents=True, exist_ok=True)
    (repo / "docs/journal.d/2026-01-01-x.md").write_text(
        "## t\n**Plan deviations:** none\n", encoding="utf-8"
    )
    _commit(repo, "docs: touch journal fragment")
    result = run_gate(repo, gate_script, "phase", "1.0")
    combined = result.stdout + result.stderr
    assert "empty (sub)expression" not in combined, combined
    journal_lines = [
        line
        for line in result.stdout.splitlines()
        if "journal touched" in line or "journal not touched" in line
    ]
    assert journal_lines, f"expected a journal-touched row:\n{result.stdout}"
    assert journal_lines[0].startswith("✓"), (
        f"journal_dir was genuinely touched in the commit range — expected ✓, got: {journal_lines}"
    )


_NS_PER_SEC = 1_000_000_000


def _write_evidence_at_ns(repo: Path, mtime_ns: int) -> Path:
    (repo / ".claude").mkdir(exist_ok=True)
    ev = repo / ".claude/.last-test-run"
    ev.write_text("ok\n", encoding="utf-8")
    os.utime(ev, ns=(mtime_ns, mtime_ns))
    return ev


# The evidence-freshness check compares evidence against HEAD's committer-date, a whole-second
# stamp — so its granularity is ≤1s by construction. These three cases pin that documented
# contract and REPLACE the earlier `.git/HEAD`-mtime fixtures: X7 proved `.git/HEAD`'s mtime does
# not track HEAD (`git commit` leaves it at checkout time), so those fixtures anchored the freshness
# comparison to the wrong file. `find -newer`'s own sub-second ordering (the original Defect-C
# property) is unchanged in `fresh()`; the evidence row simply no longer feeds it a sub-second
# reference, because a git commit's time is whole-second to begin with.


def test_evidence_after_head_commit_is_fresh(tmp_path: Path, gate_script: str) -> None:
    """Evidence written a clear second AFTER the HEAD commit is genuinely fresh → ✓."""
    manifest = {"test_command": "true", "test_evidence": ".claude/.last-test-run"}
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    _commit_at(repo, "feat: work", epoch=1_000_000)
    _write_evidence_at_ns(repo, 1_000_002 * _NS_PER_SEC)  # 2s after the commit
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✓"), f"evidence postdates the commit — expected fresh: {rows}"


def test_evidence_a_second_before_head_commit_is_stale(tmp_path: Path, gate_script: str) -> None:
    """Evidence written a clear second BEFORE the HEAD commit predates the code it claims to cover → ✗."""
    manifest = {"test_command": "true", "test_evidence": ".claude/.last-test-run"}
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    _commit_at(repo, "feat: work", epoch=1_000_000)
    _write_evidence_at_ns(repo, 999_998 * _NS_PER_SEC)  # 2s before the commit
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✗"), f"evidence predates the commit — expected stale: {rows}"


def test_evidence_same_second_as_commit_reads_fresh_documented_1s_residual(
    tmp_path: Path, gate_script: str
) -> None:
    """X5/X7 residual, pinned so it is not silently "fixed": the committer-date stamp is whole-second
    (`touch -t`), so evidence in the SAME wall-clock second as the commit reads FRESH — a ≤1s fail-OPEN
    window, and the correct side in the realistic run-tests-then-commit order. This also preserves the
    original Defect-C intent (genuinely-fresh evidence written <1s after the commit must not read
    stale). If a future change makes this fail-closed, that is a deliberate decision this test forces
    into the open rather than letting it ride in as an accident."""
    manifest = {"test_command": "true", "test_evidence": ".claude/.last-test-run"}
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    _commit_at(repo, "feat: work", epoch=1_000_000)
    _write_evidence_at_ns(repo, 1_000_000 * _NS_PER_SEC + 500_000_000)  # same second, +0.5s
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✓"), f"same-second evidence reads fresh (≤1s residual): {rows}"


# --- X7: legacy evidence freshness anchors to HEAD's committer-date, not .git/HEAD's mtime ---
# `git commit` does NOT advance .git/HEAD's file mtime (verified: it stays at init/checkout time),
# so `fresh "$EV" .git/HEAD` compares evidence against WHEN THE BRANCH WAS CHECKED OUT, not against
# the commit it claims to cover. Evidence written between an early checkout and a later commit then
# false-PASSES as fresh though it predates HEAD. The fix anchors freshness to HEAD's committer-date
# (the semantic commit time), accepting X5's documented ≤1s whole-second truncation as the residual.


def _commit_at(repo: Path, msg: str, epoch: int) -> None:
    """Add a commit whose author+committer date is exactly `epoch` (seconds). Lets a test fix the
    commit time without sleeping, so evidence/`.git/HEAD` mtimes can be placed on either side of it."""
    (repo / f"f{epoch}.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    env = {**os.environ, "GIT_AUTHOR_DATE": f"@{epoch} +0000", "GIT_COMMITTER_DATE": f"@{epoch} +0000"}
    subprocess.run(
        ["git", "commit", "-q", "-m", msg], cwd=repo, check=True, capture_output=True, env=env
    )


def test_x7_evidence_predating_head_commit_is_stale_despite_git_head_mtime(
    tmp_path: Path, gate_script: str
) -> None:
    """The X7 defect, reproduced: `.git/HEAD` mtime is stuck at checkout time (`git commit` does
    not touch it), so evidence written AFTER checkout but BEFORE the current HEAD commit is newer
    than `.git/HEAD` yet older than the commit — genuinely stale, but the legacy `fresh $EV
    .git/HEAD` check reads it as fresh. Anchoring to HEAD's committer-date catches it."""
    manifest = {"test_command": "true", "test_evidence": ".claude/.last-test-run"}
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    # HEAD advances to a commit dated well after the evidence; .git/HEAD mtime does not follow it.
    _commit_at(repo, "feat: later work", epoch=1_000_010)
    head_mtime, ev_mtime = 1_000_000, 1_000_005  # both < the 1_000_010 commit; ev newer than .git/HEAD
    os.utime(repo / ".git/HEAD", ns=(head_mtime * _NS_PER_SEC, head_mtime * _NS_PER_SEC))
    ev = _write_evidence_at_ns(repo, ev_mtime * _NS_PER_SEC)
    # Sanity: the fixture is the exact false-PASS shape — ev newer than .git/HEAD, older than HEAD.
    assert ev.stat().st_mtime_ns > (repo / ".git/HEAD").stat().st_mtime_ns
    head_commit_epoch = int(
        subprocess.run(
            ["git", "show", "-s", "--format=%ct", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()
    )
    assert ev.stat().st_mtime_ns // _NS_PER_SEC < head_commit_epoch

    result = run_gate(repo, gate_script, "task")
    evidence_lines = [line for line in result.stdout.splitlines() if "test-evidence" in line]
    assert evidence_lines, f"expected a test-evidence row:\n{result.stdout}"
    assert evidence_lines[0].startswith("✗"), (
        f"evidence predates the HEAD commit it claims to cover — expected stale, got: {evidence_lines}"
    )


# --- X9: task-mode check #1 is path-based (product_paths) with a verb fallback ---
# Ports X8's local product-tree check into the canonical gate. The old `feat|fix` commit-verb
# test was a proxy for "the task shipped a product change"; a legit refactor-only commit under the
# product tree had to be mislabeled `feat` to pass. BACKWARD-COMPATIBLE: an absent product_paths
# key falls back to the legacy verb check, so no existing adopter manifest changes behavior.

_X9_MANIFEST = {"product_paths": ["src/"], "test_command": "true", "test_evidence": ".claude/.last-test-run"}


def test_task_product_tree_touch_passes_on_a_refactor_commit(tmp_path: Path, gate_script: str) -> None:
    """A `refactor:` commit (NOT feat/fix) that touches a product_paths dir passes check #1 —
    the exact case the verb check wrongly failed."""
    repo = make_fixture_repo(tmp_path, _X9_MANIFEST, {"README.md": "hi\n"})
    (repo / "src").mkdir()
    (repo / "src/app.py").write_text("x = 1\n", encoding="utf-8")
    _commit(repo, "refactor: tidy app")
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "product tree" in ln]
    assert rows and rows[0].startswith("✓"), (
        f"a refactor commit touching src/ must pass the product-tree check:\n{result.stdout}"
    )


def test_task_meta_only_change_fails_the_product_tree_check(tmp_path: Path, gate_script: str) -> None:
    """A commit that touches NO product_paths path fails check #1, even titled `docs:` — a
    meta-only change is not a task, and a widened verb list could never catch this."""
    repo = make_fixture_repo(tmp_path, _X9_MANIFEST, {"README.md": "hi\n"})
    (repo / "README.md").write_text("hi\nmore\n", encoding="utf-8")
    _commit(repo, "docs: readme typo")
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "product-tree path" in ln]
    assert rows and rows[0].startswith("✗"), (
        f"a meta-only change (no product path) must fail the product-tree check:\n{result.stdout}"
    )


def test_task_absent_product_paths_falls_back_to_the_verb_check(tmp_path: Path, gate_script: str) -> None:
    """No product_paths key at all → the legacy `feat|fix` commit-verb check runs unchanged, so
    a manifest predating the key keeps its behavior (backward compatibility)."""
    manifest = {"test_command": "true", "test_evidence": ".claude/.last-test-run"}
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    (repo / "README.md").write_text("hi\nx\n", encoding="utf-8")
    _commit(repo, "chore: not a feat")
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "feat/fix commit" in ln]
    assert rows and rows[0].startswith("✗"), (
        f"absent product_paths must fall back to the verb check (a chore: commit fails it):\n{result.stdout}"
    )


def test_task_malformed_product_paths_fails_closed(tmp_path: Path, gate_script: str) -> None:
    """product_paths present but not a non-empty array (here an object) fails closed — even a
    `feat:` commit must not rescue a malformed key, mirroring the local gate's type guard."""
    manifest = {"product_paths": {"a": "src/"}, "test_command": "true", "test_evidence": ".claude/.last-test-run"}
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    (repo / "src").mkdir()
    (repo / "src/app.py").write_text("x = 1\n", encoding="utf-8")
    _commit(repo, "feat: add app")
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "product_paths present" in ln]
    assert rows and rows[0].startswith("✗"), (
        f"a malformed product_paths (object) must fail closed:\n{result.stdout}"
    )


def test_task_root_commit_touching_product_tree_passes(tmp_path: Path, gate_script: str) -> None:
    """Regression for the --root flag: when HEAD IS the repo's root commit (no parent — an adopter's
    very first commit, e.g. init-harness scaffold + first product code in one commit), the diff must
    still list HEAD's files. Without `git diff-tree … --root` the root commit diffs against a
    nonexistent parent and prints nothing → a false ✗ on a legitimate product change."""
    # make_fixture_repo's single "init" commit IS the root; put product code in it and add no second
    # commit, so HEAD has no parent — the exact case a plain `diff-tree HEAD` mis-handles.
    repo = make_fixture_repo(tmp_path, _X9_MANIFEST, {"src/app.py": "x = 1\n"})
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "product tree" in ln]
    assert rows and rows[0].startswith("✓"), (
        f"a ROOT commit touching src/ must pass the product-tree check (needs --root):\n{result.stdout}"
    )


def test_task_empty_product_paths_array_fails_closed(tmp_path: Path, gate_script: str) -> None:
    """An empty array is malformed too: it declares the key but names no tree, so the path check has
    nothing to match. It must fail closed, NOT fall back to the verb check and NOT pass vacuously —
    even for a `feat:` commit that touches the product tree."""
    manifest = {"product_paths": [], "test_command": "true", "test_evidence": ".claude/.last-test-run"}
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    (repo / "src").mkdir()
    (repo / "src/app.py").write_text("x = 1\n", encoding="utf-8")
    _commit(repo, "feat: add app")
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "product_paths present" in ln]
    assert rows and rows[0].startswith("✗"), (
        f"an empty-array product_paths must fail closed, not fall through:\n{result.stdout}"
    )


# --- X6: task-mode test-evidence is a content fingerprint when test_evidence_inputs is declared ---
# Ports the local gate's fingerprint check into the canonical gate. Opt-in: declaring
# test_evidence_inputs switches the row from the legacy mtime check to a content digest of the
# declared inputs. Absent key → legacy mtime unchanged (backward-compatible).

_X6_MANIFEST = {
    "test_command": "true",
    "test_evidence": ".claude/.last-test-run",
    "test_evidence_inputs": ["src/**"],
}


def _headed_evidence(repo: Path, gate_script: str, body: str = "ok\n") -> None:
    """Write the evidence file with a REAL fingerprint header, produced by the gate's own
    `evidence-header` subcommand — the same path an adopter's runner uses."""
    header = run_gate(repo, gate_script, "evidence-header").stdout
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude/.last-test-run").write_text(header + body, encoding="utf-8")


def test_evidence_header_subcommand_emits_a_hex_digest(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, _X6_MANIFEST, {"src/app.py": "x = 1\n"})
    out = run_gate(repo, gate_script, "evidence-header").stdout
    assert out.startswith("# plc-gate-evidence inputs="), f"header shape wrong: {out!r}"
    digest = out.split("inputs=", 1)[1].strip()
    assert len(digest) >= 40 and all(c in "0123456789abcdef" for c in digest), f"not a hex digest: {digest!r}"


def test_task_fingerprint_matches_passes(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, _X6_MANIFEST, {"src/app.py": "x = 1\n"})
    _headed_evidence(repo, gate_script)
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✓"), f"a matching fingerprint must pass:\n{result.stdout}"


def test_task_fingerprint_stale_when_a_declared_input_changes(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, _X6_MANIFEST, {"src/app.py": "x = 1\n"})
    _headed_evidence(repo, gate_script)
    # change a declared input AFTER the header was generated → digest no longer matches
    (repo / "src/app.py").write_text("x = 999\n", encoding="utf-8")
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✗") and "stale" in rows[0], (
        f"a changed input must read stale:\n{result.stdout}"
    )


def test_task_fingerprint_missing_header_hard_fails(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, _X6_MANIFEST, {"src/app.py": "x = 1\n"})
    # evidence with content but NO fingerprint header (an adopter who declared the key but did not
    # update their runner) — must hard fail, never silently fall back to mtime
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude/.last-test-run").write_text("ok\n", encoding="utf-8")
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✗") and "first line" in rows[0], (
        f"a declared-inputs manifest with an unheaded evidence file must hard fail:\n{result.stdout}"
    )


def test_task_fingerprint_inputs_match_nothing_fails_closed(tmp_path: Path, gate_script: str) -> None:
    manifest = {**_X6_MANIFEST, "test_evidence_inputs": ["does-not-exist/**"]}
    repo = make_fixture_repo(tmp_path, manifest, {"src/app.py": "x = 1\n"})
    _headed_evidence(repo, gate_script)  # header will carry the EMPTY sentinel
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "matched no tracked files" in ln]
    assert rows and rows[0].startswith("✗"), (
        f"inputs matching nothing must fail closed, not pass vacuously:\n{result.stdout}"
    )


def test_task_malformed_test_evidence_inputs_fails_closed(tmp_path: Path, gate_script: str) -> None:
    manifest = {**_X6_MANIFEST, "test_evidence_inputs": "src/"}  # string, not array
    repo = make_fixture_repo(tmp_path, manifest, {"src/app.py": "x = 1\n"})
    _headed_evidence(repo, gate_script)
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test_evidence_inputs present" in ln]
    assert rows and rows[0].startswith("✗"), (
        f"a non-array test_evidence_inputs must fail closed:\n{result.stdout}"
    )


def test_task_absent_inputs_uses_legacy_mtime(tmp_path: Path, gate_script: str) -> None:
    """No test_evidence_inputs key → the legacy mtime check runs unchanged; a fresh evidence file
    (written after the commit) passes without any fingerprint header."""
    manifest = {"test_command": "true", "test_evidence": ".claude/.last-test-run"}
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    time.sleep(1.1)  # cross a whole-second boundary — bash 3.2 -nt is whole-second
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude/.last-test-run").write_text("ok\n", encoding="utf-8")  # no header, legacy is fine
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✓"), (
        f"absent test_evidence_inputs must use legacy mtime and pass a fresh unheaded file:\n{result.stdout}"
    )


def test_task_absent_test_evidence_key_hard_fails(tmp_path: Path, gate_script: str) -> None:
    """A manifest with a test_command but NO test_evidence path is a misconfiguration — it must
    HARD FAIL (byte-identical to the pre-X6 blocks), never warn-and-skip. Guards against the
    vacuous-pass-on-absent-key defect the refactor's shared entry point could have reintroduced."""
    manifest = {"test_command": "true"}  # test_evidence deliberately absent
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✗") and "stale/missing" in rows[0], (
        f"absent test_evidence must hard fail, not skip:\n{result.stdout}"
    )


# --- milestone mode — the one place the gate actually bites ---


# The required-artifact check (phase_docs_glob / plan_glob / acceptance_glob — handoff_glob
# was dropped from this set when the handoff file was retired, so a required key
# naming it could never be satisfied by any manifest value, hard-failing every milestone
# close out of the box) now runs UNCONDITIONALLY in milestone mode — PHASE arg or not (fixing
# the finding that a bare `close-gate.sh milestone` silently skipped it). MANIFEST
# (module-level, above) leaves all three keys unconfigured, so it can no longer be used for a
# milestone fixture that wants to isolate the count-cap check in isolation: an unconditional
# required-artifact check would also fire and the test would be asserting on a fail() that
# could come from either row. This manifest configures the three keys (values need not
# resolve to a real file — see test_milestone_mode_passes_when_required_artifacts_configured's
# docstring) so the two brief-literal count-cap tests below test count-cap promotion in
# isolation, mirroring how _make_otherwise_passing_phase_fixture isolates concerns for phase
# mode.
MILESTONE_COUNT_ISOLATION_MANIFEST = {
    "test_command": "true",
    "phase_docs_glob": "docs/superpowers/specs/*-phase-{PHASE}-*",
    "plan_glob": "docs/superpowers/plans/*-phase-{PHASE}-*",
    "acceptance_glob": "tests/acceptance/**/*phase-{PHASE}*",
    "retention": {
        "journal_dir": "docs/journal.d",
        "archive_dir": "docs/archive",
        "count_caps": {"specs": 2, "plans": 2, "docs_total": 5},
    },
}


def test_milestone_mode_blocks_when_over_count_cap(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, MILESTONE_COUNT_ISOLATION_MANIFEST, _docs(3, "specs"))
    result = run_gate(repo, gate_script, "milestone")
    assert result.returncode == 1
    assert "count: docs/superpowers/specs 3 files (cap 2)" in result.stdout


def test_milestone_mode_passes_when_under_count_cap(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, MILESTONE_COUNT_ISOLATION_MANIFEST, _docs(2, "specs"))
    result = run_gate(repo, gate_script, "milestone")
    assert result.returncode == 0


def test_phase_mode_still_does_not_block_over_count_cap(tmp_path: Path, gate_script: str) -> None:
    """The daily gate must never bite — a gate that bites daily gets switched off.

    Uses `_make_otherwise_passing_phase_fixture`, not a plain `make_fixture_repo`, so the
    count-cap overage is the sole thing that could fail the gate (see that helper's docstring):
    a bare single-commit fixture has an empty origin/main..HEAD range, which independently
    fails the CHANGELOG/ROADMAP/journal-touched checks regardless of the count row under
    test — that would make this assertion pass or fail for reasons that have nothing to do
    with the count-cap warn-only guarantee it exists to prove."""
    repo = _make_otherwise_passing_phase_fixture(tmp_path, spec_count=3)
    assert run_gate(repo, gate_script, "phase", "1.0").returncode == 0


# --- additional requirement: milestone hard-fails on unconfigured required-artifact
# manifest keys (⊘ rows at task/phase are non-blocking by design; milestone is where an
# accumulated, ignored ⊘ finally stops being free) ---


def test_milestone_mode_blocks_when_required_artifact_unconfigured(
    tmp_path: Path, gate_script: str
) -> None:
    """MANIFEST (module-level, above) never configures phase_docs_glob / plan_glob /
    acceptance_glob — exactly the three keys flagged as reaching
    close-gate PASS at task/phase while showing ⊘ (handoff_glob was dropped from this set by
    see test_gate_never_requires_handoff_glob_key below). Under the count cap
    (2 specs), so the count-cap check cannot be what fails this — only the new required-artifact
    check. Also mutates one key back to configured to confirm the check is not vacuous: the
    row for that key must disappear from the failure while the other two still block."""
    repo = make_fixture_repo(tmp_path, MANIFEST, _docs(2, "specs"))
    result = run_gate(repo, gate_script, "milestone", "1.0")
    assert result.returncode == 1
    assert (
        "✗ milestone cannot close with required-artifact checks never configured in manifest"
        in result.stdout
    )
    for key in ("phase_docs_glob", "plan_glob", "acceptance_glob"):
        assert key in result.stdout, f"expected '{key}' named in the ✗ message:\n{result.stdout}"
    assert "handoff_glob" not in result.stdout, (
        "handoff_glob was retired from the required-artifact set — it must never "
        f"appear in the milestone failure message any more:\n{result.stdout}"
    )

    # Not-vacuous check: configuring ONE of the three keys must remove exactly that key's
    # name from the failure message while the other two keep blocking. (Separate tmp_path
    # parent dir — make_fixture_repo hardcodes a "repo" subdir, so reusing tmp_path directly
    # for a second fixture would collide with the first repo's directory.)
    partial_manifest = dict(MANIFEST, phase_docs_glob="docs/superpowers/specs/*-phase-{PHASE}-*")
    parent2 = tmp_path / "partial"
    parent2.mkdir()
    repo2 = make_fixture_repo(parent2, partial_manifest, _docs(2, "specs"))
    result2 = run_gate(repo2, gate_script, "milestone", "1.0")
    assert result2.returncode == 1, "two keys are still unconfigured — must still block"
    assert "phase_docs_glob" not in result2.stdout, (
        f"phase_docs_glob was configured — it must drop out of the unconfigured list:\n{result2.stdout}"
    )
    assert "plan_glob" in result2.stdout and "acceptance_glob" in result2.stdout


def test_milestone_mode_passes_when_required_artifacts_configured(
    tmp_path: Path, gate_script: str
) -> None:
    """All three keys configured (values need not resolve to an existing file for THIS check —
    it tests manifest wiring, not per-phase artifact existence, which is phase mode's job)."""
    manifest = {
        "test_command": "true",
        "phase_docs_glob": "docs/superpowers/specs/*-phase-{PHASE}-*",
        "plan_glob": "docs/superpowers/plans/*-phase-{PHASE}-*",
        "acceptance_glob": "tests/acceptance/**/*phase-{PHASE}*",
        "retention": {
            "journal_dir": "docs/journal.d",
            "archive_dir": "docs/archive",
            "count_caps": {"specs": 2, "plans": 2, "docs_total": 5},
        },
    }
    repo = make_fixture_repo(tmp_path, manifest, _docs(2, "specs"))
    result = run_gate(repo, gate_script, "milestone", "1.0")
    assert result.returncode == 0
    assert "not configured in manifest" not in result.stdout


def test_bare_milestone_mode_without_phase_arg_still_blocks_when_required_artifact_unconfigured(
    tmp_path: Path, gate_script: str
) -> None:
    """Regression guard for the finding that made this the whole point of that work: a bare
    `close-gate.sh milestone` (no PHASE) used to route around the required-artifact check
    entirely — silent PASS, zero output — because the check was gated on `[ -n "$PHASE" ]`.
    That gating was never architecturally justified: the check tests MANIFEST WIRING
    (`[ -n "$(g "$key")" ]`, whether a key is configured at all), not per-phase artifact
    existence, and g()'s `{PHASE}` substitution via sed does not change whether a configured,
    non-empty glob string is empty. Critically, `$(PHASE)` expanding empty is exactly what
    happens when the checked-in `make milestone-done: ; @bash scripts/close-gate.sh milestone
    $(PHASE)` wiring is invoked without `PHASE=X.Y` on the command line — the most likely way
    to hit this mode by accident. Same fixture as
    test_milestone_mode_blocks_when_required_artifact_unconfigured, minus the PHASE arg: must
    fail identically, not silently pass."""
    repo = make_fixture_repo(tmp_path, MANIFEST, _docs(2, "specs"))
    result = run_gate(repo, gate_script, "milestone")
    assert result.returncode == 1
    assert (
        "✗ milestone cannot close with required-artifact checks never configured in manifest"
        in result.stdout
    )
    for key in ("phase_docs_glob", "plan_glob", "acceptance_glob"):
        assert key in result.stdout, f"expected '{key}' named in the ✗ message:\n{result.stdout}"


def test_phase_mode_still_does_not_block_on_unconfigured_artifact_keys(
    tmp_path: Path, gate_script: str
) -> None:
    """Equivalent guard to test_phase_mode_still_does_not_block_over_count_cap, but for the
    new milestone-only ⊘ hard-fail: phase mode must keep printing the ⊘ rows for the three
    required-artifact keys without ever flipping $fail on them — only
    milestone mode's new check treats an unconfigured key as blocking."""
    repo = _make_otherwise_passing_phase_fixture(tmp_path, spec_count=2)  # under count cap too
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert "⊘ phase_docs_glob not configured in manifest" in result.stdout
    assert "⊘ plan_glob not configured in manifest" in result.stdout
    assert "⊘ acceptance_glob not configured in manifest" in result.stdout
    assert result.returncode == 0, "⊘ rows must stay non-blocking in phase mode"


def test_gate_never_requires_handoff_glob_key(tmp_path: Path, gate_script: str) -> None:
    """Regression guard: handoff_glob must never be checked by the gate again, in
    EITHER mode — not as a phase-mode artifact (bad()/req_glob), not as a milestone-mode
    required-artifact key. Configuring handoff_glob (as a project that adopted before this fix
    still might) pointing at a path with NO matching file must not fail phase mode, and must
    not appear anywhere in the gate's output."""
    manifest = {
        "test_command": "true",
        "phase_docs_glob": "docs/superpowers/specs/*-phase-{PHASE}-*",
        "plan_glob": "docs/superpowers/plans/*-phase-{PHASE}-*",
        "acceptance_glob": "tests/acceptance/**/*phase-{PHASE}*",
        # legacy leftover key — must be silently ignored, not read at all
        "handoff_glob": "docs/handoff/*-phase-{PHASE}-handoff.md",
        "retention": {
            "journal_dir": "docs/journal.d",
            "archive_dir": "docs/archive",
            "count_caps": {"specs": 2, "plans": 2, "docs_total": 5},
        },
    }
    repo = make_fixture_repo(tmp_path, manifest, _docs(2, "specs"))
    result = run_gate(repo, gate_script, "milestone", "1.0")
    assert result.returncode == 0
    assert "handoff" not in result.stdout.lower(), (
        f"a leftover handoff_glob manifest key must never surface in gate output:\n{result.stdout}"
    )


# --- reconcile the enforcement layer with the handoff-file retirement ---
#
# Milestone mode has a blocking check over phase_docs_glob/plan_glob/handoff_glob/
# acceptance_glob. A later change retired the handoff FILE. The two contradicted: handoff_glob
# configured (as /init-harness scaffolded it) -> the glob matches nothing since no handoff
# file is written any more -> phase-done hard-fails, on every single phase, out of the box.
# handoff_glob absent -> milestone hard-fails instead. No manifest value satisfied both.
#
# This is the regression guard for the whole contradiction: a manifest configured exactly the
# way /init-harness now scaffolds it (mirrors the JSON example under close-gate.md's
# "## Portable gate script" heading, minus test_command/test_evidence substituted for the
# fixture harness), in a project that follows the post-Task-7 skill correctly (no
# docs/handoff/*.md file anywhere on disk), must pass BOTH phase mode and milestone mode.
#
# Run this test file against the close-gate.md as it stood before this change (before this
# task's edits) to see it RED: phase mode fails with "no handoff doc for phase 1.0" because
# handoff_glob was configured (matching /init-harness's old scaffold) but no file matched it.


def _init_harness_scaffolded_manifest() -> dict:
    """Mirrors close-gate.md's `.claude/close-gate.json` example (post-Task-7.5: no
    handoff_glob key) as closely as a test fixture can — same key set, same glob shapes,
    {PHASE} left in place for make_fixture_repo/run_gate's own {PHASE} substitution via g()."""
    return {
        "phase_docs_glob": "docs/superpowers/specs/*-phase-{PHASE}-*",
        "plan_glob": "docs/superpowers/plans/*-phase-{PHASE}-*",
        "journal": "docs/iteration-journal.md",
        "status_doc": "docs/STATUS.md",
        "smoke_a_glob": "docs/smoke/*-phase-{PHASE}-*checklist*",
        "smoke_b_glob": "tests/e2e/**/*phase-{PHASE}*",
        "acceptance_glob": "tests/acceptance/**/*phase-{PHASE}*",
        "test_evidence": ".claude/.last-test-run",
        "test_command": "true",
        "test_runs_required": 1,
        "user_visible": True,
        "exempt_user_story": False,
        "exempt_changelog": False,
        "retention": {
            "journal_dir": "docs/journal.d",
            "archive_dir": "docs/archive",
            "count_caps": {"specs": 10, "plans": 10, "docs_total": 150},
        },
    }


def _make_init_harness_fixture(tmp_path: Path, phase: str = "1.0") -> Path:
    """A repo that has run every step of the post-Task-7 skill correctly for one phase: real
    user-story + spec + plan + acceptance-test + smoke files, CHANGELOG/ROADMAP/journal
    touched, fresh test-evidence — and, critically, NO docs/handoff/*.md file anywhere,
    because a later change retired writing one. If any manifest value could still hard-fail a
    correctly-followed post-Task-7 project, it fails here."""
    manifest = _init_harness_scaffolded_manifest()
    files = {
        f"docs/superpowers/specs/2026-01-01-phase-{phase}-x-user-story.md": "# User story\n",
        f"docs/superpowers/specs/2026-01-01-phase-{phase}-x-design.md": "# Design\n",
        f"docs/superpowers/plans/2026-01-01-phase-{phase}-x.md": "# Plan\n",
        f"tests/acceptance/x/phase-{phase}-ac1.test.js": "// ac1\n",
        f"docs/smoke/2026-01-01-phase-{phase}-checklist.md": "# Track A checklist\n",
        f"tests/e2e/x/phase-{phase}-flow.spec.ts": "// track B\n",
    }
    repo = make_fixture_repo(tmp_path, manifest, files)
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n- x\n", encoding="utf-8")
    (repo / "docs/ROADMAP.md").write_text(
        # must NAME the phase: the ROADMAP row is content-checked, not touch-checked
        "- [x] phase 1.0 — fixture row\n", encoding="utf-8"
    )
    (repo / "docs/journal.d").mkdir(parents=True, exist_ok=True)
    (repo / "docs/journal.d/2026-01-01-x.md").write_text(
        "## t\n**Plan deviations:** none\n\n### Findings\nnone\n" + _FACT_BLOCK, encoding="utf-8"
    )
    _commit(repo, "docs: wrap-up artifacts for init-harness fixture")
    time.sleep(1.1)  # see _make_otherwise_passing_phase_fixture: bash 3.2's -nt is whole-second
    (repo / ".claude/.last-test-run").write_text("ok\n", encoding="utf-8")
    return repo


def test_init_harness_scaffolded_manifest_passes_phase_mode_with_no_handoff_file(
    tmp_path: Path, gate_script: str
) -> None:
    """THE acceptance test for that retirement. A manifest configured the way /init-harness now
    scaffolds it, in a project that followed the post-Task-7 skill (wrote every wrap-up
    artifact except a handoff file, because a later change retired writing one), must pass phase
    mode cleanly — no ✗ rows at all, and specifically none naming a handoff doc."""
    repo = _make_init_harness_fixture(tmp_path, phase="1.0")
    assert not list(repo.glob("docs/handoff/**/*")), "fixture must not contain a handoff file"
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert result.returncode == 0, f"phase-done must pass a correctly-followed post-Task-7 project:\n{result.stdout}"
    assert "✗" not in result.stdout, f"no manifest value may hard-fail this project:\n{result.stdout}"
    assert "handoff" not in result.stdout.lower(), f"no handoff-doc row should exist at all:\n{result.stdout}"


def test_init_harness_scaffolded_manifest_passes_milestone_mode_with_no_handoff_file(
    tmp_path: Path, gate_script: str
) -> None:
    """Companion half of the acceptance condition: the SAME manifest shape must also pass
    milestone mode (both with and without a PHASE arg — the bare-invocation case already
    guarded) — the other side of the contradiction the brief describes."""
    repo = _make_init_harness_fixture(tmp_path, phase="1.0")
    result = run_gate(repo, gate_script, "milestone", "1.0")
    assert result.returncode == 0, f"milestone must pass a correctly-scaffolded manifest:\n{result.stdout}"
    assert "not configured in manifest" not in result.stdout

    result_bare = run_gate(repo, gate_script, "milestone")
    assert result_bare.returncode == 0, f"bare milestone (no PHASE) must pass too:\n{result_bare.stdout}"
    assert "not configured in manifest" not in result_bare.stdout


# --- FACT-entry enforcement ---
#
# journal-schema.md claimed the FACT schema (Date/Decision/Why/Rejected/Source) "is enforced"
# and close-gate.md claimed the retired handoff's non-derivable content "is enforced" via
# that schema — but nothing in the gate, close_gate_lib.py, or retention-drain.sh ever grepped
# for those field names. journal-touched only proved SOME file under journal_dir changed, which
# was already required pre-retirement — so retiring the handoff file made machine enforcement
# of its content go DOWN. These tests are the RED/GREEN pair for the check that closes that gap.

_COMPLETE_FACT = (
    "## FACT — x\n"
    "- **Date:** 2026-01-01\n"
    "- **Decision:** x\n"
    "- **Why:** x\n"
    "- **Backing:** x — measured in y\n"
    "- **Rejected:** x\n"
    "- **Source:** deadbeef:docs/x.md\n"
)

_FACT_MISSING_REJECTED = (
    "## FACT — x\n"
    "- **Date:** 2026-01-01\n"
    "- **Decision:** x\n"
    "- **Why:** x\n"
    "- **Backing:** x — measured in y\n"
    "- **Source:** deadbeef:docs/x.md\n"
)

_FACT_MISSING_BACKING = (
    "## FACT — x\n"
    "- **Date:** 2026-01-01\n"
    "- **Decision:** x\n"
    "- **Why:** x\n"
    "- **Rejected:** x\n"
    "- **Source:** deadbeef:docs/x.md\n"
)


def _make_fact_fixture(tmp_path: Path, journal_body: str) -> Path:
    """Otherwise-clean phase fixture (CHANGELOG/ROADMAP/journal all genuinely touched on a
    second commit, fresh test-evidence, no count_caps configured so no count row can be the
    cause of a failure) whose journal fragment content the caller controls — isolates the new
    FACT-entry check as the only thing that can flip `fail`. Mirrors
    `_make_otherwise_passing_phase_fixture`'s isolation technique for the count-cap tests."""
    manifest = {
        "test_command": "true",
        "test_evidence": ".claude/.last-test-run",
        "retention": {"journal_dir": "docs/journal.d", "archive_dir": "docs/archive"},
    }
    repo = make_fixture_repo(tmp_path, manifest, {})
    (repo / "docs/journal.d").mkdir(parents=True, exist_ok=True)
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n- x\n", encoding="utf-8")
    (repo / "docs/ROADMAP.md").write_text(
        # must NAME the phase: the ROADMAP row is content-checked, not touch-checked
        "- [x] phase 1.0 — fixture row\n", encoding="utf-8"
    )
    (repo / "docs/journal.d/2026-01-01-x.md").write_text(journal_body, encoding="utf-8")
    _commit(repo, "docs: wrap-up artifacts for FACT fixture")
    time.sleep(1.1)  # bash 3.2's -nt is whole-second; see _make_otherwise_passing_phase_fixture
    (repo / ".claude/.last-test-run").write_text("ok\n", encoding="utf-8")
    return repo


def test_fact_entry_complete_passes_phase_mode(tmp_path: Path, gate_script: str) -> None:
    repo = _make_fact_fixture(tmp_path, _COMPLETE_FACT)
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert result.returncode == 0, f"a complete FACT entry must not block phase-done:\n{result.stdout}"
    assert "✓ journal FACT entry has all required fields" in result.stdout, result.stdout


def test_fact_entry_missing_rejected_fails_phase_mode(tmp_path: Path, gate_script: str) -> None:
    """Mutation half of the RED/GREEN pair: removing exactly ONE required field (`Rejected`)
    from an otherwise-complete entry must flip the row from ✓ to a hard ✗ naming that field —
    proves the check actually reads content instead of vacuously passing any journal touch."""
    repo = _make_fact_fixture(tmp_path, _FACT_MISSING_REJECTED)
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert result.returncode == 1, f"a FACT entry missing a required field must hard-fail:\n{result.stdout}"
    fact_lines = [line for line in result.stdout.splitlines() if "FACT entry" in line]
    assert fact_lines, f"expected a FACT-entry row:\n{result.stdout}"
    assert fact_lines[0].startswith("✗"), fact_lines
    assert "Rejected" in fact_lines[0], f"the missing field must be named:\n{fact_lines[0]}"
    for present_field in ("Date", "Decision", "Why", "Backing", "Source"):
        assert present_field not in fact_lines[0], (
            f"a field that IS present must not be listed as missing: {fact_lines[0]}"
        )


def test_fact_entry_missing_backing_fails_phase_mode(tmp_path: Path, gate_script: str) -> None:
    """`Backing` is the evidence slot, and it is required for the same reason the other five are.

    Its absence was measured: an acceptance test distilled
    a spec into a FACT entry carried `Rejected` 7/7 and lost most of `Why`, because the schema had
    a slot for the conclusion and none for the evidence it rested on — so every argument silently
    degraded into an assertion. The single statistic the whole spec turned on,
    and a corollary the spec itself marked load-bearing, both vanished. The schema was derived from
    `references-log`, whose entries carry a `Backing` field precisely so a claim cannot be stated
    without its support — and `journal-schema.md` said so, two lines below a schema block that had
    copied `Date` and dropped `Backing`. This test is the enforcement that closes that gap."""
    repo = _make_fact_fixture(tmp_path, _FACT_MISSING_BACKING)
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert result.returncode == 1, f"a FACT entry missing Backing must hard-fail:\n{result.stdout}"
    fact_lines = [line for line in result.stdout.splitlines() if "FACT entry" in line]
    assert fact_lines, f"expected a FACT-entry row:\n{result.stdout}"
    assert fact_lines[0].startswith("✗"), fact_lines
    assert "Backing" in fact_lines[0], f"the missing field must be named:\n{fact_lines[0]}"
    for present_field in ("Date", "Decision", "Why", "Rejected", "Source"):
        assert present_field not in fact_lines[0], (
            f"a field that IS present must not be listed as missing: {fact_lines[0]}"
        )


def test_fact_entry_absent_journal_fails_phase_mode(tmp_path: Path, gate_script: str) -> None:
    """No journal fragment at all (dir never created, no monolith configured) — the newest-
    fragment lookup resolves to nothing, and the FACT check must fail closed (every field
    "missing"), not silently pass because there was nothing to grep."""
    manifest = {
        "test_command": "true",
        "test_evidence": ".claude/.last-test-run",
        "retention": {"journal_dir": "docs/journal.d", "archive_dir": "docs/archive"},
    }
    repo = make_fixture_repo(tmp_path, manifest, {})
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n- x\n", encoding="utf-8")
    (repo / "docs/ROADMAP.md").write_text(
        # must NAME the phase: the ROADMAP row is content-checked, not touch-checked
        "- [x] phase 1.0 — fixture row\n", encoding="utf-8"
    )
    _commit(repo, "docs: wrap-up artifacts, no journal fragment")
    time.sleep(1.1)
    (repo / ".claude/.last-test-run").write_text("ok\n", encoding="utf-8")
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert result.returncode == 1
    fact_lines = [line for line in result.stdout.splitlines() if "FACT entry" in line]
    assert fact_lines and fact_lines[0].startswith("✗"), f"expected a hard-fail FACT row:\n{result.stdout}"
    for field in ("Date", "Decision", "Why", "Backing", "Rejected", "Source"):
        assert field in fact_lines[0], fact_lines[0]


# --- X4: a ROADMAP touch is not the ceremony (canonical gate) ---


def test_roadmap_touched_but_not_naming_the_phase_fails(
    tmp_path: Path, gate_script: str
) -> None:
    """The sibling of a defect in the gitignored-docs gate, which checked
    mtime and printed "✓ ROADMAP.md updated this phase" while the phase appeared nowhere
    in the file. Here the proxy is a git-range touch rather than an mtime, but it fails the
    same way: a whitespace-only edit satisfies "touched" without the roadmap ever reflecting
    the phase. The row must read the file, not infer from the diff."""
    repo = _make_fact_fixture(tmp_path, _COMPLETE_FACT)
    # ROADMAP.md IS in origin/main..HEAD (the fixture committed it) — only its content
    # stops naming the phase.
    (repo / "docs/ROADMAP.md").write_text("- [x] some unrelated phase\n", encoding="utf-8")

    result = run_gate(repo, gate_script, "phase", "1.0")

    assert result.returncode == 1, (
        "gate passed a ROADMAP that never mentions the phase:\n" + result.stdout
    )
    assert "never mentions phase 1.0" in result.stdout, result.stdout


def test_roadmap_not_touched_at_all_still_fails_on_the_touch_check(
    tmp_path: Path, gate_script: str
) -> None:
    """The content check must not swallow the older touch check: a phase that never edited
    the roadmap should still be told THAT, not told the file lacks the phase id."""
    manifest = {
        "test_command": "true",
        "test_evidence": ".claude/.last-test-run",
        "retention": {"journal_dir": "docs/journal.d", "archive_dir": "docs/archive"},
    }
    # ROADMAP lands in the FIRST commit (origin/main == HEAD there), so it is absent from
    # origin/main..HEAD however green its contents are. Deleting it later would not express
    # this: a deletion is itself a change in the range.
    repo = make_fixture_repo(
        tmp_path, manifest, {"docs/ROADMAP.md": "- [x] phase 1.0 — committed before the branch\n"}
    )
    (repo / "docs/journal.d").mkdir(parents=True, exist_ok=True)
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n- x\n", encoding="utf-8")
    (repo / "docs/journal.d/2026-01-01-x.md").write_text(_COMPLETE_FACT, encoding="utf-8")
    _commit(repo, "docs: everything except the roadmap")
    time.sleep(1.1)
    (repo / ".claude/.last-test-run").write_text("ok\n", encoding="utf-8")

    result = run_gate(repo, gate_script, "phase", "1.0")

    assert result.returncode == 1
    assert "not updated in" in result.stdout, result.stdout
