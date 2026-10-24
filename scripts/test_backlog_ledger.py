"""Acceptance suite for backlog state derived from an append-only closure log.

Several rows read the maintainer's own tracked `docs/` artifacts and an untracked marker
vocabulary; they fail or skip, naming the missing file, in a tree that does not carry them.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import session_card as sc

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "docs" / "BACKLOG.md"
ROADMAP = ROOT / "docs" / "ROADMAP.md"
TOC = ROOT / "scripts" / "backlog-toc.sh"

# The mechanisms under test.
LEDGER = ROOT / ".claude" / "backlog-closures.tsv"
SNAPSHOT = ROOT / ".claude" / "backlog-state-premigration.tsv"
PARSER = ROOT / "scripts" / "backlog-closures.sh"
GATE = ROOT / "scripts" / "invariants" / "backlog-closure-log.sh"
HELPER = ROOT / "scripts" / "lib" / "closure-log-added.sh"
TITLE_INV = ROOT / "scripts" / "invariants" / "backlog-no-title-markers.sh"
RECONCILE = ROOT / "scripts" / "backlog-reconcile.sh"
REPORT = ROOT / "docs" / "superpowers" / "migration-report.md"
ROADMAP_GEN = ROOT / "scripts" / "roadmap-batchmap-status.sh"

# Both exemptions are named literals, never a pattern. A pattern is a table that can grow
# quietly until the arithmetic balances. The count and the literals are asserted together,
# and they mirror EXEMPT_IDS in scripts/backlog-toc.sh.
EXEMPT_LITERALS = ["B-example-legacy", "B9001 (original)"]
MARKERS = ROOT / ".claude" / "roadmap-progress-markers.txt"

# **No test carries this marker any more.** It is kept, and
# kept named, because that is the record of the transition — every AC in this file was red under
# it first and lost it only when its mechanism landed. Deleting it would erase the evidence that
# the suite was ever a baseline rather than something written after the fact.
xfail_t0 = pytest.mark.xfail(strict=True, reason="baseline: mechanism not built yet")


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------
# maintainer-local artifacts: present in the maintainers' working copy, absent from this repository
# --------------------------------------------------------------------------------------
#
# The artifacts these rows read are split in two:
#
#   REPO_ARTIFACTS  -- tracked in the maintainers' repository and not shipped here. The rows
#                      that read them are skipped by name in conftest.py; where the artifacts
#                      exist, a missing one is a broken tree and never skips.
#   AUTHOR_LOCAL    -- still untracked. Absent artifact -> SKIP, loudly, naming the file. Not a
#                      silent pass, and not a red that says "not built yet" about something that
#                      was built and is simply not in git.
#
# WHAT THE SPLIT COSTS, stated rather than left for the next reader to discover: `AUTHOR_LOCAL` now
# holds ONE entry, so `_author_local_mode()` can no longer return "mixed" and the all-or-nothing
# guard is structurally unable to fire. It is kept — a second untracked artifact would re-arm it —
# but it is no longer evidence of anything, and `test_meta_author_local_artifacts_are_all_or_nothing`
# says so in its own body rather than continuing to read as coverage.
REPO_ARTIFACTS: dict[str, Path] = {
    "docs/BACKLOG.md": BACKLOG,
    "docs/ROADMAP.md": ROADMAP,
    "the migration report": REPORT,
}

AUTHOR_LOCAL: dict[str, Path] = {
    "the marker vocabulary": MARKERS,
}


def _author_local_mode() -> str:
    present = sorted(k for k, v in AUTHOR_LOCAL.items() if v.exists())
    if len(present) == len(AUTHOR_LOCAL):
        return "author"
    if not present:
        return "clone"
    return "mixed:" + ",".join(present)


def _require_repo_artifact(path: Path, what: str) -> None:
    """A file that is git-tracked: present in every clone, so absence is a broken tree.

    A tracked file is present in every clone, so skipping on its absence would hide a
    deleted file behind a reason that is not true. It fails instead and names the path.
    """
    assert path.exists(), (
        f"{what} ({path.relative_to(ROOT)}) is missing. It is git-tracked, so there is "
        f"no checkout in which it is legitimately absent — this is a broken tree, not a clone. "
        f"Restore it with `git checkout -- {path.relative_to(ROOT)}`."
    )


def _require_author_local(path: Path, what: str) -> None:
    if path.exists():
        return
    mode = _author_local_mode()
    assert not mode.startswith("mixed"), (
        f"{what} ({path.name}) is missing, but other author-local artifacts ARE present ({mode}). "
        "That is a broken tree, not a fresh clone — failing rather than skipping, because a skip "
        "here would hide exactly the case where someone deleted one of these by accident."
    )
    pytest.skip(
        f"author-local artifact absent: {what} ({path.name}). It lives under the still-gitignored "
        "`.claude/`, so this AC can only run where the artifact was written. It is NOT proven by "
        "CI, and this skip says so rather than reporting a green."
    )


def _require_gh() -> None:
    """The ROADMAP status generator derives PR state from `gh`; a clone has no credentials.

    Refusing to run without `gh` is the generator's own contract (AC12b pins the non-zero exit),
    so the absence is checked here rather than being read as a generator failure.
    """
    if shutil.which("gh") is None:
        pytest.skip("gh is not installed — AC12 derives PR state from it and cannot run here")
    res = subprocess.run(
        ["gh", "pr", "list", "--limit", "1", "--json", "number"],
        capture_output=True, text=True, check=False,
    )
    if res.returncode != 0:
        pytest.skip("gh cannot reach the repo (no network or no credentials) — AC12 cannot run here")


def _need(path: Path, what: str) -> None:
    """Fail with a cause, not an ImportError or a stack trace from something unrelated.

    An AC whose mechanism is missing must go red **for that reason and say so**, otherwise a
    typo in the test is indistinguishable from an unbuilt mechanism.
    """
    if not path.exists() and path in REPO_ARTIFACTS.values():
        # Tracked: "not built yet" would be a lie, and so would a skip.
        _require_repo_artifact(path, what)
    if not path.exists() and path in AUTHOR_LOCAL.values():
        # Built, but not in git. "not built yet" would be a lie on a clone.
        _require_author_local(path, what)
    assert path.exists(), f"not built yet: {what} ({path.relative_to(ROOT)})"


def _markers(section: str) -> list[str]:
    """Load one section of the author-local marker vocabulary.

    **Absent-file behaviour is explicit and loud, never a silent skip.** A detector that quietly
    matches nothing when its vocabulary is missing reports a clean green while checking nothing —
    the same failure the title-marker invariant has to answer for.
    So: missing file, or a section with no tokens, is a hard failure that names the
    file and the section.
    """
    _require_author_local(MARKERS, "the marker vocabulary")
    out, cur = [], None
    for raw in MARKERS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = line[1:-1]
            continue
        if cur == section:
            out.append(line)
    assert out, f"marker section [{section}] is empty in {MARKERS.relative_to(ROOT)}"
    return out


def _headings() -> list[str]:
    _require_repo_artifact(BACKLOG, "the backlog")
    text = BACKLOG.read_text(encoding="utf-8")
    return [l for l in text.split("\n") if l.startswith("## B")]


def _extracted_ids() -> list[str]:
    """Extract ids with the GENERATOR'S OWN pipeline, not a competing regex.

    A hand-written regex here would be a second implementation, and when a probe and its subject
    disagree you cannot tell which one is wrong. Worse, when they share a blind spot you learn
    nothing at all.
    """
    out = []
    for h in _headings():
        res = subprocess.run(
            ["sed", "-E", r"s/^## (B[0-9.]+(\(original\))?).*/\1/;s/ .*//"],
            input=h,
            capture_output=True,
            text=True,
            check=True,
        )
        out.append(res.stdout.strip())
    return out


def _index_block() -> str:
    _require_repo_artifact(BACKLOG, "the backlog")
    text = BACKLOG.read_text(encoding="utf-8")
    head, _, rest = text.partition("| id |")
    assert rest, "index table header not found in docs/BACKLOG.md"
    return ("| id |" + rest).split("\n---\n")[0]


def _roadmap_section(first_line_idx: int) -> str:
    """Return the paragraph beginning at a 1-based line number, up to the next blank-ish break."""
    _require_repo_artifact(ROADMAP, "the roadmap")
    lines = ROADMAP.read_text(encoding="utf-8").split("\n")
    return lines[first_line_idx - 1]


# `_card_stdout` used to live here: it ran the card in the repository root, i.e. against the
# author's live roadmap. It is deleted rather than left unused. A dead helper that does
# exactly the forbidden thing is the next reader's shortcut back into the defect.


def _run_lc_c(script: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """`_run` under `LC_ALL=C`. p169: a byte-based tool misbehaves identically on GNU userland
    in EVERY locale, and `LC_ALL=C` is the one setting that reproduces it on BSD too -- so a
    portability assertion that does not pin the locale measures one shell, not the
    property."""
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LC_ALL": "C"},
    )


def _run(script: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _run_toc_on_a_copy(tmp_path: Path) -> subprocess.CompletedProcess:
    """Run the generator against a THROWAWAY COPY of the real backlog.

    `backlog-toc.sh` rewrites `docs/BACKLOG.md` in place. The first version of this file ran it
    with `cwd=ROOT` and therefore rewrote the real ledger mid-measurement — an instrument that
    mutates its own subject. No damage was observable (the generator has an
    idempotence test), but there was no byte-level before-image to prove it with, which is the
    whole problem. Never point this script at ROOT from a test.
    """
    _require_repo_artifact(BACKLOG, "the backlog")
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "BACKLOG.md").write_text(BACKLOG.read_text(encoding="utf-8"), encoding="utf-8")
    return _run(TOC, cwd=tmp_path)


# --------------------------------------------------------------------------------------
# key set
# --------------------------------------------------------------------------------------


def test_ac1_key_set_is_whole_minus_exactly_one_named_exemption() -> None:
    """AC1 — relational, not absolute, and the exemption cannot grow.

    `|exempt| == 1` plus the verbatim literal are load-bearing: without them the exemption table
    is a back door that can be widened until the equation balances, which is the self-satisfying
    shape AC1 was rewritten to escape in the first place.
    """
    _need(TOC, "backlog-toc.sh exemption table")
    src = TOC.read_text(encoding="utf-8")
    table = re.search(r"EXEMPT_IDS=\((.*?)\)\n", src, re.S)
    assert table, "no exemption table in the generator"
    entries = re.findall(r'"([^"]+)"', table.group(1))
    assert len(entries) == len(EXEMPT_LITERALS), (
        f"exemption table must hold exactly {len(EXEMPT_LITERALS)} entries, holds {len(entries)}"
    )
    assert entries == EXEMPT_LITERALS, f"exemption entries are {entries!r}, expected {EXEMPT_LITERALS!r}"

    indexed = set(re.findall(r"^\|\s\*\*([^*]+)\*\*\s\|", _index_block(), re.M))
    assert len(indexed) == len(_headings()) - len(EXEMPT_LITERALS), (
        f"{len(indexed)} indexed ids vs {len(_headings())} headings minus "
        f"{len(EXEMPT_LITERALS)} exemptions"
    )
    bad = sorted(i for i in indexed if not re.fullmatch(r"B\d+(\.\d+)?", i))
    assert not bad, f"non-B<n> id shapes survive in the index: {bad}"


@pytest.mark.parametrize(
    "heading",
    [
        "## B-brand-new — nobody exempted this one",
        "## B12. — a trailing dot",
        "## B1.2.3 — three components",
    ],
)
def test_ac1c_a_malformed_id_is_refused_not_laundered(tmp_path: Path, heading: str) -> None:
    """AC1's shape conjunct, pinned against **laundering** rather than only against junk rows.

    Found by a surviving mutant. An earlier version "tightened" the extraction pattern to
    `B[0-9]+(\\.[0-9]+)?`, and mutating it back changed nothing — every remaining heading is
    well-formed, so no fixture in the real corpus could tell the two patterns apart. The
    difference only shows on malformed input, and there the tightened pattern was **worse**: it
    matches the well-formed prefix and drops the rest, so `B12.` extracts as `B12` and `B1.2.3`
    as `B1.2` — malformed ids laundered into valid-looking ones, sailing past the very shape
    check that was supposed to catch them. Extraction stays permissive so validation can be
    strict, and these three fixtures are what hold that in place.

    The refusal must also be **total**: nothing written, original file untouched. The generator
    rewrites in place, so a half-written index is a worse outcome than a refusal.
    """
    _require_repo_artifact(BACKLOG, "the backlog")
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "BACKLOG.md"
    body = BACKLOG.read_text(encoding="utf-8") + f"\n{heading}\n\nbody\n"
    target.write_text(body, encoding="utf-8")
    before = target.read_bytes()

    res = _run(TOC, cwd=tmp_path)

    assert res.returncode == 4, f"malformed id accepted (exit {res.returncode})"
    assert target.read_bytes() == before, "the file was modified despite the refusal"
    assert heading.split(" — ")[0].removeprefix("## ") in res.stderr, (
        f"the refusal does not name the offending heading: {res.stderr!r}"
    )


def test_ac1b_maxid_input_set_is_unchanged_by_the_fix(tmp_path: Path) -> None:
    """AC1's third conjunct. `MAXID` is the authority for the next free id; an id collision is
    what happens when it is wrong, so the key-set repair must not touch its input set.

    The property pinned is
    "MAXID is the highest `## B<n>` heading in the corpus, and the key-set repair did not change
    which headings feed it". That is now computed from the headings here, independently of the
    generator, so a change to the generator's input set still reddens this and an ordinary filing
    does not.
    """
    _need(TOC, "backlog-toc.sh")
    src = TOC.read_text(encoding="utf-8")
    assert re.search(r"EXEMPT_IDS?=\(", src), "the exemption table has not landed — a no-change guard alone is vacuous"
    # Deliberately an INDEPENDENT computation, not the generator's own pipeline: the value is what
    # is under test here, so an oracle that shares the subject's arithmetic would prove nothing.
    # (Contrast `_extracted_ids`, which reuses the generator's extraction on purpose — there the
    # question is which ids exist, not what the arithmetic makes of them.)
    expected = max(int(m) for m in re.findall(r"^## B(\d+)", "\n".join(_headings()), re.M)) + 1
    res = _run_toc_on_a_copy(tmp_path)
    assert f"next free id B{expected}" in res.stdout, (
        f"MAXID is not the corpus maximum + 1 (expected B{expected}): {res.stdout.strip()!r}"
    )


# --------------------------------------------------------------------------------------
# ledger format, parser, state derivation
# --------------------------------------------------------------------------------------


def _index_rows_from_a_run(tmp_path: Path, ledger: str | None) -> dict[str, str]:
    """Regenerate the index against a THROWAWAY ledger and return its id -> state map.

    `ledger=None` means "run with no closure log at all", which is the negative control: the
    derivation has nothing to read and every id must fall back to `open`.
    """
    _require_repo_artifact(BACKLOG, "the backlog")
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "BACKLOG.md").write_text(BACKLOG.read_text(encoding="utf-8"), encoding="utf-8")
    env = dict(os.environ)
    if ledger is None:
        env["PLC_CLOSURE_LOG"] = str(tmp_path / "no-such-ledger.tsv")
    else:
        log = tmp_path / "ledger.tsv"
        log.write_text(ledger, encoding="utf-8")
        env["PLC_CLOSURE_LOG"] = str(log)
    res = subprocess.run(
        ["bash", str(TOC)], cwd=str(tmp_path), capture_output=True, text=True, check=False, env=env
    )
    assert res.returncode == 0, f"generator failed: {res.stdout}{res.stderr}"
    text = (docs / "BACKLOG.md").read_text(encoding="utf-8")
    block = ("| id |" + text.partition("| id |")[2]).split("\n---\n")[0]
    return dict(re.findall(r"\|\s\*\*(B[\d.]+)\*\*\s\|\s([^|]+?)\s\|", block))


def test_ac3_state_is_derived_from_the_ledger_not_from_title_words(tmp_path: Path) -> None:
    """AC3 pins the derivation itself: an id with a `closed` event renders `closed (<reason>)`,
    and **deleting that line flips it back to `open`**. Pinning only the value domain would be
    satisfied by a generator that emits `open` for every row.

    The delete-flips-it-back half is the load-bearing one.
    Without it the test passes on a generator that reads title words and happens to print
    `closed (completed)` — which is precisely the mechanism being replaced.
    """
    _need(LEDGER, "the closure ledger")
    _need(TOC, "backlog-toc.sh")
    rows = dict(re.findall(r"\|\s\*\*(B[\d.]+)\*\*\s\|\s([^|]+?)\s\|", _index_block()))
    closed = [i for i, s in rows.items() if s.startswith("closed (")]
    assert closed, "no id renders as closed(<reason>) — the derivation is not wired"

    # Negative control: same headings, same generator, no ledger. Every id must read `open`.
    without = _index_rows_from_a_run(tmp_path, None)
    still_closed = [i for i in closed if without.get(i, "").startswith("closed (")]
    assert not still_closed, (
        "these ids render closed with NO ledger behind them, so the value is coming from the "
        f"heading text and not from the derivation: {sorted(still_closed)[:5]}"
    )

    # Positive control: a one-line ledger closes exactly the id it names, and nothing else.
    victim = sorted(closed)[0]
    with_one = _index_rows_from_a_run(
        tmp_path / "pos", f"{victim}\tclosed\tsuperseded\t2026-01-13\t-\n"
    )
    assert with_one[victim] == "closed (superseded)", (
        f"the reason is not carried through: {victim} rendered {with_one[victim]!r}"
    )
    others = [i for i, s in with_one.items() if i != victim and s.startswith("closed (")]
    assert not others, f"ids closed that the ledger never named: {sorted(others)[:5]}"


BAD_LINES = [
    ("bad reason", "B1005\tclosed\tbogus\t2026-01-11\t#22"),
    ("bad event", "B1005\tdone\tcompleted\t2026-01-11\t#22"),
    ("bad id shape", "BX9\tclosed\tcompleted\t2026-01-11\t#22"),
    ("four columns", "B1005\tclosed\tcompleted\t2026-01-11"),
    ("six columns", "B1005\tclosed\tcompleted\t2026-01-11\t#22\textra"),
    ("spaces not tabs", "B1005 closed completed 2026-01-11 #1"),
    ("closed with no reason", "B1005\tclosed\t-\t2026-01-11\t#22"),
    ("reopen carrying a reason", "B1005\treopen\tcompleted\t2026-01-11\t#22"),
    ("ref-amend carrying a reason", "B1005\tref-amend\tcompleted\t2026-01-11\t#22"),
    ("ref-amend with no ref", "B1005\tref-amend\t-\t2026-01-11\t-"),
]


@pytest.mark.parametrize("label,line", BAD_LINES, ids=[b[0] for b in BAD_LINES])
def test_ac5_parser_rejects_out_of_domain_values_instead_of_accepting_them(
    label: str, line: str
) -> None:
    """AC5 — every out-of-domain value must be an ERROR, never a silently accepted value.

    A reason nobody recognises would otherwise be rendered into the index as authoritative text,
    which is the hand-written state the log replaces, re-entering through the parser.

    The last two cases go beyond the original criterion: `closed` with
    reason `-` declares a closure with no stated cause, and `reopen` carrying a real reason mixes
    two axes in one column. Both parse fine as "five columns, values in domain" and both are
    nonsense.
    """
    _need(PARSER, "the closure-log parser")
    res = subprocess.run(
        ["bash", str(PARSER), "--check-line"],
        input=line + "\n", capture_output=True, text=True, check=False,
    )
    assert res.returncode != 0, f"{label}: accepted silently"
    assert "backlog-closures:" in res.stderr, f"{label}: rejected without saying why"


def test_ac5b_a_valid_line_and_a_comment_are_both_accepted() -> None:
    """The positive control. Without it, a parser that rejects everything scores 8/8 above."""
    _need(PARSER, "the closure-log parser")
    for line in ("B1006\tclosed\tcompleted\t2026-01-10\t#21", "# a comment", "",
                 "B1006\tref-amend\t-\t2026-01-24\t#24"):
        res = subprocess.run(
            ["bash", str(PARSER), "--check-line"],
            input=line + "\n", capture_output=True, text=True, check=False,
        )
        assert res.returncode == 0, f"a legal line was rejected: {line!r} -> {res.stderr!r}"


def _ledger(tmp_path: Path, *lines: str) -> Path:
    f = tmp_path / "ledger.tsv"
    f.write_text("# header comment\n" + "".join(l + "\n" for l in lines), encoding="utf-8")
    return f


def test_ac6_only_the_pinned_file_counts_not_a_lookalike_elsewhere(tmp_path: Path) -> None:
    """AC6 — the log's authority comes from its PATH, not from its shape. A same-shaped TSV
    sitting anywhere else must not be picked up, and `#` lines are comments, not data."""
    _need(PARSER, "the closure-log parser")
    real = _ledger(tmp_path, "B1006\tclosed\tcompleted\t2026-01-10\t#21")
    decoy = tmp_path / "decoy.tsv"
    decoy.write_text("B1003\tclosed\tcompleted\t2026-01-01\t#1\n", encoding="utf-8")

    ids = _run(PARSER, "--list-ids", str(real)).stdout.split()
    assert ids == ["B1006"], f"expected only the pinned file's ids, got {ids}"
    assert "B1003" not in ids, "a lookalike TSV outside the pinned path was counted"

    commented = _ledger(tmp_path, "# B1002\tclosed\tcompleted\t2026-01-01\t#2")
    assert _run(PARSER, "--list-ids", str(commented)).stdout.split() == [], (
        "a commented-out line was read as data"
    )


def test_ac16_state_takes_the_last_event_not_the_first(tmp_path: Path) -> None:
    """AC16 — derivation reads the id's LAST event. Taking the first would report an id as
    closed forever after one closure, which is precisely the trap the event log exists to avoid:
    an append-only record with no way back is a state field wearing a log's clothes."""
    _need(PARSER, "the closure-log parser")
    f = _ledger(
        tmp_path,
        "B1006\tclosed\tcompleted\t2026-01-10\t#21",
        "B1006\treopen\t-\t2026-01-11\t#23",
    )
    assert _run(PARSER, "--derive", "B1006", str(f)).stdout.strip() == "open"

    g = _ledger(
        tmp_path,
        "B1007\treopen\t-\t2026-01-10\t#21",
        "B1007\tclosed\tnot_planned\t2026-01-11\t#23",
    )
    assert _run(PARSER, "--derive", "B1007", str(g)).stdout.strip() == "closed (not_planned)", (
        "the reverse order must derive the reverse state, or the test would pass on a "
        "constant-returning implementation"
    )


def test_ac17_partial_renders_as_open_and_stays_visible_in_the_ledger(tmp_path: Path) -> None:
    """AC17 — a half-closed entry counts as open so it keeps appearing in planning, while
    the `partial` event stays in the log carrying the detail. The second assertion is the one
    that matters: rendering open is only correct if the event is still findable."""
    _need(PARSER, "the closure-log parser")
    f = _ledger(tmp_path, "B1005\tpartial\tcompleted\t2026-01-11\t#22")
    assert _run(PARSER, "--derive", "B1005", str(f)).stdout.strip() == "open"
    assert _run(PARSER, "--list-ids", str(f)).stdout.split() == ["B1005"], (
        "a partial id vanished from the log — open must not mean forgotten"
    )


def test_ac17b_an_id_with_no_events_is_open(tmp_path: Path) -> None:
    """The absent case, pinned separately. `open` must be the derivation for "no events", not a
    fallback that also swallows an event the parser failed to understand."""
    _need(PARSER, "the closure-log parser")
    f = _ledger(tmp_path, "B1006\tclosed\tcompleted\t2026-01-10\t#21")
    assert _run(PARSER, "--derive", "B1008", str(f)).stdout.strip() == "open"


def test_a_ref_amend_records_a_reference_and_moves_no_state(tmp_path: Path) -> None:
    """`ref-amend` exists so a PR number learned AFTER the closure can still be recorded.

    Its whole contract is that it carries a reference and nothing else, so the assertions are
    about what does NOT move. The `--derive-event` probe is checked for the absence of a state
    word rather than for a phrase: printing `open` there would assert that amending a ref can
    reopen an entry, which is precisely the property this event is built not to have.
    """
    _need(PARSER, "the closure-log parser")
    f = _ledger(
        tmp_path,
        "B1006\tclosed\tcompleted\t2026-01-10\tpending",
        "B1006\tref-amend\t-\t2026-01-24\t#24",
    )
    assert _run(PARSER, "--derive", "B1006", str(f)).stdout.strip() == "closed (completed)", (
        "an amend changed the derived state — it is not a transition"
    )
    assert _run(PARSER, "--list-ids", str(f)).stdout.split() == ["B1006"]

    probe = _run(PARSER, "--derive-event", "ref-amend").stdout.strip()
    assert probe and probe not in ("open", "closed (<reason>)"), (
        f"the domain probe gave ref-amend a state: {probe!r}"
    )

    # The ordering half: an amend written BEFORE a later reopen must not shadow it either.
    gdir = tmp_path / "g"
    gdir.mkdir()
    g = _ledger(
        gdir,
        "B1006\tclosed\tcompleted\t2026-01-10\t#21",
        "B1006\tref-amend\t-\t2026-01-24\t#24",
        "B1006\treopen\t-\t2026-01-25\t#25",
    )
    assert _run(PARSER, "--derive", "B1006", str(g)).stdout.strip() == "open"


BASE_LEDGER = (
    "# header\n"
    "B1006\tclosed\tcompleted\t2026-01-10\t#21\n"
    "B1004\tclosed\tnot_planned\t2026-01-11\t#22\n"
    "B1001\tclosed\tmoved\t2026-01-04\tother-repo\n"
)


def _repo(tmp_path: Path, base: str = BASE_LEDGER, mutate: str = "") -> Path:
    """A throwaway git repo whose base commit already carries >=3 ledger lines.

    The >=3 matters: AC15's original form ("no existing line changed") is trivially true when
    the file does not exist, because there are no existing lines to change. The antecedent has
    to be non-empty for the assertion to mean anything.
    """
    d = tmp_path / "repo"
    (d / ".claude" / "invariants").mkdir(parents=True, exist_ok=True)
    (d / "scripts" / "invariants").mkdir(parents=True, exist_ok=True)
    (d / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy(PARSER, d / "scripts" / PARSER.name)
    shutil.copy(GATE, d / "scripts" / "invariants" / GATE.name)
    # The gate sources scripts/lib/closure-log-added.sh for the base/added split,
    # because `closure-declaration.sh reconcile` needs the same set and a second computation
    # would be a copy. The fixture has to carry the real dependency set or it stops testing
    # the real gate. MEASURED, not anticipated: without this line the source failed, the gate
    # RETURNED 0, and criterion 4 switched itself off silently -- tests went red and
    # the reason was not in any assertion they name.
    shutil.copy(HELPER, d / "scripts" / "lib" / HELPER.name)
    log = d / ".claude" / "backlog-closures.tsv"
    log.write_text(base, encoding="utf-8")

    def git(*a: str) -> None:
        subprocess.run(["git", *a], cwd=d, capture_output=True, check=False)

    git("init", "-q")
    git("symbolic-ref", "HEAD", "refs/heads/main")
    git("config", "user.email", "t@t"); git("config", "user.name", "t")
    git("add", "-A"); git("commit", "-qm", "base")
    git("checkout", "-qb", "feat")
    if mutate:
        log.write_text(mutate, encoding="utf-8")
        git("add", "-A"); git("commit", "-qm", "change")
    return d


def _gate(d: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "scripts/invariants/backlog-closure-log.sh"],
        cwd=d, capture_output=True, text=True, check=False,
    )


LEGAL_APPEND = BASE_LEDGER + "B1005\tpartial\tcompleted\t2026-01-11\t#22\n"

GATE_CASES = [
    ("no change", BASE_LEDGER, 0),
    ("legal append", LEGAL_APPEND, 0),
    ("dotted id", BASE_LEDGER + "B1000.3\tclosed\tcompleted\t2026-01-11\t#1\n", 0),
    ("reopen then close", BASE_LEDGER + "B1006\treopen\t-\t2026-01-11\t#23\n"
                                        "B1006\tclosed\tcompleted\t2026-01-12\t#25\n", 0),
    ("ref-amend on an id with history", BASE_LEDGER + "B1006\tref-amend\t-\t2026-01-24\t#24\n", 0),
    ("ref-amend on an id closed in this same branch",
     BASE_LEDGER + "B1009\tclosed\tcompleted\t2026-01-24\t-\n"
                   "B1009\tref-amend\t-\t2026-01-25\t#24\n", 0),
    ("ref-amend on an id with no events at all",
     BASE_LEDGER + "B1009\tref-amend\t-\t2026-01-24\t#24\n", 1),
    # Criterion 5's counterpart on criterion 3. If the duplicate-closure join counted `ref-amend`
    # as an event, this second `closed` would see `prior == ref-amend` instead of `closed` and be
    # accepted — an amend would become a laundering step for the exact line criterion 3 exists to
    # refuse. Every other duplicate fixture has the two closures adjacent, so a green board would
    # have said nothing about it.
    ("duplicate close with an amend between them",
     BASE_LEDGER + "B1006\tref-amend\t-\t2026-01-24\t#24\n"
                   "B1006\tclosed\tcompleted\t2026-01-25\t#25\n", 1),
    ("bad reason", BASE_LEDGER + "B1005\tclosed\tbogus\t2026-01-11\t#22\n", 1),
    ("bad id", BASE_LEDGER + "BX9\tclosed\tcompleted\t2026-01-11\t#22\n", 1),
    ("four columns", BASE_LEDGER + "B1005\tclosed\tcompleted\t2026-01-11\n", 1),
    ("no trailing newline", BASE_LEDGER + "B1005\tclosed\tcompleted\t2026-01-11\t#22", 1),
    ("duplicate close", BASE_LEDGER + "B1006\tclosed\tcompleted\t2026-01-12\t#25\n", 1),
    ("duplicate within branch", BASE_LEDGER + "B1009\tclosed\tcompleted\t2026-01-11\t#1\n"
                                              "B1009\tclosed\tcompleted\t2026-01-12\t#2\n", 1),
    # The same duplicate with a BLANK LINE in the added range. Criterion 3 counted non-blank,
    # non-comment lines but indexed into a stream from which only comments had been removed, so
    # every blank shortened the "strictly before this one" window by one and the duplicate walked
    # through. Every fixture above happens to have no blank line in the added range, which is why
    # a green board said nothing about it.
    ("duplicate after a blank line", BASE_LEDGER + "\n"
                                                   "B1009\tclosed\tcompleted\t2026-01-11\t#1\n"
                                                   "B1009\tclosed\tcompleted\t2026-01-12\t#2\n", 1),
    ("a blank line alone is still legal", BASE_LEDGER + "\n"
                                                        "B1009\tclosed\tcompleted\t2026-01-11\t#1\n", 0),
    ("edit an old line", BASE_LEDGER.replace("not_planned", "duplicate"), 1),
    ("delete an old line", BASE_LEDGER.replace("B1004\tclosed\tnot_planned\t2026-01-11\t#22\n", ""), 1),
    ("insert above the end", BASE_LEDGER.replace("B1006", "B1003\tclosed\tcompleted\t2026-01-01\t#1\nB1006", 1), 1),
]


@pytest.mark.parametrize("label,content,expected", GATE_CASES, ids=[c[0] for c in GATE_CASES])
def test_ac7_gate_enforces_every_criterion(
    tmp_path: Path, label: str, content: str, expected: int
) -> None:
    """AC7 — every criterion, each with a fixture that exercises it.

    Six of these are green cases. Without them a gate that simply rejects everything would score
    a clean sweep on the violations, which is the same hole AC5's positive control closes.
    """
    _need(GATE, "the closure-log gate")
    res = _gate(_repo(tmp_path, mutate=content if content != BASE_LEDGER else ""))
    assert res.returncode == expected, (
        f"{label}: expected exit {expected}, got {res.returncode}\n{res.stdout}{res.stderr}"
    )
    assert res.stdout.startswith("PASS " if expected == 0 else "FAIL "), (
        f"{label}: invariant contract violated — output was {res.stdout!r}"
    )


def test_ac7b_gate_pins_the_two_operands_it_was_corrected_on() -> None:
    """Both of these were measured wrong first, so both are pinned in the source.

    `merge-base` rather than main's tip: with several branches in flight on one repo
    an advancing tip fails a legal older branch. No `head -n 0`: BSD head errors on
    it, and the probe that first used it produced the right answer only because the failure
    returned an empty string.
    """
    _need(GATE, "the closure-log gate")
    src = GATE.read_text(encoding="utf-8")

    # Scan CODE lines, not the whole file. The first version of this assertion searched the raw
    # text and failed on the gate's own comment explaining why `head -n 0` must not be used —
    # a checker that cannot tell a USE from a MENTION. The rule belongs on the shape: executable
    # lines only.
    # The base/added split lives in scripts/lib/closure-log-added.sh so the
    # reconcile check can share ONE computation instead of copying it. The property being
    # pinned did not change; its FILE did. Scanning only the gate turned this red while the
    # behaviour was intact -- a pin attached to a location rather than to a shape.
    # Scan the gate AND the helper it
    # sources; the assertion then survives the code living wherever it lives.
    src = src + "\n" + (HELPER.read_text(encoding="utf-8") if HELPER.exists() else "")
    code = "\n".join(
        l for l in src.splitlines() if l.strip() and not l.lstrip().startswith("#")
    )
    assert "merge-base" in code, "the gate compares against main's tip, not the merge-base"
    assert "head -n 0" not in code, "BSD head -n 0 errors in executable code; use awk 'NR<n'"
    assert "head -n 0" in src, (
        "the comment explaining why head -n 0 is banned has gone — the ban now looks arbitrary, "
        "and this assertion would no longer prove it can tell a use from a mention"
    )


AC8_CASES = [
    ("a: history already violates, branch adds nothing", "", 0),
    ("b: history already violates, branch adds a legal line",
     "B1005\tclosed\tcompleted\t2026-01-12\t#25\n", 0),
    ("c: history already violates, branch adds a violating line",
     "B1001\tclosed\tcompleted\t2026-01-12\t#25\n", 1),
]

HISTDUP = BASE_LEDGER + "B1006\tclosed\tcompleted\t2026-01-10\t#21\n"


@pytest.mark.parametrize("label,added,expected", AC8_CASES, ids=[c[0] for c in AC8_CASES])
def test_ac8_gate_does_not_fire_on_history_but_does_fire_on_new_lines(
    tmp_path: Path, label: str, added: str, expected: int
) -> None:
    """AC8 — three observations against a base that ALREADY contains a duplicate closure.

    (a) and (b) alone are satisfied by a gate that never fires, which is why (c) is not
    optional: it is the half that proves the gate fires at all. The base is deliberately
    dirty: a gate that judged history would block every push
    in the repo, which is why criterion 3 was narrowed after measurement.
    """
    _need(GATE, "the closure-log gate")
    res = _gate(_repo(tmp_path, base=HISTDUP, mutate=(HISTDUP + added) if added else ""))
    assert res.returncode == expected, (
        f"{label}: expected exit {expected}, got {res.returncode}\n{res.stdout}{res.stderr}"
    )


@pytest.mark.parametrize("n", [0, 1, 2, 3])
def test_ac9_examined_count_is_real_and_moves_with_n(tmp_path: Path, n: int) -> None:
    """AC9 — the count must be TRUE and must track N.

    The original form only required that a count be printed, which an unconditional
    `examined 0` satisfies — precisely the class it exists to catch. Parametrising over N is
    what makes a hardcoded constant impossible to hide.
    """
    _need(GATE, "the closure-log gate")
    added = "".join(f"B{900 + i}\tclosed\tcompleted\t2026-08-0{i + 1}\t#{i}\n" for i in range(n))
    res = _gate(_repo(tmp_path, mutate=(BASE_LEDGER + added) if added else ""))
    assert res.returncode == 0, res.stdout + res.stderr
    assert f"examined {n} added line(s)" in res.stdout, (
        f"expected a true count of {n}, got: {res.stdout.strip()!r}"
    )


AC15_CASES = [
    ("edit an old line", BASE_LEDGER.replace("not_planned", "duplicate")),
    ("delete an old line", BASE_LEDGER.replace("B1004\tclosed\tnot_planned\t2026-01-11\t#22\n", "")),
    ("reorder old lines", "# header\n" + "".join(
        l + "\n" for l in reversed(BASE_LEDGER.rstrip("\n").split("\n")[1:]))),
    ("insert above the end", BASE_LEDGER.replace("B1006", "B1003\tclosed\tcompleted\t2026-01-01\t#1\nB1006", 1)),
]


@pytest.mark.parametrize("label,content", AC15_CASES, ids=[c[0] for c in AC15_CASES])
def test_ac15_ledger_is_append_only_against_a_base_that_has_old_lines(
    tmp_path: Path, label: str, content: str
) -> None:
    """AC15 — append-only, asserted as a BYTE PREFIX against a base carrying >=3 old lines.

    Both halves were corrected after measurement. The non-empty base is the antecedent the
    original lacked; the byte-prefix formulation replaces `git diff` line semantics, which
    reject a legal append onto a file whose last line has no trailing newline.
    """
    _need(GATE, "the closure-log gate")
    res = _gate(_repo(tmp_path, mutate=content))
    assert res.returncode == 1, f"{label}: an old line was modified and the gate allowed it"
    assert "append-only" in res.stdout, f"{label}: rejected without naming the property"


def test_ac15b_appending_onto_a_base_with_no_trailing_newline_is_allowed(tmp_path: Path) -> None:
    """The measured false positive that forced criterion 4's rewrite: git renders the last old
    line as -/+ when the base lacks a final newline, so a diff-based check rejects a legal
    append. The prefix comparison normalises that once."""
    _need(GATE, "the closure-log gate")
    nonl = BASE_LEDGER.rstrip("\n")
    res = _gate(_repo(tmp_path, base=nonl,
                      mutate=nonl + "\nB1005\tclosed\tcompleted\t2026-01-11\t#22\n"))
    assert res.returncode == 0, f"a legal append was rejected:\n{res.stdout}{res.stderr}"


# --------------------------------------------------------------------------------------
# migration tool and its report
# --------------------------------------------------------------------------------------


def test_ac10_every_ruled_id_carries_a_human_written_rationale() -> None:
    """AC10 — the criterion is not "contains no arrow literal", and it has a non-empty
    antecedent: an empty report satisfies "every entry has a rationale" vacuously."""
    _need(REPORT, "the migration report")
    text = REPORT.read_text(encoding="utf-8")
    ruled = re.findall(r"^\|\s*(B[\d.]+)\s*\|", text, re.M)
    assert len(ruled) >= 1, "the migration report rules on zero ids — vacuously 'all justified'"
    (rationale,) = _markers("rationale")
    assert text.count(rationale) >= len(ruled), "some ruled id carries no human rationale line"


def test_ac11_migration_tool_is_gone_and_the_report_it_produced_is_present() -> None:
    """AC11 is a conjunction. Without the reverse oracle the left half passes trivially on any
    unrelated PR — the script is absent today and always was."""
    assert not RECONCILE.exists(), "the migration tool is still in the tree"
    _need(REPORT, "the migration report (the reverse oracle for AC11)")


def _closed_bit(value: str) -> bool:
    """The one comparable fact across the two state vocabularies: is this entry closed?

    The old column said `✅ done` / `—` / `🟡 med` / `↗ moved`; the new one must say
    `open` / `closed (<reason>)` (AC19). Only `✅ done` and `closed (` mean closed.
    """
    v = value.strip()
    return v.startswith("closed (") or "done" in v


def _migration_commit() -> str:
    """The commit that introduced the pre-migration snapshot — i.e. the moment the report ruled on.

    Located from git rather than written down as a literal SHA: a hand-copied pin is one more
    hand-maintained state. `--diff-filter=A` with the
    earliest hit is the add.
    """
    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", str(SNAPSHOT.relative_to(ROOT))],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    shas = [l for l in out.stdout.split() if l]
    if not shas:
        pytest.skip("snapshot's adding commit is unreachable (shallow clone?) — cannot pin the moment")
    return shas[-1]


def _states_at_migration() -> dict[str, str]:
    """Derived state as the ledger stood AT the migration, not as it stands today.

    **This operand was once wrong.** It used to be the LIVE
    `docs/BACKLOG.md` index — a value derived from an append-only log, frozen into an equality
    against a one-time report. Every later closure event therefore had to appear in a report
    written before it existed, so any legitimate closure appended after the migration
    turned this red. An assertion that pins a derived value like that
    reports the mechanism being USED as a regression.

    The report is a one-time artifact about one moment, so both operands must come from that
    moment: the left from the committed snapshot, the right from the ledger's content at the same
    commit. Neither moves again, and neither is derived from the other.
    """
    out = subprocess.run(
        ["git", "show", f"{_migration_commit()}:{LEDGER.relative_to(ROOT)}"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        pytest.skip(f"ledger unreadable at the migration commit: {out.stderr.strip()}")
    tmp = ROOT / ".claude" / ".ac20-ledger-at-migration.tmp"
    tmp.write_text(out.stdout, encoding="utf-8")
    try:
        states = subprocess.run(
            ["/bin/bash", str(PARSER), "--states", str(tmp)],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
    finally:
        tmp.unlink(missing_ok=True)
    return dict(
        l.split("\t", 1) for l in states.splitlines() if "\t" in l
    )


def test_ac20_report_matches_the_premigration_snapshot_not_itself() -> None:
    """AC20 — the right operand is the pre-migration snapshot. When this was written `docs/` was gitignored
    (the count WAS 0, before p39), so "ids whose state changed in this PR" was not derivable
    from the PR; deriving it from the report would have the report compare against itself. **The
    premise has since been retired — `docs/` is tracked as of p39 — but the conclusion stands on
    its own:** a report that is its own right operand proves nothing, whatever the diff can see.

    The comparison is on the open/closed BIT, not literal: the
    two vocabularies are disjoint by construction, so a literal comparison reads every id as changed and
    demands a hand-written rationale for all of them, most of which could only be the same
    sentence -- a vacuous-satisfaction shape at a larger
    scale, and it makes the check weaker rather than stronger: a report can satisfy "every ruled
    id has a rationale" while ruling on nothing anyone decided. So the comparison is
    the open/closed BIT. What must not change is which side comes from where — the left
    operand is still the report and the right is still the committed pre-migration snapshot
    joined to the current index, so the report still never compares against itself.
    """
    _need(SNAPSHOT, "the pre-migration snapshot")
    _need(REPORT, "the migration report")
    before = dict(
        l.split("\t")[:2] for l in SNAPSHOT.read_text(encoding="utf-8").splitlines() if "\t" in l
    )
    ruled = set(re.findall(r"^\|\s*(B[\d.]+)\s*\|", REPORT.read_text(encoding="utf-8"), re.M))
    after = _states_at_migration()
    changed = {
        i
        for i in before
        if _closed_bit(before[i]) != _closed_bit(after.get(i, "open"))
    }
    assert ruled and changed, f"both sides must be non-empty: ruled={len(ruled)} changed={len(changed)}"
    assert ruled == changed, (
        f"the report lies: only-in-report={ruled - changed} only-in-diff={changed - ruled}"
    )

    # Second conjunct, added after review. The bit comparison above is blind to every id that was
    # ALREADY `✅ done` before the migration and is closed after it, and
    # because it is a set equality it also forbids the report from documenting them. Those are
    # named in the report's own blind-spot section rather than left implicit. What can still be
    # checked about the ruled set, cheaply and without changing what the report contains, is that
    # every id it claims to have ruled is actually closed in the log: a fabricated ruling row for
    # an id with no closure event is caught here even though the bit comparison would not see it.
    states = subprocess.run(
        ["bash", str(PARSER), "--states"], cwd=str(ROOT), capture_output=True, text=True, check=False
    ).stdout
    closed_in_log = {
        l.split("\t")[0] for l in states.splitlines() if "\t" in l and l.split("\t")[1].startswith("closed")
    }
    unbacked = ruled - closed_in_log
    assert not unbacked, f"the report rules on ids the log does not close: {sorted(unbacked)}"


# --------------------------------------------------------------------------------------
# the two-column index
# --------------------------------------------------------------------------------------


def test_ac4_header_names_which_column_comes_from_where_and_points_at_the_right_one() -> None:
    """AC4 — the criterion is that it points at the *right* column, not that the words appear.

    The first version asserted both provenance words appeared somewhere in the first four lines
    of the block. That is containment, not association: a header with the two labels SWAPPED —
    `state (hand-written) | priority (derived)`, a lie about the exact property the header
    exists to state — passed it unchanged. The producer reads the two labels positionally
    out of the marker file, so a reordering there is one edit away. Assert per CELL instead.
    """
    header = _index_block().split("\n")[0]
    assert "state" in header and "priority" in header, f"index header is still {header!r}"
    cells = [c.strip() for c in header.strip().strip("|").split("|")]
    prov = dict(l.split("\t", 1) for l in _markers("provenance") if "\t" in l)
    derived, handwritten = prov["derived"], prov["hand-written"]
    state_cell = next((c for c in cells if c.startswith("state")), "")
    prio_cell = next((c for c in cells if c.startswith("priority")), "")
    assert state_cell and prio_cell, f"no state/priority cell in header: {cells}"
    assert derived in state_cell and handwritten not in state_cell, (
        f"the state column is not labelled as derived: {state_cell!r}"
    )
    assert handwritten in prio_cell and derived not in prio_cell, (
        f"the priority column is not labelled as hand-written: {prio_cell!r}"
    )


def test_ac19_no_placeholder_rows_and_at_least_one_backed_closed_value() -> None:
    """AC19 — no inert third conjunct. 'or is open' would let an index that emits
    `open` for every id satisfy it, the same or-clause weakness AC3 was rewritten to escape."""
    index = _index_block()
    assert " — " not in index and "**##**" not in index, "placeholder rows survive"
    closed = re.findall(r"\|\s(closed \([a-z_]+\))\s\|", index)
    assert len(closed) >= 1, "no closed(<reason>) value at all — the or-clause would hide this"


# --------------------------------------------------------------------------------------
# title markers
# --------------------------------------------------------------------------------------


def test_ac18_marker_glyphs_are_banned_but_prose_is_not(tmp_path: Path) -> None:
    """AC18 — only marker shapes (✅, or ALL-CAPS DONE/CLOSED/MERGED). Case-normalising would
    misread '...until the drain is done', so lowercase prose must stay green."""
    _need(TITLE_INV, "the title-marker invariant")
    offenders = [h for h in _headings() if "✅" in h or re.search(r"\b(DONE|CLOSED|MERGED)\b", h)]
    assert not offenders, f"{len(offenders)} headings still carry marker shapes"

    # The subject is passed as a PATH, never piped. The first version piped it, and that is why
    # the guard read git's pre-push ref lines instead of the backlog on every real push: a
    # subject taken from fd 0 is whatever the caller happened to be holding. Passing a file also
    # makes this assertion mean something — with a pipe the guard fell back to the real (clean)
    # ledger and returned 0 without ever seeing the prose being tested.
    tol = tmp_path / "prose.md"
    tol.write_text("## B1009 — hold this until the drain is done\n", encoding="utf-8")
    res = _run(TITLE_INV, str(tol))
    assert res.returncode == 0, f"lowercase prose 'done' was judged a closure marker: {res.stdout}"
    assert str(tol) in res.stdout, "the guard did not report the subject it was given"

    # The same probe must be able to go red, or the green above proves nothing.
    marked = tmp_path / "marked.md"
    marked.write_text("## B1009 — ✅ DONE 2026-01-13 — thing\n", encoding="utf-8")
    assert _run(TITLE_INV, str(marked)).returncode == 1, "the probe cannot fail — its green is vacuous"


def _p172_is_quoted(line: str) -> bool:
    """True for a markdown blockquote line, with or without a leading comment marker.

    A SCANNER THAT CANNOT TELL "ASSERTING X" FROM "QUOTING SOMEONE WHO ASSERTED X" reports the
    repository's own historical record as a defect, and the cheapest way to make it green is to
    falsify that record. This is not hypothetical: on its first run the p172 guard flagged
    `test_backlog_ledger.py`'s comment block that opens *"THE PREMISE OF THIS BLOCK WAS RETIRED
    BY p39, AND CI IS WHAT SAID SO. It used to open:"* and then quotes the retired premise
    verbatim. That block is CORRECT -- the quote is what makes the correction legible -- and
    "fixing" it would have deleted the evidence. This repository files the same shape as a
    lesson of its own: a text scanner cannot distinguish USING a token from TALKING ABOUT one.

    Shape, not position: a `>` marker is the author saying "these are not my words here". Keyed
    on neither line numbers nor paths, both of which go stale on the next edit.
    """
    stripped = line.lstrip()
    for marker in ("#", "//"):
        if stripped.startswith(marker):
            stripped = stripped[len(marker):].lstrip()
            break
    return stripped.startswith(">")


def test_p169_the_diagnostic_truncates_characters_not_bytes(tmp_path: Path) -> None:
    """p169 -- the FAIL diagnostic was `cut -c1-140`, and `cut -c` is byte-based.

    MEASURED, and the first measurement was WRONG IN THE REASSURING DIRECTION. Run on a
    macOS shell the defect does not reproduce at all: BSD `cut -c` is character-aware
    under a UTF-8 locale, so the diagnostic came out valid and untruncated and the bug looked
    absent. It is GNU coreutils where `cut -c` counts bytes **regardless of locale** -- the
    exact finding `scripts/utf8-text.sh` was written for -- so the portable oracle is
    `LC_ALL=C`, which reproduces on either userland. Under it, the heading below emitted a
    dangling `\xe9` lead byte: invalid UTF-8, terminal mojibake, the same shape as a
    dangling-lead-byte failure CI has caught before.

    The subject here is only a transient stderr diagnostic -- nothing is written to disk, which
    is why this is low-stakes. It is fixed because the character-safe helper already sits one
    directory over, not because it is dangerous.

    The padding is load-bearing and is not a magic number: the diagnostic's prefix is
    `<lineno>:## B1009 - ` and the title is 3-byte characters, so with no padding byte 140 lands
    exactly on a character boundary and the cut is clean BY LUCK. One ASCII byte of padding
    moves the boundary into the middle of a character. A fixture without it passes against the
    defect.
    """
    _need(TITLE_INV, "the title-marker invariant")
    subject = tmp_path / "cjk.md"
    title = "X" + "\u4e2d\u6587\u6807\u9898\u5f88\u957f" * 10
    subject.write_text(
        f"# Backlog\n\n## B1009 \u2014 {title} \u2014 \u2705 DONE 2026-01-01\n\nbody\n",
        encoding="utf-8",
    )
    res = subprocess.run(
        ["bash", str(TITLE_INV), str(subject)],
        cwd=str(tmp_path),
        capture_output=True,
        text=False,
        check=False,
        env={**os.environ, "LC_ALL": "C"},
    )
    assert res.returncode == 1, "the probe cannot fail -- a green here would be vacuous"
    try:
        res.stderr.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(
            f"the diagnostic is not valid UTF-8 -- truncated mid-character: {exc}; "
            f"tail={res.stderr[-8:]!r}"
        ) from None


def test_p169_the_diagnostic_is_still_bounded(tmp_path: Path) -> None:
    """The other half: character-safety must not become "print the whole line".

    A truncation that stops truncating is a different defect with the same green, and the
    reason the bound exists is that `$OFFENDERS` can hold every offending heading in a
    large file. The bound is asserted in CHARACTERS, because that is now the unit.
    """
    _need(TITLE_INV, "the title-marker invariant")
    subject = tmp_path / "long.md"
    tail = "\u5c3e\u5df4"  # must survive nowhere -- it sits far past the cut
    body = "\u4e2d\u6587" * 200
    heading = "## B1009 \u2014 " + body + tail + " \u2014 \u2705 DONE 2026-01-01"
    subject.write_text("# Backlog\n\n" + heading + "\n\nbody\n", encoding="utf-8")
    res = _run_lc_c(TITLE_INV, str(subject), cwd=tmp_path)
    assert res.returncode == 1
    diag = [ln for ln in res.stderr.splitlines() if ln.lstrip().startswith("3:##")]
    assert diag, f"the offending heading was not echoed at all: {res.stderr!r}"
    assert len(diag[0]) <= 140, f"the diagnostic is no longer bounded: {len(diag[0])} chars"
    assert tail not in diag[0], "the cut did not happen -- the whole heading was printed"


def test_ac18b_invariant_states_its_behaviour_when_docs_is_absent(tmp_path: Path) -> None:
    """Not an AC of its own, pinned here because a guard that
    silently no-ops is a known failure shape. When this was written `docs/` was gitignored (the count WAS
    0, before p39), so 'absent' was the normal state on every other clone. **That is
    no longer why the branch matters:** `docs/` is tracked now, so an absent `docs/BACKLOG.md`
    means a broken or partial tree rather than a fresh clone — and a guard that says nothing in
    that case is still indistinguishable from one that ran and found nothing, which is the
    property actually being pinned."""
    _need(TITLE_INV, "the title-marker invariant")
    # stdin is fed a git-style ref line on purpose. The guard used to treat a piped stdin as its
    # subject, so this test passed only because pytest replaces stdin — under `-s` with a real
    # pipe it failed, printing the hijack verbatim. The subject must come from the argument or
    # the ledger path, never from fd 0.
    res = subprocess.run(
        ["bash", str(TITLE_INV)], cwd=str(tmp_path), capture_output=True, text=True, check=False,
        input="refs/heads/x sha refs/heads/x sha\n",
    )
    assert "docs/BACKLOG.md" in (res.stdout + res.stderr), (
        "with no docs/ the invariant says nothing at all — silently no-ops"
    )


# --------------------------------------------------------------------------------------
# ROADMAP generator and the /catchup parser
# --------------------------------------------------------------------------------------


ROADMAP_FIXTURE = """### batch map

#### mainline

| PR | batch | what | why | eta |
|---|---|---|---|---|
| **1** ○ | merged one | x | y | [#11](https://example/pull/11) |
| **2** ✅ | closed unmerged | x | y | see [#12](https://example/pull/12) |
| **3** ✅ | a number gh never heard of | x | y | [#99999](https://example/pull/99999) |
| **4** ✅ | no PR number at all | x | y | not filed yet |
| **5** prose first, no glyph | x | y | [#11](https://example/pull/11) |

not a table row at all
"""


def _roadmap_gen(tmp_path: Path, body: str = ROADMAP_FIXTURE) -> tuple[Path, subprocess.CompletedProcess]:
    f = tmp_path / "ROADMAP.md"
    f.write_text(body, encoding="utf-8")
    res = _run(ROADMAP_GEN, str(f), cwd=ROOT)
    return f, res


def test_ac12_merged_only_and_unresolvable_numbers_render_a_question_mark(tmp_path: Path) -> None:
    """AC12's three hard rules, each against a stubbed `gh` answer.

    `#12` is a CLOSED-unmerged PR in the stub's answer, so "MERGED only, not `!= OPEN`" has a
    positive instance, not only a merged one. `#99999` stands for the hand-typed
    number nobody notices is wrong — the row would otherwise be handed the generator's authority
    while showing a glyph nobody derived.
    """
    _need(ROADMAP_GEN, "the ROADMAP status generator")
    stub_dir = tmp_path / "bin"; stub_dir.mkdir(); (stub_dir / "gh").write_text("#!/bin/sh\nprintf '11\\tMERGED\\n12\\tCLOSED\\n'\n", encoding="utf-8"); (stub_dir / "gh").chmod(0o755)
    f = tmp_path / "ROADMAP.md"; f.write_text(ROADMAP_FIXTURE, encoding="utf-8"); res = subprocess.run(["bash", str(ROADMAP_GEN), str(f)], cwd=ROOT, capture_output=True, text=True, check=False, env={**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}"})
    assert res.returncode in (0, 1), f"generator failed outright:\n{res.stdout}{res.stderr}"
    out = f.read_text(encoding="utf-8")

    def glyph(n: int) -> str:
        line = next(l for l in out.splitlines() if l.startswith(f"| **{n}** "))
        return line.split("** ")[1][0]

    assert glyph(1) == "\u2705", "a MERGED PR did not render as shipped"
    assert glyph(2) != "\u2705", "a CLOSED-unmerged PR rendered as shipped (`!= OPEN` logic)"
    assert glyph(3) == "?", "an unresolvable PR number did not render an explicit ?"
    assert glyph(4) == "?", "a row with no PR number did not render an explicit ?"
    assert "| **5** prose first" in out, "a row not starting with a glyph must be left untouched"


def test_ac12b_no_gh_is_a_nonzero_exit_not_a_warning(tmp_path: Path) -> None:
    """"Printed a note but the table still looks normal" is the failure this replaces: a table
    that silently keeps yesterday's glyphs is indistinguishable from a correct one."""
    _need(ROADMAP_GEN, "the ROADMAP status generator")
    f = tmp_path / "ROADMAP.md"
    f.write_text(ROADMAP_FIXTURE, encoding="utf-8")
    before = f.read_bytes()
    res = subprocess.run(
        ["bash", str(ROADMAP_GEN), str(f)],
        cwd=ROOT, capture_output=True, text=True, check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert res.returncode != 0, "a missing gh was tolerated"
    assert f.read_bytes() == before, "the table was rewritten without being able to derive state"


def test_ac12d_an_empty_gh_answer_is_refused_not_treated_as_no_prs(tmp_path: Path) -> None:
    """A surviving mutant named this gap: nothing in the fixture set made `gh` return NOTHING.

    An empty answer is not "no PRs are merged" — it is "the query did not work", and treating the
    two the same rewrites every glyph to `?` while exiting 0, which reads as a confident report
    that the whole batch map is unresolvable. The stub is a real executable on PATH rather than a
    monkeypatch, because the thing under test is a shell script's view of its own environment.
    """
    _need(ROADMAP_GEN, "the ROADMAP status generator")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)

    f = tmp_path / "ROADMAP.md"
    f.write_text(ROADMAP_FIXTURE, encoding="utf-8")
    before = f.read_bytes()

    res = subprocess.run(
        ["bash", str(ROADMAP_GEN), str(f)],
        cwd=ROOT, capture_output=True, text=True, check=False,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
    )
    assert res.returncode != 0, "an empty gh answer was treated as valid state"
    assert f.read_bytes() == before, "the table was rewritten from an empty answer"


def test_ac12c_check_mode_never_writes(tmp_path: Path) -> None:
    """The generator is also the checker, so --check must be provably read-only — otherwise
    running it to ask a question changes the answer."""
    _need(ROADMAP_GEN, "the ROADMAP status generator")
    f = tmp_path / "ROADMAP.md"
    f.write_text(ROADMAP_FIXTURE, encoding="utf-8")
    before = f.read_bytes()
    _run(ROADMAP_GEN, "--check", str(f), cwd=ROOT)
    assert f.read_bytes() == before, "--check modified the file"


def _roadmap_prose_section() -> str:
    """The 🔄 section's PROSE — from the heading down to the first `### ` subsection.

    Scoped deliberately. The batch map lives inside the same section and is *supposed* to carry
    completion words: it is the source of truth. What must not restate progress is the prose
    around it, and that prose is exactly what feeds the card.
    """
    _require_repo_artifact(ROADMAP, "the roadmap")
    lines = ROADMAP.read_text(encoding="utf-8").split("\n")
    s0 = next(i for i, l in enumerate(lines) if l.startswith("## \U0001f504"))
    e0 = next((i for i, l in enumerate(lines) if i > s0 and l.startswith("### ")), len(lines))
    return "\n".join(lines[s0:e0])


_SYNTH_DONE = "✅"    # done glyph
_SYNTH_DOING = "▶"   # doing glyph


def _synthetic_roadmap(*, doing: bool, taint: str = "") -> str:
    """A whole synthetic roadmap, in English, with or without a station in flight.

    Zero rows of the repository's real roadmap take part. Using the live file as the golden oracle
    while repairing a test that reads the live file would be the defect performing its own
    acceptance.

    `taint` plants one token of the completion vocabulary in the `current` prose. It is the
    positive control: no vocabulary token occurs in these fixtures by accident, so without a
    tainted run "no completion claim found" would be true no matter what the detector did.
    """
    rows = [f"| **Station alpha** {_SYNTH_DONE} shipped | did it | light | ~1 session |"]
    rows.append(
        f"| {_SYNTH_DOING} **Station beta** | in flight | light | ~1 session |"
        if doing else
        "| Station beta | not started | light | ~1 session |"
    )
    return "\n".join([
        "# Roadmap",
        "",
        "**Vision** one card whose answers agree",
        f"**Current** next station is Station beta{(' ' + taint) if taint else ''}",
        "",
        "## \U0001f6e3 Mainline",
        "",
        "| Name | What | Weight | ETA |",
        "|---|---|---|---|",
        *rows,
        "",
    ])


def _synthetic_card(root: Path, roadmap_md: str) -> str:
    """Render a whole card over a synthetic tree — no live file, and no monkeypatch either.

    `gather_card_facts` already takes its root and its git runner as arguments, so the fixture
    is supplied by passing them rather than by rebinding a module constant. That removes the
    cross-test-pollution risk instead of mitigating it: a module-level rebind would leak into
    the sibling tests below that read the repository's real roadmap on purpose, and could be green
    in both directions depending on execution order.
    """
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "ROADMAP.md").write_text(roadmap_md, encoding="utf-8")

    def run(args: list[str]) -> str:
        return "main\n" if args[:1] == ["rev-parse"] else ""

    facts = sc.gather_card_facts(root, run, resume_runner=lambda _root: {"found": False})
    return sc.render_facts_text(facts)


def _progress_lines(card: str) -> list[str]:
    """Every card line that says where the work stands: `current:`, `doing:`, and the
    finished-stations block — WHICHEVER of them exist.

    Which ones exist is state, not a precondition. Standing between two stations means there is
    no `doing:` line, and demanding one is what made this assertion fail on a correct tree.
    """
    out, in_done_block = [], False
    for line in card.split("\n"):
        if line.startswith("  current:") or line.startswith("  doing:"):
            out.append(line)
            in_done_block = False
        elif line.startswith("  mainline-done ("):
            out.append(line)
            in_done_block = True
        elif in_done_block and line.startswith("    - "):
            out.append(line)
        else:
            in_done_block = False
    return out


def test_ac13_the_cards_progress_bearing_lines_carry_no_completion_claim(tmp_path) -> None:
    """AC13 + AC6 + AC7 + AC8, in the durable form. **The byte-diff form is deliberately not
    what is asserted here.**

    The AC was written as "compare the card's stdout before and after, the difference must be
    non-empty and confined to `current:` and `doing:`". That is a one-time measurement, not
    something a test can re-run: once the change lands there is no "before" to diff against, so
    rather than reconstruct a number, the
    claim is pinned in the form that survives: **the progress-bearing lines carry no completion
    claim.** That is the property the byte diff was evidence *for*.

    An older form treated "a `doing:` line exists" as an entry
    condition, so the test went red the moment the work stood between two stations — which is the
    correct state, not a fault. Measured both ways on the same code, the verdict flipped with
    whether a row happened to carry a doing glyph that day.
    The verdict has to be the same in both states, so both are run here.
    """
    verdicts = {}
    for state in (True, False):
        root = tmp_path / f"doing-{state}"
        card = _synthetic_card(root, _synthetic_roadmap(doing=state))
        assert card == _synthetic_card(root, _synthetic_roadmap(doing=state)), (
            "the card oracle is not deterministic on one tree"
        )
        lines = _progress_lines(card)
        assert lines, "the card showed no progress-bearing surface at all"
        assert (" doing:" in "".join(lines)) is state, (
            "the doing line must appear exactly when a station is in flight"
        )
        verdicts[state] = sorted({m for l in lines for m in _markers("completion") if m in l})

    assert verdicts[True] == verdicts[False] == [], (
        f"the card's progress-bearing lines still claim progress: {verdicts}"
    )

    # Positive control. Without it this test cannot fail: no vocabulary token occurs in the
    # fixtures by accident, and "found nothing" would be true of a detector that looks at
    # nothing at all.
    token = _markers("completion")[0]
    for state in (True, False):
        tainted = _synthetic_card(
            tmp_path / f"tainted-{state}", _synthetic_roadmap(doing=state, taint=token)
        )
        hits = [m for l in _progress_lines(tainted) for m in _markers("completion") if m in l]
        assert token in hits, "the detector missed a planted completion claim"


def test_ac7_the_finished_stations_surface_cannot_also_claim_a_station_is_in_flight() -> None:
    """AC7's revision — the scan reaches the third progress-bearing surface, `mainline_done`,
    which the old oracle could not see.

    **The revision's literal wording does not survive contact, and that is recorded rather than
    quietly reinterpreted.** It asks for the completion-marker scan to be extended over
    `mainline_done`. Those rows are finished stations: carrying completion wording is what they
    are FOR, so that scan would either be backwards or, on synthetic English fixtures, vacuous.
    What the revision was protecting is that the card's answers must agree — and
    the testable core of it is that no station is simultaneously finished and in flight.

    Structural, so it is a real regression guard rather than a restatement: the bucketing loop
    files each row into exactly one band, and dropping that would trip this.
    """
    md = "\n".join([
        "**Vision** one card whose answers agree",
        "**Current** anything",
        "",
        "## \U0001f6e3 Mainline",
        "",
        "| Name | What | Weight | ETA |",
        "|---|---|---|---|",
        f"| {_SYNTH_DOING} **Station gamma** {_SYNTH_DONE} partly | in flight | light | ~1 day |",
        f"| **Station delta** {_SYNTH_DONE} shipped | did it | light | ~1 day |",
        "",
    ])
    parsed = sc.parse_roadmap(md)
    assert parsed["doing"] and parsed["mainline_done"], "both surfaces must be populated here"
    # Conservation, not set-disjointness. Disjointness alone would be vacuous here: a row filed
    # into both bands lands in `mainline_done` with its doing glyph still on the front, so the
    # two strings differ and the intersection is empty while the row is double-counted. The sum
    # is what actually notices.
    filed = len(parsed["doing"]) + len(parsed["mainline_done"]) + len(parsed["mainline"])
    assert filed == 2, f"each row belongs in exactly one band, got {filed} filings for 2 rows"
    assert not (set(parsed["doing"]) & set(parsed["mainline_done"]))


def test_ac14a_the_in_progress_prose_asserts_no_completion_state() -> None:
    r"""AC14(a) — the 🔄 section's prose, which is what feeds the card's `doing:`.

    Scoped to the prose, not the whole section: the batch map inside it is *supposed* to carry
    completion words. The original fixture was a single line, and that was too narrow — the card
    reads every bold-at-line-start in the section, and stale progress can live in several of them,
    not one. **A detector narrower than its oracle cannot hold the property the oracle exposes.**

    A `#\d+`-only detector would also wave this through: prose can name
    upcoming stations by their PR ordinals and carry no `#`-prefixed number anywhere.
    """
    prose = _roadmap_prose_section()
    hits = [m for m in _markers("completion") if m in prose]
    assert not hits, f"the in-progress prose still restates progress: {hits}"


def test_ac14b_the_you_are_here_paragraph_asserts_no_completion_state() -> None:
    """AC14(b) — the half that actually matters.

    This is the paragraph `/catchup` reads for `current:` (`session_card.parse_roadmap` ->
    `bold_values[1]` -> the head block -> line 6 of the roadmap). Without this
    half, (a) can go green while the card keeps printing a stale next-stop.
    """
    line = _roadmap_section(6)
    hits = [m for m in _markers("completion") if m in line]
    assert not hits, f"the paragraph /catchup reads still restates progress: {hits}"


# --------------------------------------------------------------------------------------
# meta
# --------------------------------------------------------------------------------------


def test_meta_author_local_artifacts_are_all_or_nothing() -> None:
    """The guard on the guard: a skip must mean "fresh clone", never "someone deleted one file".

    An AC that reads a gitignored artifact skips on CI. That is honest only while the skip is
    all-or-nothing: if one artifact went missing on a machine that has the others, those ACs would
    quietly stop running and the board would still read green. A mixed tree fails here instead.

    THIS ROW CANNOT CURRENTLY FIRE, AND SAYING SO IS THE POINT. `AUTHOR_LOCAL` holds a single
    entry; the other artifacts are in `REPO_ARTIFACTS`, which asserts
    presence outright rather than skipping. One entry remains, so `_author_local_mode()` can only
    return "author" or "clone" and never "mixed". The row is kept because a second untracked
    artifact re-arms it the day one is added — but a green here is presently worth nothing, and a
    reader counting it as coverage would be counting an assertion that has no reachable failure.

    That is asserted rather than left in prose: the row below fails if the set ever silently grows
    past one WITHOUT this docstring being revisited, and fails if it shrinks to zero (at which
    point the guard should be deleted, not kept as decoration).
    """
    assert len(AUTHOR_LOCAL) >= 1, (
        "AUTHOR_LOCAL is empty — every artifact is tracked now, so this guard and the skip path "
        "it protects are dead code. Delete them rather than leaving a row that cannot fail."
    )
    if len(AUTHOR_LOCAL) == 1:
        pytest.skip(
            f"structurally unreachable: AUTHOR_LOCAL holds one entry ({sorted(AUTHOR_LOCAL)[0]}), "
            "so a 'mixed' tree is not expressible. Kept for the day a second untracked artifact "
            "is added; a SKIP here is an absence of coverage, never a pass."
        )

    mode = _author_local_mode()
    assert not mode.startswith("mixed"), (
        f"author-local artifacts are partly present ({mode}). Expected either all of "
        f"{sorted(AUTHOR_LOCAL)} (a full working checkout) or none of them (a clone). "
        "Restore the missing one, or the ACs that read it are silently not running."
    )


def test_meta_the_tracked_artifacts_really_are_tracked() -> None:
    """The row that makes the REPO_ARTIFACTS/AUTHOR_LOCAL split evidence rather than a claim.

    The split asserts "these three are in git now". Nothing checked that. If `docs/` were ever
    re-ignored, `_require_repo_artifact` would start hard-failing on every clone with a message
    saying the tree is broken — a true failure with a false reason, one directory move away.
    """
    for what, path in REPO_ARTIFACTS.items():
        rel = path.relative_to(ROOT)
        res = subprocess.run(
            ["/usr/bin/git", "ls-files", "--error-unmatch", "--", str(rel)],
            cwd=str(ROOT), capture_output=True, text=True, check=False,
        )
        assert res.returncode == 0, (
            f"{what} ({rel}) is in REPO_ARTIFACTS but is NOT git-tracked. Either it was untracked "
            f"again — in which case it belongs in AUTHOR_LOCAL and the skip path — or the split "
            f"was wrong from the start."
        )


def test_meta_no_test_name_is_defined_twice() -> None:
    """A duplicate `def test_x` does not collide — the later definition silently replaces the
    earlier one, and pytest reports a clean result for whichever survived.

    This is not hypothetical here. Rewriting AC16 and AC17 against real fixtures left the
    original xfail-marked versions further down the file; Python kept the *old* ones, the new
    ones never executed, and the run reported XFAIL exactly as if nothing were wrong. A green
    board said "as expected" about two tests that did not exist.
    """
    names: dict[str, int] = {}
    for line in Path(__file__).read_text(encoding="utf-8").splitlines():
        if line.startswith("def test_"):
            n = line[4 : line.index("(")]
            names[n] = names.get(n, 0) + 1
    dupes = {n: c for n, c in names.items() if c > 1}
    assert not dupes, f"test names defined more than once (later silently wins): {dupes}"

LIVE_ACS = [
    "ac1", "ac3", "ac4", "ac5", "ac6", "ac7", "ac8", "ac9", "ac10",
    "ac11", "ac12", "ac13", "ac14a", "ac14b", "ac15", "ac16", "ac17", "ac18", "ac19", "ac20",
]


def test_meta_every_live_ac_still_has_at_least_one_test() -> None:
    """A deletion is invisible in a way a duplicate is not, and this file has now suffered both.

    Rewriting AC7/AC8/AC9/AC15 against git fixtures used an end-anchor that landed past AC10, so
    **AC10, AC11 and AC20 were removed along with the block being replaced.** The suite went
    green, the count went up, and nothing said a word — `test_meta_no_test_name_is_defined_twice`
    only catches names that appear twice, never names that stopped appearing.

    So the live AC list is written down here as a literal rather than derived. The reason has
    changed and the decision has not. It used to be that deriving it from the spec was impossible
    on other machines, because `docs/` was untracked until p39 and the spec was absent on
    every other clone; `docs/` is tracked now and that objection is gone. What survives is the
    part that never depended on it: a coverage check that cannot read its own reference silently
    covers nothing — the shape this phase has already had to answer for
    `ac14` is listed as its two halves because they are separate claims: (a) alone can be
    green while the card still prints a stale next-stop.
    """
    src = Path(__file__).read_text(encoding="utf-8")
    missing = [ac for ac in LIVE_ACS if f"def test_{ac}_" not in src]
    assert not missing, f"AC(s) with no test at all — silently deleted?: {missing}"
    assert len(LIVE_ACS) == 20, (
        f"the live-AC list holds {len(LIVE_ACS)} entries; 19 numbered ACs, AC14 counted as its "
        "two halves, AC2 retired"
    )
    assert "ac2" not in LIVE_ACS, "AC2 was retired and must not be resurrected here"
