"""No surface still claims the runner always exits 0, never blocks, or degrades
silently, and the copy-paste block a caller actually copies from carries the exit codes.

WHY THIS EXISTS AS A STANDING ASSERTION rather than a one-time sweep:
The same over-claim comes back in many faces — a helper word like "fresh", a
runner's summary line, or an evidence
file reading "I DID NOT RUN ANY TEST" while the gate prints a check-mark — and each
is caught by a person or not at all, unless a suite is looking.

"""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "skills/project-lifecycle/references"

# Phrases that are false now that the runner can exit non-zero. Matched case-insensitively.
FORBIDDEN = [
    "always exits 0",
    "always exit 0",
    "never blocks",
    "degrades silently",
    "degrade silently",
]

TRACKED_CARRIERS = {
    "runner": ROOT / "scripts/cross-family-review.sh",
    "code-review wrapper": ROOT / "scripts/cross-family-code-review.sh",
    "runner tests": ROOT / "scripts/test_cross_family_review.py",
    "gate-flow reference": REFS / "cross-family-review.md",
    "protocol reference": REFS / "brainstorm-research-protocol.md",
    "output-format reference": REFS / "output-format.md",
}


# A literal phrase scan cannot tell a CLAIM from a MENTION (attach the rule to the shape,
# not to the marker). The first
# run of this file fired on four of its own corrections — sentences whose whole job is to
# say the phrase is no longer true — while a multi-line `[SUPERSEDED …]` note went
# unseen because the marker sat on a later line than the phrase.
#
# So the unit is the BLOCK, not the line, and a block is exonerated by a marker that turns
# the phrase into a mention:
EXONERATING = (
    "superseded",     # a historical record, explicitly marked
    "no longer",
    "does not",
    "do not",
    "not always",
    "used to",
    "was false",
    "stops",
)


def _blocks(text: str):
    """Paragraphs. A `[SUPERSEDED …]` note attaches to the sentence above it, and the two
    are one unit for this purpose even though they are several lines apart."""
    block, start = [], 1
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip():
            if not block:
                start = n
            block.append((n, line))
        elif block:
            yield start, block
            block = []
    if block:
        yield start, block


def _offending_lines(path: Path) -> list[str]:
    out = []
    for _start, block in _blocks(path.read_text(encoding="utf-8")):
        low_block = "\n".join(l for _n, l in block).lower()
        if not any(p in low_block for p in FORBIDDEN):
            continue
        if any(e in low_block for e in EXONERATING):
            continue
        for n, line in block:
            if any(p in line.lower() for p in FORBIDDEN):
                out.append(f"{path.name}:{n}: {line.strip()[:120]}")
    return out




@pytest.mark.parametrize("name", sorted(TRACKED_CARRIERS))
def test_no_tracked_carrier_still_claims_it(name):
    offending = _offending_lines(TRACKED_CARRIERS[name])
    assert not offending, "an exit-0 / never-blocks claim survived:\n" + "\n".join(offending)




def test_the_installer_never_claims_what_the_rest_of_the_hook_does():
    """This claim needs its own oracle; the checker above does not own it.

    Putting the old wording back — "(existing hook preserved, still runs first)" — left
    every other test green. The exit-0 checker above cannot see it: its phrase list is
    about "always exits 0 / never blocks / degrades silently", and this is a different family
    of claim entirely.

    The installer never reads the body it inserts above, so it cannot say that body is
    preserved, that it still runs, or what it is. It may only report where the chain went.
    """
    src = (ROOT / "scripts/install-close-gate-hook.sh").read_text(encoding="utf-8")
    lines = [l for l in src.splitlines()
             if l.strip().startswith("echo ") or l.strip().startswith("cat >&2")]
    forbidden = ("preserved", "runs first", "still runs", "untouched", "existing checks")
    offending = [f"{l.strip()[:110]}" for l in lines
                 if any(p in l.lower() for p in forbidden)]
    assert not offending, (
        "a user-facing line asserts something about the rest of the hook, which this script "
        "never reads:\n" + "\n".join(offending)
    )


def test_the_changelog_entry_is_marked_superseded_not_rewritten():
    """The released `[3.7.0]` entry keeps its sentence — it is an accurate record of what
    that version shipped — and carries a superseded marker instead. Rewriting it would
    back-date later behaviour into a version that never had it."""
    # THE ARCHIVE IS PART OF THE CORPUS. `retention-drain.sh` rolls released CHANGELOG sections
    # into `docs/archive/CHANGELOG/<YYYY-MM>.md` verbatim, by design, so the `[3.7.0]` entry this
    # row is about leaves `CHANGELOG.md` on the first drain that passes it:
    # a drain moved it to `docs/archive/CHANGELOG/<YYYY-MM>.md`, and this row did not fail
    # with a message -- `next()` raised a bare StopIteration, which names no file, no cause and
    # no remedy. Reading hot + archive is what makes the row track the entry rather than the path.
    sources = [ROOT / "CHANGELOG.md"] + sorted(
        (ROOT / "docs" / "archive" / "CHANGELOG").glob("20*.md")
    )
    present = [q for q in sources if q.is_file()]
    assert present, "no CHANGELOG to read: neither CHANGELOG.md nor docs/archive/CHANGELOG/*.md"
    text = "\n".join(q.read_text(encoding="utf-8") for q in present)

    # An explicit assertion instead of `next()`, so "the entry is nowhere" is a sentence rather
    # than a StopIteration traceback. The two outcomes it keeps apart -- entry absent vs entry
    # present but unmarked -- have different remedies, and a bare next() reports neither.
    matches = [l for l in text.splitlines() if "the adapter always exits 0" in l]
    assert matches, (
        "the released entry naming the exit-0 contract is in none of %d CHANGELOG source(s); it "
        "is not gone until this list is wrong -- check whether a drain rolled it into "
        "docs/archive/CHANGELOG/<YYYY-MM>.md" % len(present)
    )
    assert all("SUPERSEDED" in l for l in matches), (
        "the released entry states a contract that no longer holds (%d occurrence(s), %d marked)"
        % (len(matches), sum("SUPERSEDED" in l for l in matches))
    )


def test_the_copy_paste_block_carries_the_exit_codes():
    """Guidance has to land where a caller actually copies from. The exit-0 claim and the
    invocation people paste are in different parts of this file, and only one of them ends
    up in someone's terminal."""
    text = (REFS / "cross-family-review.md").read_text(encoding="utf-8")
    start = text.index("```bash\ngit diff main...HEAD")
    block = text[start:text.index("```", start + 3)]
    assert "rc=$?" in block, "the pasted invocation does not capture the status"
    # The spellings below are pinned verbatim for this block. Pinning
    # spellings rather than meaning is a known way to train "just edit the test", so the
    # scope is kept narrow on purpose: this asserts only that all three codes and the
    # chaining advice survive in the thing a caller copies, not how the sentences read.
    for needle in ("exit 3", "exit 2", "0 = "):
        assert needle in block, f"the pasted block no longer explains `{needle.strip()}`"
    assert "|| true" in block, "the block does not say how to chain on it"
