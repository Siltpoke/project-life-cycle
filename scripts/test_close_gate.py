"""The canonical close-gate bash lives inside references/close-gate.md.
These tests extract it and actually run it — nothing else in this repo does."""
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from close_gate_lib import (
    extract_gate_script,
    extract_self_test_script,
    make_fixture_repo,
    run_gate,
)

GATE_MD = Path(__file__).resolve().parents[1] / "skills/project-lifecycle/references/close-gate.md"


@pytest.fixture(scope="module")
def gate_script() -> str:
    return extract_gate_script(GATE_MD)


def test_extracts_a_runnable_bash_script(gate_script: str) -> None:
    assert gate_script.startswith("#!/usr/bin/env bash")
    assert 'MODE="${1:?' in gate_script


def test_self_test_extractor_is_not_fooled_by_a_decoy_self_test_heading(tmp_path: Path) -> None:
    """`close_gate_lib._SELF_TEST_HEADING` was tightened from the prefix `"## Self-test"` to the full
    heading; this is the oracle that tightening did not have. A decoy is written into a COPY of the
    real markdown, EARLIER in the document than the genuine heading, because `str.find` returns the
    first hit — under the old prefix anchor the extractor would have walked to the decoy's fence and
    returned it, while every assertion phrased as "the harness does X" kept passing against a fence
    that is not the harness.

    A copy of the real file, not a hand-built minimal document: the thing under test is which of
    SEVERAL bash fences in THIS doc gets picked, and a two-fence fixture cannot pose that question.
    The decoy is inserted immediately before the `## Portable gate script` heading — comfortably
    ahead of §Self-test, and its fence opens with the same `#!/usr/bin/env bash` line the fence
    regex requires, so the decoy is a fence the extractor genuinely could return."""
    real = GATE_MD.read_text(encoding="utf-8")
    anchor = "## Portable gate script"
    assert anchor in real, anchor
    decoy_marker = "DECOY-FENCE-NOT-THE-HARNESS"
    decoy = (
        "## Self-test — something else\n\n"
        "```bash\n"
        "#!/usr/bin/env bash\n"
        f"echo {decoy_marker}\n"
        "```\n\n"
    )
    md = tmp_path / "close-gate.md"
    md.write_text(real.replace(anchor, decoy + anchor, 1), encoding="utf-8")

    extracted = extract_self_test_script(md)
    assert decoy_marker not in extracted, (
        "extract_self_test_script returned the DECOY fence — its heading anchor is a prefix of "
        "`## Self-test — something else`, so a section added earlier in the doc silently becomes "
        f"'the harness':\n{extracted}"
    )
    assert extracted == extract_self_test_script(GATE_MD), (
        "the decoy did not change what is returned, but the returned fence is not the real "
        "harness either — the extractor moved for some other reason and this test now watches "
        "nothing"
    )


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
    neither a ✓ nor silence. Before the gate printed that row, these four printed a VACUOUS ✓:
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
        # "empty (sub)expression" on that. A later fix made the gate build the alternation only
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
        # count_caps itself is entirely ABSENT — the same gap the gate had already closed for req_glob and
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
    docs, which loses the record, or raising the cap, which disables the gate). This test
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
# contract and REPLACE the earlier `.git/HEAD`-mtime fixtures: `.git/HEAD`'s mtime does
# not track HEAD (`git commit` leaves it at checkout time), so those fixtures anchored the freshness
# comparison to the wrong file. `find -newer`'s own sub-second ordering (the original same-second
# freshness property) is unchanged in `fresh()`; the evidence row simply no longer feeds it a sub-second
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
    """The residual, pinned so it is not silently "fixed": the committer-date stamp is whole-second
    (`touch -t`), so evidence in the SAME wall-clock second as the commit reads FRESH — a ≤1s fail-OPEN
    window, and the correct side in the realistic run-tests-then-commit order. This also preserves the
    original same-second freshness intent (genuinely-fresh evidence written <1s after the commit must not read
    stale). If a future change makes this fail-closed, that is a deliberate decision this test forces
    into the open rather than letting it ride in as an accident."""
    manifest = {"test_command": "true", "test_evidence": ".claude/.last-test-run"}
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    _commit_at(repo, "feat: work", epoch=1_000_000)
    _write_evidence_at_ns(repo, 1_000_000 * _NS_PER_SEC + 500_000_000)  # same second, +0.5s
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✓"), f"same-second evidence reads fresh (≤1s residual): {rows}"


# --- legacy evidence freshness anchors to HEAD's committer-date, not .git/HEAD's mtime ---
# `git commit` does NOT advance .git/HEAD's file mtime (verified: it stays at init/checkout time),
# so `fresh "$EV" .git/HEAD` compares evidence against WHEN THE BRANCH WAS CHECKED OUT, not against
# the commit it claims to cover. Evidence written between an early checkout and a later commit then
# false-PASSES as fresh though it predates HEAD. The fix anchors freshness to HEAD's committer-date
# (the semantic commit time), accepting the documented ≤1s whole-second truncation as the residual.


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
    """The defect, reproduced: `.git/HEAD` mtime is stuck at checkout time (`git commit` does
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


# --- task-mode check #1 is path-based (product_paths) with a verb fallback ---
# Ports the local gate's product-tree check into the canonical gate. The old `feat|fix` commit-verb
# test was a proxy for "the task shipped a product change"; a legit refactor-only commit under the
# product tree had to be mislabeled `feat` to pass. BACKWARD-COMPATIBLE: an absent product_paths
# key falls back to the legacy verb check, so no existing adopter manifest changes behavior.

_PRODUCT_PATHS_MANIFEST = {"product_paths": ["src/"], "test_command": "true", "test_evidence": ".claude/.last-test-run"}


def test_task_product_tree_touch_passes_on_a_refactor_commit(tmp_path: Path, gate_script: str) -> None:
    """A `refactor:` commit (NOT feat/fix) that touches a product_paths dir passes check #1 —
    the exact case the verb check wrongly failed."""
    repo = make_fixture_repo(tmp_path, _PRODUCT_PATHS_MANIFEST, {"README.md": "hi\n"})
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
    repo = make_fixture_repo(tmp_path, _PRODUCT_PATHS_MANIFEST, {"README.md": "hi\n"})
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
    repo = make_fixture_repo(tmp_path, _PRODUCT_PATHS_MANIFEST, {"src/app.py": "x = 1\n"})
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


# --- task-mode test-evidence is a content fingerprint when test_evidence_inputs is declared ---
# Ports the local gate's fingerprint check into the canonical gate. Opt-in: declaring
# test_evidence_inputs switches the row from the legacy mtime check to a content digest of the
# declared inputs. Absent key → legacy mtime unchanged (backward-compatible).

_FINGERPRINT_MANIFEST = {
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
    repo = make_fixture_repo(tmp_path, _FINGERPRINT_MANIFEST, {"src/app.py": "x = 1\n"})
    out = run_gate(repo, gate_script, "evidence-header").stdout
    assert out.startswith("# plc-gate-evidence inputs="), f"header shape wrong: {out!r}"
    digest = out.split("inputs=", 1)[1].strip()
    assert len(digest) >= 40 and all(c in "0123456789abcdef" for c in digest), f"not a hex digest: {digest!r}"


def test_task_fingerprint_matches_passes(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, _FINGERPRINT_MANIFEST, {"src/app.py": "x = 1\n"})
    _headed_evidence(repo, gate_script)
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✓"), f"a matching fingerprint must pass:\n{result.stdout}"


def test_task_fingerprint_stale_when_a_declared_input_changes(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, _FINGERPRINT_MANIFEST, {"src/app.py": "x = 1\n"})
    _headed_evidence(repo, gate_script)
    # change a declared input AFTER the header was generated → digest no longer matches
    (repo / "src/app.py").write_text("x = 999\n", encoding="utf-8")
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✗") and "stale" in rows[0], (
        f"a changed input must read stale:\n{result.stdout}"
    )


def test_task_fingerprint_missing_header_hard_fails(tmp_path: Path, gate_script: str) -> None:
    repo = make_fixture_repo(tmp_path, _FINGERPRINT_MANIFEST, {"src/app.py": "x = 1\n"})
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
    manifest = {**_FINGERPRINT_MANIFEST, "test_evidence_inputs": ["does-not-exist/**"]}
    repo = make_fixture_repo(tmp_path, manifest, {"src/app.py": "x = 1\n"})
    _headed_evidence(repo, gate_script)  # header will carry the EMPTY sentinel
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "matched no tracked files" in ln]
    assert rows and rows[0].startswith("✗"), (
        f"inputs matching nothing must fail closed, not pass vacuously:\n{result.stdout}"
    )


def test_task_malformed_test_evidence_inputs_fails_closed(tmp_path: Path, gate_script: str) -> None:
    manifest = {**_FINGERPRINT_MANIFEST, "test_evidence_inputs": "src/"}  # string, not array
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
    HARD FAIL (byte-identical to the blocks before the fingerprint option), never warn-and-skip. Guards against the
    vacuous-pass-on-absent-key defect the refactor's shared entry point could have reintroduced."""
    manifest = {"test_command": "true"}  # test_evidence deliberately absent
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if "test-evidence" in ln]
    assert rows and rows[0].startswith("✗") and "stale/missing" in rows[0], (
        f"absent test_evidence must hard fail, not skip:\n{result.stdout}"
    )


# --- what row 7's ✓ is ALLOWED to claim ---
#
# Deliberately adjacent to the fingerprint tests above: those pin what the row DOES, these pin
# what its ✓ may SAY: never more than the mechanism behind it. The listed wordings ("fresh",
# "since it ran", anything beyond the caller-owned detail string) each assert more
# than the mechanism behind it — the gate reads a FILE and no branch of it observes a process.
#
# This same assertion also lives in the embedded self-test harness in references/close-gate.md.
# The two intentionally cover the SAME locked contract in different execution contexts —
# the harness is what adopters materialize, and this file is the only layer in this repo that is
# actually executed here, so it is the only one whose red path can be observed. Neither replaces the
# other. `ROW7_FORBIDDEN_TOKENS` and `ROW7_CONTRACT_PHRASE` below are mirrored BYTE-IDENTICALLY into
# that harness; a change to either literal must be made in both places, and there is a
# cross-file check that reddens on divergence.

# The claim this row is permitted to make, in prose. It is the failure message's payload — a
# maintainer who trips one of these assertions is told the contract, not just that a token matched,
# because the token list cannot be complete (see ROW7_FORBIDDEN_TOKENS).
ROW7_CONTRACT_PHRASE = (
    "this row may only claim fingerprint/evidence agreement, not test execution"
)

# GUIDANCE, NOT ENFORCEMENT. These four wordings each overclaim what this row can know;
# matching one is a tripwire for that specific phrasing, NOT a proof that the
# row is honest. An unlisted synonym ("verified", "confirmed", "attests") passes this list and
# reintroduces the same claim-creep. What stops that is a human reading ROW7_CONTRACT_PHRASE when
# rewording — which is why the phrase is in the failure message. Claiming this list were exhaustive
# would be the very defect (a claim wider than its mechanism) these tests exist to catch.
ROW7_FORBIDDEN_TOKENS = ("fresh", "since it ran", "proves", "proving")

# The nouns the ✓ must still carry for a reader to know what was compared against what. Pinned as
# load-bearing CONTENT rather than as a sentence: an anchor on a memorable phrase breaks on a
# legitimate re-wrap (false red) and survives the explanation being deleted (false green).
# Not part of the byte-identical mirror — that covers the forbidden list and the phrase.
#
# The last entry is the DISCLAIMER, and it is the one that does real work. Review demonstrated two
# rows that keep every other token, add no banned token, and still lie:
#   "…are unchanged and the test command that generated this file ran clean"
#   "…are unchanged, verifying the suite that generated it passed"
# Both die on the disclaimer. Banning the bare word `ran` is not available — the honest row says
# "NOT proof a test command ran" — so the cheap fix has to be a REQUIRED token, not a forbidden one.
ROW7_REQUIRED_TOKENS = (
    "test_evidence_inputs",
    "unchanged",
    "generated",
    "NOT proof a test command ran",
)

# The legacy mtime mode's ✓ makes a DIFFERENT claim (mtime, not a fingerprint), so it needs its own
# required set — but it is the same row, printed by the same helper, and it is the DEFAULT path:
# `test_evidence_inputs` is opt-in, and the example manifest this file scaffolds does not declare
# it. Scoping the guard to the mode this repo happens to run would leave most adopters' row 7
# unguarded, which is the shape of the defect being repaired. The banned list applies to both.
ROW7_LEGACY_REQUIRED_TOKENS = ("mtime", "not evidence")


def _normalised(row: str) -> str:
    """Collapse ASCII whitespace runs to a single space and lower-case, so a re-wrapped or
    re-indented row still matches on content and `Fresh` cannot slip past the token list.

    Deliberately ASCII-only rather than `str.split()` + `str.casefold()`, and the bash mirror pins
    `LC_ALL=C` on its `tr` pair — the two halves together are what make the homes agree, and the
    first version of this comment claimed the ASCII half alone was enough. Measured on macOS, BSD
    `tr -s '[:space:]'` under a UTF-8 locale IS multibyte-aware: a banned wording separated by
    non-breaking spaces was caught by the bash home and missed here, i.e. green in the layer that
    runs and red in the layer that does not, with the literal-mirror comparison green throughout
    because the literals never moved. With the locale pinned both homes agree — and they agree on
    MISSING that row. Named limitation, not a claim of coverage."""
    return re.sub(r"[ \t\r\n\f\v]+", " ", row).lower()


def assert_row7_names_its_evidence_basis(
    row: str, required: tuple[str, ...] = ROW7_REQUIRED_TOKENS
) -> None:
    """The ✓ exists and says what it compared. A banned-claims assertion alone is
    structurally blind to the row DISAPPEARING: deleting it removes the offending words too, and a
    negative-only test goes green on an empty screen."""
    folded = _normalised(row)
    missing = [tok for tok in required if tok.lower() not in folded]
    assert not missing, (
        f"row 7's ✓ no longer names its evidence basis (missing {missing}) — "
        f"{ROW7_CONTRACT_PHRASE}, and it has to say which fingerprint it means. "
        f"row: {_normalised(row)!r}"
    )


def assert_row7_makes_no_execution_claim(row: str) -> None:
    """The ✓ carries none of the wordings that have previously smuggled an execution or
    freshness claim into a statement about bytes."""
    folded = _normalised(row)
    banned = [tok for tok in ROW7_FORBIDDEN_TOKENS if tok in folded]
    assert not banned, (
        f"row 7's ✓ makes an execution/freshness claim {banned} — "
        f"{ROW7_CONTRACT_PHRASE}. "
        f"row: {_normalised(row)!r}"
    )


def _row7_ok_row(tmp_path: Path, gate_script: str) -> str:
    """The ✓ the fingerprint mode actually prints, taken from a real gate run rather than from the
    gate's source text — a source-text assertion cannot tell a row that is present from one that is
    unreachable. Scoped to the fingerprint mode (the mode this repo declares, and the one whose
    wording was repaired for); the legacy mtime ✓ carries a different, mtime-specific claim.

    The exactly-one requirement is part of the assertion, not fixture hygiene: if the ✓ is deleted
    this raises here rather than letting a downstream `for row in rows` pass vacuously."""
    repo = make_fixture_repo(tmp_path, _FINGERPRINT_MANIFEST, {"src/app.py": "x = 1\n"})
    _headed_evidence(repo, gate_script)
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if ln.startswith("✓") and "test-evidence" in ln]
    assert len(rows) == 1, (
        f"expected exactly one passing test-evidence row, got {rows} — "
        f"{ROW7_CONTRACT_PHRASE}, and it cannot claim anything at all if it is not printed.\n"
        f"{result.stdout}"
    )
    return rows[0]


def _row7_legacy_ok_row(tmp_path: Path, gate_script: str) -> str:
    """The ✓ the LEGACY mtime mode prints — the default path, reached by any manifest that does not
    opt into `test_evidence_inputs`. Same helper, same row, different claim."""
    manifest = {"test_command": "true", "test_evidence": ".claude/.last-test-run"}
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "hi\n"})
    _commit_at(repo, "feat: work", epoch=1_000_000)
    _write_evidence_at_ns(repo, 1_000_002 * _NS_PER_SEC)  # 2s after the commit -> fresh
    result = run_gate(repo, gate_script, "task")
    rows = [ln for ln in result.stdout.splitlines() if ln.startswith("✓") and "test-evidence" in ln]
    assert len(rows) == 1, (
        f"expected exactly one passing test-evidence row in legacy mode, got {rows} — "
        f"{ROW7_CONTRACT_PHRASE}, and it cannot claim anything at all if it is not printed.\n"
        f"{result.stdout}"
    )
    return rows[0]


def test_row7_ok_names_the_fingerprint_it_checked(tmp_path: Path, gate_script: str) -> None:
    """The positive half. Reddens when the row is removed or stops naming its basis."""
    assert_row7_names_its_evidence_basis(_row7_ok_row(tmp_path, gate_script))


def test_row7_ok_claims_no_test_execution(tmp_path: Path, gate_script: str) -> None:
    """The negative half. Reddens when a repaired wording is re-introduced."""
    assert_row7_makes_no_execution_claim(_row7_ok_row(tmp_path, gate_script))


def test_row7_legacy_mtime_row_is_held_to_the_same_contract(
    tmp_path: Path, gate_script: str
) -> None:
    """Both halves on the mode most adopters actually run. The helper's contract comment says the
    adjective "asserted more than EITHER mode actually checks" and names two callers; guarding one
    of them would leave the other free to regain the claim, which is how this row got repaired
    three times already."""
    row = _row7_legacy_ok_row(tmp_path, gate_script)
    assert_row7_makes_no_execution_claim(row)
    assert_row7_names_its_evidence_basis(row, required=ROW7_LEGACY_REQUIRED_TOKENS)


@pytest.mark.parametrize("token", ROW7_FORBIDDEN_TOKENS)
def test_every_forbidden_token_has_an_observed_red_path(token: str) -> None:
    """Each entry in the banned list must actually redden something. Review shrank the tuple to a
    single token and all three tests stayed green: `fresh` (the regression the list was built
    for), `proves` and `proving` were load-bearing in the list and inert in the tests — a guard
    nobody had watched fire is exactly what this file exists to remove."""
    row = f"✓ test-evidence non-empty; declared test_evidence_inputs are {token} unchanged"
    with pytest.raises(AssertionError) as caught:
        assert_row7_makes_no_execution_claim(row)
    assert token in str(caught.value), caught.value


@pytest.mark.parametrize("token", ROW7_REQUIRED_TOKENS)
def test_every_required_token_has_an_observed_red_path(token: str) -> None:
    """Mirror of the above for the presence half: drop exactly one required token from an otherwise
    complete row and watch that specific token reported missing."""
    row = "✓ test-evidence non-empty; " + " ".join(
        tok for tok in ROW7_REQUIRED_TOKENS if tok != token
    )
    with pytest.raises(AssertionError) as caught:
        assert_row7_names_its_evidence_basis(row)
    assert token in str(caught.value), caught.value


def test_row7_matching_survives_a_rewrap_and_ignores_case() -> None:
    """The normalisation is load-bearing in both directions and neither behaviour was exercised:
    deleting the case fold or the whitespace collapse left every test green. A row re-wrapped by a
    later editor must still match (false red), and a capitalised banned word must still be caught
    (false green)."""
    # The multi-word required token is deliberately split ACROSS the wrap: with every token on one
    # line, dropping the whitespace collapse reddened nothing — the first version of this test
    # exercised the case fold only, and said so in its name. Measured, not assumed.
    wrapped = (
        "✓ test-evidence non-empty; declared test_evidence_inputs\n   are unchanged since this "
        "file was\tgenerated — NOT proof a\n   test command ran"
    )
    assert_row7_names_its_evidence_basis(wrapped)  # must NOT raise

    with pytest.raises(AssertionError):
        assert_row7_makes_no_execution_claim("✓ test-evidence non-empty; FRESH evidence")


def test_row7_assertions_state_the_contract_when_they_fire() -> None:
    """The message is the deliverable, not just the red.

    Both assertions above would pass their own checks while failing with a bare "assert not banned",
    and the one clause the human locked — that this row may claim agreement, never execution —
    would be dropped. Since the token list is admittedly incomplete, the message is the only thing
    that tells the next maintainer what an unlisted synonym would be violating. Asserted on both
    assertions: genericising either one in isolation must redden.

    The first line below is not ceremony. Without it this test was SELF-CERTIFYING: both messages
    are built by interpolating `ROW7_CONTRACT_PHRASE`, so emptying that constant made every message
    lose the locked clause and all three tests still passed — and the byte-identical cross-file
    check cannot catch it either, since both copies would be empty and still identical. The clause
    is therefore spelled out here, independent of the constant it guards."""
    assert ROW7_CONTRACT_PHRASE == (
        "this row may only claim fingerprint/evidence agreement, not test execution"
    ), f"the locked contract clause was reworded or emptied: {ROW7_CONTRACT_PHRASE!r}"

    # Same reasoning one level down: the per-token tests parametrize over the tuples, so SHRINKING
    # a tuple silently removes tests instead of failing any. These two entries are the ones with a
    # shipped history — `fresh` is the regression the banned list was built for, and the
    # disclaimer is what kills a row that keeps every other token and still claims execution.
    assert "fresh" in ROW7_FORBIDDEN_TOKENS
    assert "NOT proof a test command ran" in ROW7_REQUIRED_TOKENS

    with pytest.raises(AssertionError) as banned_claim:
        assert_row7_makes_no_execution_claim(
            "✓ test-evidence non-empty; declared test_evidence_inputs are unchanged since it ran"
        )
    assert ROW7_CONTRACT_PHRASE in str(banned_claim.value), (
        f"the banned-claims failure must state the contract, got: {banned_claim.value}"
    )

    with pytest.raises(AssertionError) as missing_basis:
        assert_row7_names_its_evidence_basis("✓ test-evidence non-empty; looks good to me")
    assert ROW7_CONTRACT_PHRASE in str(missing_basis.value), (
        f"the presence failure must state the contract, got: {missing_basis.value}"
    )


# --- the two homes of the row-7 contract may not drift apart ---
#
# The extraction rule lives ONCE, in close_gate_lib beside the other two extractors. A private
# copy here would be a third statement of "which fence is the harness" in a task whose whole
# subject is two copies that can silently disagree.
def _embedded_harness() -> str:
    """The self-test harness's bash source, as an adopter materializes it."""
    return extract_self_test_script(GATE_MD)


def _strip_bash_comments(src: str) -> str:
    """`#`-to-end-of-line removed, so a mention of a variable inside a COMMENT cannot stand in for
    the code that expands it. Deliberately not shell-aware: a `#` inside a string would truncate a
    real line and can therefore only cause a FALSE RED, never a false green — and both expansions
    this guards live inside double quotes in the harness, where a bare `#` does not appear."""
    return "\n".join(ln.split("#", 1)[0] for ln in src.splitlines())


def test_row7_contract_literals_are_identical_in_both_homes() -> None:
    """TWO homes for this contract were accepted knowingly; this is the assertion that
    stops them becoming two contracts. It reads the forbidden-token list and the contract phrase
    out of the embedded harness and compares them to the constants above.

    The comparison is one-directional on purpose: the constants above are the source, the harness
    is the mirror, and nothing here re-states either literal. A canonical third copy to compare
    both against would put the contract in three places — the failure mode this check exists to
    prevent, one layer up.

    Scope, stated because it is narrower than it looks: this covers these two literals ONLY. It
    does NOT cover ROW7_REQUIRED_TOKENS (which is mode detail — the two evidence modes name
    different nouns, and the harness deliberately asserts the load-bearing half of each rather
    than mirroring the tuples), and it does NOT cover the MATCHING SEMANTICS. Two byte-identical
    token lists compared with different normalisers are still two contracts; that is why
    `_normalised()` folds ASCII whitespace only AND the harness pins `LC_ALL=C` on its `tr` pair.
    Those are the two halves of one agreement, not a rationale and a detail: measured on macOS,
    BSD `tr -s '[:space:]'` under a UTF-8 locale is multibyte-aware, so without the locale pin the
    bash home caught a banned wording separated by non-breaking spaces that this home missed —
    green in the layer that does not run and red in the layer that does, with the comparison below
    green throughout because the literals never moved. A divergence there is invisible to this
    check."""
    harness = _embedded_harness()

    # findall, not search: `search` reads the FIRST lexical definition, so appending a second
    # assignment later in the harness leaves this check green while the harness RUNS with the
    # override — a divergence this check is required to see. Exactly one definition, or it is a finding.
    phrases = re.findall(r"^ROW7_CONTRACT_PHRASE='(.*)'$", harness, re.M)
    assert len(phrases) == 1, (
        f"the embedded harness defines ROW7_CONTRACT_PHRASE {len(phrases)} times "
        f"({phrases}) — zero means the mirror was moved, renamed, re-indented, re-wrapped or "
        "re-quoted; more than one means a later re-assignment silently overrides the mirror this "
        "check reads"
    )
    phrase_value = phrases[0]
    assert phrase_value == ROW7_CONTRACT_PHRASE, (
        "the contract phrase diverged between its two homes:\n"
        f"  scripts/test_close_gate.py: {ROW7_CONTRACT_PHRASE!r}\n"
        f"  references/close-gate.md:   {phrase_value!r}\n"
        "a change to this literal has to be made in BOTH places"
    )

    token_defs = re.findall(r"^ROW7_FORBIDDEN_TOKENS=\((.*)\)$", harness, re.M)
    assert len(token_defs) == 1, (
        f"the embedded harness defines ROW7_FORBIDDEN_TOKENS {len(token_defs)} times "
        f"({token_defs}) — zero means the mirror was moved, renamed, re-indented, re-wrapped or "
        "re-quoted; more than one means a later re-assignment silently overrides the mirror this "
        "check reads"
    )
    mirrored = tuple(shlex.split(token_defs[0]))
    assert mirrored == ROW7_FORBIDDEN_TOKENS, (
        "the forbidden-token list diverged between its two homes:\n"
        f"  scripts/test_close_gate.py: {list(ROW7_FORBIDDEN_TOKENS)}\n"
        f"  references/close-gate.md:   {list(mirrored)}\n"
        "a change to this literal has to be made in BOTH places"
    )

    # Byte-identical literals sitting in a block nobody reads would satisfy everything above, so
    # the mirror also has to be LIVE: each literal must be expanded somewhere in the harness's
    # code. Matched against comment-stripped source — the first version read the raw fence, and
    # deleting the banned-claims loop while leaving a comment that MENTIONS the variable kept it
    # green. Deliberately not a count: a later refactor into a helper is legitimate.
    code = _strip_bash_comments(harness)
    assert '"${ROW7_FORBIDDEN_TOKENS[@]}"' in code, (
        "the embedded harness defines ROW7_FORBIDDEN_TOKENS but never expands it — the mirrored "
        "literal is dead and the harness no longer asserts the banned-claims half"
    )
    assert "$ROW7_CONTRACT_PHRASE" in code, (
        "the embedded harness defines ROW7_CONTRACT_PHRASE but never expands it — its assertion "
        "would fire without stating the contract, which is the locked clause"
    )


# --- the context-floor arming row reports THREE states, never two ---
#
# The row used to answer one question — is the hook named in a settings file — and print a ✓ that a
# reader takes as "the floor is on". Wiring is liveness; being able to run is readiness. The hook's
# first act is `command -v jq >/dev/null || exit 0`, so a wired floor on a machine without jq is
# silently off, and `hooks/context-floor.sh`'s comment justified that fail-open by pointing at an
# arming warning that did not exist. Three states now: not wired · wired · wired but inert.
#
# Everything below is the row-7 shape reused rather than a second style: `_normalised()` above does
# the folding, a forbidden-token tuple carries the known-bad wordings, and the failure message
# states the contract because the tuple cannot be complete.

# What this row is permitted to claim, in prose — the payload of every failure message here. The
# check is a gate-time `command -v jq` in the gate's own process; it cannot observe the environment
# the hook is later spawned in (a GUI client with a stripped PATH is the concrete blind spot, named
# in the row's own comment in the gate, not in its output).
FLOOR_CONTRACT_PHRASE = (
    "this row may only claim that jq was resolvable when the gate ran, not that the hook works"
)

# GUIDANCE, NOT ENFORCEMENT — the same honest limitation the row-7 list carries. These are the three
# claims the human locked as out of bounds for this row ("works", "will run", "verified"); an
# unlisted synonym ("functional", "active", "confirmed") passes the list and reintroduces the same
# claim-creep. What stops that is a maintainer reading FLOOR_CONTRACT_PHRASE when rewording, which
# is why the phrase is in the message rather than a bare "assert not banned".
FLOOR_FORBIDDEN_TOKENS = ("works", "will run", "verified")

# The three states' discriminators. Chosen so that no marker is a substring of another state's row
# — the point is that the states do not BLUR, and a marker that matched two of them would
# be a test that cannot tell them apart while looking like one that can. `context-floor hook wired`
# on its own is exactly that trap (it matches both the wired and the inert row), so the wired
# marker carries its parenthetical and the inert marker carries `but inert`.
FLOOR_STATE_MARKERS = {
    "not wired": "context-floor hook not wired",
    "wired": "context-floor hook wired (settings reference context-floor.sh)",
    "wired but inert": "context-floor hook wired but inert",
}

# What the ✓ must still SAY, so the wired row cannot be gutted to a bare "wired" and keep passing:
# the basis (a gate-time probe) and the disclaimer. The disclaimer is load-bearing for the same
# reason row 7's is — a row can keep every other token, add no banned token, and still imply the
# hook is live. Banning the bare word "run" is not available (the honest row talks about the gate
# having run), so the cheap guard has to be a REQUIRED token.
FLOOR_WIRED_REQUIRED_TOKENS = (
    "jq was resolvable when this gate ran",
    "not proof the hook fires",
)


def assert_floor_row_claims_no_hook_capability(row: str) -> None:
    """The row's text may not outrun its check."""
    folded = _normalised(row)
    banned = [tok for tok in FLOOR_FORBIDDEN_TOKENS if tok in folded]
    assert not banned, (
        f"the context-floor arming row claims hook capability {banned} — "
        f"{FLOOR_CONTRACT_PHRASE}. "
        f"row: {_normalised(row)!r}"
    )


def assert_floor_wired_row_names_its_basis(row: str) -> None:
    """The positive half: a banned-claims assertion alone goes green on a row that says nothing."""
    folded = _normalised(row)
    missing = [tok for tok in FLOOR_WIRED_REQUIRED_TOKENS if tok.lower() not in folded]
    assert not missing, (
        f"the wired ✓ no longer names what it checked (missing {missing}) — "
        f"{FLOOR_CONTRACT_PHRASE}, and it has to say which probe it means. "
        f"row: {_normalised(row)!r}"
    )


def test_floor_state_markers_are_identical_in_all_their_homes() -> None:
    """The literal-mirror check's twin, for the floor contract. The three markers above have a THIRD home nobody was
    comparing: the embedded harness hand-copies them into its own `FLOOR_NOT_WIRED` /
    `FLOOR_WIRED` / `FLOOR_INERT` shell variables, and until this check the only thing holding the
    two lists together was that they had been typed together.

    Rewording the inert marker in BOTH gates and in FLOOR_STATE_MARKERS while
    leaving the harness literal stale left the whole suite green — and the harness's
    `grep -qF "$FLOOR_INERT"` could then never match the row it asserts, so its state-3 row would
    print ✗ forever, in the layer this repo does not run.

    Same shape and same direction as test_row7_contract_literals_are_identical_in_both_homes: the
    constants above are the source, the harness is the mirror, nothing here re-types either side,
    and a canonical third literal to compare both against would be the very failure this check
    exists to prevent, one level up. `findall` with an exactly-one guard per name rather than
    `search`, because `search` reads the FIRST lexical definition and a re-assignment appended
    later would silently override the mirror while this check kept reading the old one.

    Scope, narrower than it looks: the three MARKERS only. The harness's `FLOOR_SETTINGS` fixture
    JSON is not covered (it is fixture detail, not the contract), and neither is the harness's
    each-state-excludes-the-other-two STRUCTURE — that is shape rather than a literal, and it has
    its own row in the harness's output."""
    harness = _embedded_harness()

    for var, state in (
        ("FLOOR_NOT_WIRED", "not wired"),
        ("FLOOR_WIRED", "wired"),
        ("FLOOR_INERT", "wired but inert"),
    ):
        defs = re.findall(rf"^{var}='(.*)'$", harness, re.M)
        assert len(defs) == 1, (
            f"the embedded harness defines {var} {len(defs)} times ({defs}) — zero means the "
            "mirror was moved, renamed, re-indented, re-wrapped or re-quoted; more than one means "
            "a later re-assignment silently overrides the mirror this check reads"
        )
        assert defs[0] == FLOOR_STATE_MARKERS[state], (
            f"the {state!r} state marker diverged between its homes:\n"
            f"  scripts/test_close_gate.py FLOOR_STATE_MARKERS[{state!r}]: "
            f"{FLOOR_STATE_MARKERS[state]!r}\n"
            f"  references/close-gate.md {var}: {defs[0]!r}\n"
            "a change to this literal has to be made in BOTH places (and in both gates' rows)"
        )

        # Byte-identical literals in a block nobody expands would satisfy everything above, so the
        # mirror also has to be LIVE — same liveness clause as the row-7 twin, matched against
        # comment-stripped source so a mention inside a comment cannot stand in for the code.
        assert f'"${var}"' in _strip_bash_comments(harness), (
            f"the embedded harness defines {var} but never expands it — the mirrored literal is "
            f"dead and the harness no longer asserts the {state!r} state through it"
        )


# Extracted from the gate's real bytes, never re-typed here. `floor_arming_row` takes no arguments
# and reads no gate state precisely so these bytes can be run on their own — which is the only way
# to observe the inert branch at all (see test_floor_row_wired_but_inert_... for the measurement
# that proves the full gate cannot reach it).
_FLOOR_ROW_FN = re.compile(r"^floor_arming_row\(\) \{$.*?^\}$", re.M | re.S)
_FLOOR_ROW_HELPERS = re.compile(r"^(?:ok|warn)\(\).*$", re.M)


def _floor_row_body(gate_script: str) -> str:
    """The row's definition, verbatim from the gate. Every reader of `_FLOOR_ROW_FN` goes through
    here: a bare `findall(...)[0]` raises `IndexError: list index out of range` when the row is
    renamed, inlined or re-indented — the one situation in which the message has to say what
    happened, because at that point these tests are watching nothing and nothing else says so."""
    fns = _FLOOR_ROW_FN.findall(gate_script)
    assert len(fns) == 1, (
        f"expected exactly one floor_arming_row definition in the gate, found {len(fns)} — "
        "zero means the row was renamed, inlined or re-indented and these tests now watch nothing"
    )
    return fns[0]


def _floor_row_only_script(gate_script: str) -> str:
    """The row plus the two printers it calls, verbatim, under the gate's own shell options.

    Deliberately not a hand-written `ok()`/`warn()` stub: an unfaithful stub of the thing under
    test is how a green test stops meaning anything. `set -euo pipefail` is copied in for the
    same reason — `grep -qs` returning 1 under `set -e` is a live hazard for this exact row."""
    body = _floor_row_body(gate_script)
    helpers = _FLOOR_ROW_HELPERS.findall(gate_script)
    assert len(helpers) == 2, f"expected the ok()/warn() printers, found {helpers}"
    return "set -euo pipefail\n" + "\n".join(helpers) + "\n" + body + "\nfloor_arming_row\n"


# The THREE settings files the row greps, by the label these tests wire through. Every fixture in
# the first version of this file wrote the PROJECT `.claude/settings.json` and nothing else, so
# deleting the user-global entry — the location the ⚠ names FIRST, and the one the rationale calls
# the primary home of a machine-local hook — from the grep list passed the whole suite. A list of
# paths needs one fixture per path or the extra entries are decoration.
_FLOOR_SETTINGS_LOCATIONS = {
    "home": ("home", ".claude/settings.json"),
    "project": ("proj", ".claude/settings.json"),
    "project-local": ("proj", ".claude/settings.local.json"),
}

# The wiring the row is meant to find, and the near-miss that proves the pattern is the string the
# ✓ names. The near-miss says `context-floor` WITHOUT `.sh`, which the old `'context-floor'` pattern
# matched while the ✓ claimed "settings reference context-floor.sh".
_FLOOR_WIRED_SETTINGS = (
    '{"hooks":{"PreToolUse":[{"matcher":"Edit|Write","hooks":'
    '[{"type":"command","command":"/path/to/context-floor.sh"}]}]}}\n'
)
_FLOOR_NEAR_MISS_SETTINGS = (
    '{"hooks":{"PreToolUse":[{"matcher":"Edit|Write","hooks":'
    '[{"type":"command","command":"/path/to/context-floor"}]}]}}\n'
)


def _floor_env(
    tmp_path: Path,
    name: str,
    *,
    wired_at: str | None,
    jq_present: bool,
    settings_body: str = _FLOOR_WIRED_SETTINGS,
    home_set: bool = True,
) -> tuple[Path, dict]:
    """A hermetic world for the row: a fake HOME, settings written to AT MOST ONE of the three
    locations the row greps, and a PATH holding ONLY the commands the row itself uses. jq presence
    is then the single variable between the wired and the inert state — with the ambient PATH,
    `command -v jq` would be true on any machine that can run this suite, and the inert branch would
    be unreachable for a reason that has nothing to do with the row.

    One location at a time, never several: a fixture that wires two of them cannot tell which entry
    of the grep list carried the ✓. `home_set=False` OMITS `HOME` from the child's environment
    entirely (not `HOME=""`) — the only way to exercise the `${HOME:-}` guard, since an empty HOME
    expands fine under `set -u` and a bare `$HOME` only aborts when the name is unset."""
    work = tmp_path / name
    home = work / "home"
    proj = work / "proj"
    shim = work / "bin"
    for d in (home, proj, shim):
        d.mkdir(parents=True)
    if wired_at is not None:
        assert wired_at in _FLOOR_SETTINGS_LOCATIONS, f"unknown settings location {wired_at!r}"
        root, rel = _FLOOR_SETTINGS_LOCATIONS[wired_at]
        target = work / root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(settings_body, encoding="utf-8")
    grep = shutil.which("grep")
    assert grep, "no grep on PATH"
    (shim / "grep").symlink_to(grep)
    if jq_present:
        jq = shutil.which("jq")
        assert jq, "no jq on PATH — the gate's own dependency"
        (shim / "jq").symlink_to(jq)
    env = {"PATH": str(shim)}
    if home_set:
        env["HOME"] = str(home)
    return proj, env


def _run_floor_row(
    tmp_path: Path,
    gate_script: str,
    name: str,
    *,
    wired_at: str | None,
    jq_present: bool,
    settings_body: str = _FLOOR_WIRED_SETTINGS,
    home_set: bool = True,
) -> subprocess.CompletedProcess[str]:
    proj, env = _floor_env(
        tmp_path,
        name,
        wired_at=wired_at,
        jq_present=jq_present,
        settings_body=settings_body,
        home_set=home_set,
    )
    script = proj.parent / "row.sh"
    script.write_text(_floor_row_only_script(gate_script), encoding="utf-8")
    bash = shutil.which("bash")
    assert bash, "no bash on PATH"
    return subprocess.run(
        [bash, str(script)], cwd=proj, env=env, capture_output=True, text=True, check=False
    )


def assert_floor_row_is_silent(result: subprocess.CompletedProcess[str]) -> None:
    """A warn-only row prints its warning on stdout and NOTHING on stderr — two of the three states
    grep files that are legitimately absent, and `grep`'s own "No such file or directory" leaking
    into a close would read as a gate error.

    Honest scope: the row carries `-s` AND `2>/dev/null`, which are redundant, so this assertion
    reddens only when BOTH are dropped; removing either one alone stays silent and stays green.
    Kept redundant deliberately (`-s` is not portable-guaranteed for every grep an adopter has),
    with the limit written down rather than implied by a passing test."""
    assert result.stderr == "", (
        "the context-floor arming row wrote to stderr — a warn-only row must stay silent there: "
        f"{result.stderr!r}"
    )


def _jq_less_but_otherwise_complete_env(tmp_path: Path, name: str) -> dict:
    """A PATH that mirrors the ambient one MINUS jq, so "the gate died" has exactly one candidate
    cause. Built by shadowing every name on the real PATH (first occurrence wins, preserving PATH
    precedence) rather than by listing the tools the gate uses: a hand-written list silently
    reintroduces the confound the moment the gate reaches for one more command, and the reader of a
    127 cannot tell an omission from the measurement. HOME points at an empty dir for the usual
    reason — a machine with the floor wired globally must not colour the run."""
    work = tmp_path / name
    shim = work / "bin"
    home = work / "home"
    for d in (shim, home):
        d.mkdir(parents=True)
    seen = {"jq"}  # never shadowed — its absence is the whole measurement
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        directory = Path(entry)
        if not entry or not directory.is_dir():
            continue
        # os.scandir + a name set rather than `link.exists()`: some entries on a macOS system PATH
        # (e.g. /usr/sbin/weakpass_edit) cannot even be stat-ed by an unprivileged process, and a
        # stat-based skip raises PermissionError before the measurement starts.
        for tool in os.scandir(directory):
            if tool.name in seen:
                continue
            seen.add(tool.name)
            (shim / tool.name).symlink_to(tool.path)
    assert not (shim / "jq").is_symlink(), "jq leaked into the jq-less PATH"
    assert (shim / "sed").exists() and (shim / "git").exists(), (
        "the jq-less PATH is missing tools the gate needs for reasons other than jq — the "
        "measurement would be confounded before it started"
    )
    return {"PATH": str(shim), "HOME": str(home)}


def _run_gate_with_env(
    repo: Path, script: str, *args: str, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """`run_gate` with a controlled environment. Local rather than in close_gate_lib because HOME
    is the arming row's only input that the fixture repo cannot carry: with the real HOME, every
    machine that has the floor wired globally would silently test the wired state three times."""
    gate = repo / ".gate.sh"
    gate.write_text(script, encoding="utf-8")
    gate.chmod(0o755)
    bash = shutil.which("bash")
    assert bash, "no bash on PATH"
    # absolute bash, resolved from the AMBIENT PATH: `env=` makes Python resolve the program name
    # against the passed PATH, and one caller deliberately passes a PATH holding only the row's own
    # commands — an interpreter looked up there would fail before the gate ever started, and the
    # jq-less measurement would be an artifact of the harness rather than of the gate.
    return subprocess.run(
        [bash, str(gate), *args], cwd=repo, capture_output=True, text=True, check=False, env=env
    )


def _floor_row_of(stdout: str) -> str:
    rows = [ln for ln in stdout.splitlines() if "context-floor hook" in ln]
    assert len(rows) == 1, (
        f"expected exactly one context-floor arming row, got {rows} — "
        f"{FLOOR_CONTRACT_PHRASE}, and it claims nothing at all if it is not printed.\n{stdout}"
    )
    return rows[0]


# The row's `grep` call, taken apart: the pattern it searches for and the file list it searches.
# Both are asserted against below — the pattern against the string the ✓ names, the file list
# against the set of locations these tests actually wire — so neither can grow or shrink without a
# test noticing. `-q[a-z]*` rather than `-qs` so tightening or loosening the flags is a matter for
# assert_floor_row_is_silent, not a silent no-match here.
_FLOOR_GREP = re.compile(r"grep -q[a-z]* '(?P<pattern>[^']*)' (?P<paths>.*?) 2>/dev/null")


def _floor_grep_call(gate_script: str) -> tuple[str, list[str]]:
    body = _floor_row_body(gate_script)
    match = _FLOOR_GREP.search(body)
    assert match, (
        "could not find the row's `grep -q… '<pattern>' <files> 2>/dev/null` call — it was "
        f"reshaped, and every assertion about what it searches now watches nothing:\n{body}"
    )
    paths = [tok.strip('"') for tok in shlex.split(match["paths"], posix=False)]
    return match["pattern"], paths


def test_every_settings_location_the_row_greps_can_arm_it_on_its_own(
    tmp_path: Path, gate_script: str
) -> None:
    """The user-global settings file is the location the ⚠ names FIRST and the rationale calls the
    primary home of a machine-local hook — and until this test, no fixture ever wrote it. Every
    fixture wired the PROJECT `.claude/settings.json`, the fake HOME was always empty, and deleting
    `"${HOME:-}/.claude/settings.json"` (or `.claude/settings.local.json`) from the grep list passed
    the entire suite. A list of paths needs one fixture PER PATH; the rest is decoration.

    The second half keeps that true as the list changes: the locations wired here are compared to
    the paths actually in the gate's grep call, so a fourth entry added tomorrow fails here rather
    than joining the list unwatched."""
    _, grepped = _floor_grep_call(gate_script)
    expected = {
        "${HOME:-}/.claude/settings.json",
        ".claude/settings.json",
        ".claude/settings.local.json",
    }
    assert set(grepped) == expected, (
        f"the row's settings-file list changed to {grepped} — add the new location to "
        f"_FLOOR_SETTINGS_LOCATIONS and give it a fixture, or these tests cover a shorter list "
        f"than the gate reads"
    )
    assert len(_FLOOR_SETTINGS_LOCATIONS) == len(expected), _FLOOR_SETTINGS_LOCATIONS

    for location in _FLOOR_SETTINGS_LOCATIONS:
        result = _run_floor_row(
            tmp_path, gate_script, f"only-{location}", wired_at=location, jq_present=True
        )
        row = _floor_row_of(result.stdout)
        assert row.startswith("✓"), (
            f"the hook wired ONLY via the {location} settings file did not arm the row — that "
            f"entry of the grep list has no effect: {row!r}"
        )
        assert FLOOR_STATE_MARKERS["wired"] in row, row
        assert_floor_wired_row_names_its_basis(row)
        assert_floor_row_claims_no_hook_capability(row)
        assert result.returncode == 0, f"the arming row is warn-only: rc={result.returncode}"
        assert_floor_row_is_silent(result)


def test_floor_row_survives_a_genuinely_unset_home(tmp_path: Path, gate_script: str) -> None:
    """`${HOME:-}`'s reason for existing, given an oracle. The comment calls aborting the gate "the
    one thing a warn-only row must not do", and under `set -u` a bare `$HOME` does exactly that when
    HOME is UNSET — which no fixture ever arranged, so `${HOME:-}` → `$HOME` passed the whole suite.

    Unset, not empty: `HOME=""` expands fine under `set -u`, so a fixture that merely blanks it
    tests nothing. `home_set=False` omits the variable from the child's environment entirely."""
    result = _run_floor_row(
        tmp_path, gate_script, "no-home", wired_at=None, jq_present=True, home_set=False
    )
    assert result.returncode == 0, (
        "the arming row aborted with HOME unset — a warn-only row must never take the gate down "
        f"with it (rc={result.returncode}):\n{result.stderr}"
    )
    row = _floor_row_of(result.stdout)
    assert row.startswith("⚠") and FLOOR_STATE_MARKERS["not wired"] in row, row
    assert_floor_row_is_silent(result)


def test_the_grep_pattern_and_the_wired_claim_are_the_same_string(gate_script: str) -> None:
    """The row used to grep for `context-floor` while the ✓ said "settings reference
    context-floor.sh" — a claim one extension wider than the check, and swapping the pattern for the
    string the ✓ names reddened nothing. Tie them together instead of asserting either literal:
    whichever one a maintainer edits, the other has to follow."""
    pattern, _ = _floor_grep_call(gate_script)
    unescaped = re.sub(r"\\(.)", r"\1", pattern)
    claims = re.findall(r"settings reference ([^)\s]+)\)", _floor_row_body(gate_script))
    assert len(claims) == 1, (
        f"expected exactly one 'settings reference <string>)' claim in the row, found {claims} — "
        f"{FLOOR_CONTRACT_PHRASE}, and the claim has to name what was searched for"
    )
    assert claims[0] == unescaped, (
        f"the ✓ claims the settings reference {claims[0]!r} but the row greps for {unescaped!r} — "
        "the claim and the check must be the same string"
    )


def test_settings_naming_context_floor_without_the_extension_do_not_arm_the_row(
    tmp_path: Path, gate_script: str
) -> None:
    """The behavioural half of the same fix, on the near-miss the loose pattern accepted: settings
    that name `context-floor` and not `context-floor.sh` must read as NOT wired, because that is
    what the ✓ would have claimed about them."""
    result = _run_floor_row(
        tmp_path,
        gate_script,
        "near-miss",
        wired_at="project",
        jq_present=True,
        settings_body=_FLOOR_NEAR_MISS_SETTINGS,
    )
    row = _floor_row_of(result.stdout)
    assert row.startswith("⚠") and FLOOR_STATE_MARKERS["not wired"] in row, (
        "settings naming 'context-floor' without the extension armed the row — the ✓ then claims "
        f"they reference context-floor.sh, which they do not: {row!r}"
    )
    assert result.returncode == 0, f"the arming row is warn-only: rc={result.returncode}"
    assert_floor_row_is_silent(result)


def test_floor_row_reports_not_wired_without_failing_the_gate(
    tmp_path: Path, gate_script: str
) -> None:
    """State 1, end to end on an otherwise-passing phase fixture — so rc 0 means the row
    did not flip the gate, not that nothing else could have."""
    repo = _make_otherwise_passing_phase_fixture(tmp_path, spec_count=2)
    home = tmp_path / "unwired-home"
    home.mkdir()
    result = _run_gate_with_env(
        repo, gate_script, "phase", "1.0", env={**os.environ, "HOME": str(home)}
    )
    row = _floor_row_of(result.stdout)
    assert row.startswith("⚠"), f"the un-armed floor must warn, never fail: {row!r}"
    assert FLOOR_STATE_MARKERS["not wired"] in row, row
    assert result.returncode == 0, f"the arming row is warn-only:\n{result.stdout}"


def test_floor_row_reports_wired_without_failing_or_overclaiming(
    tmp_path: Path, gate_script: str
) -> None:
    """State 2, end to end. The ✓ is read from a real gate run rather than from the
    gate's source: a source-text assertion cannot tell a row that prints from one that is dead."""
    repo = _make_otherwise_passing_phase_fixture(tmp_path, spec_count=2)
    (repo / ".claude/settings.json").write_text(
        '{"hooks":{"PreToolUse":[{"matcher":"Edit|Write","hooks":'
        '[{"type":"command","command":"/path/to/context-floor.sh"}]}]}}\n',
        encoding="utf-8",
    )
    home = tmp_path / "wired-home"
    home.mkdir()
    result = _run_gate_with_env(
        repo, gate_script, "phase", "1.0", env={**os.environ, "HOME": str(home)}
    )
    row = _floor_row_of(result.stdout)
    assert row.startswith("✓"), row
    assert FLOOR_STATE_MARKERS["wired"] in row, row
    assert_floor_wired_row_names_its_basis(row)
    assert_floor_row_claims_no_hook_capability(row)
    assert result.returncode == 0, f"the arming row is warn-only:\n{result.stdout}"


def test_floor_row_reports_wired_but_inert_and_the_full_gate_cannot_reach_it(
    tmp_path: Path, gate_script: str
) -> None:
    """State 3 — and the measurement of why it is run this way.

    THE BOOTSTRAP WRINKLE, asserted rather than narrated: this row warns that a wired hook is inert
    because `jq` is missing, inside a gate whose every manifest read goes through `jq`. The second
    half of this test runs the WHOLE gate in the same jq-less world and pins what actually happens —
    it dies at its first `g` call with 127 and prints nothing, so the inert branch is not reachable
    end to end on any machine, by anyone, ever. (Nor in the other direction: the stripped-PATH GUI
    client this warning is ABOUT leaves the gate itself able to resolve jq, so that world prints the
    ✓ wired row. The branch cannot print for a user either way — it is a contract for gates that can
    reach it.) Driving `floor_arming_row` directly is therefore not a convenience: it is the only
    execution context in which this branch exists. What that costs is stated in
    test_floor_row_unit_runner_agrees_with_the_full_gate, which pins the unit runner and the gate to
    the same bytes for the two states both can reach."""
    result = _run_floor_row(tmp_path, gate_script, "inert", wired_at="project", jq_present=False)
    row = _floor_row_of(result.stdout)
    assert row.startswith("⚠"), f"an inert floor must warn, never fail: {row!r}"
    assert FLOOR_STATE_MARKERS["wired but inert"] in row, row
    assert_floor_row_claims_no_hook_capability(row)
    assert result.returncode == 0, f"the arming row is warn-only: rc={result.returncode}"
    assert_floor_row_is_silent(result)

    repo = _make_otherwise_passing_phase_fixture(tmp_path, spec_count=2)
    env = _jq_less_but_otherwise_complete_env(tmp_path, "inert-e2e")
    whole_gate = _run_gate_with_env(repo, gate_script, "phase", "1.0", env=env)
    assert whole_gate.returncode == 127, (
        "the jq-less full-gate measurement this test's approach rests on has changed: expected the "
        f"gate to die at its first jq call, got rc={whole_gate.returncode}\n{whole_gate.stdout}"
    )
    # rc=127 ALONE does not name a cause. The first version of this measurement ran the gate under
    # the row's own tiny PATH, which is missing sed, git and awk as well as jq — and reproduces the
    # identical rc in a world where jq is present and only sed is gone, i.e. it would have "proved"
    # the bootstrap wrinkle in a world that does not have one. The environment above supplies every
    # tool the gate reaches for EXCEPT jq, and this asserts that the set of unresolvable commands is
    # exactly {jq}: if the gate dies for any other reason, or for jq PLUS something else, this fails.
    unresolvable = sorted(set(re.findall(r": ([\w.+-]+): command not found", whole_gate.stderr)))
    assert unresolvable == ["jq"], (
        "the jq-less measurement is confounded — rc=127 was not caused by jq alone. Commands the "
        f"gate could not resolve: {unresolvable}\nstderr: {whole_gate.stderr}"
    )
    assert "context-floor hook" not in whole_gate.stdout, (
        "the full gate now reaches the arming row without jq — the inert branch has become "
        f"observable end to end and this test should be rewritten to assert that:\n{whole_gate.stdout}"
    )


def test_the_three_floor_states_are_pairwise_distinct_and_none_can_fail_the_gate(
    tmp_path: Path, gate_script: str
) -> None:
    """The real content: not that three rows exist, but that no two of them can be mistaken for
    each other. Each state's marker must appear in exactly ONE of the three rows — asserted against
    the other states' output, not against a silent baseline, because a marker that matches two
    states passes a baseline comparison while proving nothing.

    The structural half rides along: the row reaches ok()/warn() and never bad() or `fail=`, so
    warn-only is a property of the code rather than of three observed exit codes."""
    runs = {
        state: _run_floor_row(
            tmp_path, gate_script, f"state-{i}", wired_at=wired_at, jq_present=jq
        )
        for i, (state, wired_at, jq) in enumerate(
            [
                ("not wired", None, True),
                ("wired", "project", True),
                ("wired but inert", "project", False),
            ]
        )
    }
    for run in runs.values():
        assert_floor_row_is_silent(run)
    rows = {state: _floor_row_of(run.stdout) for state, run in runs.items()}
    for state, row in rows.items():
        others = [s for s in rows if s != state]
        assert FLOOR_STATE_MARKERS[state] in row, f"{state} row lost its marker: {row!r}"
        for other in others:
            assert FLOOR_STATE_MARKERS[other] not in row, (
                f"the {state!r} row also matches the {other!r} marker "
                f"{FLOOR_STATE_MARKERS[other]!r} — the two states blur: {row!r}"
            )
    assert len(set(rows.values())) == 3, f"two states print the same row: {rows}"

    body = _floor_row_body(gate_script)
    assert " bad " not in body and "fail=" not in body, (
        f"the arming row can now flip the gate's failure status — it must only ok()/warn():\n{body}"
    )


def test_floor_row_unit_runner_agrees_with_the_full_gate(
    tmp_path: Path, gate_script: str
) -> None:
    """The bridge that makes the inert state's unit run worth anything. For the two states the full
    gate CAN reach, the bytes-only runner must print the identical line; if it ever diverges, the
    third state's evidence is evidence about a different program.

    Byte-identical, not "contains": the whole risk being covered is a runner that has drifted into
    printing its own approximation of the row."""
    repo = _make_otherwise_passing_phase_fixture(tmp_path, spec_count=2)
    home = tmp_path / "bridge-home"
    home.mkdir()
    gate_unwired = _floor_row_of(
        _run_gate_with_env(
            repo, gate_script, "phase", "1.0", env={**os.environ, "HOME": str(home)}
        ).stdout
    )
    (repo / ".claude/settings.json").write_text(
        '{"hooks":{"PreToolUse":[{"matcher":"Edit|Write","hooks":'
        '[{"type":"command","command":"/path/to/context-floor.sh"}]}]}}\n',
        encoding="utf-8",
    )
    gate_wired = _floor_row_of(
        _run_gate_with_env(
            repo, gate_script, "phase", "1.0", env={**os.environ, "HOME": str(home)}
        ).stdout
    )
    unit_unwired = _floor_row_of(
        _run_floor_row(tmp_path, gate_script, "bridge-a", wired_at=None, jq_present=True).stdout
    )
    unit_wired = _floor_row_of(
        _run_floor_row(
            tmp_path, gate_script, "bridge-b", wired_at="project", jq_present=True
        ).stdout
    )
    assert unit_unwired == gate_unwired, (
        f"unit runner and gate disagree on the not-wired row:\n{unit_unwired!r}\n{gate_unwired!r}"
    )
    assert unit_wired == gate_wired, (
        f"unit runner and gate disagree on the wired row:\n{unit_wired!r}\n{gate_wired!r}"
    )


def test_every_floor_forbidden_token_has_an_observed_red_path(
    tmp_path: Path, gate_script: str
) -> None:
    """The banned list's tripwire, held to row 7's standard: a banned list nobody has watched fire is exactly the
    thing this file exists to remove. Each token is injected into an otherwise-honest row and must
    be reported BY NAME. Looped rather than parametrized so shrinking the tuple deletes coverage
    visibly here instead of silently removing test items from the run.

    The second half is the direction the loop cannot see: every row the gate ACTUALLY prints must
    survive the list. A banned token that can only be caught in a synthetic string, while a real row
    smuggles it past, would be a guard aimed at the wrong text."""
    assert FLOOR_FORBIDDEN_TOKENS, "the banned list was emptied"
    for token in FLOOR_FORBIDDEN_TOKENS:
        row = f"✓ context-floor hook wired and the hook {token} on this machine"
        with pytest.raises(AssertionError) as caught:
            assert_floor_row_claims_no_hook_capability(row)
        assert token in str(caught.value), caught.value

    for state, wired_at, jq in [("a", None, True), ("b", "project", True), ("c", "project", False)]:
        assert_floor_row_claims_no_hook_capability(
            _floor_row_of(
                _run_floor_row(
                    tmp_path, gate_script, f"banned-{state}", wired_at=wired_at, jq_present=jq
                ).stdout
            )
        )


def test_floor_assertions_state_the_contract_when_they_fire() -> None:
    """The message is the deliverable. Both assertions would pass their own checks while failing
    with a bare "assert not banned", and the one clause the human locked (this row may claim
    resolvability, never capability) would be dropped for the next maintainer.

    The literal is spelled out here rather than only interpolated: every message below is built from
    FLOOR_CONTRACT_PHRASE, so emptying that constant would strip the locked clause from all of them
    and leave every assertion green — the self-certifying shape row 7 already tripped over once."""
    assert FLOOR_CONTRACT_PHRASE == (
        "this row may only claim that jq was resolvable when the gate ran, "
        "not that the hook works"
    ), f"the locked contract clause was reworded or emptied: {FLOOR_CONTRACT_PHRASE!r}"
    # All three, individually. The red-path loop above parametrizes over the tuple, so SHRINKING it
    # deletes coverage without failing anything — asserting only one entry (row 7's shape) would leave
    # the other two free to be dropped silently. Adding a fourth claim stays legal; removing one of
    # the three the human locked does not.
    for locked in ("works", "will run", "verified"):
        assert locked in FLOOR_FORBIDDEN_TOKENS, f"a locked banned claim was dropped: {locked!r}"
    assert "not proof the hook fires" in FLOOR_WIRED_REQUIRED_TOKENS

    with pytest.raises(AssertionError) as banned_claim:
        assert_floor_row_claims_no_hook_capability(
            "✓ context-floor hook wired — verified"
        )
    assert FLOOR_CONTRACT_PHRASE in str(banned_claim.value), (
        f"the banned-claims failure must state the contract, got: {banned_claim.value}"
    )

    with pytest.raises(AssertionError) as missing_basis:
        assert_floor_wired_row_names_its_basis("✓ context-floor hook wired")
    assert FLOOR_CONTRACT_PHRASE in str(missing_basis.value), (
        f"the presence failure must state the contract, got: {missing_basis.value}"
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
    close-gate PASS at task/phase while showing ⊘ (handoff_glob was dropped from this set;
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
    """Regression guard for the finding that made this block necessary: a bare
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
# fixture harness), in a project that follows the current skill correctly (no
# docs/handoff/*.md file anywhere on disk), must pass BOTH phase mode and milestone mode.
#
# Run this test file against a close-gate.md from before handoff_glob left the scaffold
# to see it RED: phase mode fails with "no handoff doc for phase 1.0" because
# handoff_glob was configured (matching /init-harness's old scaffold) but no file matched it.


def _init_harness_scaffolded_manifest() -> dict:
    """Mirrors close-gate.md's `.claude/close-gate.json` example (no
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
    """A repo that has run every step of the current skill correctly for one phase: real
    user-story + spec + plan + acceptance-test + smoke files, CHANGELOG/ROADMAP/journal
    touched, fresh test-evidence — and, critically, NO docs/handoff/*.md file anywhere,
    because a later change retired writing one. If any manifest value could still hard-fail a
    correctly-followed project, it fails here."""
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
    scaffolds it, in a project that followed the current skill (wrote every wrap-up
    artifact except a handoff file, because a later change retired writing one), must pass phase
    mode cleanly — no ✗ rows at all, and specifically none naming a handoff doc."""
    repo = _make_init_harness_fixture(tmp_path, phase="1.0")
    assert not list(repo.glob("docs/handoff/**/*")), "fixture must not contain a handoff file"
    result = run_gate(repo, gate_script, "phase", "1.0")
    assert result.returncode == 0, f"phase-done must pass a correctly-followed project:\n{result.stdout}"
    assert "✗" not in result.stdout, f"no manifest value may hard-fail this project:\n{result.stdout}"
    assert "handoff" not in result.stdout.lower(), f"no handoff-doc row should exist at all:\n{result.stdout}"


def test_init_harness_scaffolded_manifest_passes_milestone_mode_with_no_handoff_file(
    tmp_path: Path, gate_script: str
) -> None:
    """Companion half of the acceptance condition: the SAME manifest shape must also pass
    milestone mode (both with and without a PHASE arg — the bare-invocation case already
    guarded) — the other side of the contradiction described in the section comment above."""
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

    Without it, a spec distilled
    into a FACT entry can keep `Rejected` whole and lose most of `Why`, because the schema has
    a slot for the conclusion and none for the evidence it rests on — so every argument silently
    degrades into an assertion, and the figures the spec turned on
    vanish. The field exists
    precisely so a claim cannot be stated
    without its support, as `journal-schema.md` says beside the schema block that lists
    `Backing`. This test is the enforcement."""
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


# --- a ROADMAP touch is not the ceremony (canonical gate) ---


def test_roadmap_touched_but_not_naming_the_phase_fails(
    tmp_path: Path, gate_script: str
) -> None:
    """The sibling of a defect in a local-file gate variant, which checked
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


# ------------------------------------------------------------------------------------------
# The archive fallback for the ADOPTER, not only for this repo — the control that was missing
#
# `references/close-gate.md` carries TWO implementations of check 5: the prose checklist at the
# top, and the portable script `/init-harness` scaffolds into every adopter's repo. The checklist
# got the archive fallback; the script kept `ls -t "$JD"/*.md | head -1` for a while, so
# an adopter who closed a milestone got the exact bug the fallback fixed — including the unpushable
# branch, since the row runs in task mode on every push.
#
# That is a familiar shape: the local implementation gets the guard, the adopter-facing one
# gets the description. `retention.md`'s embedded copy cannot drift because the suite byte-compares
# it against the real script; this file's script is a DIFFERENT gate (the canonical git-range
# variant) so it cannot be byte-compared — and nothing else was watching it. This is that watcher,
# and it RUNS the resolver rather than grepping for its name.
# ------------------------------------------------------------------------------------------

_POST_DRAIN_ARCHIVE = (
    "# Journal archive — 2026-08\n\n## 📑 Index\n\n---\n"
    "\n<!-- fragment: docs/journal.d/2026-08-01-phase-p7-x.md -->\n"
    "# phase p7\n\n"
    "- **Date:** 2026-08-01\n- **Decision:** d\n- **Why:** w\n"
    "- **Backing:** b\n- **Rejected:** r\n- **Source:** s\n"
)


def _adopter_resolver(tmp_path: Path, gate_script: str) -> Path:
    """The adopter gate's own `journal_slice` + `resolve_journal`, lifted verbatim out of the
    extracted script — not re-typed here, or this test would assert against a copy that can
    disagree with what adopters actually run."""
    lines = gate_script.splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines) if ln.startswith('JARCHIVE=""; JSLICE=""'))
    end = next(
        i for i in range(len(lines) - 1, start, -1) if lines[i].startswith("resolve_journal()")
    )
    close = next(i for i in range(end, len(lines)) if lines[i].rstrip() == "}")
    lib = tmp_path / "adopter-lib.sh"
    lib.write_text("".join(lines[start : close + 1]), encoding="utf-8")
    return lib


def _resolve(repo: Path, lib: Path, phase: str) -> subprocess.CompletedProcess[str]:
    script = (
        'set -euo pipefail\n'
        f'. "{lib}"\n'
        f'P="$(resolve_journal docs/journal.d {phase} docs/archive docs/iteration-journal.md)"\n'
        'echo "PATH=$P"\n'
        'echo "FIELDS=$(grep -c \'^- \\*\\*\' "$P" 2>/dev/null || echo 0)"\n'
    )
    return subprocess.run(
        ["bash", "-c", script], cwd=repo, capture_output=True, text=True, check=False
    )


def test_the_adopter_gate_reads_the_archive_after_the_mandated_drain(
    tmp_path: Path, gate_script: str
) -> None:
    """The post-drain state: the hot directory is empty by design, and the phase's FACT entry
    lives in the archive. Before this, the adopter's resolver fell through to the monolith path
    and reported every FACT field missing."""
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "journal_dir": "docs/journal.d"}},
        files={"docs/archive/journal/2026-08.md": _POST_DRAIN_ARCHIVE},
    )
    (repo / "docs/journal.d").mkdir(parents=True, exist_ok=True)
    lib = _adopter_resolver(tmp_path, gate_script)
    result = _resolve(repo, lib, "p7")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FIELDS=6" in result.stdout, result.stdout + result.stderr


def test_the_adopter_gate_still_prefers_the_hot_fragment(
    tmp_path: Path, gate_script: str
) -> None:
    """The positive control, and the thing the fix must not break: while the fragment is still in
    the hot directory it wins, and the archive is not consulted at all. Without this, a resolver
    that always returned the archive slice would pass the test above."""
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "journal_dir": "docs/journal.d"}},
        files={
            "docs/journal.d/2026-08-01-phase-p7-x.md": "# phase p7\n\n- **Date:** 2026-08-01\n",
            "docs/archive/journal/2026-08.md": _POST_DRAIN_ARCHIVE,
        },
    )
    lib = _adopter_resolver(tmp_path, gate_script)
    result = _resolve(repo, lib, "p7")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PATH=docs/journal.d/2026-08-01-phase-p7-x.md" in result.stdout, result.stdout


def test_the_adopter_gate_does_not_read_the_qa_log_archive_as_the_journal(
    tmp_path: Path, gate_script: str
) -> None:
    """`<archive_dir>/journal/`, never `<archive_dir>/*.md`. The qa-log archive sits beside the
    journal archive, is written by the same drain, carries the SAME `<!-- fragment: … -->`
    sentinel format AND the same `<date>-phase-<id>-<slug>.md` fragment names — so the wider glob
    reads Q&A content as though it were the phase's journal entry. Two of the three readings an
    adopter could take from the prose selected it."""
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "journal_dir": "docs/journal.d"}},
        files={
            "docs/archive/brainstorming-qa-log-archive.md": (
                "# QA archive\n\n"
                "\n<!-- fragment: docs/qa-log.d/2026-08-01-phase-p7-x.md -->\n"
                "# qa\n\n- **Decision:** a LOCKED Q&A decision, not a journal FACT entry\n"
            ),
            "docs/archive/journal/2026-08.md": _POST_DRAIN_ARCHIVE,
        },
    )
    (repo / "docs/journal.d").mkdir(parents=True, exist_ok=True)
    lib = _adopter_resolver(tmp_path, gate_script)
    result = _resolve(repo, lib, "p7")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FIELDS=6" in result.stdout, (
        f"the qa-log archive has one bullet, the journal archive six: {result.stdout}"
    )
