"""Fixture bench for the session card — its three answers to
"where are we" have to agree with each other.

Seventeen synthetic ROADMAP fixtures (F1-F17). Every one is SYNTHETIC: nothing
here reads the repo's live roadmap file. A test that reads the live file
is not a test: using it as the golden oracle while fixing a defect would
reproduce the very thing under repair.

Each fixture pins one shape; the table below names what each one is for.

Fixture shapes:

    F1  done glyph LEADS the name cell            the form a migrating author types
    F2  done glyph MID name cell                  the common form
    F3  name cell clean, glyph in `what`          cross-cell counter-example
    F4  doing glyph leads the name cell           existing behavior
    F5  doing and done glyph on one row           precedence case
    F6  zero doing rows                           standing between stations
    F7  `current` names a finished row's token    stale `current` prose
    F8  `current` names nothing finished          the agreeing path
    F9  first token is pure letters               the guard's deliberate under-detection
    F10 short-token substring trap                word-bounded search (F16, F17: separator-ended tokens)
    F11 unescaped pipe, done glyph AFTER it       counted as unreadable
    F12 composite multi-id first token            known boundary
    F13 sub-plan glyph, no row-level claim        known boundary
    F14 the table declares FIVE columns           the schema axis
    F15 finished row named without digits         under-detection made visible
"""
from pathlib import Path

import session_card as sc

_DONE = "✅"      # done glyph
_DOING = "▶"     # doing glyph
_ROAD = "\U0001f6e3"  # mainline band
_FILE = "\U0001f5c2"  # backlog band


def _roadmap(rows: list[str], current: str = "no station named here",
             header: str = "| Name | What | Weight | ETA |",
             sep: str = "|---|---|---|---|",
             backlog: list[str] | None = None) -> str:
    """A whole synthetic ROADMAP doc around the mainline rows under test.

    The head carries two bold-value lines because `parse_roadmap` reads vision
    and current POSITIONALLY (first and second bold value), never by label —
    the parser is language-agnostic on purpose and the fixtures must not
    accidentally depend on the words.
    """
    out = [
        "# Roadmap",
        "",
        "**Vision** one card whose three answers agree",
        f"**Current** {current}",
        "",
        f"## {_ROAD} Mainline",
        "",
        header,
        sep,
        *rows,
        "",
        f"## {_FILE} Backlog",
        "",
        "| Name | What | Weight | ETA |",
        "|---|---|---|---|",
        *(backlog or ["| Idea one | someday | light | ~1 session |"]),
        "",
    ]
    return "\n".join(out)


def _names(md: str) -> list[str]:
    """Names the card would render in its Future band."""
    return [m["name"] for m in sc.parse_roadmap(md)["mainline"]]


# --------------------------------------------------------------------------
# F1-F5 - row state: which rows are finished, which are in flight
# --------------------------------------------------------------------------

F1 = _roadmap([
    f"| {_DONE} **Station one** | shipped it | light | ~1 session |",
    "| Station two | not started | medium | ~2 sessions |",
])


def test_f1_a_done_glyph_leading_the_name_cell_keeps_the_row_out_of_future():
    """F1. This is the form a migrating author would type, not the common one.
    The leading-glyph rule alone would miss the common form, so
    both layers are load-bearing, which is why F2 exists as well."""
    # Substring over list membership. Written first as `"Station one" not in
    # _names(F1)`, it passed against the unfixed parser: the rendered name is
    # `<glyph> Station one`, so exact membership was satisfied while the row
    # sat in Future - the assertion going green for the wrong reason, which is
    # the failure this bench exists to make impossible.
    assert not any("Station one" in n for n in _names(F1))
    assert "Station two" in _names(F1)


F2 = _roadmap([
    f"| **Station two** ships the thing {_DONE} closed out "
    "| shipped it | light | ~1 session |",
    "| Station three | not started | medium | ~2 sessions |",
])


def test_f2_a_done_glyph_mid_name_cell_keeps_the_row_out_of_future():
    """F2. This is the common shape: finished rows carry the glyph
    INSIDE the name cell. Without the mid-cell rule every
    one of those rows would render in the Future band."""
    assert "Station three" in _names(F2)
    # substring, not startswith: `_clean_name` can leave an unmatched `**` in
    # front, and a prefix test would then pass while the row sat in Future -
    # an assertion satisfied by the wrong thing.
    assert not any("Station two" in n for n in _names(F2))


F3 = _roadmap([
    f"| Station four | shipped it {_DONE} | light | ~1 session |",
])


def test_f3_a_done_glyph_outside_the_name_cell_does_not_finish_the_row():
    """F3. The counter-example that pins "no cross-cell scan": a glyph in
    `what` says something about the work, not about the row's state.
    Real roadmaps rarely take this shape, which is
    exactly why it needs a fixture rather than a live row."""
    assert _names(F3) == ["Station four"]


F4 = _roadmap([
    f"| {_DOING} **Station five** | in flight | light | ~1 session |",
    "| Station six | not started | medium | ~2 sessions |",
])


def test_f4_a_doing_glyph_leading_the_name_cell_is_the_focal_station():
    """F4. Existing behavior, pinned so it cannot regress."""
    parsed = sc.parse_roadmap(F4)
    assert parsed["doing"] == ["Station five"]
    assert _names(F4) == ["Station six"]


F5 = _roadmap([
    f"| {_DOING} **Station seven** {_DONE} partially closed "
    "| in flight | light | ~1 session |",
])


def test_f5_a_doing_glyph_wins_when_both_glyphs_sit_on_one_row():
    """F5. The precedence has to be decided somewhere,
    and the doing test comes first (a row marked as in flight is in
    flight regardless of what its prose recalls). The row must land in exactly
    one band - not in doing AND in Future, which would be a second focus
    marker."""
    parsed = sc.parse_roadmap(F5)
    assert parsed["doing"] == [f"Station seven {_DONE} partially closed"]
    assert _names(F5) == []


# --------------------------------------------------------------------------
# F6 - zero doing rows is a legal state
# --------------------------------------------------------------------------

F6 = _roadmap([
    f"| **Station eight** {_DONE} closed out | shipped it | light | ~1 session |",
    "| Station nine | not started | medium | ~2 sessions |",
])


def test_f6_zero_doing_rows_parses_as_a_state_not_an_error():
    """F6. Standing between two stations is the correct state, not a
    fault. A parser that errors here passes or fails depending on whether a
    row happens to carry a doing glyph that day - same code, same assertion,
    opposite verdict."""
    parsed = sc.parse_roadmap(F6)
    assert parsed["doing"] == []
    assert all(m["name"] for m in parsed["mainline"]), "no blank focal row"
    assert parsed["unreadable_rows"] == 0


# --------------------------------------------------------------------------
# F7-F12, F15 - cross-reading `current` against the finished rows
# --------------------------------------------------------------------------

F7 = _roadmap(
    [
        f"| **M31 report export** {_DONE} closed out | shipped it | light | ~1 session |",
        "| M58 search page | not started | medium | ~2 sessions |",
    ],
    current="back to the surfaces adopters see - candidates are M58, M31; both light",
)


def test_f7_current_naming_a_finished_row_is_reported():
    """F7. Stale prose, reproduced synthetically: the
    `current` calls M31 a candidate while the M31 row is finished.
    The card has to say so; the two halves are read independently and
    something has to compare them."""
    parsed = sc.parse_roadmap(F7)
    assert parsed["current_conflicts"] == ["M31"]


F8 = _roadmap(
    [
        f"| **M31 report export** {_DONE} closed out | shipped it | light | ~1 session |",
    ],
    current="back to the surfaces adopters see - candidate is M58, which is light",
)


def test_f8_current_naming_nothing_finished_reports_no_conflict():
    """F8. The agreeing path. A cross-read that cannot stay quiet is
    worse than none: a false alarm costs the reader's trust in the whole card,
    which is why under-detection is accepted and this direction is pinned."""
    assert sc.parse_roadmap(F8)["current_conflicts"] == []


F9 = _roadmap(
    [
        f"| **Fix login bug** {_DONE} closed out | shipped it | light | ~1 session |",
    ],
    current="Fix whatever the reviewer flagged next",
)


def test_f9_a_first_token_of_pure_letters_is_left_out_of_the_cross_read():
    """F9. A station called
    `Fix login bug` yields the token `Fix`, and any prose can contain it. The
    guard requires a digit or a separator, so this row does not take part -
    under-detection, on purpose, and F15 pins that the skip is visible."""
    parsed = sc.parse_roadmap(F9)
    assert parsed["current_conflicts"] == []
    assert parsed["crossread_skipped"] == 1


F10 = _roadmap(
    [
        f"| **M7 old station** {_DONE} closed out | shipped it | light | ~1 session |",
        f"| **M26 older station** {_DONE} closed out | shipped it | light | ~1 session |",
    ],
    current="next up is M74, then M261 and M262",
)


def test_f10_a_short_token_does_not_hit_as_a_substring():
    """F10. As plain substrings `M7` and `M26`
    both hit `M74, M261, M262`, and both are correctly rejected once the search
    is word-bounded. Two rows, so a single stray hit cannot pass by accident."""
    assert sc.parse_roadmap(F10)["current_conflicts"] == []


F16 = _roadmap(
    [
        f"| **AUTH- login work** {_DONE} closed out | shipped it | light | ~1 session |",
    ],
    current="next up is AUTH-2, a different station",
)

F17 = _roadmap(
    [
        f"| **1. Setup auth** {_DONE} closed out | shipped it | light | ~1 session |",
    ],
    current="we are on 1. Setup auth right now",
)


def test_f16_a_token_ending_in_a_separator_does_not_hit_a_longer_sibling():
    """F16, for the OTHER half of the token space. The guard admits a token on either a
    digit or a `-_.`, and F10 only covers digits. Written
    as `\\b` - the obvious form - the boundary after a trailing separator is satisfied by the very
    next word character, so `AUTH-` matches inside `AUTH-2`: the defect F10 pins, re-opened for
    the token shape the guard was widened to accept."""
    assert sc.parse_roadmap(F16)["current_conflicts"] == []


def test_f17_a_token_ending_in_a_separator_is_still_found_when_it_is_really_there():
    """F17, the other direction of the same defect. `\\b` after a trailing separator asks for
    a transition that ordinary prose never provides - a period followed by a space is two non-word
    characters - so an ordinal station name like `1. Setup auth` was missed even when the prose
    named it exactly. Both directions are pinned, because a fix for one that breaks the other
    would look correct from either fixture alone."""
    assert sc.parse_roadmap(F17)["current_conflicts"] == ["1."]


F12 = _roadmap(
    [
        f"| **M43+M47 sync state** {_DONE} closed out | shipped it | light | ~1 session |",
    ],
    current="still owe the M43 half of that work",
)

F12_VERBATIM = _roadmap(
    [
        f"| **M43+M47 sync state** {_DONE} closed out | shipped it | light | ~1 session |",
    ],
    current="still owe the M43+M47 work",
)


def test_f12_a_composite_id_token_only_hits_when_current_repeats_it_verbatim():
    """F12, a KNOWN boundary recorded rather than fixed. `M12+M305+M318+
    M19+M36` (21 chars) and `M43+M47` (7 chars) are realistic station names.
    Splitting on separators would fix
    this and would walk `M7`-class tokens straight back into the substring
    trap F10 pins, so the boundary stands and is written down."""
    assert sc.parse_roadmap(F12)["current_conflicts"] == []
    assert sc.parse_roadmap(F12_VERBATIM)["current_conflicts"] == ["M43+M47"]


F15 = _roadmap(
    [
        f"| **MVP** {_DONE} closed out | shipped it | light | ~1 session |",
        f"| **GA** {_DONE} closed out | shipped it | light | ~1 session |",
        f"| **M31 report export** {_DONE} closed out | shipped it | light | ~1 session |",
    ],
    current="MVP is the candidate now",
)


def test_f15_rows_skipped_by_the_token_guard_are_counted_out_loud():
    """F15. The guard is easy to justify with "every one
    of our rows carries a digit" - a property of one repo's numbering,
    not of the ROADMAP format. An adopter naming stations `MVP` / `GA` gets the
    cross-read silently skipped and no way to know: here `current` names MVP,
    MVP is finished, and the conflict is invisible. The guard stays; the
    under-detection becomes a number, 0 included."""
    parsed = sc.parse_roadmap(F15)
    assert parsed["crossread_skipped"] == 2
    assert parsed["current_conflicts"] == []


# --------------------------------------------------------------------------
# F11, F13 - the two shapes that can make the fix reproduce the defect
# --------------------------------------------------------------------------

F11 = _roadmap([
    f"| **M400 fix the `a | b` config** {_DONE} closed out "
    "| shipped it | light | ~1 session |",
])


def test_f11_a_pipe_before_the_done_glyph_counts_as_unreadable_not_as_future():
    """F11, the shape that can leak a finished row back into Future.
    The doing test runs on RAW cells because the doing glyph LEADS the name, so
    a stray pipe cannot hide it. The done glyph sits at the name's END, so the
    same ordering truncates it away and the row falls into Future.
    Do not guess, do not go quiet: the row is counted
    by the honest unreadable counter."""
    parsed = sc.parse_roadmap(F11)
    assert parsed["unreadable_rows"] >= 1
    # Substring for the same reason as F2: the truncated cell keeps its opening
    # `**`, so a prefix test would go green with the row still in Future.
    assert not any("M400" in m["name"] for m in parsed["mainline"])


F13 = _roadmap([
    f"| **M600 rollout** ({_DONE} phase 1 - phase 2 open) "
    "| half shipped | medium | ~2 sessions |",
])


def test_f13_a_sub_plan_glyph_reads_as_finished_which_is_a_recorded_boundary():
    """F13, recorded and NOT fixed. A row that
    carries sub-plan glyphs AND a row-level claim buckets correctly by
    luck. Strip the row-level claim and the mechanism - "the glyph appears
    anywhere in the name cell" - reads a station with work still open as
    finished. Counting glyphs or comparing them against an open-box glyph are
    both heuristics with no clean structural answer, so none is attempted.
    This test states what the shipped mechanism does, not what is right."""
    assert _names(F13) == []
    assert sc.parse_roadmap(F13)["mainline_done"] == [
        f"M600 rollout ({_DONE} phase 1 - phase 2 open)"
    ]


# --------------------------------------------------------------------------
# F14 - the schema axis: characterization, deliberately not a fix
# --------------------------------------------------------------------------

F14 = _roadmap(
    [
        f"| **Station ten** {_DONE} closed out | someone | shipped it | light | ~1 session |",
        "| Station eleven | someone | not started | medium | ~2 sessions |",
    ],
    header="| Name | Owner | What | Weight | ETA |",
    sep="|---|---|---|---|---|",
)


def test_f14_a_five_column_mainline_table_is_wholly_unreadable():
    """F14 - the axis the other fixtures miss. They vary row
    CONTENT; none varies table STRUCTURE. The parser has a cliff there: a
    declared width other than four makes every row unreadable, including rows
    that would split into four. An adopter who adds an Owner column and keeps
    the same status convention gets an empty mainline plus a count, while a
    green matrix says everything is fine. Supporting variable schemas is a new
    capability - Builder work, not Maintainer work - so this records the
    behavior and changes nothing."""
    parsed = sc.parse_roadmap(F14)
    assert parsed["mainline"] == []
    assert parsed["unreadable_rows"] >= 2


# --------------------------------------------------------------------------
# What the card actually prints
# --------------------------------------------------------------------------

def _blob(root, md: str) -> str:
    """The card's rendered facts blob over a synthetic tree.

    Root and git runner are arguments to `gather_card_facts`, so the fixture goes in through the
    front door - nothing is rebound, so nothing can leak into another test.
    """
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "ROADMAP.md").write_text(md, encoding="utf-8")

    def run(args: list[str]) -> str:
        return "main\n" if args[:1] == ["rev-parse"] else ""

    return sc.render_facts_text(
        sc.gather_card_facts(root, run, resume_runner=lambda _r: {"found": False})
    )


def test_the_skipped_count_is_printed_even_when_it_is_zero(tmp_path):
    """The skipped count on the surface a human reads, not just in the parsed dict. The count is printed
    unconditionally because the interesting value is the one an adopter would never think to ask
    for: their stations are named `MVP` and `GA`, every row is skipped, and the cross-read does
    nothing for them. Zero is a value."""
    assert "  crossread-skipped: 0" in _blob(tmp_path / "none", F7)
    assert "  crossread-skipped: 2" in _blob(tmp_path / "two", F15)


F1_CROSSREAD = _roadmap(
    [
        f"| {_DONE} **M31 report export** | shipped it | light | ~1 session |",
    ],
    current="candidates are M58, M31; both light",
)


def test_a_leading_glyph_row_still_takes_part_in_the_cross_read():
    """F1 again, on the cross-read rather than the band. A row in the leading-glyph form makes
    the GLYPH the first token, which carries no digit and no separator - so without stripping it
    the row is filed as skipped and the skipped count reports the extractor's own parse mistake as
    an adopter naming problem."""
    parsed = sc.parse_roadmap(F1_CROSSREAD)
    assert parsed["crossread_skipped"] == 0
    assert parsed["current_conflicts"] == ["M31"]


def test_an_empty_future_band_is_printed_as_a_count_not_as_silence(tmp_path):
    """Before finished rows got their own band, the Future band could not be empty -
    finished rows lived in it - so an absent line meant "no roadmap at all". Now it can be empty
    for a good reason, and an absent line would be indistinguishable from "not computed".
    The count is
    printed at 0 for the same reason the unreadable and skipped counts are."""
    blob = _blob(tmp_path / "empty-future", F6_ALL_DONE)
    assert "  mainline (0):" in blob
    assert "  mainline-done (1):" in blob


F6_ALL_DONE = _roadmap([
    f"| **Station eight** {_DONE} closed out | shipped it | light | ~1 session |",
])

F_DUP = _roadmap(
    [
        f"| **M209 first half** {_DONE} closed out | did it | light | ~1 day |",
        f"| **M209 second half** {_DONE} closed out | did it | light | ~1 day |",
    ],
    current="still owe the M209 work",
)


def test_one_station_named_twice_is_one_observation_not_two():
    """A station can legitimately hold two finished rows - a batch reopened
    for a partial fix - and the card would otherwise
    name it twice inside one sentence. Reported once, however many rows carry it."""
    assert sc.parse_roadmap(F_DUP)["current_conflicts"] == ["M209"]


def test_the_conflict_is_printed_when_current_names_a_finished_station(tmp_path):
    """F7 on the rendered surface. The blob names the token; the wording that makes it an
    OBSERVATION rather than a verdict is the renderer's job and lives in `commands/catchup.md` -
    a retrospective mention trips this legitimately, and a false alarm is only affordable when
    what is reported is "these two look out of step, take a look"."""
    assert "  current-conflicts: M31" in _blob(tmp_path / "hit", F7)
    assert "current-conflicts" not in _blob(tmp_path / "miss", F8)


F_ALL_FINISHED = "\n".join([
    f"## {_ROAD} Mainline",
    "",
    "| Name | What | Weight | Status |",
    "|---|---|---|---|",
    f"| {_DONE} Station one | did it | light | {_DONE} done |",
    "",
])


def test_a_roadmap_whose_stations_are_all_finished_is_still_read_by_the_fisheye_parser():
    """The signal test decides whether the fisheye parse found anything before falling through to
    the older Milestones-table parser, and finished rows now leave `mainline` - so a roadmap whose
    stations are ALL finished has an empty `mainline` and hangs entirely on the new bucket being
    counted as signal.

    This fixture is built so the two parsers DISAGREE: the name cell carries the glyph (fisheye
    reads a finished station) and the last cell leads with one (the fallback reads a milestone
    row). Without that, dropping the bucket is unobservable and the test would pass either way.

    Without this test, dropping `mainline_done` from the signal test leaves every other test
    green - the exact desync that function's own
    docstring was written to warn about."""
    parsed = sc.parse_roadmap(F_ALL_FINISHED)
    assert parsed["mainline_done"] == [f"{_DONE} Station one"]
    assert parsed["done"] == []


# --------------------------------------------------------------------------
# Band isolation and the no-live-file rule
# --------------------------------------------------------------------------

F_BACKLOG = _roadmap(
    ["| Station twelve | not started | medium | ~2 sessions |"],
    backlog=[
        f"| M63 shared helper {_DONE} prerequisite lifted | still open | light | ~1 session |",
        f"| M85 cleanup {_DONE} dropped, not doing | closed | heavy | blocked |",
    ],
)


def test_backlog_band_rows_are_untouched_by_the_row_state_rules():
    """The backlog band uses the done glyph for other things: one
    glyph means "a prerequisite lifted" and the other means "dropped" (the
    legend's own `x`). Nothing derives
    done or future from this band today, so narrowing the scope costs nothing
    and keeps the ambiguity from spreading through this change."""
    parsed = sc.parse_roadmap(F_BACKLOG)
    assert [b["name"] for b in parsed["backlog"]] == [
        f"M63 shared helper {_DONE} prerequisite lifted",
        f"M85 cleanup {_DONE} dropped, not doing",
    ]
    assert parsed["mainline_done"] == []


def test_no_acceptance_path_in_this_file_reads_the_live_roadmap():
    """Every fixture above is a string built in this file. This asserts the
    property directly instead of trusting the reader: the source names no live
    roadmap path. Using the live file
    to accept a fix for a test that reads the
    live file is the defect performing its own acceptance."""
    src = Path(__file__).read_text(encoding="utf-8")
    # Assembled at runtime so this guard's own source does not contain the
    # string it forbids - otherwise the check could only ever fail.
    live = "docs/" + "ROADMAP" + ".md"
    assert live not in src
