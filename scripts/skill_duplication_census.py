"""One-shot probe: which passages of an always-loaded SKILL.md also exist in an on-demand
reference? Read-only, no LLM.

READ THIS BEFORE TRUSTING A NUMBER FROM IT.

This is a CANDIDATE GENERATOR, not a gate and not a measuring instrument. It ranks passages by
how much of their text also appears in some `references/*.md` and prints, for each, the single
piece of evidence a human can check in ten seconds: the longest run of consecutive words the
passage shares with that file. **A candidate is not a finding until someone reads that run.**

It is written this way because each of the following claims sounds natural for a tool like this,
and none of them holds, so none is made:

  * "zero false positives" -- a control that builds its negative population by
    removing a passage's own source file from the index and calling the remainder original.
    Reference files in a set like this quote each other, so that premise is false: a verbatim
    block shared by two files, once a random seed draws it into the "original" corpus, makes
    the control fail. A clean figure from such a control is an artifact of its seed.
  * "the figure is a lower bound" -- shingles are a SET, so a passage repeating three words
    forty times matches a six-word reference at 100%. This can OVERCOUNT; nothing here bounds
    anything in either direction.
  * "N% of the surface exists somewhere in the tree" -- computed from a union across files.
    A passage whose every 3-word window appears in a DIFFERENT file scores 100% on that union
    while existing nowhere.
  * a calibration table of light-edit and heavy-paraphrase bands simulated by DELETING words --
    deletion only breaks the windows straddling the gap;
    substitution at the same nominal rate breaks every window containing the word, so bands
    built that way measure the edit model, not the text.

What this file does claim:

  * it reads every byte of SKILL.md and can say so -- the coverage line is an accounting
    identity whose residue is 0, not "small";
  * every candidate carries re-checkable evidence, so a human can confirm or reject it;
  * a passage sharing no consecutive run with its best match is never shortlisted.

Usage:  python3 scripts/skill_duplication_census.py [REPO_ROOT]
"""
from __future__ import annotations

import argparse
import collections
import difflib
import re
from pathlib import Path

SHINGLE_K = 3
# Ranking cut-off, NOT a verdict. Chosen so the printed list stays short enough to read by
# hand. A passage below it is not thereby original; one above it is not thereby a duplicate.
SHORTLIST = 0.60
# A candidate must share at least this fraction of its words as ONE consecutive run. Below it,
# two texts merely use the same vocabulary in the same order in places, which is what a house
# style produces on its own.
MIN_RUN = 0.25

_WORD = re.compile(r"[a-z0-9]+")
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def shingles(seq: list[str], k: int | None = None) -> set[tuple[str, ...]]:
    # k is resolved at CALL time so the controls can force it back to 8 and require the
    # shortlist to collapse. A default argument would freeze it at import and make that
    # mutation a no-op -- a mutation that cannot change the implementation proves nothing.
    k = SHINGLE_K if k is None else k
    return {tuple(seq[i:i + k]) for i in range(len(seq) - k + 1)}


def build_index(ref_dir: Path) -> dict[tuple[str, ...], set[str]]:
    index: dict[tuple[str, ...], set[str]] = collections.defaultdict(set)
    for path in sorted(ref_dir.glob("*.md")):
        for sh in shingles(words(path.read_text(encoding="utf-8", errors="replace"))):
            index[sh].add(path.name)
    return index


def score(text: str, index) -> tuple[float, str]:
    """Fraction of this passage's shingles present in its single best-matching file.

    A ranking signal only. Deliberately NOT summed across files: a union over the whole tree
    reaches 100% on a passage assembled from windows that each live in a different document,
    which is evidence of nothing.
    """
    seq = words(text)
    if len(seq) < SHINGLE_K:
        return 0.0, "-"
    own = shingles(seq)
    hits: collections.Counter[str] = collections.Counter()
    for sh in own:
        for name in index.get(sh, ()):
            hits[name] += 1
    if not hits:
        return 0.0, "-"
    name, count = hits.most_common(1)[0]
    return count / len(own), name


def longest_shared_run(text: str, target_text: str) -> tuple[int, int]:
    """(longest run of consecutive shared words, passage word count).

    This is the evidence column. Shingle containment is reachable by scattered coincidence; a
    long consecutive run is not, which is why checking one row means reading only this.
    """
    a, b = words(text), words(target_text)
    if not a or not b:
        return 0, len(a)
    match = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(
        0, len(a), 0, len(b))
    return match.size, len(a)


class Unit:
    __slots__ = ("section", "start", "end", "text", "nbytes",
                 "score", "target", "run", "nwords")

    def __init__(self, section: str, start: int, end: int, text: str, nbytes: int) -> None:
        self.section = section
        self.start = start
        self.end = end
        self.text = text
        self.nbytes = nbytes
        self.score = 0.0
        self.target = "-"
        self.run = 0
        self.nwords = 0

    @property
    def run_fraction(self) -> float:
        return self.run / self.nwords if self.nwords else 0.0

    @property
    def is_candidate(self) -> bool:
        """Worth a human's attention. NOT a verdict that this passage is duplicated."""
        return self.score >= SHORTLIST and self.run_fraction >= MIN_RUN

    @property
    def unmeasurable(self) -> bool:
        """Substantial text the word regex cannot see -- reported, never scored 0 in silence.

        Keyed on `words() == 0`, not on a shingle count: an earlier version used the latter,
        fired on a two-word heading, and announced "no ASCII letters or digits" -- a message
        wider than its trigger.
        """
        return len(self.text.strip()) >= 24 and not words(self.text)


def _line_bytes(lines: list[str]) -> list[int]:
    """Per-line byte cost summing exactly to the file length.

    `split("\\n")` inverts `"\\n".join(...)`, so every line costs len+1 EXCEPT the last. An
    earlier version charged +1 unconditionally and produced residue -1 on every input -- a
    negative count of bytes not looked at, visible on a large file only as a wrong positive.
    """
    out = [len(ln.encode("utf-8")) + 1 for ln in lines]
    if out:
        out[-1] -= 1
    return out


def split_units(skill_text: str) -> tuple[list[Unit], list[str], list[str]]:
    """One unit per bullet / table row / paragraph, tagged with its enclosing `## ` section.

    Returns (units, lines, per-line category) with category in 'prose' | 'heading' | 'blank'.
    ANY heading line -- `#`, `###`, `##` -- is categorised 'heading', so the prose total is
    prose. An earlier version categorised only `## ` and let `#`/`###` lines into the prose
    bucket while excluding them from results: the identity balanced for the wrong reason.

    Fenced code is opaque: a `## ` or `- ` inside a fence is sample output, not structure.
    """
    lines = skill_text.split("\n")
    costs = _line_bytes(lines)
    category = ["blank"] * len(lines)
    units: list[Unit] = []
    section = "(preamble)"
    buf: list[int] = []
    in_fence = False

    def flush(end_idx: int) -> None:
        nonlocal buf
        if buf:
            text = "\n".join(lines[i] for i in buf).strip()
            if text:
                nbytes = sum(costs[i] for i in buf)
                units.append(Unit(section, buf[0] + 1, end_idx + 1, text, nbytes))
                for i in buf:
                    category[i] = "heading" if lines[i].lstrip().startswith("#") else "prose"
        buf = []

    for idx, line in enumerate(lines):
        if _FENCE.match(line):
            in_fence = not in_fence
            buf.append(idx)
            continue
        if not in_fence:
            if line.startswith("## "):
                flush(idx - 1)
                section = line[3:].strip()
                category[idx] = "heading"
                continue
            if not line.strip() or line.startswith(("- ", "| ", "### ", "#### ")):
                flush(idx - 1)
        if line.strip():
            buf.append(idx)
    flush(len(lines) - 1)
    return units, lines, category


def coverage(lines: list[str], category: list[str]) -> tuple[int, dict[str, int], int]:
    """(total bytes, bytes per category, residue). Residue is 0 by construction or a bug."""
    costs = _line_bytes(lines)
    total = sum(costs)
    per: dict[str, int] = collections.defaultdict(int)
    for cost, cat in zip(costs, category):
        per[cat] += cost
    return total, dict(per), total - sum(per.values())


def run(root: Path):
    skill = root / "skills" / "project-lifecycle" / "SKILL.md"
    ref_dir = root / "skills" / "project-lifecycle" / "references"
    if not skill.is_file():
        raise SystemExit(f"no SKILL.md under {skill.parent}")
    if not ref_dir.is_dir():
        raise SystemExit(f"no references/ under {ref_dir.parent}")

    index = build_index(ref_dir)
    ref_text = {p.name: p.read_text(encoding="utf-8", errors="replace")
                for p in sorted(ref_dir.glob("*.md"))}
    units, lines, category = split_units(skill.read_text(encoding="utf-8"))
    for unit in units:
        unit.score, unit.target = score(unit.text, index)
        if unit.target != "-":
            unit.run, unit.nwords = longest_shared_run(unit.text, ref_text[unit.target])
        else:
            unit.nwords = len(words(unit.text))
    return skill, ref_dir, index, units, lines, category


def report(root: Path) -> int:
    skill, ref_dir, index, units, lines, category = run(root)
    n_refs = len(list(ref_dir.glob("*.md")))
    total, per_cat, residue = coverage(lines, category)

    print(f"# duplication PROBE  k={SHINGLE_K}  shortlist>={SHORTLIST}  min-run>={MIN_RUN}")
    print("# rows below are CANDIDATES, not verdicts. Read the run column before believing one.")
    print(f"# {len(units)} units, {n_refs} reference files, {len(index)} distinct shingles")
    print(f"# coverage: {total} file bytes = {per_cat.get('prose', 0)} prose "
          f"+ {per_cat.get('heading', 0)} heading + {per_cat.get('blank', 0)} blank "
          f"+ {residue} residue")
    if residue != 0:
        print(f"# WARNING: residue {residue} != 0 — the accounting does not balance and "
              f"nothing below can be trusted")

    unmeasurable = [u for u in units if u.unmeasurable]
    if unmeasurable or not index:
        ub = sum(u.nbytes for u in unmeasurable)
        print(f"# WARNING: {len(unmeasurable)} units ({ub} bytes) contain no ASCII letters or "
              f"digits, so the metric scores them 0 against everything INCLUDING a "
              f"byte-identical copy. They are absent from the list below, not cleared by it.")
    print()

    cands = sorted((u for u in units if u.is_candidate), key=lambda u: -u.nbytes)
    print(f"{'lines':>13} {'bytes':>7} {'shingle':>8} {'longest run':>14}  target | text")
    for u in cands:
        head = " ".join(u.text.split())[:60]
        print(f"  L{u.start}-{u.end:<8} {u.nbytes:6d}B {u.score:7.0%} "
              f"{u.run:4d}/{u.nwords:<4d} {u.run_fraction:3.0%}  {u.target:<24} | {head}")
    if not cands:
        print("  (no candidates)")

    prose = per_cat.get("prose", 0)
    cb = sum(u.nbytes for u in cands)
    strong = [u for u in cands if u.run_fraction >= 0.50]
    sb = sum(u.nbytes for u in strong)
    print()
    if prose:
        print(f"{len(cands)} candidates, {cb} bytes ({100.0 * cb / prose:.1f}% of prose); "
              f"{len(strong)} of them share half their words as one run, {sb} bytes "
              f"({100.0 * sb / prose:.1f}%).")
    print("Neither figure is a measurement of duplication. This probe overcounts on repetitive "
          "text and undercounts on rewording, and neither direction is bounded — the list is "
          "a reading queue.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    # Root is an argument, not derived from __file__: a fixture tree must be reachable, or the
    # self-check path exercises different code from the real one.
    parser.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parent.parent),
                        help="repo root containing skills/project-lifecycle/")
    args = parser.parse_args()
    return report(Path(args.root))


if __name__ == "__main__":
    raise SystemExit(main())
