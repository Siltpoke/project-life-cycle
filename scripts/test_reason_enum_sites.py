"""The fallback-reason enumeration agrees across all FOUR places it is declared,
and every declared reason is one the runner can actually emit.

Two mechanisms, because "a human re-reads four markdown files" is not one.
`close-gate.sh` checks none of this.

WHY A NON-EMPTINESS FLOOR PER CARRIER: the four sites have four different shapes — a
two-line comment enum, a gate table with `fallback: X` scattered across several lines,
an inline parenthetical in prose, and a sentence of back-ticked tokens. Each needs its
own parser, and if two of them silently extract ZERO the comparison is empty-equals-
empty and passes green. A sibling guard says it verbatim
(`scripts/invariants/named-interpreter.sh`): "An empty set compared equal to an
empty set is how scripts/invariants/ledger-contract-sync.sh once passed while checking
nothing; that lesson is paid for and does not need paying twice."

WHY EMITTABILITY: without it, set-equality REWARDS THE WRONG FIX. At one point
`brainstorm-research-protocol.md` declared `declined-install`, which the runner emits
nowhere; the cheapest way to make four carriers agree would have been to copy the ghost
into the other three.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNNER = REPO / "scripts/cross-family-review.sh"
REFS = REPO / "skills/project-lifecycle/references"

GATE_TABLE = REFS / "cross-family-review.md"
PROTOCOL = REFS / "brainstorm-research-protocol.md"
OUTPUT_FORMAT = REFS / "output-format.md"

# Each carrier must yield at least this many tokens. Six is the size of the set without
# `empty-answer`; a parser that silently drifts to zero, one or two
# fails here rather than passing a vacuous comparison.
FLOOR = 6

# The hyphen is OPTIONAL, and that is not a detail. Written `(?:-[a-z]+)+` — requiring
# at least one hyphen — this pattern drops `unparseable`, the one reason with no hyphen
# in it, from ALL FOUR carriers at once. Set-equality stays green (they agree on the
# same wrong set) and the ≥6 floor stays green (six of seven survive). Measured while
# writing this file: only the emittability direction, which extracts from the runner's
# call sites with a different pattern, reported it. A floor cannot catch a systematic
# off-by-one-token; an independent second oracle can.
REASON = r"[a-z]+(?:-[a-z]+)*"


def _runner_header_enum() -> set[str]:
    """Site 1 — the `fallback_reason ∈ {…}` comment block in the runner's header."""
    text = RUNNER.read_text(encoding="utf-8")
    m = re.search(r"fallback_reason ∈ \{(.+?)\}", text, re.S)
    assert m, "the runner header no longer declares `fallback_reason ∈ {…}`"
    return set(re.findall(REASON, m.group(1)))


def _gate_table_enum() -> set[str]:
    """Site 2 — `fallback: <reason>` scattered through the 4-gate flow block."""
    text = GATE_TABLE.read_text(encoding="utf-8")
    return set(re.findall(rf"fallback: ({REASON})", text))


def _protocol_enum() -> set[str]:
    """Site 3 — the inline `(reason ∈ a / b / c)` parenthetical."""
    text = PROTOCOL.read_text(encoding="utf-8")
    m = re.search(r"\(reason ∈ ([^)]+)\)", text)
    assert m, "the protocol no longer declares `(reason ∈ …)`"
    return set(re.findall(REASON, m.group(1)))


def _output_format_enum() -> set[str]:
    """Site 4 — the back-ticked token list in the `second-agent-family` key's prose.

    This site is the reason the floor exists. It once spelled the set as
    prose — "not installed / not authed / spawn / parse / timeout / declined install" —
    with spaces for hyphens and `spawn`/`parse` for `spawn-failed`/`unparseable`. A
    parser looking for the canonical tokens extracted ZERO from it, and the fix was to
    rewrite the sentence, not to add a token.
    """
    text = OUTPUT_FORMAT.read_text(encoding="utf-8")
    m = re.search(r"Every failure \(([^)]+)\)", text)
    assert m, "output-format.md no longer declares the failure set"
    return set(re.findall(rf"`({REASON})`", m.group(1)))


def _emittable() -> set[str]:
    """What the runner can ACTUALLY emit, read from its `emit fallback "<reason>"` sites."""
    text = RUNNER.read_text(encoding="utf-8")
    return set(re.findall(r'emit fallback "([^"]+)"', text))


CARRIERS = {
    "runner header": _runner_header_enum,
    "gate table": _gate_table_enum,
    "protocol parenthetical": _protocol_enum,
    "output-format prose": _output_format_enum,
}


def test_every_carrier_yields_a_real_set_before_anything_is_compared():
    """The floor. Runs first, and on its own, so a drifted parser is reported as a
    drifted parser rather than as a set mismatch somewhere else."""
    for name, parse in CARRIERS.items():
        got = parse()
        assert len(got) >= FLOOR, f"{name} yielded {len(got)} reasons ({sorted(got)}) — parser drifted"


def test_the_four_declaration_sites_agree():
    sets = {name: parse() for name, parse in CARRIERS.items()}
    reference = sets["runner header"]
    for name, got in sets.items():
        assert got == reference, (
            f"{name} declares {sorted(got)} but the runner header declares {sorted(reference)}; "
            f"only in {name}: {sorted(got - reference)}; missing from {name}: {sorted(reference - got)}"
        )


def test_nothing_is_declared_that_the_runner_cannot_emit():
    """The ghost check. `declined-install` was declared for two releases and emitted never."""
    emittable = _emittable()
    assert len(emittable) >= FLOOR, f"only {len(emittable)} emit sites found — parser drifted"
    for name, parse in CARRIERS.items():
        ghosts = parse() - emittable
        assert not ghosts, f"{name} declares reasons the runner cannot emit: {sorted(ghosts)}"


def test_nothing_is_emitted_that_goes_undeclared():
    """The other direction, which is the one easiest to miss: a new reason
    class added to the runner and to three of the four carriers."""
    emittable = _emittable()
    for name, parse in CARRIERS.items():
        missing = emittable - parse()
        assert not missing, f"{name} is missing reasons the runner emits: {sorted(missing)}"


def test_empty_answer_is_in_the_set():
    """A pin, not a tautology: it names the most recently added reason, so a revert that
    removes the class from the runner is reported here as well as by the shape table."""
    assert "empty-answer" in _emittable()
