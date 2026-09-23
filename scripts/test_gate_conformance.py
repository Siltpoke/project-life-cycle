"""Conformance suite — what a close gate must DO, authored once, run against each gate alone.

This file is deliberately not a comparison. It never diffs the two gate scripts against each
other and never imports a constant from either one. Each gate is handed the same fixture and
judged on its own against a requirement written here, from the phase's signed-off acceptance
criteria (p37 AC1-AC3) rather than from any implementation.

Why that shape, and what it buys (the conformance design):

    A byte-identity check, a behavioural diff, and a feature-parity ledger all report
    "consistent" when BOTH gates are wrong in the same way. Consistency between two wrong things
    is not correctness. Only an independently authored requirement can fail both at once.

What it does NOT buy, stated because the claim was first written too wide and a cross-check
caught it: this catches both gates disagreeing with THE REQUIREMENT BELOW. It cannot catch both
gates agreeing with a requirement that is itself wrong. The requirement's content came from a
human-signed acceptance criterion, which is a judgement, not a fact -- check 9's own source
records an earlier, stricter version of this same shape rule being rejected. Independence here
is real at the level of code and partial at the level of judgement.

SCOPE: check 9 only. Every other check this gate performs is uncovered by this file, on purpose
(the conformance design). A check ported into a gate without a requirement added here produces a fully green
run and a real coverage hole -- the suite cannot notice a check it was never told about. That
hole is named rather than mitigated in this phase.
"""
from pathlib import Path

import pytest

from close_gate_lib import extract_gate_script, make_fixture_repo, run_gate

ROOT = Path(__file__).resolve().parents[1]
GATE_MD = ROOT / "skills/project-lifecycle/references/close-gate.md"
GATE_SH = ROOT / "scripts/close-gate.sh"

# The manifest key under test. This is the ADOPTER-FACING contract -- it is the name a person
# writes in their own .claude/close-gate.json -- not an internal symbol lifted out of a script.
KEY = "validator_input_paths_rationale"
NARROWING_KEY = "test_evidence_inputs"

# --- The requirement, transcribed from the signed-off story (p37 AC1-AC3) -------------------
#
# AC1  narrowing declared + rationale absent  -> non-zero exit AND a failure row naming the key
# AC2  no narrowing at all                    -> the check does not fire; no row names the key
# AC3  rationale present but a placeholder    -> a failure row names the key
# AC3  rationale shaped like a measurement    -> no failure row names the key
#      ("at least two numbers, matching /track/i" -- AC3's own wording)
# AC3  rationale present but not a JSON array -> a failure row names the key
#
# A "measurement-shaped" value, per AC3. Written here from that prose; the phrase happens to
# read like this repo's own rationale, which is where AC3's wording came from in the first place.
MEASUREMENT = ["2050 files, 77 tracked -- the narrowed set is exactly the validator's inputs"]

# A placeholder in the scaffolder's own house style. It carries NO two numbers and NOT the word
# "track", which is precisely what must keep it from satisfying the requirement (the conformance design).
PLACEHOLDER = ["REPLACE_ME_WHY_THE_INPUT_SET_IS_NARROW"]

# p30's replacement shape. `surface_kept` is deliberately ABSENT: the gate derives it, and writing
# it is itself a failure (p30:AC2).
OBJECT_SHAPE = {
    "surface_total": 2050,
    "basis": "tracked-files",
    "why": ["the narrowed set is exactly the validator's inputs"],
}


GATES = ["canonical", "variant"]


@pytest.fixture(params=GATES)
def gate(request: pytest.FixtureRequest) -> tuple[str, str]:
    """One gate at a time. Never both in the same assertion."""
    if request.param == "canonical":
        return "canonical", extract_gate_script(GATE_MD)
    return "variant", GATE_SH.read_text(encoding="utf-8")


# A sentinel meaning "write the key with an explicit JSON null", as distinct from `None`, which
# means "omit the key entirely". They are DIFFERENT manifests and a gate can treat them
# differently; before this existed, `narrowing=None` covered only the omitted case while
# .claude/ac-evidence.json claimed both were covered -- a claim wider than its mechanism, inside
# the file whose whole job is recording what is covered. Found by a blind cross-family review.
EXPLICIT_NULL = object()


def _manifest(*, narrowing: object, rationale: object) -> dict:
    m: dict = {"test_command": "true", "test_evidence": ".claude/.last-test-run"}
    if narrowing is EXPLICIT_NULL:
        m[NARROWING_KEY] = None
    elif narrowing is not None:
        m[NARROWING_KEY] = narrowing
    if rationale is EXPLICIT_NULL:
        m[KEY] = None
    elif rationale is not None:
        m[KEY] = rationale
    return m


def _rows_naming_the_key(repo: Path, script: str) -> list[str]:
    """EVERY non-passing row naming the key, whatever its glyph. Used by the assertions that
    require SILENCE -- "the check did not fire" must mean no ✗ and no ⚠ and no anything else, so
    this side is deliberately the widest possible net."""
    result = _task(repo, script)
    return [
        ln
        for ln in result.stdout.splitlines()
        if KEY in ln and not ln.lstrip().startswith(("✓", "⊘"))
    ]


def _failing_rows_naming_the_key(repo: Path, script: str) -> list[str]:
    """Rows that BLOCK. Used by the assertions that require the gate to REPORT the problem.

    THE ✗ IS LOAD-BEARING AND ITS ABSENCE WAS A REAL HOLE, found by a blind cross-family review
    that ran the experiment rather than reasoning about it: with a single net for both directions,
    changing a gate's `bad "...rationale..."` to `warn "...rationale..."` -- turning check 9 from
    blocking into advisory, which is most of the point of the check -- left every assertion in this
    file GREEN, because `⚠` is neither `✓` nor `⊘`. Requiring `✗` here is what makes "reported"
    mean "refused". The suite deliberately does not read the process exit code (many other checks
    move it), so the glyph is the only signal of blocking-ness available."""
    result = _task(repo, script)
    return [ln for ln in result.stdout.splitlines() if KEY in ln and ln.lstrip().startswith("✗")]


def _task(repo: Path, script: str):
    """Run task mode. A PHASE argument is passed because one of the two gates REQUIRES it and the
    other ignores it -- an interface divergence between the two homes that this suite discovered
    on its first run and that nothing else in the repo states. Passing it keeps the invocation
    identical for both gates, which is what makes the comparison-free assertions comparable."""
    return run_gate(repo, script, "task", "1.0")


def _repo(tmp_path: Path, manifest: dict) -> Path:
    return make_fixture_repo(tmp_path, manifest, {"src/app.py": "x = 1\n"})


# --- AC1 -------------------------------------------------------------------------------------
def test_narrowing_without_a_rationale_is_reported(tmp_path: Path, gate: tuple[str, str]) -> None:
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=None))
    rows = _failing_rows_naming_the_key(repo, script)
    assert rows, (
        f"[{name}] a manifest that narrows {NARROWING_KEY} and declares no {KEY} must be told so.\n"
        f"Narrowing is a safety-reducing choice; the requirement is that it be argued, not silent."
    )


# AC1's other half -- "and exits non-zero" -- is NOT asserted here, and the reason is a finding
# rather than an omission. A test that only reads the exit code passed for the canonical gate on
# this suite's first run, at a moment when that gate had no check 9 at all: every other check in
# the same fixture (product tree, journal, CHANGELOG) was already failing, so the process exit
# code could not discriminate. An assertion that cannot fail for the reason it names is the
# "green that proves nothing" this repo keeps filing, so it was deleted rather than kept for
# coverage arithmetic. Isolating the exit code would need an otherwise-passing fixture -- every
# other check satisfied -- which is a fixture this phase does not build. The row IS the gate's
# statement about this key, and the row is what the requirement is written against.


# --- AC2 -------------------------------------------------------------------------------------
def test_no_narrowing_means_the_check_does_not_fire(tmp_path: Path, gate: tuple[str, str]) -> None:
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=None, rationale=None))
    rows = _rows_naming_the_key(repo, script)
    assert not rows, (
        f"[{name}] with no {NARROWING_KEY} there is no narrowing to argue for, so nothing may be\n"
        f"demanded. Got:\n" + "\n".join(rows)
    )


# --- AC3 -------------------------------------------------------------------------------------
def test_a_placeholder_does_not_satisfy_the_requirement(tmp_path: Path, gate: tuple[str, str]) -> None:
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=PLACEHOLDER))
    rows = _failing_rows_naming_the_key(repo, script)
    assert rows, (
        f"[{name}] an untouched scaffold placeholder must not pass -- if it does, the key becomes\n"
        f"a formality and the whole requirement is theatre."
    )


def test_the_object_shape_satisfies_it_in_total_silence(tmp_path: Path, gate: tuple[str, str]) -> None:
    """p30:AC1 -- the shape that replaced the prose rule passes with NO row of any glyph.

    This is where the widest net stays fully wide, and that matters: `_rows_naming_the_key` refuses
    ANY row that is not a pass, so flipping this branch's `bad` to `warn` -- the downgrade attack a
    blind review found this suite blind to -- still reddens here.
    """
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=OBJECT_SHAPE))
    rows = _rows_naming_the_key(repo, script)
    assert not rows, (
        f"[{name}] the object shape is the accepted form and must produce no row at all.\n"
        f"Got:\n" + "\n".join(rows)
    )


def test_a_measurement_shaped_array_still_passes_but_is_marked_deprecated(
    tmp_path: Path, gate: tuple[str, str]
) -> None:
    """p30:AC12 -- the legacy shape keeps working, and says so, WITHOUT blocking.

    Two assertions, and the split is the point. A warning that fails the build is a removal wearing
    a warning's words, so the first assertion is that nothing BLOCKS. The second is that exactly one
    row appeared and it is the deprecation row, identified by a stable token rather than by a
    sentence -- if a future edit downgraded the object branch's `bad` into a `warn`, this count would
    read two.

    STATED LIMIT, because the net here is necessarily narrower than in the object case: for the
    legacy shape "silence" is the WRONG expectation -- the check did fire, and saying so is the
    feature. What replaces the wide net is the count plus the token, not prose matching.
    """
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=MEASUREMENT))
    blocking = _failing_rows_naming_the_key(repo, script)
    assert not blocking, (
        f"[{name}] the legacy array shape is DEPRECATED, not removed -- it must not block.\n"
        f"Got:\n" + "\n".join(blocking)
    )
    rows = _rows_naming_the_key(repo, script)
    assert len(rows) == 1, f"[{name}] expected exactly one deprecation row, got:\n" + "\n".join(rows)
    assert rows[0].lstrip().startswith("\u26a0"), f"[{name}] deprecation row is not a warning: {rows[0]}"
    assert DEPRECATION_MARKER in rows[0], (
        f"[{name}] the one row is not the deprecation row: {rows[0]}"
    )


def test_a_non_array_rationale_is_reported(tmp_path: Path, gate: tuple[str, str]) -> None:
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale="two numbers, 7 tracked"))
    rows = _failing_rows_naming_the_key(repo, script)
    assert rows, (
        f"[{name}] the declared shape is a JSON array; a bare string must be reported, not\n"
        f"silently accepted because its text happens to look right."
    )


# --- AC2's edges ------------------------------------------------------------------------------
# AC2 says "no test_evidence_inputs at all". Four values are not "at all" in four different ways,
# and a gate that guesses differently on any of them is a gate whose escape hatch is unpredictable.
# The resolutions are the ones written into both gate scripts at the check's insertion point, and
# each is asserted here rather than left to be read out of the code.


def test_an_empty_narrowing_array_does_not_fire(tmp_path: Path, gate: tuple[str, str]) -> None:
    """`[]` is a declared key holding no narrowing. Nothing was narrowed, so nothing is owed."""
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=[], rationale=None))
    rows = _rows_naming_the_key(repo, script)
    assert not rows, (
        f"[{name}] an empty {NARROWING_KEY} array narrows nothing and must demand nothing.\n"
        f"Got:\n" + "\n".join(rows)
    )


def test_a_malformed_narrowing_does_not_demand_a_rationale(tmp_path: Path, gate: tuple[str, str]) -> None:
    """A non-array value is already rejected as a malformed narrowing by the freshness check. A
    second row demanding a rationale for it would name a fix that does not fix anything: writing
    the rationale leaves the manifest just as broken."""
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing="src/", rationale=None))
    rows = _rows_naming_the_key(repo, script)
    assert not rows, (
        f"[{name}] a malformed {NARROWING_KEY} is the freshness check's finding, not this one's.\n"
        f"Got:\n" + "\n".join(rows)
    )


def test_a_blank_glob_is_still_a_declared_narrowing(tmp_path: Path, gate: tuple[str, str]) -> None:
    """`["  "]` IS a narrowing -- a broken one. This is not a fresh judgement: the freshness check
    already treats it that way, word-splitting the glob list to zero pathspecs and rejecting it as
    a narrowing that matched nothing. Declared-and-broken is not undeclared, so the argument is
    still owed."""
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=["  "], rationale=None))
    rows = _failing_rows_naming_the_key(repo, script)
    assert rows, (
        f"[{name}] a declared-but-broken {NARROWING_KEY} is still a declared narrowing, and the\n"
        f"argument for it is still owed. Treating it as 'no narrowing' would make the escape hatch\n"
        f"reachable by writing a glob badly."
    )


# --- AC4 --------------------------------------------------------------------------------------
# The failing row must name the fix. Asserted by substring against REAL gate output, per the
# criterion's own wording ("not by reading the source").
#
# WHAT THIS DOES NOT PROVE, stated because the plan required it stated rather than discovered: a
# substring pin stays green while the wording around it rots. These assertions catch the example
# and the escape hatch's price DISAPPEARING; they cannot catch either becoming wrong, misleading,
# or unreadable. No claim is made here that AC4 protects message quality.

# A literal an adopter can paste. Pinned as the opening of a JSON key/array, not as the whole
# sentence, so an honest re-measurement of the numbers inside it does not turn this red -- the same
# reason check 9 itself asserts a measurement's SHAPE and not its digits.
# p30 CHANGED THE PASTEABLE SHAPE. It used to be the array form; the object form is what an
# adopter must now paste, so pinning the old prefix would pin the message to the shape this phase
# deprecated. The marker below is the stable identity of the deprecation row -- pinned by TOKEN
# rather than by prose, because a substring of an English sentence is not an identity.
PASTEABLE = '"validator_input_paths_rationale": {'
DEPRECATION_MARKER = "[p30-deprecated-array-shape]"
# The escape hatch is not free and the row has to say so: deleting the narrowing silences check 9
# AND drops the freshness check to mtime. This is a deliberate concession -- the phase declined a timed
# migration window, and the price being stated in the error is what was given instead.
ESCAPE_HATCH_PRICE = "legacy mtime"


def _failing_row(repo: Path, script: str) -> str:
    rows = _failing_rows_naming_the_key(repo, script)
    assert rows, "expected a failing row to inspect"
    return "\n".join(rows)


def test_the_missing_rationale_row_names_the_fix(tmp_path: Path, gate: tuple[str, str]) -> None:
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=None))
    row = _failing_row(repo, script)
    assert PASTEABLE in row, f"[{name}] no pasteable example in:\n{row}"
    assert ESCAPE_HATCH_PRICE in row, f"[{name}] the escape hatch's price is not stated in:\n{row}"


def test_the_placeholder_row_names_the_fix(tmp_path: Path, gate: tuple[str, str]) -> None:
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=PLACEHOLDER))
    row = _failing_row(repo, script)
    assert PASTEABLE in row, f"[{name}] no pasteable example in:\n{row}"
    assert ESCAPE_HATCH_PRICE in row, f"[{name}] the escape hatch's price is not stated in:\n{row}"
    # p30 RE-POINTED THIS ASSERTION, and the intent is unchanged: the row must say what shape it
    # WANTS, not merely that the value is wrong. It used to check for "two numbers", which was the
    # old prose rule's own wording -- keeping that string would pin the message to the rule this
    # phase removed. What it checks now is a requirement the old rule did not have and that an
    # author will otherwise get wrong: the kept-count is DERIVED, so writing it is itself a failure
    # (p30:AC2), and a row that does not say so sends the author to add the very member the gate
    # refuses.
    assert "surface_kept" in row, (
        f"[{name}] the row must say what shape it wants -- including that surface_kept is derived\n"
        f"and must not be written -- not merely that the value is wrong:\n{row}"
    )


def test_an_explicit_null_narrowing_does_not_fire(tmp_path: Path, gate: tuple[str, str]) -> None:
    """`"test_evidence_inputs": null` written out, as opposed to the key being absent. Two
    different manifests; a gate reads them through `jq -r '... | type'`, which answers "null" for
    both, but nothing guarantees a future implementation keeps that. This assertion existed only
    as a claim in the evidence row until a blind cross-family review pointed out the fixture
    helper could not even express it."""
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=EXPLICIT_NULL, rationale=None))
    rows = _rows_naming_the_key(repo, script)
    assert not rows, (
        f"[{name}] an explicit null {NARROWING_KEY} narrows nothing, exactly as an absent key does.\n"
        f"Got:\n" + "\n".join(rows)
    )


# --- p30: the object shape's own rules ---------------------------------------------------------
#
# These live in the CONFORMANCE suite rather than in a p30-only file on purpose: the whole point of
# this file is that a change landing on one gate home and not the other goes red, and these rules are
# exactly the kind of thing an author would port to one home and forget in the other.

@pytest.mark.parametrize(
    "label,rationale",
    [
        # p30:AC2 -- a declared kept-count is REFUSED, not ignored. Accepting-and-ignoring it lets a
        # stale copied number sit in the manifest looking authoritative while nothing reads it, which
        # is the 77-vs-595 shape this phase exists to remove.
        ("declares the derived member",
         {"surface_total": 2050, "surface_kept": 77, "basis": "tracked-files", "why": ["x"]}),
        # p30:AC1 -- each member checked for what it IS.
        ("surface_total is a numeric STRING",
         {"surface_total": "2050", "basis": "tracked-files", "why": ["x"]}),
        ("surface_total is zero",
         {"surface_total": 0, "basis": "tracked-files", "why": ["x"]}),
        ("surface_total is negative",
         {"surface_total": -1, "basis": "tracked-files", "why": ["x"]}),
        ("surface_total absent",
         {"basis": "tracked-files", "why": ["x"]}),
        ("basis is not in the enum",
         {"surface_total": 2050, "basis": "whatever-i-felt-like", "why": ["x"]}),
        ("basis absent",
         {"surface_total": 2050, "why": ["x"]}),
        ("why is an empty array",
         {"surface_total": 2050, "basis": "tracked-files", "why": []}),
        ("why is a bare string, not an array",
         {"surface_total": 2050, "basis": "tracked-files", "why": "x"}),
        ("why holds only whitespace",
         {"surface_total": 2050, "basis": "tracked-files", "why": ["   "]}),
        ("why holds a non-string",
         {"surface_total": 2050, "basis": "tracked-files", "why": [7]}),
    ],
)
def test_a_malformed_object_is_refused(
    tmp_path: Path, gate: tuple[str, str], label: str, rationale: dict
) -> None:
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=rationale))
    rows = _failing_rows_naming_the_key(repo, script)
    assert rows, f"[{name}] {label}: this must be refused, and it was not"


@pytest.mark.parametrize("basis", ["tracked-files", "all-files", "glob-set", "explicit-path-list"])
def test_every_declared_enum_value_is_accepted(
    tmp_path: Path, gate: tuple[str, str], basis: str
) -> None:
    """All four, not just the one the examples use.

    `all-files` in particular MUST be accepted: p30:AC6's object-branch cheat string uses it, and if
    it were rejected on the enum predicate the mutant would never reach `surface_total` -- it would
    silently prove enum-rejection works while appearing to prove that forgery passes. A test green
    for the wrong reason. Cross-check agent B found that the enum had never been written down at all.
    """
    name, script = gate
    rationale = {"surface_total": 2050, "basis": basis, "why": ["prose"]}
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=rationale))
    rows = _rows_naming_the_key(repo, script)
    assert not rows, f"[{name}] basis={basis} is a declared enum value and must pass:\n" + "\n".join(rows)


def test_why_may_be_any_language_and_the_gate_reads_none_of_it(
    tmp_path: Path, gate: tuple[str, str]
) -> None:
    """The whole point. These four are quoted from the filing table itself.

    No CJK literal appears in this file: the CJK rule exempts `docs/` outright and nothing
    else, so the Chinese case is written with escapes. That is a constraint of where this file lives,
    not a hedge about what is being tested -- the bytes reaching the gate are the same either way.
    """
    name, script = gate
    prose = [
        "two thousand fifty markdown files, seventy seven tracked files",
        "dos mil cincuenta archivos markdown; setenta y siete bajo git",
        # "the whole repo has 2050 .md, git tracks 77" -- escaped, see the docstring
        "\u5168\u4ed3 2050 \u4e2a .md\uff0cgit \u8ddf\u8e2a 77 \u4e2a",
        "All validator inputs are enumerated by path; the suite reads no other files",
    ]
    for text in prose:
        rationale = {"surface_total": 2050, "basis": "tracked-files", "why": [text]}
        sub = tmp_path / f"r{prose.index(text)}"
        sub.mkdir(parents=True, exist_ok=True)
        repo = _repo(sub, _manifest(narrowing=["src/**"], rationale=rationale))
        rows = _rows_naming_the_key(repo, script)
        assert not rows, f"[{name}] this honest argument was refused: {text!r}\n" + "\n".join(rows)


@pytest.mark.parametrize(
    "label,rationale",
    [("a bare string", "some string"), ("a number", 7), ("an explicit null", EXPLICIT_NULL)],
)
def test_neither_object_nor_array_fails_cleanly(
    tmp_path: Path, gate: tuple[str, str], label: str, rationale: object
) -> None:
    """p30:AC13 -- refused with a row, and NOT with a jq traceback.

    This file has crashed that way before: `jq join` exits non-zero on a non-string array element,
    and under `set -euo pipefail` a bare assignment took the whole gate down with a raw trace instead
    of printing the row. The stderr assertion is what tells a clean refusal from a crash -- the exit
    code cannot, because many other checks move it.
    """
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=rationale))
    result = _task(repo, script)
    rows = [ln for ln in result.stdout.splitlines() if KEY in ln and ln.lstrip().startswith("✗")]
    assert rows, f"[{name}] {label}: must be refused with a row"
    assert "jq: error" not in result.stderr, (
        f"[{name}] {label}: the gate crashed instead of refusing:\n{result.stderr[:600]}"
    )


# --- what the failing row SAYS -------------------------------------------------------

ESC = chr(27)


def _row_for(tmp_path, script, rationale):
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=rationale))
    return "\n".join(_failing_rows_naming_the_key(repo, script))


def test_the_row_names_only_the_predicate_that_failed(tmp_path: Path, gate: tuple[str, str]) -> None:
    """p30:AC9 -- a row that restates the whole rule tells you nothing about YOUR value.

    Three manifests, each broken in exactly one way. Each row must name its own predicate and must
    NOT name the other two, which is the difference between "here is the rule again" and "here is
    what you got wrong". The old row failed this by construction: it printed the same paragraph for
    every failure.
    """
    name, script = gate
    cases = {
        "surface_total": {"basis": "tracked-files", "why": ["x"]},
        "basis": {"surface_total": 2050, "why": ["x"]},
        "why": {"surface_total": 2050, "basis": "tracked-files"},
    }
    for broken, rationale in cases.items():
        row = _row_for(tmp_path / broken, script, rationale)
        missing = row.split("what is missing:", 1)[1].split("| help:", 1)[0]
        assert broken in missing, f"[{name}] {broken} broken but not named in: {missing!r}"
        for other in cases:
            if other != broken:
                assert other not in missing, (
                    f"[{name}] {broken} broken, but the row also names {other}: {missing!r}"
                )


def test_the_row_echoes_this_manifests_own_value(tmp_path: Path, gate: tuple[str, str]) -> None:
    """p30:AC9 -- "what this manifest has" must be THIS manifest's, not a generic example."""
    name, script = gate
    marker = "a-string-that-appears-in-no-template-anywhere"
    rationale = {"surface_total": 2050, "basis": "nope", "why": [marker]}
    row = _row_for(tmp_path, script, rationale)
    assert marker in row, f"[{name}] the row does not echo the author's own text:\n{row}"


def test_a_control_character_never_reaches_the_terminal(tmp_path: Path, gate: tuple[str, str]) -> None:
    """p30:AC10 (a) and (b) -- a complete escape sequence AND one split by the truncation point.

    Printing untrusted text carrying escape sequences to a terminal is CWE-150, with live CVEs
    (CVE-2025-55754, CVE-2025-58160). A manifest is normally self-authored, and "normally" is doing
    the work in that sentence.
    """
    name, script = gate
    complete = {"surface_total": 2050, "basis": "nope", "why": [f"a{ESC}[31mRED{ESC}[0m b"]}
    # 100 is the gate's declared truncation point; put the ESC where the cut lands.
    split = {"surface_total": 2050, "basis": "nope", "why": ["x" * 99 + ESC + "[31mtail"]}
    for label, rationale in (("complete", complete), ("split", split)):
        sub = tmp_path / label
        sub.mkdir(parents=True, exist_ok=True)
        repo = _repo(sub, _manifest(narrowing=["src/**"], rationale=rationale))
        result = _task(repo, script)
        assert ESC not in result.stdout, (
            f"[{name}] a raw ESC byte reached stdout for the {label} sequence"
        )


def test_an_over_length_value_is_actually_truncated(tmp_path: Path, gate: tuple[str, str]) -> None:
    """p30:AC10 (c) -- proves the limit FIRES, not merely that it is written down.

    Without this, a truncation limit set higher than any fixture is indistinguishable from no
    truncation at all.
    """
    name, script = gate
    rationale = {"surface_total": 2050, "basis": "nope", "why": ["y" * 500]}
    row = _row_for(tmp_path, script, rationale)
    assert "[truncated]" in row, f"[{name}] a 500-character value was not truncated:\n{row[:400]}"


def test_the_class_based_stripper_is_why_this_is_safe(tmp_path: Path) -> None:
    """p30:AC10's negative control -- gate-independent, and deliberately so.

    This does not exercise the gate. It exercises the two candidate stripping strategies directly,
    so the REASON the gate uses a character-class stripper is visible rather than asserted. The
    claim it protects is narrow and was narrowed BY this measurement: revision 2 of the story said
    the strip-then-truncate ORDER was load-bearing, and it is not -- a class-based stripper is safe
    in either order. What is load-bearing is that the stripper matches the character rather than the
    whole sequence, because a cut leaves a bare introducer behind.
    """
    import json as _json
    import subprocess as _sp

    payload = _json.dumps({"v": ["0123456789012345678" + ESC + "[31mtail"]})
    def jq(expr: str) -> str:
        return _sp.run(["jq", "-r", f".v|join(\" \")|{expr}"], input=payload,
                       capture_output=True, text=True, check=True).stdout

    assert ESC not in jq('gsub("\\\\p{Cc}";"")|.[0:20]'), "class-based, strip first: leaked"
    assert ESC not in jq('.[0:20]|gsub("\\\\p{Cc}";"")'), "class-based, truncate first: leaked"
    assert ESC in jq('.[0:20]|gsub("\\\\x{1b}\\\\[[0-9;]*m";"")'), (
        "the whole-sequence stripper was expected to LEAK a bare ESC after a cut -- if it no longer "
        "does, this control has stopped controlling anything and the story's claim needs re-measuring"
    )


def test_the_row_says_the_old_language_bound_rule_is_gone(tmp_path: Path, gate: tuple[str, str]) -> None:
    """p30:AC17 (failing-row half) -- the obituary, not a silent deletion.

    p37 deliberately WROTE "write the counts as DIGITS and use the word tracked" into three
    surfaces, each with an assertion. Dropping the sentence would leave a reader unable to tell a
    lift from an oversight, so each failing row now says the requirement is gone.
    """
    name, script = gate
    row = _row_for(tmp_path, script, {"surface_total": 2050, "basis": "nope", "why": ["x"]})
    assert "no longer requires Arabic numerals" in row, (
        f"[{name}] the row does not say the old constraint was lifted:\n{row}"
    )
    assert "write the counts as DIGITS" not in row, (
        f"[{name}] the row still carries the retired instruction:\n{row}"
    )


def test_the_passing_row_says_which_number_it_did_not_audit(tmp_path: Path, gate: tuple[str, str]) -> None:
    """p30:AC11 -- the ✓ row distinguishes the DERIVED number from the DECLARED one.

    This assertion exists because writing "no assertion pins this" into the evidence row was the
    wrong answer to noticing it. The blind second agent's named risk against its own recommendation
    was that typed fields look more official than prose and invite a reader to treat them as
    audited; the sentence is the mitigation, so the sentence needs a guard.

    Pinned by two short phrases rather than the whole sentence: a whole-row match would break on any
    rewording, and the property is that BOTH halves are stated, not that they are stated this way.
    """
    name, script = gate
    rationale = {"surface_total": 2050, "basis": "tracked-files", "why": ["prose"]}
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=rationale))
    passing = [
        ln for ln in _task(repo, script).stdout.splitlines()
        if KEY in ln and ln.lstrip().startswith("✓")
    ]
    assert len(passing) == 1, f"[{name}] expected exactly one passing row, got: {passing}"
    row = passing[0]
    assert "DERIVED" in row, f"[{name}] the row does not say the count was derived:\n{row}"
    assert "not audited" in row, (
        f"[{name}] the row does not say the declared figures were not audited:\n{row}"
    )


def test_blank_strings_may_separate_paragraphs_in_why(tmp_path: Path, gate: tuple[str, str]) -> None:
    """p30:AC1, refined by dogfooding -- `why` is prose, and prose has paragraphs.

    FOUND BY MIGRATING THIS REPOSITORY'S OWN MANIFEST, not by design. The first version of the rule
    required EVERY element to be non-blank, and it refused the twelve-line argument this repo
    actually carries, which uses empty strings as paragraph separators. The property that matters is
    that the value SAYS something, not that every line does.

    The pair below is the whole rule: content among the blanks passes, blanks alone do not.
    """
    name, script = gate
    ok_case = {"surface_total": 2050, "basis": "tracked-files",
               "why": ["first paragraph", "", "second paragraph"]}
    (tmp_path / "ok").mkdir(parents=True, exist_ok=True)
    repo = _repo(tmp_path / "ok", _manifest(narrowing=["src/**"], rationale=ok_case))
    assert not _rows_naming_the_key(repo, script), (
        f"[{name}] blank separators between real prose must be accepted"
    )
    empty_case = {"surface_total": 2050, "basis": "tracked-files", "why": ["", "   ", ""]}
    (tmp_path / "empty").mkdir(parents=True, exist_ok=True)
    repo = _repo(tmp_path / "empty", _manifest(narrowing=["src/**"], rationale=empty_case))
    assert _failing_rows_naming_the_key(repo, script), (
        f"[{name}] an array of nothing but blanks says nothing and must still be refused"
    )


def test_check_nine_is_byte_identical_across_locales(
    tmp_path: Path, gate: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """p30:AC8 -- and this test says what it does NOT establish, in its own docstring.

    WHAT IT PROVES: the same tree and the same manifest produce a byte-identical check-9 row whether
    the shell's locale is `C` or a UTF-8 one. That is a measured hazard rather than a hypothetical:
    BSD `grep`'s `[[:digit:]]` matches Arabic-Indic and fullwidth digits under UTF-8 and collapses
    to ASCII-only under `C`, so a gate routed through it accepts or rejects the SAME manifest
    depending on the environment that invoked it. Nothing in the new path uses that construct, and
    this is what holds that true.

    WHAT IT DOES NOT PROVE, stated because revision 2 of the story overstated it and cross-check
    agent A caught that: it does not show macOS and Linux agree, and it exercises no GNU build of
    anything. Every measurement behind this phase was taken on one macOS host, where GNU grep is not
    installed. The cross-OS argument is STRUCTURAL -- the new path does not touch the
    locale-sensitive construct at all -- and this repository's CI, which runs on ubuntu-latest, is
    the only second host in play. A green CI run is that evidence; this test is not it.

    BOTH LOCALES RUN INSIDE ONE TEST on purpose. Splitting them across two parametrised cases would
    need the two runs to compare against each other through some shared cache, and a comparison that
    silently does nothing when the cache is empty is exactly the shape of an assertion that passes
    without testing anything.
    """
    name, script = gate
    rationale = {
        "surface_total": 2050,
        "basis": "tracked-files",
        # Written as \u escapes, not literals: `scripts/` is outside the CJK rule's only exemption
        # (`docs/`). The bytes reaching the gate are identical either way.
        # Arabic-Indic 2050, fullwidth 77, CJK "whole repo", plus ASCII -- one string, four scripts.
        # Under the OLD rule these are exactly the inputs whose verdict moved with the locale.
        "why": ["\u0662\u0660\u0665\u0660 \uff17\uff17 \u5168\u4ed3 tracked 2050/77"],
    }
    rows = {}
    for locale in ("C", "en_US.UTF-8"):
        monkeypatch.setenv("LC_ALL", locale)
        monkeypatch.setenv("LANG", locale)
        sub = tmp_path / locale.replace(".", "_")
        sub.mkdir(parents=True, exist_ok=True)
        repo = _repo(sub, _manifest(narrowing=["src/**"], rationale=rationale))
        result = run_gate(repo, script, "task", "1.0")
        rows[locale] = [ln for ln in result.stdout.splitlines() if KEY in ln]
        assert rows[locale], f"[{name}] no check-9 row at all under LC_ALL={locale}"

    assert rows["C"] == rows["en_US.UTF-8"], (
        f"[{name}] check 9's row is not byte-identical across locales.\n"
        f"LC_ALL=C:           {rows['C']}\n"
        f"LC_ALL=en_US.UTF-8: {rows['en_US.UTF-8']}"
    )
    assert any(ln.lstrip().startswith("\u2713") for ln in rows["C"]), (
        f"[{name}] the mixed-script rationale must PASS -- that is the whole point of p30.\n"
        f"{rows['C']}"
    )


# --- the cheat strings, RUN --------------------------------------------------------

def test_the_object_branch_cheat_string_passes_and_that_is_the_point(
    tmp_path: Path, gate: tuple[str, str]
) -> None:
    """p30:AC6 -- this string had NEVER been executed, and executing it is the whole assertion.

    It began as the blind second agent's REASONED claim that typed numeric fields do not stop a
    determined cheater. Revision 1 of the story and revision 1 of the design both called it
    "measured". It was not: it had never been run, and it predated the `basis` member entirely.
    Cross-check agent A caught the mislabel -- a claim wider than its mechanism, written into the
    spec of the phase about that class.

    So this test asserts the UNCOMFORTABLE thing: fabricated numbers PASS. If it ever started
    failing, the honest reading is not "we got stronger" but "something changed and the phase's
    stated limit needs re-measuring".

    `all-files` must be a real enum member for this to test what it is for. If it were not, the
    manifest would be rejected on the enum predicate and never reach `surface_total`, and the test
    would silently prove enum-rejection works while appearing to prove forgery passes.
    """
    name, script = gate
    cheat = {"surface_total": 999999, "basis": "all-files", "why": ["asdf"]}
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=cheat))
    rows = _rows_naming_the_key(repo, script)
    assert not rows, (
        f"[{name}] the object branch now refuses fabricated numbers. That may be an improvement, "
        f"but p30:AC6's stated limit says it does not -- re-measure the claim before celebrating.\n"
        + "\n".join(rows)
    )


def test_the_legacy_branch_cheat_string_still_passes_exactly_as_before(
    tmp_path: Path, gate: tuple[str, str]
) -> None:
    """p30:AC6 -- `0 0 track` is nine characters, says nothing, and satisfied the old rule.

    Measured against the pre-p30 predicate before any code was written. It still passes here,
    behind the deprecation warning, which is what "no cheat passes the new gate that would not also
    have passed the old one" means for the branch that kept the old rule.
    """
    name, script = gate
    repo = _repo(tmp_path, _manifest(narrowing=["src/**"], rationale=["0 0 track"]))
    assert not _failing_rows_naming_the_key(repo, script), (
        f"[{name}] the legacy branch must behave exactly as it did before p30"
    )


def test_an_incidental_digit_no_longer_satisfies_the_row(tmp_path: Path, gate: tuple[str, str]) -> None:
    """p30:AC7 -- the ONE axis on which this phase is a tightening, with its own assertion.

    "We did not get weaker" and "we got stronger here" are different claims and this repository has
    measured a phase proving one and being read as having proved the other.

    Under the old rule ANY two digits anywhere in the prose satisfied it -- a date, a version, a
    glob. The text below carries four such digits and the word `track`, so it PASSED before. Under
    the object shape the quantities are members read by name, so incidental digits in prose satisfy
    nothing: with `surface_total` absent, this must fail.
    """
    name, script = gate
    incidental = "on 2026-08-26 we bumped to v4.0.0 and the tracked set was unchanged"
    # Same prose, as the legacy array: this is what the OLD rule accepted.
    (tmp_path / "legacy").mkdir(parents=True, exist_ok=True)
    (tmp_path / "object").mkdir(parents=True, exist_ok=True)
    legacy = _repo(tmp_path / "legacy", _manifest(narrowing=["src/**"], rationale=[incidental]))
    assert not _failing_rows_naming_the_key(legacy, script), (
        f"[{name}] control: this prose satisfied the old rule and the legacy branch must still take "
        f"it -- if it does not, the comparison below is against the wrong baseline"
    )
    # The same prose in the object shape, with no declared quantity.
    obj = _repo(tmp_path / "object", _manifest(
        narrowing=["src/**"], rationale={"basis": "tracked-files", "why": [incidental]}))
    rows = _failing_rows_naming_the_key(obj, script)
    assert rows, (
        f"[{name}] four incidental digits in prose must NOT satisfy the object shape"
    )
    assert "surface_total" in "\n".join(rows), (
        f"[{name}] the row must name the missing quantity, not just refuse:\n" + "\n".join(rows)
    )
