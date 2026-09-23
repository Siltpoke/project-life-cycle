"""p30:AC18 -- the sweep's findings and the cross-check's findings are FILED, not mentioned.

No CJK in this file, deliberately: the CJK rule exempts `docs/` outright and nothing else.
The backlog entries themselves are Chinese, which is legal because they live under `docs/`; this
test therefore matches on ids and on the two ASCII structural markers rather than on their prose.

WHY THIS TEST EXISTS AT ALL. Revision 1 of AC18 said only "three backlog entries exist ... each with
Trigger and Exit". Cross-check agent A called it the one acceptance criterion of fourteen with no
oracle: no command, no path, no target, so a builder could satisfy it with three loosely-worded
entries and a passing journal mention of anything vaguely on-topic. What follows is that oracle.
"""

import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "docs" / "BACKLOG.md"

# The five. Three came from the sibling sweep p30's Exit clause asked for; two came from the
# cross-check that read this phase's own design and found gaps in it.
FILED = {
    "B9208": "the /builder-profile tokenizer is blind to CJK prompts",
    "B9209": "/capture's related-intent surfacing never fires for a CJK subject",
    "B9210": "a diagnostic line truncates by bytes and garbles a CJK title",
    "B9211": "the dual-shape window has no end condition",
    "B9212": "nothing cross-checks `basis` against the real narrowing",
}


@pytest.mark.parametrize("bid,what", sorted(FILED.items()))
def test_the_entry_exists_and_is_a_filing_not_a_mention(bid: str, what: str) -> None:
    """A heading, plus the two structural markers that make it a filing.

    Trigger and Exit are what this repository's backlog discipline requires of a deferred decision:
    what put it here, and what would let it be closed. An entry without them is a note.
    """
    text = BACKLOG.read_text(encoding="utf-8")
    heads = [i for i, ln in enumerate(text.splitlines()) if ln.startswith(f"## {bid} ")]
    assert len(heads) == 1, f"{bid} ({what}): expected exactly one heading, found {len(heads)}"

    lines = text.splitlines()
    start = heads[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## B")), len(lines))
    section = "\n".join(lines[start:end])
    assert "**Trigger.**" in section, f"{bid} ({what}): no Trigger -- this is a note, not a filing"
    assert "**Exit.**" in section, f"{bid} ({what}): no Exit -- nothing says what would close it"


def test_the_index_lists_every_filing_as_open(tmp_path) -> None:
    """The index is DERIVED, so this checks the generator's view rather than the author's.

    `state` in that table comes from `.claude/backlog-closures.tsv` via the generator, not from
    editing the row -- so an entry that is filed but somehow already recorded as closed would show
    up here rather than in the section text above.

    p33 -- RUN AGAINST A COPY. This ran the generator with `cwd=ROOT`, and `backlog-toc.sh`
    rewrites `docs/BACKLOG.md` IN PLACE (`F="docs/BACKLOG.md"` ... `mv "$F.new" "$F"`). So every
    full-suite run silently rewrote the real ledger. Caught when a `-n 4` run left
    `M docs/BACKLOG.md` behind: the write was CORRECT -- it added the row for an entry that had
    just been filed -- which is exactly why nothing ever noticed. A side effect that looks like
    help is the hardest kind to see.

    The rule already existed and was already written down, in this same directory:
    `test_backlog_ledger.py::_run_toc_on_a_copy` says "Never point this script at ROOT from a
    test", and explains that it once rewrote the real ledger mid-measurement. The fix was applied
    there and never paved to this call site. A rule existing is not evidence it ran.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "BACKLOG.md").write_text(BACKLOG.read_text(encoding="utf-8"), encoding="utf-8")

    # INVOKE THE SCRIPT BY ITS REAL ABSOLUTE PATH, redirecting only `cwd`. The first version of
    # this fixture COPIED backlog-toc.sh into tmp_path and ran the copy, which silently broke it:
    # the script sources `$(dirname "${BASH_SOURCE[0]}")/utf8-text.sh`, so a copy without that
    # sibling loses every helper it defines. Measured — 272 `plc_utf8_head: command not found`,
    # 137 titles blanked, and the script still exits 0 because it has no `set -e`. The assertions
    # below only read the `state` column, so the test passed against a generator that had been
    # gutted. `test_backlog_ledger.py::_run_toc_on_a_copy` already had this right; found by an
    # independent reviewer, reproduced here before being believed.
    #
    # The relative `F="docs/BACKLOG.md"` inside the script resolves against cwd, so the copy is
    # still what gets rewritten and the real ledger is still untouched — asserted below rather
    # than assumed.
    # THE CLOSURE LOG MUST BE STAGED, and this is the second half of the same lesson. The first
    # version of this fixture copied the SCRIPT (breaking `utf8-text.sh`); the correction ran the
    # script from its real path and deleted the copy loop entirely -- which broke the OTHER half.
    # `backlog-closures.sh:54` resolves `LOG="${PLC_CLOSURE_LOG:-.claude/backlog-closures.tsv}"`
    # RELATIVELY, against this process's cwd. With cwd=tmp_path and no log staged there, the
    # parser emits zero lines and exits 0 -- legal by its own design, an adopter with no log at
    # all -- so every row rendered `open`. Measured: 272 rows, 272 `open`, 0 `closed`, against a
    # real ledger holding 131 closed. The test still passed because the five ids it checks happen
    # to be genuinely open. Scripts resolve via `$0` and need no copy; DATA resolves via cwd and
    # does. Found by an independent review of the commit that fixed the first half.
    claude = tmp_path / ".claude"
    claude.mkdir(exist_ok=True)
    (claude / "backlog-closures.tsv").write_bytes((ROOT / ".claude/backlog-closures.tsv").read_bytes())

    before = BACKLOG.read_bytes()
    subprocess.run(["/bin/bash", str(ROOT / "scripts/backlog-toc.sh")], cwd=tmp_path, check=True,
                   capture_output=True, text=True)
    assert BACKLOG.read_bytes() == before, (
        "the real docs/BACKLOG.md changed while running the generator -- this test must operate "
        "only on the copy under tmp_path (p33)")

    # p33 -- THE FIXTURE MUST BE FAITHFUL, not merely non-destructive. Both halves of this
    # generator have now been silently disabled once each while every assertion below still
    # passed, so the fixture asserts its own inputs reached the script rather than trusting that
    # they did. A copy that renders every row `open` is a copy whose closure log was never read.
    rendered = (docs / "BACKLOG.md").read_text(encoding="utf-8")
    closed_rows = len(re.findall(r"^\|\s*\*\*B[0-9.]+\*\*\s*\|\s*closed", rendered, re.M))
    assert closed_rows > 0, (
        "the regenerated copy shows zero closed entries, so the closure log was not read -- the "
        "fixture is not exercising the derivation it claims to test (p33)")
    blank_titles = len(re.findall(r"^\|\s*\*\*B[0-9.]+\*\*\s*\|[^|]*\|[^|]*\|\s*\|\s*$", rendered, re.M))
    assert blank_titles == 0, (
        f"{blank_titles} rows have blank titles, so `utf8-text.sh` did not load -- the generator "
        "ran gutted (p33)")

    text = (docs / "BACKLOG.md").read_text(encoding="utf-8")
    for bid in sorted(FILED):
        row = re.search(rf"^\|\s*\*\*{bid}\*\*\s*\|([^|]*)\|", text, re.M)
        assert row, f"{bid} has no row in the regenerated index"
        assert "open" in row.group(1), f"{bid} is not open in the index: {row.group(1).strip()!r}"


def test_the_label_judgement_is_recorded_as_a_decision() -> None:
    """The thing that was deliberately NOT filed has to be findable, or it reads as an omission.

    `close-gate.sh`'s Decision/Why/Backing labels are matched case-sensitively inside human-written
    journal prose, so a translated label hard-fails check 5. The sweep flagged it; the controller
    judged it a schema label rather than a language demand. A reader who finds nothing about it
    cannot tell that judgement from an oversight, so the judgement is written down and this asserts
    it stayed written down.
    """
    hits = list((ROOT / "docs" / "journal.d").glob("*language-neutral*.md")) + [
        ROOT / "docs" / "qa-log.d" / "2026-08-26-feat-phase-language-neutral-rationale.md"
    ]
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in hits if p.exists())
    assert "Decision/Why/Backing" in corpus or "Decision`/`Why`/`Backing" in corpus, (
        "no record mentions the FACT-label judgement at all"
    )
    assert "schema label" in corpus, (
        "the record does not say WHY those labels were not filed -- 'schema label rather than a "
        "language demand' is the judgement, and without it a reader finds an omission"
    )
