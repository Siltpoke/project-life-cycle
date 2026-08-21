"""Regression rows for `scripts/invariants/gate-jq-only-envelope.sh`.

WHY THIS FILE EXISTS. Each proof the checker relies on -- a planted
`python3 -c` caught in a declared script under
`scripts/invariants/`, the per-file reds, the undeclared-file red, the stale-exemption red -- can be
run by hand once and never again, and an oracle that only ever existed in a transcript is not an
oracle. These rows are the unattended version.

WHAT EACH ROW IS FOR, and how it is kept honest. Every assertion below has a MUTANT beside it (see
`MUTANTS` and the `test_mutant_*` rows): a deliberately broken copy of the checker that the row must
notice. A row no mutant can redden is a row that would pass against a checker which reports nothing
at all, which is the failure this checker exists to prevent.

WHAT THESE ROWS DELIBERATELY DO NOT DO. They do not re-prove per-file attribution for all the
declared files -- the checker's own `self_coverage` does that on every run, and
`test_self_coverage_proves_every_declared_file_was_read` pins its count and wording. Two
representative files (one from `scripts/`, one from `scripts/invariants/`) carry the end-to-end row,
because each subprocess run costs seconds and one per declared file buys nothing the checker is not already
asserting louder.

The fixture root is passed as the checker's positional ARGUMENT. That argument exists precisely so
these rows can exist: deriving the root from `$0` would make a copied checker resolve its root to
wherever the copy was written, and every mutant below is a copy.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
INVARIANT = REPO / "scripts" / "invariants" / "gate-jq-only-envelope.sh"
MANIFEST = REPO / ".claude" / "close-gate.json"
MD_REL = "skills/project-lifecycle/references/close-gate.md"
INV_DIR = "scripts/invariants"

PLANT = '\nPLANTED=$(python3 -c "pass")\n'


# --------------------------------------------------------------------------------------------
# Reading the checker's own declarations rather than restating them.
#
# A second hand-written copy of the declared set here would drift from the real one, and the row
# that noticed would be this file, months later, for the wrong reason. Parsing keeps the fixtures
# in lockstep with whatever the checker actually declares today.
# --------------------------------------------------------------------------------------------


def _block(name: str, src: str) -> str:
    m = re.search(rf'^{name}="\n(.*?)\n"$', src, re.S | re.M)
    assert m, f"could not locate the {name} block in the checker"
    return m.group(1)


def declared_files(src: str | None = None) -> list[str]:
    return [l.strip() for l in _block("DECLARED", src or INVARIANT.read_text()).splitlines() if l.strip()]


def exempt_files(src: str | None = None) -> list[str]:
    rows = _block("EXEMPT", src or INVARIANT.read_text()).splitlines()
    return [l.split("|", 1)[0].strip() for l in rows if l.strip()]


def run(script: Path | None = None, root: Path | None = None) -> subprocess.CompletedProcess:
    argv = ["/bin/bash", str(script or INVARIANT)]
    if root is not None:
        argv.append(str(root))
    return subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True)


def build_fixture(dst: Path) -> Path:
    """A full copy of the checked set -- never one substituted file.

    With the rest defaulting to the real tree, an unrelated real defect can produce the red, and a
    red that is not attributable to the plant proves nothing. The invariants directory in the
    fixture holds EXACTLY declared + exempt, so the completeness assertion stays green here and
    cannot confound whatever the row is actually testing.
    """
    for rel in [*declared_files(), *exempt_files(), MD_REL]:
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, dst / rel)
    return dst


# The two rows that read a FILE rather than run the checker keep their judgement in a helper, and
# their mutants call the SAME helper on mutated input. A mutant that restates the row's rule instead
# of exercising it proves only that two copies of the rule agree -- the self-witnessing shape.


def own_source_offenders(text: str) -> list[tuple[int, str]]:
    """Hits of the checker's own comment-truncation rule that are not structurally DATA.

    What this misses is named rather than implied: `echo x; python3 y` starts with `echo` and would
    pass. Teaching it to tell a command from a string is a shell lexer, which the checker's own
    header rejects for the same reason -- its failure direction is a false GREEN.
    """
    offenders = []
    for n, line in enumerate(text.splitlines(), 1):
        code = re.sub(r"^\s*#.*$", "", line)
        code = re.sub(r"\s#.*$", "", code)
        if not re.search(r"(^|[^A-Za-z0-9_])python[0-9]*", code):
            continue
        t = line.strip()
        is_data = (
            t.startswith(("echo ", "printf "))  # a message or a planted payload
            or re.match(r"^scripts/\S+\|", t) is not None  # an EXEMPT table row
            or "code ~ /(^|" in t  # the matcher regex itself
        )
        if not is_data:
            offenders.append((n, t))
    return offenders


def declared_and_exempt_overlap(src: str) -> set[str]:
    return set(declared_files(src)) & set(exempt_files(src))


def manifest_invocation(manifest_text: str) -> str:
    entries = [
        e for e in json.loads(manifest_text)["invariants"] if e["name"] == "gate-jq-only-envelope"
    ]
    assert len(entries) == 1, entries
    return entries[0]["command"]


def mutant(tmp_path: Path, needle: str, replacement: str, name: str = "mutant.sh") -> Path:
    src = INVARIANT.read_text()
    assert src.count(needle) == 1, f"mutation needle is not unique: {needle!r}"
    path = tmp_path / name
    path.write_text(src.replace(needle, replacement))
    return path


def assert_mutant_ran(r: subprocess.CompletedProcess, expect: str) -> None:
    """The liveness half of every negative mutant assertion.

    A `test_mutant_*` row's decisive claim is "this message is ABSENT under the mutant". That is
    equally satisfied by a mutant that never ran -- a bash syntax error, a replacement needle that
    silently missed, an early `exit`, a crash before the mutated code. Measurements have gone wrong
    through that exact door before, and the defence used while building this file was a HUMAN
    reading stderr once, which is the kind of oracle this file exists to replace.

    So every negative row also asserts, positively, that the mutant executed and reached the
    machinery under test: clean stderr, plus a row only a running checker prints.
    """
    assert r.stderr == "", f"the mutant did not run cleanly; its absence proves nothing:\n{r.stderr}"
    assert expect in r.stdout, (
        "the mutant produced no evidence of having reached the mechanism under test, so the "
        f"absent-message assertion below proves nothing.\nexpected to see: {expect!r}\ngot:\n{r.stdout}"
    )


# --------------------------------------------------------------------------------------------
# The rows.
# --------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_run():
    return run()


def test_the_real_tree_is_green(real_run):
    """The control. Every red row below is only meaningful against a green baseline."""
    assert real_run.returncode == 0, real_run.stdout + real_run.stderr
    assert "FAIL" not in real_run.stdout, real_run.stdout


def test_every_declared_file_gets_its_own_ok_row(real_run):
    """A declared entry that is never READ looks identical to one that is read and clean.

    This row only proves the entries were listed and reported; the row below is the one that proves
    they were opened.
    """
    for rel in declared_files():
        assert f"ok gate-jq-only-envelope: {rel} invokes no python interpreter" in real_run.stdout


def test_every_exemption_reports_itself_as_still_needed(real_run):
    """Pins OUTPUT SHAPE, not behaviour -- see `test_a_checker_that_only_prints_is_caught`."""
    for rel in exempt_files():
        assert f"ok gate-jq-only-envelope: {rel} exempt, still needed" in real_run.stdout


# The one hand-written list in this file, and the only one that should ever be here.
#
# Every fixture above PARSES the declared set out of the checker, so a widening cannot leave them
# behind. Doing the same for the exemptions would open a hole: move a
# gate-running script from DECLARED to EXEMPT with any plausible one-line reason, plant a REAL
# `python3 -c "print(1)"` in it, and the checker exits 0 while every test here follows the broken
# declaration and stays green.
#
# So the EXEMPT set specifically is PINNED. This is not the stale-list risk coming back: the
# declared set is a list of things that get SCANNED (growing it is safe, and the completeness
# assertion forces every directory member into one set or the other), while the exemption set is a
# list of HOLES. Opening a new hole must be a deliberate act that lands in a diff a reviewer is
# reading, in this file as well as in the checker.
PINNED_EXEMPTIONS = (
    "scripts/invariants/gate-jq-only-envelope.sh",
    "scripts/invariants/context-floor-envelope.sh",
    "scripts/invariants/named-interpreter.sh",
)


def test_the_set_of_exemptions_is_pinned():
    """Opening a new hole in the envelope requires editing this list, deliberately.

    If this row fails, do NOT simply paste the new name in. An exemption means a script that runs
    inside the gate is never scanned for the interpreter the gate is not allowed to need. Confirm
    the file genuinely cannot be scanned (it spells the token as data because it is itself a
    checker), then add it here with the same care the checker's own reason line gets.
    """
    assert tuple(exempt_files()) == PINNED_EXEMPTIONS, (
        "the exemption set changed. Every entry is a file the envelope check does not read; a new "
        "one is a new blind spot in the gate's own dependency envelope."
    )


def test_no_declared_file_is_also_exempt():
    """The two sets must be disjoint, or a file can be listed as scanned and never scanned.

    The completeness assertion asks whether each directory member is in AT LEAST one set. It cannot
    notice a file in BOTH -- and the exemption loop would report it "exempt, still needed" while the
    declared loop reported it clean, which reads like double coverage and is the opposite.
    """
    assert not declared_and_exempt_overlap(INVARIANT.read_text())


def test_the_embedded_markdown_gate_is_scanned_and_non_empty(real_run):
    """`close-gate.md` is a document; only the block an adopter copies out is in scope.

    A locator that finds nothing is a hard FAIL, so a green run must show a real, non-degenerate
    line range -- `ledger-contract-sync.sh` already paid once for an empty span comparing equal to
    an empty span.
    """
    m = re.search(
        rf"ok gate-jq-only-envelope: {re.escape(MD_REL)} \(embedded gate, lines (\d+)-(\d+)\)",
        real_run.stdout,
    )
    assert m, real_run.stdout
    start, end = int(m.group(1)), int(m.group(2))
    assert end > start, (start, end)


def test_self_coverage_proves_every_declared_file_was_read(real_run):
    """The checker's own per-file oracle, pinned by count and by wording.

    This is why the pytest rows below only carry two representative files: `self_coverage` plants a
    python invocation in each declared file in turn, against a full fixture copy, and requires a red
    that NAMES that file -- plus an all-clean control, because a red that appears with nothing
    planted is not evidence.
    """
    n = len(declared_files())
    assert (
        f"ok gate-jq-only-envelope SELF-COVERAGE: each of the {n} declared files was proven readable"
        in real_run.stdout
    ), real_run.stdout


@pytest.mark.parametrize(
    "target",
    ["scripts/close-gate.sh", "scripts/invariants/tasklist-never-tracked.sh"],
)
def test_a_planted_invocation_turns_the_scan_red_and_names_the_file(tmp_path, target):
    """End-to-end: one representative from each directory the declared set spans."""
    root = build_fixture(tmp_path)
    (root / target).write_text((root / target).read_text() + PLANT)

    r = run(root=root)
    assert r.returncode == 1, r.stdout
    assert f"FAIL gate-jq-only-envelope: {target} invokes a python interpreter" in r.stdout, r.stdout


def test_an_unplanted_fixture_of_the_same_shape_is_green(tmp_path):
    """The control for the row above: the fixture shape itself must not be what reddens it."""
    r = run(root=build_fixture(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "FAIL" not in r.stdout, r.stdout


def test_a_file_in_neither_set_is_a_hard_fail(tmp_path):
    """The stale-list risk the hooks-side envelope check NAMES and does not close.

    A hand-written declared set is a deliberate act per entry; its one weakness is a file that
    joins the directory and joins neither set. It runs inside the gate, so it is inside the
    envelope, and silence here would be the old state all over again.
    """
    root = build_fixture(tmp_path)
    (root / INV_DIR / "scratch-thing.sh").write_text("#!/usr/bin/env bash\necho hi\n")

    r = run(root=root)
    assert r.returncode == 1, r.stdout
    assert (
        f"FAIL gate-jq-only-envelope: {INV_DIR}/scratch-thing.sh is in neither the declared set"
        in r.stdout
    ), r.stdout


def test_a_filename_cannot_slip_past_completeness_by_matching_an_exemption_as_a_REGEX(tmp_path):
    """The completeness assertion compares STRINGS, never patterns.

    It used to ask `grep -q "^$rel|"`, interpolating an on-disk filename into a basic regular
    expression -- so a `.` in the name was a wildcard. Reproduced, it looked like this:
    an undeclared, unexempted `probe.v2.sh` matched an EXEMPT line reading
    `probeXv2.sh`, the "is in neither set" row never fired, and the run exited 0. A false PASS, in
    the one mechanism this check was written to add.
    """
    src = INVARIANT.read_text()
    checker = tmp_path / "checker.sh"
    checker.write_text(
        src.replace(
            "scripts/invariants/named-interpreter.sh|one line",
            f"{INV_DIR}/probeXv2.sh|a decoy exemption\nscripts/invariants/named-interpreter.sh|one line",
            1,
        )
    )
    root = build_fixture(tmp_path / "tree")
    # The decoy exemption must exist and must still hold the token, or it reddens for its own reason
    # and the row stops being about the regex at all.
    (root / INV_DIR / "probeXv2.sh").write_text('#!/usr/bin/env bash\necho "python3 kept on purpose"\n')
    # The real file: clean, undeclared, unexempted. It differs from the decoy only where it has a dot.
    (root / INV_DIR / "probe.v2.sh").write_text("#!/usr/bin/env bash\necho hi\n")

    r = run(script=checker, root=root)
    assert (
        f"FAIL gate-jq-only-envelope: {INV_DIR}/probe.v2.sh is in neither the declared set" in r.stdout
    ), f"a dot in the filename let it match an exemption as a pattern:\n{r.stdout}"
    assert r.returncode == 1, r.stdout


def test_an_exemption_that_is_no_longer_needed_turns_red(tmp_path):
    """An exemption is a hole; a hole nobody re-justifies stays open forever.

    Stated limit, inherited from the checker: this asks about the CODE-visible token, so an exempt
    file that moved its only mention into a comment goes red while being genuinely fine.
    """
    root = build_fixture(tmp_path)
    target = f"{INV_DIR}/named-interpreter.sh"
    scrubbed = "\n".join(
        line for line in (root / target).read_text().splitlines() if "python" not in line
    )
    (root / target).write_text(scrubbed + "\n")

    r = run(root=root)
    assert r.returncode == 1, r.stdout
    assert (
        f"FAIL gate-jq-only-envelope: {target} is EXEMPT but no longer contains the token" in r.stdout
    ), r.stdout


def test_an_empty_declared_set_is_a_failure_not_a_vacuous_pass(tmp_path):
    """`ledger-contract-sync.sh` already paid for this once: an empty scan prints nothing and reads
    exactly like a clean repository."""
    src = INVARIANT.read_text()
    emptied = tmp_path / "emptied.sh"
    emptied.write_text(re.sub(r'^DECLARED="\n.*?\n"$', 'DECLARED=""', src, flags=re.S | re.M))

    r = run(script=emptied, root=build_fixture(tmp_path / "tree"))
    assert r.returncode == 1, r.stdout
    assert "the declared set is EMPTY" in r.stdout, r.stdout


def test_an_empty_invariants_directory_is_a_failure(tmp_path):
    """The branch the checker's own comment calls unreachable by any fixture -- reached, once, on
    purpose.

    Many declared files live in that directory, so a root with an empty `scripts/invariants/` fails
    the "missing or unreadable" rows long before arriving here. Getting there needs a declared set
    that no longer includes anything from the directory -- which is exactly the day the branch
    becomes reachable in production, and the day a vacuous pass would look identical to a covered
    one.
    """
    src = INVARIANT.read_text()
    narrowed = tmp_path / "narrowed.sh"
    narrowed.write_text(
        re.sub(
            r'^EXEMPT="\n.*?\n"$',
            'EXEMPT=""',
            re.sub(
                r'^DECLARED="\n.*?\n"$',
                'DECLARED="\nscripts/close-gate.sh\n"',
                src,
                flags=re.S | re.M,
            ),
            flags=re.S | re.M,
        )
    )

    root = tmp_path / "tree"
    (root / "scripts" / "invariants").mkdir(parents=True)
    (root / MD_REL).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "scripts/close-gate.sh", root / "scripts/close-gate.sh")
    shutil.copy(REPO / MD_REL, root / MD_REL)

    r = run(script=narrowed, root=root)
    assert r.returncode == 1, r.stdout
    assert f"no .sh found in {INV_DIR}" in r.stdout, r.stdout


def test_the_gate_invokes_this_checker_with_no_arguments():
    """The trust boundary the checker's header states, as a row.

    The root is an argument, so a decoy root would make the scan read a tree that is not the repo.
    The mitigation named in the header is that the only invocation that matters is the one written
    into the tracked manifest, visible in every diff -- which is worth nothing unless something
    asserts it.
    """
    # Every registration in the manifest spells the interpreter the same way,
    # and it is `/bin/bash` rather than a bare `bash`
    # because `named-interpreter.sh` reds a bare `bash ` in any tracked `*.sh`, so the bare form
    # is the one that cannot be copied out of this manifest into a script. This assertion goes
    # red when that string changes rather than letting it drift silently, which is
    # the whole reason it exists.
    assert manifest_invocation(MANIFEST.read_text()) == "/bin/bash scripts/invariants/gate-jq-only-envelope.sh"


def test_the_checker_itself_invokes_no_python_interpreter():
    """The honest substitute for the one thing this checker cannot assert about itself.

    It is exempt by construction -- its matcher regex and every failure string necessarily spell the
    token it bans -- so "it is clean" cannot come from scanning it. Instead: apply the checker's own
    comment-truncation rule to its own source and require every surviving hit to be STRUCTURALLY
    data, not a command. The rule lives in `own_source_offenders`, which names what it misses.
    """
    text = INVARIANT.read_text()
    assert re.search(r"(^|[^A-Za-z0-9_])python[0-9]*", text), (
        "the token is absent entirely -- this row would pass on any file"
    )
    assert not own_source_offenders(text)


# --------------------------------------------------------------------------------------------
# The mutation table.
#
# Each entry breaks ONE mechanism and names the row above that must notice. A row with no mutant
# beside it is a row that has never been shown capable of failing.
# --------------------------------------------------------------------------------------------

BLIND_MATCHER = (
    'if (code ~ /(^|[^[:alnum:]_])python[0-9]*/) print NR ": " $0',
    'if (0) print NR ": " $0',
)
LOUD_MATCHER = (
    'if (code ~ /(^|[^[:alnum:]_])python[0-9]*/) print NR ": " $0',
    'if (1) print NR ": " $0',
)


def test_mutant_blind_matcher_defeats_the_planted_invocation_row(tmp_path):
    """M1 -- the matcher reports nothing. The per-file row must lose its named FAIL.

    Noted rather than left to be discovered: this mutant still exits 1, because a matcher that
    reports nothing also makes all three exemptions look expired. The row is therefore written
    against the NAMED failure line, not against the exit code -- an exit-code assertion here would
    have passed on a fully blinded checker.
    """
    m = mutant(tmp_path, *BLIND_MATCHER)
    root = build_fixture(tmp_path / "tree")
    target = "scripts/close-gate.sh"
    (root / target).write_text((root / target).read_text() + PLANT)

    r = run(script=m, root=root)
    assert_mutant_ran(r, "ok gate-jq-only-envelope: scripts/gen-test-evidence.sh invokes no python")
    assert (
        f"FAIL gate-jq-only-envelope: {target} invokes a python interpreter" not in r.stdout
    ), "the planted-invocation row would pass against a checker that reports nothing"


def test_mutant_loud_matcher_defeats_the_green_control_row(tmp_path):
    """M2 -- the matcher flags every line. The all-clean control must go red.

    Without this, `test_an_unplanted_fixture_of_the_same_shape_is_green` and
    `test_the_real_tree_is_green` would be satisfied by a checker that had stopped discriminating.
    """
    m = mutant(tmp_path, *LOUD_MATCHER)
    r = run(script=m, root=build_fixture(tmp_path / "tree"))
    assert r.returncode == 1, r.stdout
    assert "FAIL" in r.stdout


def test_mutant_completeness_always_known_defeats_the_undeclared_file_row(tmp_path):
    """M3 -- every file is treated as already declared."""
    m = mutant(tmp_path, "    known=0\n", "    known=1\n")
    root = build_fixture(tmp_path / "tree")
    (root / INV_DIR / "scratch-thing.sh").write_text("#!/usr/bin/env bash\necho hi\n")

    r = run(script=m, root=root)
    assert_mutant_ran(r, "ok gate-jq-only-envelope: scripts/close-gate.sh invokes no python")
    assert "is in neither the declared set" not in r.stdout


def test_mutant_tolerant_exemption_defeats_the_stale_exemption_row(tmp_path):
    """M4 -- an exemption is never re-justified."""
    m = mutant(
        tmp_path,
        '    hits="$(scan "$root/$f" 1 "$(grep -c \'\' "$root/$f")")"\n    if [ -z "$hits" ]; then',
        '    hits="$(scan "$root/$f" 1 "$(grep -c \'\' "$root/$f")")"\n    if false; then',
    )
    root = build_fixture(tmp_path / "tree")
    target = f"{INV_DIR}/named-interpreter.sh"
    (root / target).write_text(
        "\n".join(l for l in (root / target).read_text().splitlines() if "python" not in l) + "\n"
    )

    r = run(script=m, root=root)
    assert_mutant_ran(r, "ok gate-jq-only-envelope: scripts/close-gate.sh invokes no python")
    assert "is EXEMPT but no longer contains the token" not in r.stdout


def test_mutant_no_empty_list_guard_defeats_the_empty_declared_set_row(tmp_path):
    """M5 -- the empty declared set scans nothing and says nothing about it."""
    src = INVARIANT.read_text()
    m = tmp_path / "m5.sh"
    m.write_text(
        re.sub(r'^DECLARED="\n.*?\n"$', 'DECLARED=""', src, flags=re.S | re.M).replace(
            '  if [ "$n_decl" -eq 0 ]; then', "  if false; then"
        )
    )
    assert 'if [ "$n_decl" -eq 0 ]' not in m.read_text()

    r = run(script=m, root=build_fixture(tmp_path / "tree"))
    assert_mutant_ran(r, "exempt, still needed")
    assert "the declared set is EMPTY" not in r.stdout


def test_mutant_no_empty_dir_guard_defeats_the_empty_directory_row(tmp_path):
    """M6 -- a completeness check over an empty directory passes vacuously."""
    src = INVARIANT.read_text()
    m = tmp_path / "m6.sh"
    m.write_text(
        re.sub(
            r'^EXEMPT="\n.*?\n"$',
            'EXEMPT=""',
            re.sub(
                r'^DECLARED="\n.*?\n"$',
                'DECLARED="\nscripts/close-gate.sh\n"',
                src,
                flags=re.S | re.M,
            ),
            flags=re.S | re.M,
        ).replace('  if [ "$found" -eq 0 ]; then', "  if false; then")
    )
    assert 'if [ "$found" -eq 0 ]' not in m.read_text()

    root = tmp_path / "tree"
    (root / "scripts" / "invariants").mkdir(parents=True)
    (root / MD_REL).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "scripts/close-gate.sh", root / "scripts/close-gate.sh")
    shutil.copy(REPO / MD_REL, root / MD_REL)

    r = run(script=m, root=root)
    assert_mutant_ran(r, "ok gate-jq-only-envelope: scripts/close-gate.sh invokes no python")
    assert f"no .sh found in {INV_DIR}" not in r.stdout


def test_mutant_self_coverage_skipped_defeats_the_self_coverage_row(tmp_path):
    """M7 -- the per-file oracle is never called, and every declared file goes back to looking
    read."""
    m = mutant(tmp_path, 'self_coverage "$REPO_ROOT" || RC=1', ":")
    r = run(script=m, root=build_fixture(tmp_path / "tree"))
    assert_mutant_ran(r, "ok gate-jq-only-envelope: scripts/close-gate.sh invokes no python")
    assert "SELF-COVERAGE" not in r.stdout


def test_a_checker_that_only_prints_is_caught_by_the_behavioural_rows(tmp_path):
    """M11 -- the liar. Prints every expected `ok` line, reads nothing, exits 0.

    The four real-run rows above (declared ok-rows, exemption
    ok-rows, the markdown range, the self-coverage line) would all pass against exactly this, and
    they do: measured against a liar, those four are GREEN. They pin output SHAPE, which is
    worth pinning and is not the same as proving the checker read anything.

    What actually catches a liar is the behavioural rows, and this is the committed proof of that
    -- and a stub that omitted the
    `DECLARED`/`EXEMPT` blocks would make the rows die in this file's own parser rather than on any
    assertion. So the liar below carries those blocks verbatim, and the row asserts the liar gets
    caught by the thing that would actually catch it: a planted invocation goes unreported.
    """
    src = INVARIANT.read_text()
    decl_block = re.search(r'^DECLARED="\n.*?\n"$', src, re.S | re.M).group(0)
    exempt_block = re.search(r'^EXEMPT="\n.*?\n"$', src, re.S | re.M).group(0)

    lines = ["#!/usr/bin/env bash", "set -uo pipefail", decl_block, exempt_block]
    for rel in declared_files():
        lines.append(f'echo "ok gate-jq-only-envelope: {rel} invokes no python interpreter"')
    lines.append(
        f'echo "ok gate-jq-only-envelope: {MD_REL} (embedded gate, lines 1-2) invokes no python interpreter"'
    )
    for rel in exempt_files():
        lines.append(f'echo "ok gate-jq-only-envelope: {rel} exempt, still needed (a reason)"')
    lines.append(
        f'echo "ok gate-jq-only-envelope SELF-COVERAGE: each of the {len(declared_files())} '
        'declared files was proven readable"'
    )
    lines.append("exit 0")
    liar = tmp_path / "liar.sh"
    liar.write_text("\n".join(lines) + "\n")

    root = build_fixture(tmp_path / "tree")
    target = "scripts/close-gate.sh"
    (root / target).write_text((root / target).read_text() + PLANT)

    r = run(script=liar, root=root)
    assert_mutant_ran(r, "ok gate-jq-only-envelope: scripts/close-gate.sh invokes no python")
    assert r.returncode == 0, "the liar is supposed to be green; that is what makes it a liar"
    assert (
        f"FAIL gate-jq-only-envelope: {target} invokes a python interpreter" not in r.stdout
    ), "a checker that reads nothing must not be able to report a planted invocation"


def test_mutant_restructured_markdown_defeats_the_embedded_gate_row(tmp_path):
    """M9 -- the anchor heading is renamed, so the locator finds nothing.

    The row above asserts a real, non-degenerate line range. Without this mutant it would also be
    satisfied by a checker whose locator had gone stale, which is the failure the checker's own
    "an unfindable gate is not an unchecked one" message exists to prevent.
    """
    root = build_fixture(tmp_path / "tree")
    md = root / MD_REL
    md.write_text(md.read_text().replace("## Portable gate script", "## Gate script, portable"))

    r = run(root=root)
    assert r.returncode == 1, r.stdout
    assert "cannot locate the embedded gate" in r.stdout, r.stdout
    assert re.search(rf"ok gate-jq-only-envelope: {re.escape(MD_REL)} \(embedded gate", r.stdout) is None


def test_mutant_manifest_with_an_argument_defeats_the_no_arguments_row():
    """M10 -- the manifest gains a root argument, in memory.

    The row reads a tracked file, so its mutant is a modified value rather than a copy that gets
    executed. A decoy root passed from the manifest is the exact attack the checker's stated trust
    boundary leans on this row to make visible.
    """
    doc = json.loads(MANIFEST.read_text())
    for e in doc["invariants"]:
        if e["name"] == "gate-jq-only-envelope":
            e["command"] += " /tmp/decoy"
    mutated = manifest_invocation(json.dumps(doc))
    assert mutated != "bash scripts/invariants/gate-jq-only-envelope.sh", (
        "the no-arguments row cannot notice a root argument smuggled into the manifest"
    )


def test_the_liveness_check_itself_can_fire():
    """M15 -- the guard on the guards, because it was verified by hand exactly once.

    `assert_mutant_ran` is what stops six negative rows from being satisfied by a mutant that never
    ran. It was proven by rewriting this file in a temp directory so every mutant died at `exit 3`
    and watching all six go red -- a hand-run oracle, which is the shape this file exists to
    replace. This is that measurement, committed: a dead run must raise, both on empty output and on
    dirty stderr, and a live one must not.
    """
    dead = subprocess.CompletedProcess(args=[], returncode=3, stdout="", stderr="")
    with pytest.raises(AssertionError, match="no evidence of having reached"):
        assert_mutant_ran(dead, "ok gate-jq-only-envelope: scripts/close-gate.sh invokes no python")

    noisy = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="ok gate-jq-only-envelope: x", stderr="line 4: syntax error"
    )
    with pytest.raises(AssertionError, match="did not run cleanly"):
        assert_mutant_ran(noisy, "ok gate-jq-only-envelope: x")

    live = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="ok gate-jq-only-envelope: x", stderr=""
    )
    assert_mutant_ran(live, "ok gate-jq-only-envelope: x")


def test_mutant_a_new_exemption_defeats_the_pinned_exemption_row():
    """M13 -- a hole opened in the checker, in memory.

    The scenario this pin exists for: moving `ledger-contract-sync.sh`
    from DECLARED to EXEMPT with a plausible reason and planting a REAL `python3 -c "print(1)"` in
    it leaves the invariant at exit 0 and every other row green. Both oracles follow the
    broken declaration. Calls the row's OWN parser on mutated source rather than restating its rule.
    """
    mutated = INVARIANT.read_text().replace(
        f"{INV_DIR}/named-interpreter.sh|",
        f"{INV_DIR}/ledger-contract-sync.sh|a plausible reason\n{INV_DIR}/named-interpreter.sh|",
        1,
    )
    assert tuple(exempt_files(mutated)) != PINNED_EXEMPTIONS, (
        "the pin cannot notice a newly opened hole in the envelope"
    )


def test_mutant_a_file_in_both_sets_defeats_the_disjoint_row():
    """M14 -- a file listed as scanned AND exempt, in memory."""
    mutated = INVARIANT.read_text().replace(
        f"{INV_DIR}/named-interpreter.sh|",
        f"{INV_DIR}/tasklist-never-tracked.sh|listed in both, which reads as double coverage\n"
        f"{INV_DIR}/named-interpreter.sh|",
        1,
    )
    assert declared_and_exempt_overlap(mutated) == {
        f"{INV_DIR}/tasklist-never-tracked.sh"
    }


def test_mutant_planted_invocation_in_the_checker_defeats_the_own_source_row():
    """M8 -- the own-source row, mutated in memory rather than on disk.

    It reads the checker's source directly, so its mutant is a modified string, not a copy that gets
    executed. A top-level assignment is the shape a real drift would take.
    """
    offenders = own_source_offenders(INVARIANT.read_text() + PLANT)
    assert offenders, "the own-source row cannot notice a plain top-level invocation"
