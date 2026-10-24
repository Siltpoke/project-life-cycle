"""Controls for scripts/invariants/step-enforcement-table-current.sh (p31).

These are the carriers for the USER STORY's criteria — the outcomes a reader gets — not for the
design spec's implementation criteria. Both come from one design, so they share one numbering space
and this file's ids continue past the spec's last one (`AC15`) rather than restarting at 1. A second
`p31:AC1` meaning something else is exactly the "an AC number is phase-local but its text is
global" hazard this repository has already filed.

Every row here is paired with a mutant that turns it red. The invariant prints a stable
`FAIL[<slug>]` first token precisely so a mutant can assert WHICH assertion fired: exit 1 is shared
by seven of them, and without the slug a mutant proves only that something failed.

The fixture is a THROWAWAY GIT REPO, not this one. The invariant resolves its own `../..` and
hardcodes every path it reads, so a repo shaped like this one is the only faithful way to feed it a
mutated table.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

# The subject calls bare `git` from PATH, so a harness that can only find it at one absolute path
# is LESS portable than the thing it tests -- it would fail on a host where git lives elsewhere,
# and fail before reaching the awk/grep behaviour these tests exist to exercise. Prefer the absolute
# path when it is there (a shell wrapper on PATH can rewrite git's output), fall back to PATH when
# it is not.
GIT = "/usr/bin/git" if Path("/usr/bin/git").exists() else (shutil.which("git") or "git")

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "invariants" / "step-enforcement-table-current.sh"

SKILL = "skills/project-lifecycle/SKILL.md"
TABLE = "skills/project-lifecycle/references/step-enforcement.md"
LISTED = "skills/project-lifecycle/references/close-gate.md"
FP_LIST = ".claude/step-enforcement-fingerprinted.txt"
LS_LIST = ".claude/step-enforcement-listed.txt"
PIN = ".claude/step-enforcement.sha"

# Bands sum to 7, so the header must never contain a bare 7. Keep it that way when editing.
BAND_A, BAND_B, BAND_C = 2, 3, 2

# Enough distinct receivers that a band can grow without the fixture accidentally tripping the
# "a column of boilerplate says nothing" rule — a fixture that fails for its own reasons proves
# nothing about the subject.
RECEIVERS = ["author", "reviewer", "adopter", "maintainer", "operator", "next phase"]


COLS = "| required step / claim | band | enforcer | actual guarantee | known non-guarantee | risk receiver | source |\n|---|---|---|---|---|---|---|\n"


def _row(step, band, enforcer, guarantee, nonguarantee, receiver, source):
    return f"| {step} | {band} | {enforcer} | {guarantee} | {nonguarantee} | {receiver} | {source} |\n"


def table_text(band_a=BAND_A, band_b=BAND_B, band_c=BAND_C,
               a_rows=None, b_rows=None, c_rows=None,
               header_extra="", drop_boundary=None, fp_paths=None, ls_paths=None,
               drop_band=None) -> str:
    fp_paths = [SKILL] if fp_paths is None else fp_paths
    ls_paths = [LISTED] if ls_paths is None else ls_paths

    boundary_truth = ("**This table does not verify that a row's claim is true.** It records what "
                      "the skill's own text says.\n\n")
    boundary_residual = ("**A gap in a file that is not on either list below is not watched at "
                         "all.**\n\n")
    if drop_boundary == "truth":
        boundary_truth = "**This table records what the skill's own text says.**\n\n"
    if drop_boundary == "residual":
        boundary_residual = "**The lists below are what have to change.**\n\n"

    s = "# Step -> enforcement\n\n"
    s += "Counts are reported per band and never summed.\n\n"
    s += f"- Band A rows: **{band_a}**\n- Band B rows: **{band_b}**\n- Band C rows: **{band_c}**\n\n"
    if header_extra:
        s += header_extra + "\n\n"
    s += "## What this file does not do\n\n" + boundary_truth + boundary_residual
    s += "## Fingerprinted files\n\n" + "".join(f"- `{p}`\n" for p in fp_paths) + "\n"
    s += "## Listed but NOT fingerprinted\n\n" + "".join(f"- `{p}`\n" for p in ls_paths) + "\n"

    if a_rows is None:
        a_rows = [_row(f"unenforced rule {i}", "A", "none", "none",
                       f"skipping it is invisible {i}", "nobody", "`SKILL.md:1`")
                  for i in range(1, band_a + 1)]
    if b_rows is None:
        b_rows = [_row(f"fail-open guard {i}", "B", f"hook-{i}.sh", "fires when armed",
                       f"silent when unarmed {i}", f"the {RECEIVERS[(i - 1) % len(RECEIVERS)]}",
                       "`SKILL.md:1`")
                  for i in range(1, band_b + 1)]
    if c_rows is None:
        c_rows = [_row(f"narrow check {i}", "C", f"check-{i}", "checks the shape",
                       f"not the content {i}", f"the {RECEIVERS[-(i)]}",
                       "`SKILL.md:1`")
                  for i in range(1, band_c + 1)]

    for letter, rows in (("A", a_rows), ("B", b_rows), ("C", c_rows)):
        if drop_band == letter:
            continue
        s += f"## Band {letter} — this band's kind\n\n" + COLS + "".join(rows) + "\n"
    return s


SKILL_PROSE = """# The skill

<!-- plc-p31:begin -->
You must write a user story for a user-observable phase.
<!-- plc-p31:end -->

Which of these rules is actually enforced, and which is held up by nothing? `step-enforcement.md`
maps every required step to what enforces it.

## References

- `references/step-enforcement.md` — the map
"""

SKILL_BULLET_ONLY = """# The skill

<!-- plc-p31:begin -->
You must write a user story for a user-observable phase.
<!-- plc-p31:end -->

## References

- `references/step-enforcement.md` — the map
"""


def _git(root: Path, *args: str) -> str:
    r = subprocess.run([GIT, "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
                       cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, f"git {args}: {r.stdout}{r.stderr}"
    return r.stdout


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def pin_value(root: Path) -> str:
    """Recomputed here, NOT by calling the invariant: a test that derives its expectation from the
    subject agrees with the subject no matter what either one does."""
    parts = []
    for rel in (root / FP_LIST).read_text().split("\n"):
        rel = rel.strip()
        if not rel:
            continue
        parts.append(rel)
        inblk, keep = False, []
        for ln in (root / rel).read_text().split("\n"):
            if ln == "<!-- plc-p31:begin -->":
                inblk = True
                continue
            if ln == "<!-- plc-p31:end -->":
                inblk = False
                continue
            if inblk:
                keep.append(ln)
        parts.extend(keep)
    blob = "\n".join(parts) + "\n"
    return subprocess.run([GIT, "hash-object", "--stdin"], input=blob,
                          capture_output=True, text=True, check=True).stdout.strip()


def build(tmp_path: Path, skill: str = SKILL_PROSE, **table_kwargs) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")

    _write(root, SKILL, skill)
    _write(root, TABLE, table_text(**table_kwargs))
    _write(root, LISTED, "# close-gate\n\nA listed file. Not fingerprinted.\n")
    _write(root, FP_LIST, f"{SKILL}\n")
    _write(root, LS_LIST, f"{LISTED}\n")

    dst = root / "scripts" / "invariants" / GUARD.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GUARD, dst)

    _write(root, PIN, pin_value(root) + "\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "baseline")
    return root


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["/bin/bash", str(root / "scripts" / "invariants" / GUARD.name)],
                          cwd=root, capture_output=True, text=True, env=dict(os.environ))


def _assert_clean(root: Path) -> None:
    r = run(root)
    assert r.returncode == 0, f"fixture is not green before mutating:\n{r.stdout}{r.stderr}"
    assert "PASS" in r.stdout, r.stdout


def _expect(root: Path, code: int, slug: str) -> subprocess.CompletedProcess:
    """The slug must be the FIRST TOKEN of its line, not merely present somewhere.

    Found by a blind cross-family reviewer, who built the input and ran it: with a substring check,
    changing the subject's `printf 'FAIL[%s] %s\n'` to `printf 'BROKEN FAIL[%s] %s\n'` left the
    entire suite green. The invariant's own header states the first-token contract exists precisely
    so a mutation test can assert WHICH assertion fired -- and the suite was not asserting it."""
    r = run(root)
    assert r.returncode == code, f"expected exit {code}, got {r.returncode}\n{r.stdout}{r.stderr}"
    lines = (r.stdout + r.stderr).splitlines()
    assert any(ln.startswith(slug) for ln in lines), (
        f"expected a line whose FIRST token is {slug!r}; got\n{r.stdout}{r.stderr}")
    return r


# --- mutants ---------------------------------------------------------------------------
# (id, apply, expected exit, expected FAIL/CANNOT-RUN slug). Every apply() must provably change
# something on disk before the guard re-runs: a harness that never applied a mutation prints the
# same tally as one that did.

def _m_band_heading_removed(root):
    (root / TABLE).write_text(table_text(drop_band="C"))


def _m_band_declared_but_empty(root):
    (root / TABLE).write_text(table_text(c_rows=[]))


def _m_band_a_receiver_is_not_nobody(root):
    rows = [_row("unenforced rule 1", "A", "none", "none", "invisible", "the author", "`SKILL.md:1`"),
            _row("unenforced rule 2", "A", "none", "none", "invisible", "nobody", "`SKILL.md:1`")]
    (root / TABLE).write_text(table_text(a_rows=rows))


def _m_band_b_receiver_is_nobody(root):
    rows = [_row(f"fail-open guard {i}", "B", f"hook-{i}.sh", "fires when armed",
                 f"silent {i}", "nobody" if i == 1 else f"the {RECEIVERS[(i - 1) % len(RECEIVERS)]}",
                 "`SKILL.md:1`") for i in range(1, BAND_B + 1)]
    (root / TABLE).write_text(table_text(b_rows=rows))


def _m_band_c_receiver_is_nobody(root):
    """Band C has an enforcer, so `nobody` is as wrong there as it is in band B. Without this the
    subject's `for band in B C` can be narrowed to `for band in B` and the whole suite stays green
    -- measured by a blind reviewer, who then built a table with both band-C receivers reading
    `nobody` and watched the narrowed guard exit 0."""
    rows = [_row(f"narrow check {i}", "C", f"check-{i}", "checks the shape",
                 f"not the content {i}", "nobody", "`SKILL.md:1`")
            for i in range(1, BAND_C + 1)]
    (root / TABLE).write_text(table_text(c_rows=rows))


def _m_band_c_receiver_is_boilerplate(root):
    rows = [_row(f"narrow check {i}", "C", f"check-{i}", "checks the shape",
                 f"not the content {i}", "the maintainer", "`SKILL.md:1`")
            for i in range(1, BAND_C + 1)]
    (root / TABLE).write_text(table_text(band_c=BAND_C + 1, c_rows=rows + [
        _row("narrow check 3", "C", "check-3", "checks the shape", "not the content 3",
             "the maintainer", "`SKILL.md:1`")]))


def _m_receiver_column_is_boilerplate(root):
    rows = [_row(f"fail-open guard {i}", "B", f"hook-{i}.sh", "fires when armed",
                 f"silent {i}", "the reviewer", "`SKILL.md:1`") for i in range(1, BAND_B + 1)]
    (root / TABLE).write_text(table_text(b_rows=rows))


def _m_boundary_truth_sentence_removed(root):
    (root / TABLE).write_text(table_text(drop_boundary="truth"))


def _m_boundary_residual_sentence_removed(root):
    (root / TABLE).write_text(table_text(drop_boundary="residual"))


def _m_watched_list_drifts(root):
    (root / LS_LIST).write_text(f"{LISTED}\nskills/project-lifecycle/references/cadence.md\n")


def _m_combined_total_in_header(root):
    (root / TABLE).write_text(table_text(header_extra="There are 7 gaps in total."))


def _m_bracketed_text_edited_without_repinning(root):
    p = root / SKILL
    p.write_text(p.read_text().replace("You must write a user story",
                                       "You may skip the user story"))


def _m_pointer_is_only_a_bullet(root):
    (root / SKILL).write_text(SKILL_BULLET_ONLY)
    (root / PIN).write_text(pin_value(root) + "\n")
    (root / TABLE).write_text(table_text() + "\n<!-- touched in the same diff -->\n")


def _m_pin_file_removed(root):
    (root / PIN).unlink()


def _m_row_count_drifts(root):
    """The HEADER count moves and the rows do not. Bumping both would keep them consistent and
    prove nothing — a mutant that mutates the oracle and the subject together is not a mutant."""
    rows = [_row(f"fail-open guard {i}", "B", f"hook-{i}.sh", "fires when armed",
                 f"silent when unarmed {i}", f"the {RECEIVERS[(i - 1) % len(RECEIVERS)]}",
                 "`SKILL.md:1`") for i in range(1, BAND_B + 1)]
    (root / TABLE).write_text(table_text(band_b=BAND_B + 1, b_rows=rows))


MUTANTS = [
    ("p31:AC16-empty-band", _m_band_declared_but_empty, 1, "FAIL[band-empty]"),
    ("p31:AC16-count-drift", _m_row_count_drifts, 1, "FAIL[band-count-drift]"),
    ("p31:AC17-band-gone", _m_band_heading_removed, 1, "FAIL[band-missing]"),
    ("p31:AC18-a-has-receiver", _m_band_a_receiver_is_not_nobody, 1, "FAIL[receiver-not-band-shaped]"),
    ("p31:AC18-b-has-nobody", _m_band_b_receiver_is_nobody, 1, "FAIL[receiver-not-band-shaped]"),
    ("p31:AC18-boilerplate", _m_receiver_column_is_boilerplate, 1, "FAIL[receiver-not-band-shaped]"),
    ("p31:AC18-c-has-nobody", _m_band_c_receiver_is_nobody, 1, "FAIL[receiver-not-band-shaped]"),
    ("p31:AC18-c-boilerplate", _m_band_c_receiver_is_boilerplate, 1, "FAIL[receiver-not-band-shaped]"),
    ("p31:AC19-truth-sentence", _m_boundary_truth_sentence_removed, 1, "FAIL[boundary-sentence-missing]"),
    ("p31:AC19-residual-sentence", _m_boundary_residual_sentence_removed, 1, "FAIL[boundary-sentence-missing]"),
    ("p31:AC19-list-drift", _m_watched_list_drifts, 1, "FAIL[watched-set-drift]"),
    ("p31:AC20-bullet-only", _m_pointer_is_only_a_bullet, 1, "FAIL[pointer-not-prose]"),
    ("p31:AC21-stale-page", _m_bracketed_text_edited_without_repinning, 1, "FAIL[digest-mismatch]"),
    ("p31:AC21-no-pin", _m_pin_file_removed, 3, "CANNOT-RUN[missing-input]"),
    ("p31:AC22-bare-total", _m_combined_total_in_header, 1, "FAIL[bare-total]"),
]
DECLARED_MUTANTS = 15


def _snapshot(root: Path) -> dict:
    out = {}
    for rel in (SKILL, TABLE, LISTED, FP_LIST, LS_LIST, PIN):
        p = root / rel
        out[rel] = p.read_text() if p.is_file() else "<absent>"
    return out


def _apply_and_check(root: Path, mid, apply, code, slug):
    before = _snapshot(root)
    apply(root)
    assert _snapshot(root) != before, f"{mid}: the mutation changed nothing on disk"
    _expect(root, code, slug)


# --- the user story's criteria ----------------------------------------------------------

def test_every_band_the_page_declares_actually_carries_rows(tmp_path):
    """p31:AC16 — a reader opens one page and sees every requirement mapped to an enforcer. The
    machine-checkable half is that a declared band is not empty and its count is not a wish: an
    empty scope reporting PASS has verified nothing, and a header count nobody compares to the rows
    is a number, not a map."""
    root = build(tmp_path)
    _assert_clean(root)
    _apply_and_check(root, "p31:AC16-empty-band", _m_band_declared_but_empty, 1, "FAIL[band-empty]")

    root2 = build(tmp_path / "second")
    _assert_clean(root2)
    _apply_and_check(root2, "p31:AC16-count-drift", _m_row_count_drifts, 1, "FAIL[band-count-drift]")


def test_the_three_kinds_cannot_collapse_into_fewer(tmp_path):
    """p31:AC17 — "nothing enforces this" / "an enforcer that admits it fails open" / "sound but
    narrower than it reads" must stay three separate things a reader can tell apart. Deleting a
    band's heading is the cheapest way to lose one, and it reds."""
    root = build(tmp_path)
    _assert_clean(root)
    _apply_and_check(root, "p31:AC17-band-gone", _m_band_heading_removed, 1, "FAIL[band-missing]")


def test_the_risk_receiver_says_nobody_rather_than_nothing(tmp_path):
    """p31:AC18 — for a rule with no enforcer the page names who carries the risk, and where the
    answer is nobody it SAYS nobody. Three mutants because the rule has three halves: band A must
    be all `nobody`, bands B and C must contain none, and a column repeating one value is
    boilerplate that says nothing at all."""
    root = build(tmp_path)
    _assert_clean(root)
    _apply_and_check(root, "p31:AC18-a-has-receiver", _m_band_a_receiver_is_not_nobody, 1,
                     "FAIL[receiver-not-band-shaped]")

    root2 = build(tmp_path / "two")
    _assert_clean(root2)
    _apply_and_check(root2, "p31:AC18-b-has-nobody", _m_band_b_receiver_is_nobody, 1,
                     "FAIL[receiver-not-band-shaped]")

    root3 = build(tmp_path / "three")
    _assert_clean(root3)
    _apply_and_check(root3, "p31:AC18-boilerplate", _m_receiver_column_is_boilerplate, 1,
                     "FAIL[receiver-not-band-shaped]")

    # BAND C GETS ITS OWN TWO, and the reason is measured rather than symmetric. With only band-B
    # mutants, the subject's `for band in B C` narrows to `for band in B` and this entire file stays
    # green -- a blind reviewer made that edit, then built a table with both band-C receivers reading
    # `nobody`, and the narrowed guard exited 0 with PASS.
    root4 = build(tmp_path / "four")
    _assert_clean(root4)
    _apply_and_check(root4, "p31:AC18-c-has-nobody", _m_band_c_receiver_is_nobody, 1,
                     "FAIL[receiver-not-band-shaped]")

    root5 = build(tmp_path / "five")
    _assert_clean(root5)
    _apply_and_check(root5, "p31:AC18-c-boilerplate", _m_band_c_receiver_is_boilerplate, 1,
                     "FAIL[receiver-not-band-shaped]")


def test_the_page_states_its_own_limits_and_its_watched_set(tmp_path):
    """p31:AC19 — the page says what it does NOT cover in its own text, and names which files are
    behind the gate versus merely listed.

    The two boundary sentences are mutated SEPARATELY on purpose. A single combined pattern would
    let one sentence's removal pass while the other still matched — the guard would report
    enforcement it was not performing, which is the exact defect class this whole page exists to
    make countable."""
    for i, (mid, apply) in enumerate((("p31:AC19-truth-sentence", _m_boundary_truth_sentence_removed),
                                      ("p31:AC19-residual-sentence", _m_boundary_residual_sentence_removed))):
        root = build(tmp_path / f"b{i}")
        _assert_clean(root)
        _apply_and_check(root, mid, apply, 1, "FAIL[boundary-sentence-missing]")

    root = build(tmp_path / "drift")
    _assert_clean(root)
    _apply_and_check(root, "p31:AC19-list-drift", _m_watched_list_drifts, 1, "FAIL[watched-set-drift]")


def test_the_skill_points_at_the_page_in_prose_not_only_in_a_list(tmp_path):
    """p31:AC20 — a References bullet is not a pointer a reader follows. The mutant keeps the
    bullet and removes only the prose sentence, and it repins and touches the table so the digest
    row cannot be what reds it — otherwise this assertion would pass for the wrong reason."""
    root = build(tmp_path)
    _assert_clean(root)
    _apply_and_check(root, "p31:AC20-bullet-only", _m_pointer_is_only_a_bullet, 1,
                     "FAIL[pointer-not-prose]")


def test_covered_text_that_moves_without_the_page_turns_the_gate_red(tmp_path):
    """p31:AC21 — a green gate means the page has not silently gone stale. THIS IS THE ORACLE FOR
    THE WHOLE PAGE: without it the table is prose that was true once."""
    root = build(tmp_path)
    _assert_clean(root)
    _apply_and_check(root, "p31:AC21-stale-page", _m_bracketed_text_edited_without_repinning, 1,
                     "FAIL[digest-mismatch]")


def test_repinning_and_updating_a_row_is_the_way_back_to_green(tmp_path):
    """p31:AC21, positive control. Without one, the criterion above is satisfiable by a check that
    can never pass, and a guard nobody can satisfy is a guard everybody routes around — which is what
    p32 had to remove from a neighbouring invariant.

    THE RECOVERY PATH IS THE MAINTAINER'S, NOT THE CHEAPEST ONE THE GUARD ACCEPTS. An earlier version
    appended `<!-- touched in the same diff -->` to the table, which passes — the subject's own
    header says a trailing blank line satisfies the same-diff requirement. A blind reviewer pointed
    out that proving the shortcut works is not proving the documented path works. This version adds a
    new requirement to the covered text, adds its ROW to the table, bumps the band count, and repins,
    which is what a person actually does.

    The shortcut is asserted too, immediately below, and labelled as the guard's known blind spot
    rather than as a feature — the distinction only exists if both are written down."""
    root = build(tmp_path)
    _assert_clean(root)

    p = root / SKILL
    p.write_text(p.read_text().replace(
        "You must write a user story for a user-observable phase.",
        "You must write a user story for a user-observable phase.\nYou must also declare what you closed."))
    extra = _row("declare what you closed", "A", "none", "none",
                 "a phase can close naming nothing", "nobody", "`SKILL.md:2`")
    a_rows = [_row(f"unenforced rule {i}", "A", "none", "none",
                   f"skipping it is invisible {i}", "nobody", "`SKILL.md:1`")
              for i in range(1, BAND_A + 1)] + [extra]
    (root / TABLE).write_text(table_text(band_a=BAND_A + 1, a_rows=a_rows))
    (root / PIN).write_text(pin_value(root) + "\n")

    r = run(root)
    assert r.returncode == 0, f"the documented way back to green does not work:\n{r.stdout}{r.stderr}"
    assert "bands 3/3/2" in r.stdout, r.stdout


def test_a_bare_touch_of_the_table_also_passes_and_that_is_the_known_blind_spot(tmp_path):
    """Not a criterion — the guard's own documented limit, asserted so it stays visible. "The table
    was touched" is not "a row was updated", and closing that would mean judging content, which this
    design deliberately does not do. Written down as a test rather than only as a comment, because a
    limit nobody exercises is a limit nobody notices changing."""
    root = build(tmp_path)
    _assert_clean(root)
    p = root / SKILL
    p.write_text(p.read_text().replace("You must write a user story", "You must write a story"))
    (root / PIN).write_text(pin_value(root) + "\n")
    (root / TABLE).write_text(table_text() + "\n<!-- touched, no row updated -->\n")
    r = run(root)
    assert r.returncode == 0, (
        "the blind spot closed without anyone saying so — that is good news, but this test and "
        f"p31:AC21's wording both need updating:\n{r.stdout}{r.stderr}")


def test_the_page_reports_three_counts_and_never_their_sum(tmp_path):
    """p31:AC22 — a reader must not be able to skim one figure and conclude "N problems". The ban
    is on the NUMBER, not the word "total": "7 gaps" in prose walks straight through a word ban."""
    root = build(tmp_path)
    _assert_clean(root)
    _apply_and_check(root, "p31:AC22-bare-total", _m_combined_total_in_header, 1, "FAIL[bare-total]")


# --- companions, not carriers -----------------------------------------------------------

def test_a_missing_input_cannot_run_rather_than_passing_or_failing(tmp_path):
    """Exit 3 never folds into 0 OR into 1. Not a story criterion — the story is about what
    a reader gets — but shipping it unasserted would leave the invariant's own contract unproven."""
    for rel in (PIN, FP_LIST, LS_LIST, TABLE):
        root = build(tmp_path / f"missing-{rel.replace('/', '_')}")
        _assert_clean(root)
        (root / rel).unlink()
        r = run(root)
        assert r.returncode == 3, f"{rel}: expected exit 3, got {r.returncode}\n{r.stdout}{r.stderr}"
        # The SPECIFIC branch, not merely "some could-not-run". A bare `CANNOT-RUN[` prefix is
        # satisfied by a later branch too: delete the up-front existence check and a removed pin
        # still exits 3, via `CANNOT-RUN[pin-empty]` further down. The reviewer ran that edit and
        # the assertion stayed green, so it was proving the wrong thing.
        assert "CANNOT-RUN[missing-input]" in r.stderr, f"{rel}: got\n{r.stdout}{r.stderr}"


def test_an_unreadable_input_cannot_run_rather_than_passing(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root reads anything; the mode bits prove nothing here")
    root = build(tmp_path)
    _assert_clean(root)
    (root / PIN).chmod(0o000)
    try:
        r = run(root)
    finally:
        (root / PIN).chmod(0o644)
    assert r.returncode == 3, f"expected exit 3, got {r.returncode}\n{r.stdout}{r.stderr}"


def test_an_unbalanced_sentinel_is_named_rather_than_silently_skipped(tmp_path):
    """`awk`'s `exit` still runs the END block — a first version printed the verdict twice and every
    structural mutant fell through to the catch-all, reporting CANNOT-RUN instead of the balance
    failure it had actually triggered. All four shapes are asserted so that regression is visible."""
    shapes = {
        "nested": "<!-- plc-p31:begin -->\nx\n<!-- plc-p31:begin -->\ny\n<!-- plc-p31:end -->\n",
        "unopened": "<!-- plc-p31:end -->\nx\n",
        "unclosed": "<!-- plc-p31:begin -->\nx\n",
        "none": "no markers at all\n",
    }
    for name, body in shapes.items():
        root = build(tmp_path / name)
        _assert_clean(root)
        (root / SKILL).write_text(f"# The skill\n\n{body}\nprose naming `step-enforcement.md` here\n")
        r = run(root)
        assert r.returncode == 1, f"{name}: expected exit 1, got {r.returncode}\n{r.stdout}{r.stderr}"
        assert "FAIL[sentinel-balance]" in r.stderr, f"{name}: got\n{r.stdout}{r.stderr}"


def test_every_declared_mutant_actually_ran(tmp_path):
    """Count what executed against what was declared, and assert each mutation changed a file. An
    empty scope reporting PASS has verified nothing, and a mutation harness that never applied a
    mutation prints exactly the same tally as one that did."""
    executed = []
    for i, (mid, apply, code, slug) in enumerate(MUTANTS):
        root = build(tmp_path / f"m{i}")
        _assert_clean(root)
        _apply_and_check(root, mid, apply, code, slug)
        executed.append(mid)
    assert len(executed) == DECLARED_MUTANTS, f"declared {DECLARED_MUTANTS}, ran {len(executed)}: {executed}"
    assert len(set(executed)) == len(executed), f"duplicate mutant ids make a failure unattributable: {executed}"
