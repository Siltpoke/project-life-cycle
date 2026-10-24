"""the `closed-step:` entry kind, corpus mode, and the
step-line requirement. Closes `AC-11` and `AC-12`.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

**The first test in this file is the regression, and it is first on purpose.**
`parse_body` fails on any line it does not recognise, so a mistake in this task reddens
EVERY closure declaration in the repository at once — fourteen documents, sixty-two
records. `test_regression_*` runs the real corpus rather than a fixture, because a
synthetic block cannot notice that a real one drifted.

**Why `--require-steps` is a flag and not the default, stated rather than assumed.**
The design says every declaration block must carry a step line; the plan for this same
task says every declaration already written must still parse. Both cannot hold inside the
grammar: the fourteen documents predate the step format and cannot retroactively grow a
line. So the grammar keeps parsing what is there, and the REQUIREMENT lives at the gate,
the only caller that knows a declaration is being written now rather than read from
history. `test_gate_invokes_extract_with_require_steps` is what stops that flag from
quietly going missing — without it the rule would be enforced by nobody and look
identical to being enforced.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "closure-declaration.sh"
CLOSE_GATE = REPO / "scripts" / "close-gate.sh"
DOCS = REPO / "docs"
FENCE = "`" * 3


def run(*args: Path | str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), "extract", *[str(a) for a in args]],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def doc(tmp_path: Path, name: str, *lines: str) -> Path:
    p = tmp_path / name
    body = "# a doc\n\n" + "\n".join([f"{FENCE}plc-closes", *lines, FENCE, ""])
    p.write_text(body, encoding="utf-8")
    return p


def records(proc: subprocess.CompletedProcess) -> list[list[str]]:
    return [ln.split("\t") for ln in proc.stdout.splitlines() if ln.strip()]


def declaration_docs() -> list[Path]:
    """Every file in docs/ that carries a real opening fence, found by scanning rather
    than by a list somebody has to remember to update."""
    if not DOCS.is_dir():
        return []
    found = []
    for p in sorted(DOCS.rglob("*.md")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"(?m)^```plc-closes[ \t]*$", text):
            found.append(p)
    return found


# =========================================================================== regression
# The plan's stated first assertion for this task.


@pytest.mark.skipif(not DOCS.is_dir(), reason="skipped where docs/ is absent")
def test_regression_every_existing_declaration_still_parses_alone() -> None:
    """Every such document, each read the way the gate reads it: one block, default
    mode, no flags. A single unrecognised-line mistake in one line turns all of them red."""
    files = declaration_docs()
    assert len(files) >= 10, f"the corpus is smaller than expected: {files}"
    failures = []
    total = 0
    for f in files:
        p = run(f)
        if p.returncode != 0:
            failures.append((f, p.stderr))
        total += len(records(p))
    assert not failures, failures
    # A positive record count, not just clean exits: zero records with exit 0 is a
    # legitimate outcome for a file with no block, so exit codes alone prove nothing.
    assert total >= 20, f"only {total} records across {len(files)} documents"


@pytest.mark.skipif(not DOCS.is_dir(), reason="skipped where docs/ is absent")
def test_regression_whole_corpus_reads_in_one_pass() -> None:
    """The mode the corpus-wide validators need. Same fourteen documents, read together, which default mode
    refuses by design (`exactly one is allowed`)."""
    files = declaration_docs()
    assert len(files) >= 10
    p = run("--corpus", *files)
    assert p.returncode == 0, p.stderr
    recs = records(p)
    assert len(recs) >= 20, p.stdout
    # Every corpus record carries its source. A record that cannot say where it came from
    # is useless to a dangling-reference check, which must name the offending line.
    assert all(len(r) == 4 for r in recs), [r for r in recs if len(r) != 4]
    assert all(re.search(r":\d+$", r[3]) for r in recs), [r[3] for r in recs][:5]


# =========================================================================== the new kind


def test_step_token_is_accepted(tmp_path: Path) -> None:
    f = doc(tmp_path, "spec.md", "closed: B9021", "closed-step: ci-line.s1")
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert ["closed-step", "ci-line.s1", "-"] in records(p), p.stdout


def test_step_token_keeps_its_reason_verbatim(tmp_path: Path) -> None:
    f = doc(tmp_path, "spec.md", "closed-step: ci-line.s2 — measured, not reasoned")
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert records(p) == [["closed-step", "ci-line.s2", "measured, not reasoned"]]


def test_closed_step_none_is_the_sentinel_not_a_station_called_none(tmp_path: Path) -> None:
    """`none` satisfies the shared id character class, so without an explicit branch it
    would parse as a step token and then be rejected by the shape check — the format would
    reject the exact sentence it asks authors to write."""
    f = doc(tmp_path, "spec.md", "closed: B9021", "closed-step: none")
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert ["closed-step", "none", "-"] in records(p), p.stdout


def test_closed_step_none_may_not_be_mixed_with_named_steps(tmp_path: Path) -> None:
    f = doc(tmp_path, "spec.md", "closed-step: none", "closed-step: ci-line.s1")
    p = run(f)
    assert p.returncode != 0
    assert "must stand alone" in p.stderr


def test_closes_none_and_a_named_step_are_not_a_contradiction(tmp_path: Path) -> None:
    """The two sentinels belong to different families. A phase can legitimately close no
    backlog id and still close station steps; a parser that merged the rules would forbid
    a true statement."""
    f = doc(tmp_path, "spec.md", "closes: none", "closed-step: ci-line.s1")
    p = run(f)
    assert p.returncode == 0, p.stderr
    kinds = sorted(r[0] for r in records(p))
    assert kinds == ["closed-step", "none"], p.stdout


# =========================================================================== shape


def test_backlog_id_under_the_step_keyword_is_rejected(tmp_path: Path) -> None:
    """The right keyword with the wrong namespace. Without the shape check this parses
    clean and surfaces much later as a dangling reference against the station plan."""
    f = doc(tmp_path, "spec.md", "closed-step: B9021")
    p = run(f)
    assert p.returncode != 0
    assert "not a <station-id>.s<N> step token" in p.stderr


def test_station_id_without_a_step_is_rejected(tmp_path: Path) -> None:
    f = doc(tmp_path, "spec.md", "closed-step: ci-line")
    p = run(f)
    assert p.returncode != 0
    assert "not a <station-id>.s<N> step token" in p.stderr


def test_slash_separator_is_rejected_by_the_existing_character_class(tmp_path: Path) -> None:
    """The reason the token uses a dot: `.` is already in the id class and `/` is not, so
    the format needed a keyword rather than a new regex. This pins that claim."""
    f = doc(tmp_path, "spec.md", "closed-step: ci-line/s1")
    p = run(f)
    assert p.returncode != 0
    assert "is not a declaration entry" in p.stderr


def test_a_bad_step_line_does_not_hide_the_next_one(tmp_path: Path) -> None:
    """The parser reports every bad line before exiting (`bad = 1`, never `die`), so an
    author sees all the problems at once instead of one per run. A `die` in the new branch
    would silently downgrade behaviour the script already designed for."""
    f = doc(tmp_path, "spec.md", "closed-step: B9021", "closed-step: B9022")
    p = run(f)
    assert p.returncode != 0
    assert p.stderr.count("not a <station-id>.s<N> step token") == 2, p.stderr


# =========================================================================== AC-12


def test_require_steps_reddens_a_block_with_no_step_line(tmp_path: Path) -> None:
    f = doc(tmp_path, "spec.md", "closed: B9021")
    assert run(f).returncode == 0, "default mode must still accept it"
    p = run("--require-steps", f)
    assert p.returncode != 0
    assert "carries no `closed-step:` line" in p.stderr


def test_require_steps_is_satisfied_by_the_explicit_none(tmp_path: Path) -> None:
    """Silence must not be able to mean `closed nothing` — but SAYING it must work, or the
    requirement is unsatisfiable for a phase that genuinely closed no step."""
    f = doc(tmp_path, "spec.md", "closed: B9021", "closed-step: none")
    p = run("--require-steps", f)
    assert p.returncode == 0, p.stderr


def test_require_steps_is_satisfied_by_a_named_step(tmp_path: Path) -> None:
    f = doc(tmp_path, "spec.md", "closed: B9021", "closed-step: ci-line.s1")
    p = run("--require-steps", f)
    assert p.returncode == 0, p.stderr


def test_corpus_and_require_steps_are_refused_together(tmp_path: Path) -> None:
    """Refused rather than resolved. Picking a winner would make the stricter flag inert
    while still appearing on the command line."""
    f = doc(tmp_path, "spec.md", "closed-step: none")
    p = run("--corpus", "--require-steps", f)
    assert p.returncode != 0
    assert "contradict" in p.stderr


@pytest.mark.skipif(not CLOSE_GATE.is_file(), reason="close-gate.sh absent")
def test_gate_invokes_extract_with_require_steps() -> None:
    """The requirement is enforced by the gate, so the gate must actually ask for it.
    Without this assertion the flag could be dropped and every run would look the same."""
    text = CLOSE_GATE.read_text(encoding="utf-8")
    calls = [ln for ln in text.splitlines() if "closure-declaration.sh extract" in ln]
    assert calls, "close-gate.sh no longer calls the extractor at all"
    assert all("--require-steps" in ln for ln in calls), calls


# =========================================================================== corpus mode


def test_corpus_reads_blocks_from_several_files(tmp_path: Path) -> None:
    a = doc(tmp_path, "a.md", "closed: B9001")
    b = doc(tmp_path, "b.md", "closed: B9002")
    assert run(a, b).returncode != 0, "default mode must still refuse two blocks"
    p = run("--corpus", a, b)
    assert p.returncode == 0, p.stderr
    recs = records(p)
    assert [r[1] for r in recs] == ["B9001", "B9002"], p.stdout
    assert recs[0][3].endswith("a.md:3") and recs[1][3].endswith("b.md:3"), recs


def test_corpus_does_not_renumber_the_fields_a_reader_depends_on(tmp_path: Path) -> None:
    """The source is APPENDED, not prefixed. A downstream `cut -f3` for the reason must
    keep meaning the same thing in both modes, or adding the mode silently breaks readers
    that were never touched."""
    f = doc(tmp_path, "spec.md", "left-open: B9022 — waiting on the consumer")
    plain = records(run(f))[0]
    withsrc = records(run("--corpus", f))[0]
    assert len(plain) == 3 and len(withsrc) == 4
    assert withsrc[:3] == plain


def test_corpus_propagates_a_failure_instead_of_failing_open(tmp_path: Path) -> None:
    """A loop fed by a pipe would run in a subshell and lose `rc`; the heredoc is what
    keeps this red. Filed in this repo as a fail-open, so it is asserted, not
    assumed."""
    good = doc(tmp_path, "good.md", "closed: B9001")
    bad = doc(tmp_path, "bad.md", "this is not an entry")
    p = run("--corpus", good, bad)
    assert p.returncode != 0, p.stdout
    assert "is not a declaration entry" in p.stderr
    # The good block was still emitted: one bad file must not erase the rest of the scan.
    assert ["closed", "B9001"] == records(p)[0][:2], p.stdout


def test_corpus_of_one_block_is_not_a_special_case(tmp_path: Path) -> None:
    f = doc(tmp_path, "spec.md", "closed: B9001")
    p = run("--corpus", f)
    assert p.returncode == 0, p.stderr
    assert len(records(p)) == 1


# =========================================================================== reconcile


def test_reconcile_ignores_step_tokens(tmp_path: Path) -> None:
    """A step token is a position inside a station plan, not a backlog id. Reconciling it
    against the ledger would report `no event in the ledger` for every step, which is the
    exclusion the design calls required rather than an optimisation."""
    ledger = tmp_path / "ledger.tsv"
    ledger.write_text("# closure log\nB9021\tclosed\tcompleted\t2026-09-02\t-\n", encoding="utf-8")
    deriver = tmp_path / "deriver.sh"
    deriver.write_text(
        "#!/usr/bin/env bash\n[ \"${1:-}\" = --states ] || exit 2\nprintf 'B9021\\tclosed (completed)\\n'\n",
        encoding="utf-8",
    )
    deriver.chmod(0o755)
    f = doc(tmp_path, "spec.md", "closed: B9021", "closed-step: ci-line.s1")
    p = subprocess.run(
        [
            "/bin/bash", str(SCRIPT), "reconcile",
            "--ledger", str(ledger),
            "--deriver", str(deriver),
            str(f),
        ],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "ci-line.s1" not in p.stdout, p.stdout
    assert "B9021 declared closed and the ledger agrees" in p.stdout, p.stdout


def test_reconcile_names_an_unknown_record_kind_instead_of_dropping_it(tmp_path: Path) -> None:
    """What makes the exclusion above load-bearing rather than decorative. Measured while
    writing it: before this default existed, `closed-step` fell off the end of the case and
    was ignored anyway, so the explicit branch changed no behaviour and no test could bind
    it. With a default that refuses, dropping the branch turns the reconcile red.

    The stand-in for a future fifth kind is a record the extractor cannot produce today,
    fed in through a stub, because the point is what happens when the GRAMMAR grows and
    this loop does not."""
    ledger = tmp_path / "ledger.tsv"
    ledger.write_text("# closure log\n", encoding="utf-8")
    deriver = tmp_path / "deriver.sh"
    deriver.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    deriver.chmod(0o755)

    # A copy of the script whose extractor emits one unknown kind. Editing the copy, never
    # the real script, keeps this test from depending on a defect being present upstream.
    src = SCRIPT.read_text(encoding="utf-8")
    marker = '  parse_body "$path" "$open" "$close" "" "$requiresteps"'
    assert marker in src, "the extractor no longer ends in a parse_body call; re-anchor this stub"
    # The stub keeps the real script LAYOUT, not just its text: reconcile sources its
    # helper relative to `dirname $0`, so a copy dropped anywhere else dies on the missing
    # helper long before it reaches the loop under test — which is how the first run of
    # this test passed its exit-code assertion for entirely the wrong reason.
    stubdir = tmp_path / "scripts"
    (stubdir / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy(SCRIPT.parent / "lib" / "closure-log-added.sh", stubdir / "lib")
    stub = stubdir / "stubbed.sh"
    stub.write_text(src.replace(marker, '  printf %s\\\\n "future-kind\\tX\\t-"', 1), encoding="utf-8")

    f = doc(tmp_path, "spec.md", "closed: B9021")
    p = subprocess.run(
        [
            "/bin/bash", str(stub), "reconcile",
            "--ledger", str(ledger),
            "--deriver", str(deriver),
            str(f),
        ],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert p.returncode != 0, p.stdout
    assert "unknown record kind" in p.stderr, p.stderr
