"""Tests for scripts/ac-evidence.sh.

The mechanism proves each acceptance criterion HAS an oracle. It never proves the oracle is
correct. These tests hold the parser half first: find the acceptance-criteria section,
parse declarations out of it, and reject everything else loudly.
"""

import json, subprocess, textwrap, pathlib, pytest

SCRIPT = pathlib.Path(__file__).parent / "ac-evidence.sh"


def run(*args, cwd=None):
    return subprocess.run(["/bin/bash", str(SCRIPT), *args],
                          capture_output=True, text=True, cwd=cwd)


def story(tmp_path, body):
    p = tmp_path / "s.md"
    p.write_text(textwrap.dedent(body).lstrip())
    return str(p)


def test_long_form_declarations_are_the_denominator(tmp_path):
    """The denominator comes from the story, not from a list beside it."""
    s = story(tmp_path, """
        ## Acceptance Criteria
        - **p1:AC1**: first.
        - **p1:AC2**: second,
          wrapped onto a second line.
        ## Out of Scope
        - **p1:AC99**: must not count, different section.
    """)
    r = run("parse-criteria", s, "p1")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["p1:AC1", "p1:AC2"]


def test_short_form_with_anchor_is_a_declaration(tmp_path):
    s = story(tmp_path, """
        ## Acceptance Criteria
        - **AC1** {#p1:AC1}: short human label, machine-visible anchor.
    """)
    r = run("parse-criteria", s, "p1")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["p1:AC1"]


def test_lowercase_and_cjk_headings_are_found(tmp_path):
    """Real stories use a lowercase heading or the CJK heading, not only the title-case form."""
    for heading in ("## Acceptance criteria", "## \u9a8c\u6536\u6807\u51c6"):
        s = story(tmp_path, f"""
            {heading}
            - **p1:AC1**: first.
        """)
        r = run("parse-criteria", s, "p1")
        assert r.returncode == 0, (heading, r.stderr)
        assert r.stdout.split() == ["p1:AC1"]


def test_an_earlier_cjk_heading_does_not_capture_the_match(tmp_path):
    """Regression guard for macOS awk's non-ASCII `==`, which returns TRUE for ANY two non-ASCII
    strings: comparing U+6545 U+4E8B with U+9A8C U+6536 U+6807 U+51C6 prints EQUAL. The test above
    CANNOT catch it — its fixture has one heading, so a false positive has nothing to land on. This
    one puts a decoy first, which is the shape a document with several CJK headings has.

    The CJK is written as escapes so this source file stays ASCII; the runtime strings are the
    real characters."""
    decoy, real = "\u6545\u4e8b", "\u9a8c\u6536\u6807\u51c6"
    s = story(tmp_path, f"""
        ## {decoy}
        \u4f5c\u4e3a\u4f7f\u7528\u8005 oracle
        ## {real}
        - **p1:AC1**: first.
    """)
    r = run("parse-criteria", s, "p1")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["p1:AC1"]



def test_missing_section_is_its_own_failure(tmp_path):
    """Not the same case as an empty section, and never a silent zero."""
    s = story(tmp_path, "# A story with no acceptance-criteria section\n")
    r = run("parse-criteria", s, "p1")
    assert r.returncode != 0
    assert "no acceptance-criteria section" in r.stderr


def test_empty_section_is_a_failure_too(tmp_path):
    s = story(tmp_path, "## Acceptance Criteria\n\n## Next\n")
    r = run("parse-criteria", s, "p1")
    assert r.returncode != 0
    assert "no declarations" in r.stderr


def test_bare_id_declaration_fails_loudly_not_silently(tmp_path):
    """The defect this mechanism exists to close, reproduced inside it if this passes."""
    s = story(tmp_path, """
        ## Acceptance Criteria
        - **AC1**: bare label, no anchor.
    """)
    r = run("parse-criteria", s, "p1")
    assert r.returncode != 0
    assert "AC1" in r.stderr


def test_anchor_with_a_foreign_phase_token_fails(tmp_path):
    """Without this it leaks out via the cross-phase-ignore path and vanishes silently."""
    s = story(tmp_path, """
        ## Acceptance Criteria
        - **AC1** {#p2:AC1}: wrong phase in the anchor.
    """)
    r = run("parse-criteria", s, "p1")
    assert r.returncode != 0
    assert "p2" in r.stderr


def test_label_and_anchor_disagree_fails(tmp_path):
    s = story(tmp_path, """
        ## Acceptance Criteria
        - **AC1** {#p1:AC7}: label says 1, anchor says 7.
    """)
    r = run("parse-criteria", s, "p1")
    assert r.returncode != 0


def test_duplicate_id_fails_naming_both(tmp_path):
    s = story(tmp_path, """
        ## Acceptance Criteria
        - **p1:AC1**: once.
        - **AC1** {#p1:AC1}: twice, other form.
    """)
    r = run("parse-criteria", s, "p1")
    assert r.returncode != 0
    assert "duplicate" in r.stderr.lower()


def test_unrecognised_construct_in_the_section_fails(tmp_path):
    """Closed section grammar: a table row or an ### heading is a red, not a silent under-count."""
    s = story(tmp_path, """
        ## Acceptance Criteria
        - **p1:AC1**: fine.
        ### AC2 — written as a heading
    """)
    r = run("parse-criteria", s, "p1")
    assert r.returncode != 0


def test_fenced_and_quoted_lines_are_not_declarations(tmp_path):
    s = story(tmp_path, """
        ## Acceptance Criteria
        > - **p1:AC98**: inside a blockquote.
        ```
        - **p1:AC99**: inside a fence.
        ```
        - **p1:AC1**: the only real one.
    """)
    r = run("parse-criteria", s, "p1")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["p1:AC1"]


def test_subnumbered_and_dash_separator_are_admitted(tmp_path):
    """Both occur in real stories: a sub-numbered id like AC3.1, and the ' — ' separator."""
    s = story(tmp_path, """
        ## Acceptance criteria
        - **p1:AC3.1** — sub-numbered, dash separator.
    """)
    r = run("parse-criteria", s, "p1")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["p1:AC3.1"]



# ---------------------------------------------------------------------------
# the evidence matrix
# ---------------------------------------------------------------------------

_EV_SEQ = [0]


def evidence(tmp_path, obj):
    """Each call gets its OWN file. A shared `ev.json` made two 'different' fixtures the same path:
    the later write won, and the disclaimer test's green case silently read the red evidence."""
    import json
    _EV_SEQ[0] += 1
    p = tmp_path / f"ev{_EV_SEQ[0]}.json"
    p.write_text(json.dumps(obj))
    return str(p)


BASIC_STORY = """
    ## Acceptance Criteria
    - **p1:AC1**: first.
    - **p1:AC2**: second.
"""


def row_for(result, cid):
    """The output line for ONE criterion.

    Assert against this, never against the whole blob. Two ways a whole-blob assertion passes for
    the wrong reason, both measured:

      1. pytest's `tmp_path` is named after the test function, and the scope line prints the story
         path -- so `test_a_cycle_fails_naming_it` asserting "cycle" in the output matched its own
         directory name and passed against a stub that never mentioned cycles.
      2. A neighbouring healthy row satisfies it: asserting "scripts" matched AC1's carrier while
         the claim was about AC2.
    """
    out = result.stdout + result.stderr
    lines = [l for l in out.splitlines() if cid in l and not l.strip().startswith("scope:")]
    return "\n".join(lines)


def _oracle(cid, klass="pin", carrier="scripts/ac-evidence.sh", why="x"):
    return {"id": cid, "status": "oracle", "class": klass, "carrier": carrier, "why": why}


def test_all_mapped_exits_zero_and_prints_one_row_each(tmp_path):
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1", "mutant-killed"),
        _oracle("p1:AC2", "tracked-suite", why="y"),
    ]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode == 0, r.stderr
    assert "p1:AC1" in r.stdout and "mutant-killed" in r.stdout
    assert "p1:AC2" in r.stdout and "tracked-suite" in r.stdout


def test_unmapped_criterion_exits_nonzero_and_names_it_qualified(tmp_path):
    """An unmapped criterion fails the run, and says which one — the whole point."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [_oracle("p1:AC1")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    assert "p1:AC2" in (r.stdout + r.stderr)


def test_output_carries_no_summed_figure_anywhere(tmp_path):
    """No total, no n/m, no percentage, no bare count."""
    import re
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1"), _oracle("p1:AC2", why="y")]})
    r = run("report", s, "p1", "--evidence", e)
    out = r.stdout
    # Anti-vacuity FIRST. Written after this assertion PASSED against a not-implemented stub that
    # printed nothing at all: "the output contains no count" is trivially true of no output, so the
    # oracle reported green on a checker that did not exist. Prove there IS output to judge.
    assert r.returncode == 0, r.stderr
    assert "p1:AC1" in out and "p1:AC2" in out, out
    assert not re.search(r"\d+\s*/\s*\d+", out), out
    assert "%" not in out, out
    # Two things legitimately carry digits and are excluded before the scan, or the assertion could
    # never pass and would be weakened during execution — which is what an earlier revision did
    # when it printed `scope: 16 declared`: (a) criterion ids, (b) the scope line's path.
    body = "\n".join(l for l in out.splitlines() if not l.strip().startswith("scope:"))
    body = re.sub(r"p1:AC[0-9.]+[a-z]?", "", body)
    assert not re.search(r"\b\d+\b", body), body


def test_missing_why_is_malformed_and_fails_closed(tmp_path):
    s = story(tmp_path, BASIC_STORY)
    row = _oracle("p1:AC1"); del row["why"]
    e = evidence(tmp_path, {"phase": "p1", "criteria": [row, _oracle("p1:AC2", why="y")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    assert "malformed" in row_for(r, "p1:AC1")


def test_unknown_status_is_malformed_not_a_third_state(tmp_path):
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        {"id": "p1:AC1", "status": "probably-fine", "why": "x"},
        _oracle("p1:AC2", why="y")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    # A bare non-zero assertion is satisfied by "not implemented" -- measured, it was. Name the
    # criterion and the verdict so only the real mechanism can pass.
    row = row_for(r, "p1:AC1")
    assert "UNMAPPED" in row and "probably-fine" in row, row
    assert "oracle" in row_for(r, "p1:AC2"), "the healthy row must still be printed"


def test_unknown_class_is_malformed(tmp_path):
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1", klass="vibes"), _oracle("p1:AC2", why="y")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    row = row_for(r, "p1:AC1")
    assert "UNMAPPED" in row and "vibes" in row, row


def test_carrier_path_must_exist(tmp_path):
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1", carrier="scripts/nope.sh"), _oracle("p1:AC2", why="y")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    assert "scripts/nope.sh" in (r.stdout + r.stderr)


def test_a_carrier_identifier_is_not_scanned_for_bare_ids(tmp_path):
    """A pytest name cannot contain ':'. Host languages keep their own naming rules."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1", "tracked-suite",
                "scripts/test_ac_evidence.py::test_a_carrier_identifier_is_not_scanned_for_bare_ids"),
        _oracle("p1:AC2", why="y")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode == 0, r.stderr + r.stdout


def test_a_carrier_identifier_that_is_not_in_the_file_fails(tmp_path):
    """Dangling-pointer check, not a quality judgement. Without it, removing a guard cannot change
    any verdict and the guard-removal test is unreachable by construction."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1", "tracked-suite", "scripts/ac-evidence.sh::def_that_was_deleted_long_ago"),
        _oracle("p1:AC2", why="y")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    assert "def_that_was_deleted_long_ago" in (r.stdout + r.stderr)


def test_a_row_for_an_undeclared_id_is_an_orphan_not_an_extra_criterion(tmp_path):
    """An orphan is reported distinctly from 'unmapped criterion'."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1"), _oracle("p1:AC2", why="y"), _oracle("p1:AC9", why="z")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    assert "ORPHAN" in row_for(r, "p1:AC9")


def test_top_level_parse_failure_reports_a_broken_file_once(tmp_path):
    s = story(tmp_path, BASIC_STORY)
    p = tmp_path / "broken.json"; p.write_text("{not json")
    r = run("report", s, "p1", "--evidence", str(p))
    assert r.returncode != 0
    assert "p1:AC1" not in r.stderr   # not "every criterion is unmapped"
    assert "unreadable" in r.stderr or "parse" in r.stderr.lower()


def test_disclaimer_is_printed_on_every_run_green_and_red(tmp_path):
    s = story(tmp_path, BASIC_STORY)
    green = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1"), _oracle("p1:AC2", why="y")]})
    red = evidence(tmp_path, {"phase": "p1", "criteria": []})
    for ev, expect_zero in ((green, True), (red, False)):
        r = run("report", s, "p1", "--evidence", ev)
        assert (r.returncode == 0) is expect_zero
        assert "never proves the oracle is correct" in r.stdout


def test_ids_file_restricts_the_scope(tmp_path):
    """Task mode uses this: a criterion outside the scope cannot fail the run."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [_oracle("p1:AC1")]})
    ids = tmp_path / "ids"; ids.write_text("p1:AC1\n")
    r = run("report", s, "p1", "--evidence", e, "--ids", str(ids))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "p1:AC2" not in r.stdout


# ---------------------------------------------------------------------------
# self-destructing exclusions
#
# Every assertion below names the criterion AND the verdict text. A bare `returncode != 0` is
# satisfied by "not implemented" -- measured: three tests once passed against a stub that way.
# ---------------------------------------------------------------------------

def _excl(cid, etype, cond, why="because"):
    return {"id": cid, "status": "excluded",
            "exclusion": {"type": etype, "condition": cond, "why": why}}


def test_covered_by_oracle_holds_while_the_named_criterion_is_an_oracle(tmp_path):
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1"),
        _excl("p1:AC2", "covered_by_oracle", {"criteria_still_naming": ["p1:AC1"]},
              "p1:AC1's oracle already exercises this"),
    ]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "covered_by_oracle" in r.stdout and "condition holds" in r.stdout


def test_covered_by_oracle_self_destructs_when_the_named_criterion_stops_being_an_oracle(tmp_path):
    """The self-destruct is the whole mechanism."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _excl("p1:AC1", "ci_unreachable_carrier", {"path": "docs"}),
        _excl("p1:AC2", "covered_by_oracle", {"criteria_still_naming": ["p1:AC1"]}),
    ]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    row = row_for(r, "p1:AC2")
    assert "UNMAPPED" in row, row
    assert "no longer" in row and "p1:AC1" in row, \
        f"the row must say the condition stopped holding and name which criterion: {row!r}"


def test_a_cycle_fails_naming_it(tmp_path):
    """A excluded on B, B excluded on A: both conditions hold forever and neither has an oracle."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _excl("p1:AC1", "covered_by_oracle", {"criteria_still_naming": ["p1:AC2"]}),
        _excl("p1:AC2", "covered_by_oracle", {"criteria_still_naming": ["p1:AC1"]}),
    ]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    row = row_for(r, "p1:AC1") + row_for(r, "p1:AC2")
    assert "cycle" in row.lower(), row


def test_malformed_condition_fails_closed_as_unmapped_never_as_excluded(tmp_path):
    """Explicitly against Snyk's precedent of honouring a malformed expiry forever."""
    s = story(tmp_path, BASIC_STORY)
    for bad in ({"criteria_still_naming": []}, {"nonsense": 1}, {}):
        e = evidence(tmp_path, {"phase": "p1", "criteria": [
            _oracle("p1:AC1"),
            _excl("p1:AC2", "covered_by_oracle", bad)]})
        r = run("report", s, "p1", "--evidence", e)
        assert r.returncode != 0, bad
        row = row_for(r, "p1:AC2")
        assert "UNMAPPED" in row and "malformed" in row, (bad, row)
        assert "excluded" not in row, f"{bad}: a malformed condition must never render as excluded"


def test_unknown_exclusion_type_fails_closed_naming_the_type(tmp_path):
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1"), _excl("p1:AC2", "vibes", {})]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    row = row_for(r, "p1:AC2")
    assert "unknown exclusion type" in row and "vibes" in row, row


def test_certified_once_is_specified_but_unbuilt_and_says_exactly_that(tmp_path):
    """Not an unknown type, not silently accepted: unmapped, with the reason. Without this route the
    closed type set has an undefined case inside the very thing that gives 'malformed' a meaning."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1"),
        _excl("p1:AC2", "certified_once",
              {"pins": {"scripts/ac-evidence.sh": "0" * 40}, "record": "journal FACT"})]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    row = row_for(r, "p1:AC2")
    assert "not implemented" in row and "certified_once" in row, row


def _carrier_root_repo(tmp_path, *, ignored=None, tracked=None):
    """A throwaway git repo to evaluate `ci_unreachable_carrier` against.

    `ci_unreachable_carrier`'s condition is "this path is gitignored", and evaluating it needs a path
    that BOTH exists AND is ignored. Pointing it at a gitignored directory of the host repo is green
    only where that directory exists, and red in CI — where a gitignored tree is not merely ignored, it was never
    committed, so it does not exist at all and the check fails closed on "path absent".
    """
    import subprocess as sp
    d = tmp_path / "carrier-root"; d.mkdir()
    def g(*a):
        return sp.run(["/usr/bin/git", *a], cwd=d, check=True, capture_output=True, text=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@example.invalid"); g("config", "user.name", "t")
    (d / ".gitignore").write_text((ignored or "") + "\n")
    if ignored:
        (d / ignored).mkdir(); (d / ignored / "carrier.txt").write_text("the only carrier\n")
    if tracked:
        (d / tracked).mkdir(); (d / tracked / "f.txt").write_text("tracked\n")
    g("add", "-A"); g("commit", "-qm", "base")
    return d


def _report_against(root, tmp_path, rows):
    import os
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": rows})
    env = {**os.environ, "AC_CARRIER_ROOT": str(root)}
    return subprocess.run(["/bin/bash", str(SCRIPT), "report", str(s), "p1", "--evidence", str(e)],
                          capture_output=True, text=True, env=env)


def test_ci_unreachable_carrier_holds_while_the_path_is_gitignored(tmp_path):
    """Environment-independent: the fixture owns both halves of the condition."""
    root = _carrier_root_repo(tmp_path, ignored="ignored-tree")
    r = _report_against(root, tmp_path, [
        _oracle("p1:AC1", carrier=".gitignore", why="the fixture's own tracked file"),
        _excl("p1:AC2", "ci_unreachable_carrier", {"path": "ignored-tree"},
              "the only carrier lives in a gitignored tree")])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ci_unreachable_carrier" in r.stdout and "condition holds" in r.stdout


def test_ci_unreachable_carrier_self_destructs_when_the_path_becomes_tracked(tmp_path):
    root = _carrier_root_repo(tmp_path, ignored="ignored-tree", tracked="tracked-tree")
    r = _report_against(root, tmp_path, [
        _oracle("p1:AC1", carrier=".gitignore", why="the fixture's own tracked file"),
        _excl("p1:AC2", "ci_unreachable_carrier", {"path": "tracked-tree"})])
    assert r.returncode != 0
    row = row_for(r, "p1:AC2")
    assert "no longer" in row and "tracked-tree" in row, row


def test_ci_unreachable_carrier_fails_closed_when_the_path_is_absent(tmp_path):
    """The CI case, now pinned instead of discovered. A gitignored tree is usually not merely
    ignored in CI — it was never committed, so it is ABSENT, and the condition cannot be evaluated
    at all. Fail closed, and say which of the two it was: "unevaluable here" and "no longer
    gitignored" send the reader to opposite repairs."""
    root = _carrier_root_repo(tmp_path, ignored="ignored-tree")
    r = _report_against(root, tmp_path, [
        _oracle("p1:AC1", carrier=".gitignore", why="the fixture's own tracked file"),
        _excl("p1:AC2", "ci_unreachable_carrier", {"path": "not-here-at-all"})])
    assert r.returncode != 0
    row = row_for(r, "p1:AC2")
    assert "unevaluable here" in row, row
    assert "no longer gitignored" not in row, "the absent case must not be reported as a broken condition: " + row


def test_an_exclusion_without_a_why_is_malformed(tmp_path):
    s = story(tmp_path, BASIC_STORY)
    row = _excl("p1:AC2", "covered_by_oracle", {"criteria_still_naming": ["p1:AC1"]})
    del row["exclusion"]["why"]
    e = evidence(tmp_path, {"phase": "p1", "criteria": [_oracle("p1:AC1"), row]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    row = row_for(r, "p1:AC2")
    assert "UNMAPPED" in row and "malformed" in row, row


def test_a_phase_with_zero_exclusions_passes(tmp_path):
    """Story edge case: the empty case must be a pass, not an error."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1"), _oracle("p1:AC2", why="y")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# the asymmetric baseline
# ---------------------------------------------------------------------------

BASE = pathlib.Path(__file__).parent / "ac-baseline.sh"


def bl(*args):
    return subprocess.run(["/bin/bash", str(BASE), *args], capture_output=True, text=True)


def fresh_baseline(tmp_path):
    b = tmp_path / "base.json"
    r = bl("init", "--file", str(b))
    assert r.returncode == 0, r.stderr
    return b


def test_declaration_text_returns_the_whole_declaration_not_just_its_first_line(tmp_path):
    """The digest is over the full declaration. Hashing only the `- **id**:` line would let a
    one-word semantic inversion inside a continuation pass while a pure rewrap reds."""
    s = story(tmp_path, """
        ## Acceptance Criteria
        - **p1:AC1**: first line,
          and a continuation that carries the actual meaning.
        - **p1:AC2**: second.
    """)
    r = run("declaration-text", s, "p1:AC1")
    assert r.returncode == 0, r.stderr
    assert "first line" in r.stdout and "carries the actual meaning" in r.stdout
    assert "second" not in r.stdout, "it must stop at the next declaration"


def test_a_baselined_criterion_does_not_fail_the_gate(tmp_path):
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [_oracle("p1:AC1")]})
    b = fresh_baseline(tmp_path)
    assert bl("add", "p1:AC2", "--why", "legacy", "--file", str(b), "--story", s).returncode == 0
    r = run("report", s, "p1", "--evidence", e, "--baseline", str(b))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "baselined" in row_for(r, "p1:AC2")


def test_a_hand_added_entry_fails_because_the_guard_is_stale(tmp_path):
    """Adding requires an explicit, named action."""
    import json
    b = fresh_baseline(tmp_path)
    obj = json.loads(b.read_text())
    obj["criteria"].append({"id": "p1:AC2", "digest": None, "added": "2026-01-11",
                            "action": "hand-edit", "why": "snuck in"})
    b.write_text(json.dumps(obj))
    r = bl("verify", "--file", str(b))
    assert r.returncode != 0
    assert "p1:AC2" in (r.stdout + r.stderr) and "stale" in (r.stdout + r.stderr).lower()


def test_prune_removes_a_now_mapped_entry_and_prints_the_removal(tmp_path):
    """Automatic removal, and never silent."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1"), _oracle("p1:AC2", why="y")]})
    b = fresh_baseline(tmp_path)
    assert bl("add", "p1:AC2", "--why", "legacy", "--file", str(b), "--story", s).returncode == 0
    r = bl("prune", "--file", str(b), "--evidence", e)
    assert r.returncode == 0, r.stderr
    assert "p1:AC2" in r.stdout and "removed" in r.stdout.lower()
    assert bl("verify", "--file", str(b)).returncode == 0, "prune must leave the guard consistent"
    import json
    assert json.loads(b.read_text())["criteria"] == []


def test_editing_a_baselined_criterions_text_ejects_it(tmp_path):
    """The digest is what makes 'new-or-CHANGED' real, not just 'new'."""
    s = story(tmp_path, BASIC_STORY)
    b = fresh_baseline(tmp_path)
    assert bl("add", "p1:AC2", "--why", "legacy", "--file", str(b), "--story", s).returncode == 0
    s2 = story(tmp_path, BASIC_STORY.replace("second.", "second, and now it means something else."))
    e = evidence(tmp_path, {"phase": "p1", "criteria": [_oracle("p1:AC1")]})
    r = run("report", s2, "p1", "--evidence", e, "--baseline", str(b))
    assert r.returncode != 0
    row = row_for(r, "p1:AC2")
    assert "UNMAPPED" in row and "changed" in row.lower(), row


def test_a_cross_phase_entry_carries_a_null_digest(tmp_path):
    """Its story is unreadable to this checker, so no digest is possible. A bogus one would make the
    entry lose baseline protection on the next run for no reason."""
    import json
    s = story(tmp_path, BASIC_STORY)
    b = fresh_baseline(tmp_path)
    r = bl("add", "p3:AC3", "--why", "another phase", "--file", str(b), "--story", s)
    assert r.returncode == 0, r.stderr
    entry = [c for c in json.loads(b.read_text())["criteria"] if c["id"] == "p3:AC3"][0]
    assert entry["digest"] is None


def test_prune_refuses_to_run_on_a_stale_guard(tmp_path):
    """Order is load-bearing: pruning first would recompute the guard over a set that also holds a
    hand-added entry, laundering it in the same run."""
    import json
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1"), _oracle("p1:AC2", why="y")]})
    b = fresh_baseline(tmp_path)
    obj = json.loads(b.read_text())
    obj["criteria"].append({"id": "p1:AC2", "digest": None, "added": "x",
                            "action": "hand-edit", "why": "snuck in"})
    b.write_text(json.dumps(obj))
    r = bl("prune", "--file", str(b), "--evidence", e)
    assert r.returncode != 0, "prune must refuse on a stale guard, not launder it"
    assert "stale" in (r.stdout + r.stderr).lower()


def test_add_refuses_on_a_stale_guard_too(tmp_path):
    import json
    s = story(tmp_path, BASIC_STORY)
    b = fresh_baseline(tmp_path)
    obj = json.loads(b.read_text())
    obj["criteria"].append({"id": "p1:AC1", "digest": None, "added": "x",
                            "action": "hand-edit", "why": "snuck in"})
    b.write_text(json.dumps(obj))
    r = bl("add", "p1:AC2", "--why", "legacy", "--file", str(b), "--story", s)
    assert r.returncode != 0
    assert "stale" in (r.stdout + r.stderr).lower()


def test_add_requires_a_why(tmp_path):
    b = fresh_baseline(tmp_path)
    r = bl("add", "p1:AC2", "--file", str(b))
    assert r.returncode != 0
    assert "why" in (r.stdout + r.stderr).lower()


def test_the_remaining_baseline_is_printed_on_every_run(tmp_path):
    """Nothing forces the baseline to shrink. Printing it every run is the whole mitigation."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1"), _oracle("p1:AC2", why="y")]})
    b = fresh_baseline(tmp_path)
    assert bl("add", "p3:AC3", "--why", "legacy", "--file", str(b), "--story", s).returncode == 0
    r = run("report", s, "p1", "--evidence", e, "--baseline", str(b))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "baseline:" in r.stdout and "p3:AC3" in r.stdout
    assert "explicit action required" in r.stdout


# ---------------------------------------------------------------------------
# task-mode scope, read from `Closes:` commit trailers
#
# The fixtures are REAL throwaway git repos, not stubs. A stub of an external contract once let
# a probe that could never pass ship green.
# ---------------------------------------------------------------------------

def git_fixture(tmp_path, messages):
    import subprocess as sp
    d = tmp_path / "repo"
    d.mkdir()
    def g(*a):
        return sp.run(["/usr/bin/git", *a], cwd=d, check=True,
                      capture_output=True, text=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@example.invalid")
    g("config", "user.name", "t")
    (d / "f").write_text("0")
    g("add", "f"); g("commit", "-qm", "base")
    g("checkout", "-qb", "feat/phase-x")
    for i, m in enumerate(messages):
        (d / "f").write_text(str(i + 1))
        g("commit", "-qam", m)
    return d


def scope(repo, *extra):
    return subprocess.run(["/bin/bash", str(SCRIPT), "scope-from-trailers", "p1",
                           "--base", "main", *extra],
                          capture_output=True, text=True, cwd=repo)


def test_scope_is_the_union_of_closes_trailers(tmp_path):
    repo = git_fixture(tmp_path, ["task one\n\nCloses: p1:AC4 p1:AC5",
                                  "task two\n\nCloses: p1:AC7"])
    r = scope(repo)
    assert r.returncode == 0, r.stderr
    assert sorted(r.stdout.split()) == ["p1:AC4", "p1:AC5", "p1:AC7"]


def test_no_trailer_yields_an_empty_scope_and_still_exits_zero(tmp_path):
    """A branch's first task legitimately claims nothing until its commit lands. A gate that reds
    there trains --no-verify on day one."""
    repo = git_fixture(tmp_path, ["no trailer here"])
    r = scope(repo)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def _gate_path(tmp_path, message, phase="p1", story_body=None, criteria=None):
    """Run the two steps the CLOSE GATE runs, in the order and with the error handling it uses.

    THIS HELPER IS THE ORACLE, and a test of either step alone is not.
    `scripts/close-gate.sh:1348` invokes the tokeniser as

        ... scope-from-trailers ... > "$AC_IDS" 2>/dev/null || : > "$AC_IDS"

    so a non-zero tokeniser **has its output truncated and its message discarded**. Asserting
    that the tokeniser exits non-zero therefore says nothing about what the gate ends up
    reporting -- which is the entire subject of these tests. The `|| : >` is reproduced here verbatim.
    """
    repo = git_fixture(tmp_path, [message])
    ids = tmp_path / "ids.txt"
    tok = subprocess.run(["/bin/bash", str(SCRIPT), "scope-from-trailers", phase, "--base", "main"],
                         capture_output=True, text=True, cwd=repo)
    # The gate's own error handling: keep stdout on success, truncate on failure.
    ids.write_text(tok.stdout if tok.returncode == 0 else "", encoding="utf-8")
    s_path = story(tmp_path, story_body if story_body is not None else BASIC_STORY)
    e_path = evidence(tmp_path, {"phase": phase, "criteria": criteria if criteria is not None else [
        _oracle(f"{phase}:AC1"), _oracle(f"{phase}:AC2"),
    ]})
    rep = subprocess.run(["/bin/bash", str(SCRIPT), "report", s_path, phase,
                          "--evidence", e_path, "--ids", str(ids)],
                         capture_output=True, text=True)
    return tok, rep, ids


def test_p164_a_comma_separated_trailer_is_malformed_and_the_gate_still_reds(tmp_path):
    """One character decided which of two very different things the gate reported.

    MEASURED (hit while writing a commit). `Closes: p1:AC1, p1:AC2` on one
    line tokenises through `tr ' ' '\\n'`, which splits on spaces and NOT on commas, so
    `p1:AC1,` arrived at the comparison with its comma attached. It matched the old `*:AC*`
    glob -- a CONTAINMENT test -- so it was accepted as a well-formed id, compared against the
    story, matched nothing, and was reported as

        p1:AC1,    ORPHAN    claimed by a `Closes:` trailer, but the current story declares
                               no such criterion

    which is a factual claim about the STORY. The author's own formatting slip was reported as a
    defect in a different file.

    **AND THE OBVIOUS FIX MADE IT WORSE, which is why this test runs the gate's path and not the
    tokeniser alone.** Anchoring the glob in the tokeniser turned its verdict into a `die`, and
    the gate swallows that `die` and truncates the id file -- so the gate went from a RED with
    the wrong message to a GREEN printing *"no criteria claimed by any commit on this branch"*.
    A fix for a wrong message that turns a red into a reassuring green is worse than the message
    it replaces.

    So the assertion is four-sided: the malformed token is NAMED, the verdict is MALFORMED, the
    orphan wording is ABSENT, and the pipeline the gate actually runs still exits non-zero.
    """
    tok, rep, ids = _gate_path(tmp_path, "task\n\nCloses: p1:AC1, p1:AC2")
    assert tok.returncode == 0, f"the tokeniser must pass tokens on, not judge: {tok.stderr}"
    assert "p1:AC1," in ids.read_text(), "the malformed token never reached the id file"

    out = rep.stdout + rep.stderr
    assert rep.returncode != 0, f"the gate's path went GREEN on a malformed trailer: {out!r}"
    assert "MALFORMED" in out, f"not reported as a malformed trailer: {out!r}"
    assert "p1:AC1," in out, f"the offending token is not named: {out!r}"
    assert "no such criterion" not in out, (
        f"still reported as a claim about the story: {out!r}"
    )
    assert "no criteria claimed" not in out, (
        f"the id file was truncated and the run read as an empty claim: {out!r}"
    )


def test_p164_a_well_formed_sibling_in_the_same_trailer_is_still_processed(tmp_path):
    """One bad token must not cost the good ones their rows.

    The `die` it replaces aborted the whole tokenise step, so a single comma erased the scope
    entirely. Here `p1:AC2` is well formed and still gets its oracle row beside the MALFORMED
    one -- which is also what makes the MALFORMED row legible: it sits next to a correct row.
    """
    _tok, rep, _ids = _gate_path(tmp_path, "task\n\nCloses: p1:AC1, p1:AC2")
    assert "p1:AC2" in rep.stdout
    assert "MALFORMED" in rep.stdout


def test_p164_an_issue_reference_keeps_its_own_sentence(tmp_path):
    """`Closes: #32204` is habitual forge idiom and this repo files backlog items under its own ids.

    It must be told apart from a typo -- it is the WRONG KIND of reference, not a malformed id --
    and it must reach the gate rather than dying upstream where the swallow eats it.
    """
    tok, rep, ids = _gate_path(tmp_path, "task\n\nCloses: #32204")
    assert tok.returncode == 0, tok.stderr
    assert "#32204" in ids.read_text(), "the issue reference never reached the id file"
    out = rep.stdout + rep.stderr
    assert rep.returncode != 0, f"an issue reference passed the gate: {out!r}"
    assert "#32204" in out
    assert "issue" in out, f"the reader is not told it is the wrong KIND of reference: {out!r}"
    assert "no criteria claimed" not in out


def test_p164_an_unparseable_value_is_named_rather_than_read_as_an_empty_claim(tmp_path):
    """The property the old `test_an_unparseable_trailer_value_is_rejected` protected, preserved.

    Its words were *"It must error, not silently mean 'this task claims nothing'"* and its
    MECHANISM was the tokeniser's exit code -- which the gate discards. The property is kept and
    now asserted where the gate can see it; the mechanism moved.
    """
    tok, rep, ids = _gate_path(tmp_path, "task\n\nCloses: whatever")
    assert tok.returncode == 0, tok.stderr
    assert "whatever" in ids.read_text()
    out = rep.stdout + rep.stderr
    assert rep.returncode != 0, f"an unparseable value read as an empty claim: {out!r}"
    assert "whatever" in out and "MALFORMED" in out
    assert "no criteria claimed" not in out


def test_p164_the_well_formed_id_grammar_still_passes(tmp_path):
    """The positive control, and it is not decoration: the fix tightens an id test, and the
    cheapest way to tighten one too far is to reject the forms the grammar allows.

    The grammar this repository already uses elsewhere in this same file
    (`[A-Za-z0-9_.-]+:AC[0-9]+(\\.[0-9]+)?[a-z]?`) admits a dotted sub-number and a trailing
    letter, and both occur. A fix that only accepted `bNNN:ACN` would pass the tests above and
    break these.
    """
    repo = git_fixture(tmp_path, ["task\n\nCloses: p1:AC4 p1:AC4.1 p1:AC4a p1:AC10.2b"])
    r = scope(repo)
    assert r.returncode == 0, f"a legal id was rejected: {r.stderr}"
    assert sorted(r.stdout.split()) == ["p1:AC10.2b", "p1:AC4", "p1:AC4.1", "p1:AC4a"]


def test_p164_another_phases_well_formed_id_is_neither_malformed_nor_orphan(tmp_path):
    """A well-formed id belonging to a DIFFERENT phase is not this phase's business.

    The phase filter still exists and still skips silently -- correctly, because that case is not
    an error. What changed is only its POSITION: the grammar check now runs before it, so the
    filter can no longer swallow a token that is not a well-formed id at all.
    """
    _tok, rep, _ids = _gate_path(tmp_path, "task\n\nCloses: p186:AC1 p1:AC1")
    assert rep.returncode == 0, f"another phase's id was treated as an error: {rep.stdout}"
    assert "p186:AC1" not in rep.stdout, "another phase's id should not be reported at all"
    assert "p1:AC1" in rep.stdout


def test_the_merge_base_it_computed_from_is_disclosed(tmp_path):
    """Scope moves silently when the merge-base moves (a rebase, a main-merge-back). The mitigation
    is disclosure, not prevention."""
    repo = git_fixture(tmp_path, ["task\n\nCloses: p1:AC4"])
    r = scope(repo)
    assert r.returncode == 0, r.stderr
    assert "merge-base" in r.stderr


def test_a_missing_origin_head_is_a_named_error_not_a_crash(tmp_path):
    """A --single-branch clone or a fork remote leaves origin/HEAD unset, and this runs inside a
    pre-push hook where the cheapest response to a broken hook is --no-verify."""
    repo = git_fixture(tmp_path, ["task\n\nCloses: p1:AC4"])
    r = subprocess.run(["/bin/bash", str(SCRIPT), "scope-from-trailers", "p1"],
                       capture_output=True, text=True, cwd=repo)
    assert r.returncode != 0
    assert "origin/HEAD" in (r.stdout + r.stderr)
    assert "--base" in (r.stdout + r.stderr), "the message must say how to proceed"


def test_a_criterion_no_commit_claims_cannot_fail_task_mode(tmp_path):
    """The actual guarantee: nothing the branch has not claimed enters scope."""
    import os
    repo = git_fixture(tmp_path, ["task\n\nCloses: p1:AC1"])
    s = story(repo, BASIC_STORY)
    e = evidence(repo, {"phase": "p1", "criteria": [
        _oracle("p1:AC1", carrier="f", why="the fixture's only file")]})
    ids = repo / "ids"; ids.write_text("p1:AC1\n")
    env = {**os.environ, "AC_CARRIER_ROOT": str(repo)}
    r = subprocess.run(["/bin/bash", str(SCRIPT), "report", str(s), "p1",
                        "--evidence", str(e), "--ids", str(ids)],
                       capture_output=True, text=True, cwd=repo, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "p1:AC2" not in r.stdout


def test_task_mode_says_out_loud_that_nothing_was_claimed(tmp_path):
    """The printed row is what stops 'none claimed' from reading like 'no problems'."""
    repo = git_fixture(tmp_path, ["no trailer"])
    s = story(repo, BASIC_STORY)
    e = evidence(repo, {"phase": "p1", "criteria": []})
    ids = repo / "ids"; ids.write_text("")
    r = subprocess.run(["/bin/bash", str(SCRIPT), "report", str(s), "p1",
                        "--evidence", str(e), "--ids", str(ids)],
                       capture_output=True, text=True, cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no criteria claimed by any commit on this branch" in r.stdout


# ---------------------------------------------------------------------------
# reference discipline, over all THREE scanned artifacts
#
# SCOPE NOTE: four kinds of artifact carry criterion links (test name, journal, review finding, evidence
# row). The check covers ONE of them -- the evidence artifacts plus trailers. A green row here does
# not mean a repo's test files are clean; they can still carry bare AC ids.
# ---------------------------------------------------------------------------

def test_a_bare_ac_in_an_evidence_why_fails_naming_the_file(tmp_path):
    """A qualified id buys nothing if the checker also matches the bare form."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1", why="covered together with AC2"),
        _oracle("p1:AC2", why="y")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    # Assert the REFERENCE line itself. `"bare" in out.lower()` passed against a mutant that had
    # deleted the line entirely, because pytest's tmp_path is named after this test function and
    # the scope line prints the story path -- so the word "bare" was being matched inside
    # `test_a_bare_ac_in_an_evidence_why_...`. The trap this file's own row_for() docstring
    # describes, still live in the oracle for the criterion about naming things precisely.
    ref = [l for l in (r.stdout + r.stderr).splitlines() if l.strip().startswith("REFERENCE")]
    assert ref, "no REFERENCE line at all: " + (r.stdout + r.stderr)[:300]
    assert any("bare AC id" in l and "AC2" in l for l in ref), ref


def test_an_orphan_in_a_reference_scan_is_reported_too(tmp_path):
    """There are TWO orphan reporters and only one had an oracle.

    `report()` reports an id a `Closes:` trailer claims but the story does not declare;
    `scan_refs()` separately reports a this-phase id REFERENCED in an artifact that the story does
    not declare. Deleting the second one left every test green, because the
    only orphan test drove the first. Two mechanisms, one assertion."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1", why="see p1:AC77 for the other half"),
        _oracle("p1:AC2", why="y")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode != 0
    orphan = [l for l in (r.stdout + r.stderr).splitlines()
              if "ORPHAN" in l and "p1:AC77" in l]
    assert orphan, "the reference scan dropped an orphan silently: " + (r.stdout + r.stderr)[:300]
    assert "referenced in" in orphan[0], orphan


def test_scope_from_trailers_resolves_the_default_branch_when_no_base_is_given(tmp_path):
    """The trailer reader's other input path. Every other trailer test passes `--base main` explicitly, so the
    fallback -- the line that must resolve origin/HEAD and must NOT be `@{u}` -- was never executed
    by anything. Replacing it with `@{u}` left the whole suite green, which is the
    same defect seen before: on a phase branch `@{u}` is that branch's own
    remote, merge-base(@{u}, HEAD) is HEAD, and the scope comes back empty having checked nothing."""
    repo = git_fixture(tmp_path, ["task one\n\nCloses: p1:AC4"])
    subprocess.run(["git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"],
                   cwd=repo, capture_output=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "main"],
                   cwd=repo, capture_output=True)
    r = subprocess.run(["/bin/bash", str(SCRIPT), "scope-from-trailers", "p1"],
                       capture_output=True, text=True, cwd=repo)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["p1:AC4"], (r.stdout, r.stderr)


def test_a_cross_phase_qualified_reference_is_ignored(tmp_path):
    """A cross-phase qualified reference is real and useful and must never be an orphan of THIS phase."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1", why="the same shape as p5:AC5b"),
        _oracle("p1:AC2", why="y")]})
    r = run("report", s, "p1", "--evidence", e)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_baseline_file_is_scanned_too(tmp_path):
    """It is one of the three artifacts, and its `why` is free prose about criteria."""
    import json
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [
        _oracle("p1:AC1"), _oracle("p1:AC2", why="y")]})
    b = fresh_baseline(tmp_path)
    assert bl("add", "p3:AC3", "--why", "same story as AC1", "--file", str(b),
              "--story", s).returncode == 0
    r = run("report", s, "p1", "--evidence", e, "--baseline", str(b))
    out = r.stdout + r.stderr
    assert r.returncode != 0, out
    assert "bare" in out.lower() and "ac-baseline" in out or "base.json" in out


def test_an_orphan_trailer_is_reported_not_silently_dropped(tmp_path):
    """The `grep -Fxf` intersection that builds task-mode scope drops an id the story does not
    declare. Silently dropping it is the one thing that must be reported distinctly."""
    s = story(tmp_path, BASIC_STORY)
    e = evidence(tmp_path, {"phase": "p1", "criteria": [_oracle("p1:AC1")]})
    ids = tmp_path / "ids"; ids.write_text("p1:AC1\np1:AC99\n")
    r = run("report", s, "p1", "--evidence", e, "--ids", str(ids))
    out = r.stdout + r.stderr
    assert r.returncode != 0
    assert "p1:AC99" in out and "ORPHAN" in out


# ---------------------------------------------------------------------------
# wired into the close gate
# ---------------------------------------------------------------------------

GATE = pathlib.Path(__file__).parent / "close-gate.sh"
REPO = pathlib.Path(__file__).parents[1]


_GATE_CACHE = {}


def gate(mode, *args):
    """Cached per (mode, args). Each uncached call runs the WHOLE close gate -- every invariant, one
    of which walks the tree -- so a handful of them multiply the suite's runtime. A suite nobody wants
    to run is a suite that stops being run; caching keeps every assertion and pays the cost once."""
    key = (mode, args)
    if key not in _GATE_CACHE:
        _GATE_CACHE[key] = subprocess.run(["/bin/bash", str(GATE), mode, *args],
                                          capture_output=True, text=True, cwd=REPO)
    return _GATE_CACHE[key]


def test_the_check_is_in_both_modes_check_sets():
    """Task and phase both run it; the mode split is a design decision, not an option."""
    for mode in ("task", "phase"):
        r = gate(mode, "p1")
        line = [l for l in r.stdout.splitlines() if l.startswith(f"check-set ({mode}): running")]
        assert line, r.stdout[:400]
        assert "ac-oracle-binding" in line[0], (mode, line[0])


def test_phase_mode_checks_the_whole_declared_set_not_just_what_was_claimed(tmp_path):
    """Task mode scopes to trailers, phase mode does not.

    FIXTURE-BASED ON PURPOSE. The first version ran the real gate in both modes and asserted that at
    least one still-unclaimed criterion appeared in phase output and not in task output, on the reasoning
    (written in its own comment) that those criteria "are closed by later tasks". That made the
    oracle a function of how far the phase had got: it was green while criteria were still unclaimed
    and went RED the moment the last task claimed the last one — i.e. it stopped guarding the criterion
    exactly at phase close, which is the only moment phase mode matters. A mutation run exposed it:
    its control run for that criterion was already red before anything was planted.

    A synthetic story plus a synthetic ids file makes the difference between the two scopes a
    property of the mechanism rather than of the branch's progress."""
    s = story(tmp_path, """
        ## Acceptance Criteria
        - **p1:AC1**: claimed by a commit.
        - **p1:AC2**: claimed by nobody — only phase mode may reach this one.
    """)
    ev = tmp_path / "ev.json"
    ev.write_text(json.dumps({"phase": "p1", "criteria": [
        {"id": "p1:AC1", "status": "oracle", "class": "tracked-suite",
         "carrier": "scripts/ac-evidence.sh::report", "why": "fixture row"},
        {"id": "p1:AC2", "status": "oracle", "class": "tracked-suite",
         "carrier": "scripts/ac-evidence.sh::report", "why": "fixture row"},
    ]}))
    ids = tmp_path / "ids"
    ids.write_text("p1:AC1\n")

    task = run("report", s, "p1", "--evidence", str(ev), "--ids", str(ids))
    phase = run("report", s, "p1", "--evidence", str(ev))
    assert task.returncode == 0, task.stdout + task.stderr
    assert phase.returncode == 0, phase.stdout + phase.stderr
    assert row_for(task, "p1:AC1"), "task mode must reach what the trailers claim"
    assert not row_for(task, "p1:AC2"), \
        "task mode reached a criterion no trailer claims — the scopes are not different"
    assert row_for(phase, "p1:AC2"), \
        "phase mode did not reach an unclaimed criterion — it is not checking the declared set"


def test_diff_mode_says_out_loud_that_it_did_not_run():
    """A green with no row is indistinguishable from a green with a passing row."""
    r = gate("diff")
    assert "ac-oracle-binding SKIPPED in diff mode" in r.stdout, r.stdout[-500:]


def test_task_mode_does_not_write_the_baseline():
    """The baseline's other half. A pre-push hook that writes a tracked file leaves the pushed commit
    without the change, the remote stale, and the operator holding a dirty tree."""
    b = REPO / ".claude/ac-baseline.json"
    before = b.read_bytes()
    gate("task", "p1")
    assert b.read_bytes() == before, "task mode mutated the baseline"


# ---------------------------------------------------------------------------
# plan Task 9 — REMOVED in p33. Obituary, not a silent deletion.
# ---------------------------------------------------------------------------
#
# `test_the_envelope_invariant_reaches_the_two_new_gate_scripts` lived here. It planted
# `python3 -c 'pass'` into the REAL `scripts/ac-evidence.sh` and `scripts/ac-baseline.sh`,
# ran the envelope invariant, required a red, and restored the bytes in a `finally`.
#
# WHY IT IS GONE, AND WHY THAT IS SAID RATHER THAN JUST DONE. Its `finally` covers exceptions
# and nothing else -- not SIGKILL, not `pytest -x`, not a timeout, not a closed terminal. An earlier incident
# records the outcome: an interrupted run left `# planted for the self-coverage assertion` in
# BOTH shipped scripts. What caught it was a gate that happens to also scan those two files --
# luck, not a mechanism aimed at cleanup. Deleting a test while leaving no trace makes a
# deliberate removal indistinguishable from an oversight, so this note stays.
#
# WHAT COVERS IT NOW. `scripts/invariants/gate-jq-only-envelope.sh` already carries
# `self_coverage()`, which does the same experiment on a COPY: for every entry in `$DECLARED`
# -- which holds both top-level scripts -- it builds a fixture under `mktemp -d`, plants the
# python invocation into the copy, and requires a red that NAMES the planted file. Strictly
# stronger than what was here: the deleted test matched the filename anywhere in the output,
# the invariant matches its own specific failure string, and it never touches the real tree.
#
# MEASURED, NOT REASONED (p33:AC4). Mutating `scan_set` to silently skip a declared file,
# with this test already gone, in a throwaway clone:
#
#     control (pristine)                 exit=0  green
#     mutant: skip scripts/ac-evidence.sh  exit=1
#         FAIL gate-jq-only-envelope SELF-COVERAGE: a python invocation planted in
#         scripts/ac-evidence.sh did not turn the scan red -- that file is DECLARED but
#         never actually read.
#     mutant: skip scripts/ac-baseline.sh  exit=1  (same shape, names ac-baseline.sh)
#     restored                            exit=0        green
#
# BOTH halves were mutated separately on purpose. Symmetry in the code is not coverage in the
# test, and this repository has paid for that assumption before.


# --- the adopter contract -----------------------------------------------------------
#
# The adopter-contract check is about the SHIPPED document, not about this repository's own gate, so the document is
# the subject under test. The tests below mutate a COPY under `tmp_path`: an earlier shape wrote to
# the tracked file and restored it in a `finally`, which a SIGKILL or a `pytest -x` interrupt would
# have left saying `REMOVED` in the contract every adopter materializes their gate from.

DOC_INV = REPO / "scripts/invariants/close-gate-doc-has-check.sh"
DOC_REL = "skills/project-lifecycle/references/close-gate.md"


def _doc_tree(tmp_path, mutate=None):
    """A throwaway root holding just the document the invariant reads."""
    import shutil
    src = REPO / DOC_REL
    dst = tmp_path / DOC_REL
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    if mutate:
        dst.write_text(mutate(dst.read_text()))
    return str(tmp_path)


def doc_inv(root):
    return subprocess.run(["/bin/bash", str(DOC_INV), root], capture_output=True, text=True)


def test_the_doc_invariant_is_green_on_the_real_document(tmp_path):
    """The control. Both mutation tests below are meaningless without it."""
    r = doc_inv(_doc_tree(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_doc_invariant_reds_when_the_doc_loses_the_check(tmp_path):
    """The invariant must be able to FAIL, or it guards nothing."""
    r = doc_inv(_doc_tree(tmp_path, lambda t: t.replace("ac-oracle-binding", "REMOVED")))
    assert r.returncode != 0
    assert "ac-oracle-binding" in (r.stdout + r.stderr)


def test_the_doc_invariant_reds_when_the_doc_loses_the_disclaimer(tmp_path):
    """The disclaimer criterion is about the DOCUMENTATION, so the document is the subject.

    Asserts the REASON, not just a non-zero exit: written the other way this test passed while the
    invariant did not exist, because "No such file or directory" is also non-zero. That shape has
    recurred more than once."""
    r = doc_inv(_doc_tree(tmp_path,
                          lambda t: t.replace("never proves the oracle is correct", "REMOVED")))
    assert r.returncode != 0
    assert "disclaimer" in (r.stdout + r.stderr).lower()


def _drop_check_from(section_heading, text):
    """Remove the ac-oracle-binding row from ONE checklist only."""
    out, inside = [], False
    for line in text.splitlines(keepends=True):
        if line.startswith("##"):
            inside = ("`%s`" % section_heading) in line
        elif inside and line.startswith("- [ ] `ac-oracle-binding`"):
            continue
        out.append(line)
    return "".join(out)


@pytest.mark.parametrize("mode", ["task-done", "phase-done"])
def test_the_doc_invariant_reds_per_checklist_not_per_document(tmp_path, mode):
    """The global-replace test above cannot tell "reads both checklists" from "greps the
    whole document" -- with the check still present in the OTHER checklist, a document-wide grep is
    green and only a per-section read is red. Both directions, because a parser that mis-bounds the
    sections would red on one and pass on the other."""
    root = _doc_tree(tmp_path, lambda t: _drop_check_from(mode, t))
    doc = pathlib.Path(root) / DOC_REL
    assert "ac-oracle-binding" in doc.read_text(), \
        "control: the check must still be present elsewhere, or this proves nothing"
    r = doc_inv(root)
    assert r.returncode != 0, "a document-wide grep would pass here; the invariant must read sections"
    assert mode in (r.stdout + r.stderr), \
        "it reddened, but did not name the checklist: %s" % (r.stdout + r.stderr)[:300]


# --- the implementation ships too, not just the checklist row ----------------------
#
# Every other
# checklist row in the adopter contract has its implementation in the document's own embedded gate.
# The two ac-oracle-binding rows would otherwise have been the only prose-only ones -- a claim
# wider than its mechanism.

SHIP_INV = REPO / "scripts/invariants/adopter-doc-ships-ac-scripts.sh"


def ship_inv(root):
    return subprocess.run(["/bin/bash", str(SHIP_INV), root], capture_output=True, text=True)


def test_the_shipped_copies_are_byte_identical_to_the_real_scripts():
    """The control -- the mutation tests below are meaningless without it."""
    r = ship_inv(str(REPO))
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("script", ["scripts/ac-evidence.sh", "scripts/ac-baseline.sh"])
def test_the_ship_invariant_reds_when_a_copy_drifts(tmp_path, script):
    """A copy that nothing compares is a copy that drifts. One-line edit, both copies covered
    separately -- a guard that reads only the first is green on a divergence in the second."""
    import shutil
    root = tmp_path / "r"
    shutil.copytree(REPO / "scripts", root / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    doc_dst = root / DOC_REL
    doc_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / DOC_REL, doc_dst)
    assert ship_inv(str(root)).returncode == 0, "control: the fresh tree must be green"

    # Drift the SHIPPED COPY, which is what an editor of the document would do.
    text = doc_dst.read_text()
    anchor = "## AC-oracle binding" if "evidence" in script else "## AC baseline"
    head, _, tail = text.partition(anchor)
    mutated = head + anchor + tail.replace("set -euo pipefail",
                                           "set -euo pipefail  # drifted", 1)
    # A mutant that never landed is not a surviving mutant, and the first version of this test could
    # not tell the two apart: it wrote `set -uo pipefail`, which appears in neither script, so the
    # document was unchanged and the guard was blamed for a green it had earned.
    assert mutated != text, "the mutation did not land -- this test would prove nothing"
    doc_dst.write_text(mutated)
    r = ship_inv(str(root))
    assert r.returncode != 0, "a drifted copy went unnoticed"
    assert script in (r.stdout + r.stderr), \
        "it reddened, but did not name %s: %s" % (script, (r.stdout + r.stderr)[:300])


def test_the_ship_invariant_reds_when_a_section_is_deleted(tmp_path):
    """The real failure mode is not drift, it is the section never being there. A zero-line
    extraction must FAIL -- a parser that finds nothing and passes is the vacuous-pass class."""
    import shutil
    root = tmp_path / "r"
    shutil.copytree(REPO / "scripts", root / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    doc_dst = root / DOC_REL
    doc_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / DOC_REL, doc_dst)
    text = doc_dst.read_text()
    doc_dst.write_text(text.replace("## AC baseline — `scripts/ac-baseline.sh`", "## Something else"))
    r = ship_inv(str(root))
    assert r.returncode != 0
    assert "ZERO lines" in (r.stdout + r.stderr)


def test_the_embedded_gate_still_parses_as_bash():
    """The wiring lives inside a fenced block that nothing executes in CI. `bash -n` is the cheapest
    thing that would have caught a stray `fi` -- and without it the adopter is the one who finds out."""
    doc = (REPO / DOC_REL).read_text().splitlines()
    start = next(i for i, l in enumerate(doc) if l.startswith("## Portable gate script"))
    b = next(i for i in range(start, len(doc)) if doc[i] == "```bash")
    e = next(i for i in range(b + 1, len(doc)) if doc[i] == "```")
    block = "\n".join(doc[b + 1:e])
    p = subprocess.run(["/bin/bash", "-n"], input=block, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr

    # COMMENTS ARE STRIPPED, and the assertion is on the exact CALL LINES. Substring-presence plus a
    # count of two was satisfied by both calls commented out: `bash -n` still parsed, the token was
    # still in the text, and the count still reached two. Measured on a throwaway copy. Use vs
    # mention, in the test that exists to prove the wiring is real.
    code = [l.strip() for l in block.splitlines() if not l.strip().startswith("#")]
    assert "ac_oracle_binding task" in code, \
        "the task-mode block does not CALL ac_oracle_binding (a comment or a mention is not a call)"
    assert "ac_oracle_binding phase" in code, \
        "the phase-mode block does not CALL ac_oracle_binding (a comment or a mention is not a call)"
    assert any(l.startswith("ac_oracle_binding()") for l in code), \
        "the function is called but never defined in the block an adopter copies"


# --- the real regression sample ------------------------------------------

def test_removing_the_guard_reds_the_fixture(tmp_path):
    """PAIRED, both directions — a one-sided assertion is how a mutation tally can
    report kills that prove nothing.

    The guard is the ONLY variable. An earlier shape also deleted the p4:AC10 evidence row, which
    would have produced an identical red with the guard left intact — the test would have measured
    the deletion, not the resolution.

    THE REMOVAL NOW HAPPENS IN A COPY. This test used to rewrite the real, tracked
    `scripts/test_exit_zero_claims.py` and put it back in a `finally`. That covers exceptions and
    not SIGKILL, `pytest -x`, a timeout, or a closed terminal, which is exactly how that incident
    left planted bytes in two shipped scripts. `ac-evidence.sh` already resolves every carrier
    against `AC_CARRIER_ROOT` (three sites) and two other tests in this file already drive it that
    way, so nothing new was built here — this site was simply never routed through the pattern the
    file had already established.

    THE COPY HOLDS EVERY CARRIER, NOT JUST THE ONE UNDER TEST. The evidence fixture names fourteen,
    and the checker requires each one's path AND symbol to resolve. Copying only the guard would
    red the control for the wrong reason and the differential would measure nothing. The list is
    read out of the fixture rather than hard-coded, so a fixture edit cannot silently narrow it."""
    import json
    import os
    import shutil

    root = pathlib.Path(__file__).parents[1]
    crit = root / "scripts/testdata/sample-criteria.md"
    ev = root / "scripts/testdata/sample-evidence.json"

    # Build the carrier root: every carrier the fixture names, at its own relative path.
    carrier_root = tmp_path / "carrier-root"
    rows = json.loads(ev.read_text())["criteria"]
    rels = sorted({c.split("::")[0] for c in (r.get("carrier") or "" for r in rows) if c})
    assert rels, "the fixture names no carriers — the differential below would be vacuous"
    for rel in rels:
        src = root / rel
        assert src.exists(), f"fixture carrier {rel} does not exist in the real tree"
        dst = carrier_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    guard_rel = "scripts/test_exit_zero_claims.py"
    assert guard_rel in rels, "the guard under test is not among the fixture's carriers"
    guard_copy = carrier_root / guard_rel
    real_guard = root / guard_rel
    real_before = real_guard.read_bytes()

    def report():
        env = {**os.environ, "AC_CARRIER_ROOT": str(carrier_root)}
        return subprocess.run(
            ["/bin/bash", str(SCRIPT), "report", str(crit), "p4", "--evidence", str(ev)],
            capture_output=True, text=True, env=env)

    # CONTROL: with the guard present in the copy, the fixture run is green.
    r = report()
    assert r.returncode == 0, ("control failed — the guard is the only variable, so this must be "
                               "green\n" + r.stdout + r.stderr)

    # The mutation, applied to the COPY.
    src_text = guard_copy.read_text()
    name = "test_the_installer_never_claims_what_the_rest_of_the_hook_does"
    begin = src_text.index(f"def {name}")
    rest = src_text[begin + 1:]
    end = begin + 1 + rest.index("\ndef ") if "\ndef " in rest else len(src_text)
    guard_copy.write_text(src_text[:begin] + src_text[end:])
    assert name not in guard_copy.read_text(), "the removal must actually remove the symbol"

    r = report()
    assert r.returncode != 0, ("removing the guard must red the fixture — if this passes, the "
                               "carrier's identifier is not being resolved and this test is vacuous")
    assert "p4:AC10" in (r.stdout + r.stderr)

    # p33:AC5 — the real tracked file was never a participant. Asserted, not assumed: without
    # this line a future edit could quietly reintroduce the write and every other assertion here
    # would still pass.
    assert real_guard.read_bytes() == real_before, \
        "the real tracked guard file changed — this test must operate only on the copy"

def _embedded_gate_block():
    doc = (REPO / DOC_REL).read_text().splitlines()
    start = next(i for i, l in enumerate(doc) if l.startswith("## Portable gate script"))
    b = next(i for i in range(start, len(doc)) if doc[i] == "```bash")
    e = next(i for i in range(b + 1, len(doc)) if doc[i] == "```")
    return "\n".join(doc[b + 1:e])


def _run_adopter_fn(tmp_path, mode, manifest, *, phase="X.Y", extra=""):
    """Run the SHIPPED ac_oracle_binding() under the same `set` options the gate uses."""
    fn_src = _embedded_gate_block()
    start = fn_src.index("ac_oracle_binding() {")
    end = fn_src.index("\nif [ \"$MODE\" = task ]", start)
    fn = fn_src[start:end]

    m = tmp_path / "manifest.json"
    m.write_text(json.dumps(manifest))
    script = f"""
set -euo pipefail
M={json.dumps(str(m))}
PHASE={json.dumps(phase)}
fail=0
ok()  {{ printf '  ✓ %s\\n' "$1"; }}
bad() {{ printf '  ✗ %s\\n' "$1"; fail=1; }}
{extra}
{fn}
ac_oracle_binding {mode}
printf 'REACHED-THE-END fail=%s\\n' "$fail"
"""
    return subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True,
                          cwd=str(tmp_path))


def test_the_adopter_gate_survives_a_successful_phase_run(tmp_path):
    """The CRITICAL. Everything before the banner can be perfect and the adopter still never sees it.

    IT MUST REACH THE FUNCTION'S TAIL. The first version of this test used `exempt_user_story: true`
    because it was the shortest configured path — and that path returns EARLY, so the test passed
    identically with the bug restored. Verified by restoring the original tail and watching it stay
    green. That is the very shape this test exists to close, so
    the full happy path is set up here instead: a story that parses, an evidence stub that exits 0,
    and a manifest pointing at both."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/X.Y-user-story.md").write_text(
        "## Acceptance Criteria\n- **X.Y:AC1**: something.\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/ac-evidence.sh").write_text("#!/bin/bash\nexit 0\n")
    r = _run_adopter_fn(tmp_path, "phase", {
        "user_story_glob": "docs/{PHASE}-user-story*",
        "ac_evidence": ".claude/ac-evidence.json",
    })
    assert "✓ ac-oracle-binding (phase)" in r.stdout, \
        "the happy path was not reached, so this test cannot see the tail:\n" + r.stdout + r.stderr
    assert "REACHED-THE-END" in r.stdout, (
        "the shipped gate died inside ac_oracle_binding — an adopter would see the row and never "
        "the PASS/FAIL banner:\n" + r.stdout + r.stderr)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_adopter_gate_does_not_pass_a_configured_check_with_no_phase(tmp_path):
    """Once a project HAS declared the check, "I could not resolve a criterion set" is a gate that
    checked nothing while reporting a task complete. The shipped copy warned and returned 0 here,
    which made it strictly weaker than the gate it is derived from."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/ac-evidence.sh").write_text("#!/bin/bash\nexit 0\n")
    r = _run_adopter_fn(tmp_path, "task", {"user_story_glob": "docs/*-{PHASE}-*user-story*"},
                        phase="")
    assert "REACHED-THE-END fail=1" in r.stdout, \
        "a configured check with no PHASE did not fail the gate:\n" + r.stdout + r.stderr


def test_the_adopter_gate_prints_a_visible_skip_when_unconfigured(tmp_path):
    """The other direction: a manifest predating the key must not be bricked, and must not get a ✓."""
    r = _run_adopter_fn(tmp_path, "phase", {})
    assert "REACHED-THE-END fail=0" in r.stdout, r.stdout + r.stderr
    assert "⊘ user_story_glob not configured" in r.stdout, r.stdout
    assert "✓ ac-oracle-binding" not in r.stdout, \
        "an unconfigured check printed a check-mark: " + r.stdout


# --- pinning the review fixes -----------------------------------------------------------------
#
# A review round ends when every behaviour change IN IT is covered by an unattended
# oracle. Fixes verified only by hand on throwaway trees, and by
# nothing else, are the same "I checked it once" that a review round exists to replace.


def test_the_doc_invariant_reds_on_a_renamed_row_subject(tmp_path):
    """The checklist row's subject must END at the check name. A prefix match is satisfied by
    `ac-oracle-binding-disabled`, which is what a person turning the check off would most plausibly
    write — reproduced on a throwaway copy, the invariant stayed green with the real row gone."""
    root = _doc_tree(tmp_path, lambda t: t.replace("- [ ] `ac-oracle-binding` —",
                                                   "- [ ] `ac-oracle-binding-disabled` —"))
    doc = pathlib.Path(root) / DOC_REL
    assert "ac-oracle-binding-disabled" in doc.read_text(), "the mutation did not land"
    r = doc_inv(root)
    assert r.returncode != 0, "a renamed row satisfied the check's own guard"
    assert "no row whose subject is" in (r.stdout + r.stderr), (r.stdout + r.stderr)[:300]


def test_the_ship_invariant_refuses_a_duplicate_section(tmp_path):
    """`extract` reads the FIRST matching heading and exits, so an earlier duplicate carrying a
    correct copy hides drift in the later real one. There is no right answer to "which copy is the
    real one", so the guard refuses rather than picking."""
    import shutil
    root = tmp_path / "r"
    shutil.copytree(REPO / "scripts", root / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    doc_dst = root / DOC_REL
    doc_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / DOC_REL, doc_dst)

    head = "## AC baseline — `scripts/ac-baseline.sh`"
    real = (root / "scripts/ac-baseline.sh").read_text()
    t = doc_dst.read_text()
    i = t.index(head)
    dup = head + "\n\n(duplicate)\n\n````bash\n" + real + "````\n\n"
    t = t[:i] + dup + t[i:]
    j = t.rindex(head)                     # drift the LATER, real section
    t = t[:j] + t[j:].replace("set -euo pipefail", "set -euo pipefail  # drifted", 1)
    doc_dst.write_text(t)
    assert t.count(head) == 2, "the duplicate did not land"

    r = ship_inv(str(root))
    assert r.returncode != 0, "an earlier correct duplicate hid drift in the real section"
    assert "appears 2 times" in (r.stdout + r.stderr), (r.stdout + r.stderr)[:300]


def test_a_failing_trailer_scan_is_not_reported_as_an_empty_scope(tmp_path):
    """FAILURE and EMPTY SCOPE are different facts. `2>/dev/null || : > "$ids"` collapsed them, so an
    unset origin/HEAD, an absent merge-base or a malformed `Closes:` trailer all printed "no criteria
    claimed by any commit on this branch" and went green.

    Driven through the SHIPPED function, because that is where the collapse lived."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/X.Y-user-story.md").write_text(
        "## Acceptance Criteria\n- **X.Y:AC1**: something.\n")
    (tmp_path / "scripts").mkdir()
    # A stub that FAILS the way a malformed trailer makes the real one fail.
    (tmp_path / "scripts/ac-evidence.sh").write_text(
        '#!/bin/bash\n'
        'case "${1:-}" in scope-from-trailers) echo "unparseable Closes: value" >&2; exit 1 ;; esac\n'
        'exit 0\n')
    r = _run_adopter_fn(tmp_path, "task", {
        "user_story_glob": "docs/{PHASE}-user-story*",
        "ac_evidence": ".claude/ac-evidence.json",
    }, extra='git() { case "$1" in symbolic-ref) echo main ;; merge-base) echo deadbee ;; esac; }')
    out = r.stdout + r.stderr
    assert "REACHED-THE-END fail=1" in out, \
        "a failing trailer scan did not fail the gate:\n" + out
    assert "could not determine what this branch claims to close" in out, out
    assert "no criteria claimed" not in out, \
        "a FAILURE was reported as an empty scope:\n" + out


def test_the_adopter_manifest_template_configures_the_check_it_ships(tmp_path):
    """An adopter copying the documented manifest verbatim must get a WORKING check, not a ceremony.
    Without `user_story_glob` the row prints `⊘ … not configured` on every run and the gate passes —
    they would have the checklist row, the scripts, and no binding."""
    import re
    text = (REPO / DOC_REL).read_text()
    m = re.search(r"^## Project manifest.*?```json\n(.*?)\n```", text, re.S | re.M)
    assert m, "the manifest template's fence is no longer where this test looks"
    manifest = json.loads(m.group(1))
    for key in ("user_story_glob", "exempt_user_story", "ac_evidence", "ac_heading_set"):
        assert key in manifest, f"the shipped manifest template omits {key}"
    assert manifest["user_story_glob"], "the glob is present but empty — the check would still skip"

    # And prove the template actually drives the check, rather than merely containing the keys.
    r = _run_adopter_fn(tmp_path, "phase", manifest)
    assert "⊘ user_story_glob not configured" not in r.stdout, \
        "the shipped template still leaves the check unconfigured:\n" + r.stdout


