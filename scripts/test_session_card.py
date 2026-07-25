from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_card as sc  # noqa: E402


def test_pr_of_trailing_and_inline():
    assert sc.pr_of("docs: auto-maintain ritual (#605)") == 605
    assert sc.pr_of("fix #601 mid-sentence") == 601
    assert sc.pr_of("chore: no-pr-here") is None


def test_is_code_merge():
    assert sc.is_code_merge(["docs/STATUS.md", "RESUME.md"]) is False
    assert sc.is_code_merge(["src/resume/facts.ts"]) is True
    assert sc.is_code_merge(["docs/x.md", "package.json"]) is True
    assert sc.is_code_merge([".githooks/pre-commit"]) is True
    assert sc.is_code_merge(["docs/archive/src/old.md"]) is False
    assert sc.is_code_merge(["scripts/x.sh"]) is True


def test_find_merge_sha():
    log = "abc1234 fix: lockednext (#607)\ndef5678 feat: card (#606)"
    assert sc.find_merge_sha(log, 606) == "def5678"
    assert sc.find_merge_sha(log, 999) is None


def _m(pr: int) -> dict:
    return {"pr": pr, "subject": f"x (#{pr})"}


def test_classify_fresh():
    s = sc.classify_save_state(605, [_m(605), _m(601)], lambda pr: True)
    assert s["tier"] == "fresh"
    assert s["unrecorded"] == []


def test_classify_doc_behind():
    s = sc.classify_save_state(602, [_m(605), _m(604), _m(603), _m(602)], lambda pr: False)
    assert s["tier"] == "doc-behind"
    assert [m["pr"] for m in s["unrecorded"]] == [605, 604, 603]
    assert s["code_count"] == 0


def test_classify_code_behind():
    s = sc.classify_save_state(602, [_m(605), _m(604)], lambda pr: pr == 604)
    assert s["tier"] == "code-behind"
    assert s["code_count"] == 1


def test_classify_unknown_when_no_anchor():
    assert sc.classify_save_state(None, [_m(605)], lambda pr: True)["tier"] == "unknown"


def test_classify_excludes_null_pr_merges():
    merges = [{"pr": None, "subject": "chore: no pr"}, _m(605)]
    s = sc.classify_save_state(602, merges, lambda pr: True)
    assert [m["pr"] for m in s["unrecorded"]] == [605]


def _fake_run(mapping: dict):
    def run(args):
        key = " ".join(args)
        if key not in mapping:
            raise AssertionError(f"unexpected git {key}")
        return mapping[key]
    return run


def test_gather_git_facts():
    run = _fake_run({
        "rev-parse --abbrev-ref HEAD": "main\n",
        "status --porcelain": "",
        "log origin/main --oneline -8 --pretty=%s":
            "docs: ritual (#605)\nperf: memoize (#601)\nchore: no-pr\n",
    })
    f = sc.gather_git_facts(run)
    assert f["branch"] == "main"
    assert f["clean"] is True
    assert f["merges"][0] == {"pr": 605, "subject": "docs: ritual (#605)"}
    assert f["merges"][2] == {"pr": None, "subject": "chore: no-pr"}


def test_gather_git_facts_dirty():
    run = _fake_run({
        "rev-parse --abbrev-ref HEAD": "feat/x\n",
        "status --porcelain": " M scripts/a.py\n",
        "log origin/main --oneline -8 --pretty=%s": "\n",
    })
    assert sc.gather_git_facts(run)["clean"] is False


def test_resume_stacked_shape():
    md = (
        "# RESUME\n\n---\n\n"
        "## ⏳ CURRENT — 2026-07-17 — card work (#608 open)\n"
        "next: reconcile\n#607 merged, #608 open\n\n"
        "## ⏳ CURRENT — 2026-07-16 — older\n#310\n"
    )
    cp = sc.parse_newest_checkpoint(md)
    assert "2026-07-17" in cp["header"]
    assert cp["noted_max_pr"] == 608  # only the newest block scanned
    assert any("reconcile" in l for l in cp["lines"])


def test_resume_plc_single_state_shape():
    md = (
        "# RESUME — X1 invariants · DONE, awaiting merge\n\n"
        "**Branch:** hotfix/x1-cleanup → **PR #611**.\n\n"
        "## State: DONE, human merge pending\n3 commits, close-gate PASS.\n"
    )
    cp = sc.parse_newest_checkpoint(md)
    assert cp["noted_max_pr"] == 611
    assert "X1 invariants" in cp["header"]


def test_resume_absent():
    assert sc.parse_newest_checkpoint("") is None


def test_parse_status_wip_and_locked_next_filters_done_words():
    md = (
        "## 🎯 Now\n"
        "**Track (🔄 catchup card — feat/x)**: active work\n\n"
        "### Locked next\n"
        "1. **moat proof** — do it\n"
        "2. **retention drain SHIPPED** — already done\n"
        "3. **real installer** — pending\n"
        "## Next section\n"
    )
    s = sc.parse_status(md)
    assert s["wip"] == "🔄 catchup card — feat/x"
    assert s["locked_next"] == ["moat proof", "real installer"]  # SHIPPED filtered out


def test_parse_status_closed_track_is_not_wip():
    md = "## 🎯 Now\n**Track (old — CLOSED)**: done\n### Locked next\n## X\n"
    assert sc.parse_status(md)["wip"] == ""


def test_parse_status_empty_when_no_structure():
    s = sc.parse_status("# just a readme\nno ledger here\n")
    assert s == {"wip": "", "locked_next": []}


def test_parse_status_locked_next_survives_mid_body_divider():
    """Regression: a prior fix generalized the roadmap footer-bleed truncation
    into the shared _section() helper, which parse_status also uses. The real
    STATUS.md's "### Locked next" body can contain a mid-content `---` divider
    (a plain visual separator, NOT a footer/EOF marker) with numbered items on
    BOTH sides of it. _section() must return the FULL body — truncating at the
    first `---` silently dropped every item after the divider."""
    md = (
        "## \U0001f3af Now\n"
        "**Track (\U0001f504 some track — feat/x)**: active work\n\n"
        "### Locked next\n"
        "1. **item one** — first\n"
        "2. **item two** — second\n\n"
        "---\n\n"
        "3. **item three** — third\n"
        "4. **item four** — fourth\n"
        "5. **item five** — fifth\n"
        "## Next section\n"
    )
    s = sc.parse_status(md)
    assert s["locked_next"] == [
        "item one", "item two", "item three", "item four", "item five",
    ]


def test_run_resume_locates_sibling_save_session(tmp_path):
    """_run_resume must locate save_session.py as session_card.py's SIBLING (not the
    caller's cwd), and pass cwd=root so save_session derives the right repo."""
    sibling = Path(sc.__file__).resolve().parent / "save_session.py"
    assert sibling.exists()  # save_session.py IS a real sibling in this repo
    result = sc._run_resume(tmp_path)
    assert "found" in result  # shells out for real; only assert the key exists


def test_read_digest_found(tmp_path):
    digest = tmp_path / "d.md"
    digest.write_text(
        "# Session: 2026-07-17\n**Project:** plc  **Branch:** main\n"
        "## Tasks\n- did A\n- did B\n## Files Modified\n- scripts/x.py\n"
        "## Tools Used\nRead, Edit, Bash\n## Stats\n- Total user messages: 4\n"
    )
    fake = lambda root: {"found": True, "path": str(digest), "project": "plc",
                         "stale": False, "stale_days": 0, "cross_project": False}
    d = sc.read_digest(tmp_path, runner=fake)
    assert d["tasks"] == ["did A", "did B"]
    assert d["files"] == ["scripts/x.py"]
    assert d["tools"] == "Read, Edit, Bash"
    assert d["stale"] is False


def test_read_digest_not_found():
    assert sc.read_digest(Path("/x"), runner=lambda root: {"found": False}) is None


def test_read_digest_cross_project_omitted():
    fake = lambda root: {"found": True, "path": "/x", "project": "other",
                         "cross_project": True, "stale": False, "stale_days": 0}
    assert sc.read_digest(Path("/x"), runner=fake) is None


def test_read_digest_stale_flag(tmp_path):
    digest = tmp_path / "d.md"
    digest.write_text("# Session\n## Tasks\n- x\n## Files Modified\n## Tools Used\n\n")
    fake = lambda root: {"found": True, "path": str(digest), "project": "plc",
                         "stale": True, "stale_days": 9, "cross_project": False}
    d = sc.read_digest(tmp_path, runner=fake)
    assert d["stale"] is True and d["stale_days"] == 9


def test_gather_and_render_full(tmp_path, monkeypatch):
    (tmp_path / "RESUME.md").write_text(
        "## ⏳ CURRENT — 2026-07-17 — card (#608 open)\nnext: reconcile\n#607 #608\n"
    )
    (tmp_path / "STATUS.md").write_text(
        "## \U0001f3af Now\n**Track (\U0001f504 card — feat/x)**: go\n### Locked next\n1. **moat** — x\n## z\n"
    )
    run = _fake_run({
        "rev-parse --abbrev-ref HEAD": "feat/x\n",
        "status --porcelain": "",
        "log origin/main --oneline -8 --pretty=%s": "docs: ritual (#609)\n",
    })
    fake_resume = lambda root: {"found": False}  # no digest in this repo
    facts = sc.gather_card_facts(tmp_path, run, resume_runner=fake_resume)
    assert facts["status"]["wip"] == "\U0001f504 card — feat/x"
    assert facts["save_state"]["tier"] == "doc-behind"  # #609 > anchor #608, docs only
    blob = sc.render_facts_text(facts)
    assert "WIP: \U0001f504 card — feat/x" in blob
    assert "SAVE-STATE: doc-behind" in blob
    assert "SOURCES:" in blob  # sources_present map is printed


def test_gather_bare_repo_degrades(tmp_path):
    run = _fake_run({
        "rev-parse --abbrev-ref HEAD": "main\n",
        "status --porcelain": "",
        "log origin/main --oneline -8 --pretty=%s": "\n",
    })
    facts = sc.gather_card_facts(tmp_path, run, resume_runner=lambda root: {"found": False})
    assert facts["status"] == {"wip": "", "locked_next": []}
    assert facts["checkpoint"] is None
    assert facts["save_state"]["tier"] == "unknown"
    assert facts["sources_present"] == {
        "status": False, "resume": False, "digest": False, "roadmap": False,
        "roadmap_unparseable": False,
    }


def test_gather_code_behind_via_files_of_pr(tmp_path):
    """Exercises the real _files_of_pr path end to end (git show success branch),
    not the lambda-stubbed is_code used by the classify_save_state unit tests above."""
    (tmp_path / "RESUME.md").write_text(
        "## ⏳ CURRENT — 2026-07-17 — x (#608)\n#608\n"
    )
    run = _fake_run({
        "rev-parse --abbrev-ref HEAD": "feat/x\n",
        "status --porcelain": "",
        "log origin/main --oneline -8 --pretty=%s": "feat: engine (#610)\n",
        "log origin/main --oneline -40": "abc1234 feat: engine (#610)\n",
        "show --name-only --pretty=format: abc1234": "src/engine.py\n",
    })
    facts = sc.gather_card_facts(tmp_path, run, resume_runner=lambda root: {"found": False})
    assert facts["save_state"]["tier"] == "code-behind"
    assert facts["save_state"]["code_count"] == 1


_ROADMAP_MD = (
    "**Vision**  cross-agent memory\n"
    "**Where**  bug cleanup\n\n"
    "## ✅ Done (big phases)\n"
    "Phase A · Phase B · Phase C\n\n"
    "## \U0001f504 In progress\n"
    "**`fisheye card`** work is ongoing here — this must land before we can "
    "start the later **task two** batch (same files touched twice). "
    "Branch `feat/x`.\n\n"
    "## \U0001f6e3 Mainline\n\n"
    "| Name | What | Weight | ETA |\n"
    "|---|---|---|---|\n"
    "| **Brain** | do brains | \U0001f7e1 medium | ~1 session |\n"
    "| Router | route stuff | \U0001f7e2 light | ~2 days |\n\n"
    "## \U0001f5c2 backlog\n"
    "idea one · idea two\n"
)


def test_parse_roadmap_extracts_vision_and_current():
    r = sc.parse_roadmap(_ROADMAP_MD)
    assert r["vision"] == "cross-agent memory"
    assert r["current"] == "bug cleanup"


def test_parse_roadmap_done_dotlist():
    r = sc.parse_roadmap(_ROADMAP_MD)
    assert r["done"] == ["Phase A", "Phase B", "Phase C"]


def test_parse_roadmap_doing_bold_names_strip_backticks():
    r = sc.parse_roadmap(_ROADMAP_MD)
    # Only the LEADING bold on the line is a real item; "task two" is a
    # mid-sentence forward-reference, not a second doing item (see the
    # dedicated regression test below).
    assert r["doing"] == ["fisheye card"]


def test_parse_roadmap_doing_falls_back_to_dotlist():
    md = "## \U0001f504 In progress\nworking dotlist · item two\n"
    assert sc.parse_roadmap(md)["doing"] == ["working dotlist", "item two"]


def test_parse_roadmap_reads_mainline_table_rows():
    rows = sc.parse_roadmap(_ROADMAP_MD)["mainline"]
    assert rows[0] == {"name": "Brain", "what": "do brains", "weight": "\U0001f7e1 medium", "eta": "~1 session"}
    assert rows[1] == {"name": "Router", "what": "route stuff", "weight": "\U0001f7e2 light", "eta": "~2 days"}


def test_parse_roadmap_backlog_dotlist():
    r = sc.parse_roadmap(_ROADMAP_MD)
    assert r["backlog"] == [
        {"name": "idea one", "what": "", "weight": "", "eta": ""},
        {"name": "idea two", "what": "", "weight": "", "eta": ""},
    ]


def test_parse_roadmap_vision_current_skip_blockquote_intro():
    """Regression: the real ROADMAP.md's head has an intro blockquote whose
    bold markers (`> **What this is**`, `> **Not**`, `> **Living doc**`) come
    BEFORE the real vision/current lines. Those lines start with ">", never
    "**" at column 0, so they must never be mistaken for the real values."""
    md = (
        "# Title\n\n"
        "> **What this is** — the strategic main-line, prevents scope drift.\n"
        ">\n"
        "> **Not** the operational ledger — that lives elsewhere.\n"
        ">\n"
        "> **Living doc** — items move done to doing to todo over time.\n\n"
        "**Vision**  cross-agent memory layer\n"
        "**Where**  bug cleanup station\n\n"
        "---\n\n"
        "## ✅ Done\n"
        "Phase A\n"
    )
    r = sc.parse_roadmap(md)
    assert r["vision"] == "cross-agent memory layer"
    assert r["current"] == "bug cleanup station"


def test_parse_roadmap_doing_ignores_mid_sentence_bold():
    """Regression: a doing paragraph with a mid-sentence bold forward-reference
    to a later item must NOT fabricate a second doing entry."""
    md = (
        "## \U0001f504 In progress\n"
        "**`plugin rework`** — swap the install method, then start the later "
        "**retention drain** work (touches the same files twice).\n\n"
    )
    assert sc.parse_roadmap(md)["doing"] == ["plugin rework"]


def test_parse_roadmap_backlog_no_footer_bleed():
    """Regression: backlog is often the file's LAST section, so `_section`
    used to read to EOF and swallow the trailing `---` rule + italic footer
    into the last dotlist item."""
    md = (
        "## \U0001f5c2 backlog\n"
        "idea one · idea two\n\n"
        "---\n\n"
        "*Maintenance: update this file when a big item moves state.*\n"
    )
    r = sc.parse_roadmap(md)
    assert r["backlog"] == [
        {"name": "idea one", "what": "", "weight": "", "eta": ""},
        {"name": "idea two", "what": "", "weight": "", "eta": ""},
    ]
    assert not any("Maintenance" in b["name"] for b in r["backlog"])


def test_parse_roadmap_backlog_table_rows():
    """Backlog upgraded from a bare dotlist to a 4-col table (same shape as
    mainline) must parse each row's weight/eta, not just its name."""
    md = (
        "## \U0001f5c2 backlog\n\n"
        "| Name | What | Weight | ETA |\n"
        "|---|---|---|---|\n"
        "| **Widget** | do widget things | \U0001f7e1 medium | ~3 days |\n"
        "| Gadget | do gadget things | \U0001f7e2 light | ~1 day |\n"
    )
    r = sc.parse_roadmap(md)
    assert r["backlog"] == [
        {"name": "Widget", "what": "do widget things", "weight": "\U0001f7e1 medium", "eta": "~3 days"},
        {"name": "Gadget", "what": "do gadget things", "weight": "\U0001f7e2 light", "eta": "~1 day"},
    ]


def test_parse_roadmap_backlog_dotlist_fallback_fills_name_only():
    """An adopter who kept the old bare '·' list (no table) still gets a
    uniform list[dict] shape — name filled, what/weight/eta blank."""
    md = "## \U0001f5c2 backlog\nidea alpha · idea beta\n"
    r = sc.parse_roadmap(md)
    assert r["backlog"] == [
        {"name": "idea alpha", "what": "", "weight": "", "eta": ""},
        {"name": "idea beta", "what": "", "weight": "", "eta": ""},
    ]


def test_parse_roadmap_mainline_header_only_table_is_empty():
    """Coverage gap: a table with only a header row + separator (no data
    rows) must produce an empty mainline list, not crash or leak the header."""
    md = (
        "## \U0001f6e3 Mainline\n\n"
        "| Name | What | Weight | ETA |\n"
        "|---|---|---|---|\n"
    )
    assert sc.parse_roadmap(md)["mainline"] == []


def test_parse_roadmap_backlog_header_only_table_is_empty():
    """Mirrors test_parse_roadmap_mainline_header_only_table_is_empty: a
    backlog section that IS structurally a table (header + separator, no
    data rows yet — the "scaffolded the header, haven't added rows" state)
    must produce an empty backlog list. It must NOT fall through to the
    dotlist parser, which would swallow the raw pipe/dash markup into one
    garbage name string."""
    md = (
        "## \U0001f5c2 backlog\n\n"
        "| Name | What | Weight | ETA |\n"
        "|---|---|---|---|\n"
    )
    assert sc.parse_roadmap(md)["backlog"] == []


def test_parse_roadmap_backlog_malformed_table_is_empty():
    """A backlog table with the wrong column count (3 instead of 4) is still
    structurally a table, so it must go through the table path and yield
    empty rows — same shape as mainline's malformed-table behavior — rather
    than being swallowed whole by the dotlist fallback."""
    md = (
        "## \U0001f5c2 backlog\n\n"
        "| Name | What | ETA |\n"
        "|---|---|---|\n"
        "| Widget | do widget things | ~3 days |\n"
    )
    assert sc.parse_roadmap(md)["backlog"] == []


def test_parse_roadmap_empty_when_absent():
    r = sc.parse_roadmap("")
    assert r["vision"] is None
    assert r["current"] is None
    assert r["done"] == []
    assert r["doing"] == []
    assert r["mainline"] == []
    assert r["backlog"] == []


def test_gather_roadmap_sources_present_flips_true(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ROADMAP.md").write_text(_ROADMAP_MD)
    run = _fake_run({
        "rev-parse --abbrev-ref HEAD": "main\n",
        "status --porcelain": "",
        "log origin/main --oneline -8 --pretty=%s": "\n",
    })
    facts = sc.gather_card_facts(tmp_path, run, resume_runner=lambda root: {"found": False})
    assert facts["sources_present"]["roadmap"] is True
    blob = sc.render_facts_text(facts)
    assert "ROADMAP:" in blob
    assert blob.strip().split("\n")[-1].startswith("SOURCES:")


def test_gather_roadmap_sources_present_false_when_absent(tmp_path):
    run = _fake_run({
        "rev-parse --abbrev-ref HEAD": "main\n",
        "status --porcelain": "",
        "log origin/main --oneline -8 --pretty=%s": "\n",
    })
    facts = sc.gather_card_facts(tmp_path, run, resume_runner=lambda root: {"found": False})
    assert facts["sources_present"] == {
        "status": False, "resume": False, "digest": False, "roadmap": False,
        "roadmap_unparseable": False,
    }
    blob = sc.render_facts_text(facts)
    assert "ROADMAP:" not in blob
    assert blob.strip().split("\n")[-1].startswith("SOURCES:")


def test_render_includes_digest_rows():
    facts = {
        "git": {"branch": "feat/x", "clean": True, "merges": []},
        "status": {"wip": "", "locked_next": []},
        "checkpoint": None,
        "digest": {
            "project": "plc",
            "stale": True,
            "stale_days": 9,
            "tasks": ["did A", "did B"],
            "files": ["scripts/x.py"],
            "tools": "Read, Edit",
        },
        "save_state": {"tier": "unknown", "unrecorded": [], "code_count": 0},
        "sources_present": {"status": False, "resume": False, "digest": True},
    }
    blob = sc.render_facts_text(facts)
    assert "LAST DIGEST: plc" in blob
    assert "⚠ stale 9d" in blob
    assert "task: did A" in blob
    assert "task: did B" in blob
    assert "files: scripts/x.py" in blob


def test_render_mainline_carries_what_weight_eta():
    """Calibration override: future stations render full detail (not name-only),
    so the fact-gatherer must emit what/weight/eta per row, not just names."""
    facts = {
        "git": {"branch": "feat/x", "clean": True, "merges": []},
        "status": {"wip": "", "locked_next": []},
        "checkpoint": None,
        "digest": None,
        "save_state": {"tier": "unknown", "unrecorded": [], "code_count": 0},
        "roadmap": {
            "vision": None, "current": None, "done": [], "doing": [],
            "mainline": [
                {"name": "Brain", "what": "finish cross-family critic", "weight": "Med", "eta": "~1 session"},
            ],
            "backlog": [],
        },
        "sources_present": {"status": False, "resume": False, "digest": False, "roadmap": True},
    }
    blob = sc.render_facts_text(facts)
    assert "mainline:" in blob
    assert "  - Brain | finish cross-family critic | Med | ~1 session" in blob


def test_render_backlog_carries_what_weight_eta():
    """Calibration override mirrors mainline: backlog rows now carry real
    weight/eta from the source table, so the render must emit them per row,
    not collapse to a name-only comma list."""
    facts = {
        "git": {"branch": "feat/x", "clean": True, "merges": []},
        "status": {"wip": "", "locked_next": []},
        "checkpoint": None,
        "digest": None,
        "save_state": {"tier": "unknown", "unrecorded": [], "code_count": 0},
        "roadmap": {
            "vision": None, "current": None, "done": [], "doing": [],
            "mainline": [],
            "backlog": [
                {"name": "Widget", "what": "do widget things", "weight": "Med", "eta": "~3 days"},
            ],
        },
        "sources_present": {"status": False, "resume": False, "digest": False, "roadmap": True},
    }
    blob = sc.render_facts_text(facts)
    assert "backlog (1):" in blob
    assert "  - Widget | do widget things | Med | ~3 days" in blob


# ── Milestones-table ROADMAP layout ──────────────────────────────────
# PLC's own references/roadmap.md §"Required structure" MANDATES this layout;
# parse_roadmap must read it too, not only the emoji-fisheye layout above.
# Selection is by STRUCTURE (a table row whose last cell carries a status-legend
# glyph), never by header words — tracked source and tests are held to a restricted character set.

_ROADMAP_TABLE_MD = (
    "# Roadmap — testproj\n\n"
    "> Whole-plan map. One line per milestone, forever.\n\n"
    "## Index\n"
    "- [The one-sentence goal](#goal)\n"
    "- [Milestones](#milestones)\n\n"
    "## The one-sentence goal\n\n"
    "Build the thing, a traceable spec to plan to execute discipline.\n\n"
    "## The shape of the work\n\n"
    "**Build then harden then activate.**\n\n"
    "## Milestones\n\n"
    "| # | Milestone | What gets built | Depends on | Status |\n"
    "|---|---|---|---|---|\n"
    "| M1 | Groundwork | the core module | — | ✅ done |\n"
    "| M2 | Hardening | the cache layer | M1 | ✅ done |\n"
    "| X2 | Second station | does the second thing | — | ▶ current |\n"
    "| X3 | Third station | does the third thing | — | ☐ planned |\n"
    "| X4 | Someday thing | not scheduled | — | ⏸ deferred |\n\n"
    "<status legend: ✅ done · ▶ current · ☐ planned>\n\n"
    "## Plan changes\n"
)


def test_parse_roadmap_milestones_table_doing_and_current():
    r = sc.parse_roadmap(_ROADMAP_TABLE_MD)
    assert r["doing"] == ["X2 Second station"]
    assert r["current"] == "X2 Second station"


def test_parse_roadmap_milestones_table_mainline_excludes_done_and_deferred():
    r = sc.parse_roadmap(_ROADMAP_TABLE_MD)
    # only the ☐ planned row is a future station; ✅ done + ⏸ deferred excluded
    assert r["mainline"] == [
        {"name": "X3 Third station", "what": "does the third thing", "weight": "", "eta": ""},
    ]


def test_parse_roadmap_milestones_table_done_count_and_vision():
    r = sc.parse_roadmap(_ROADMAP_TABLE_MD)
    assert len(r["done"]) == 2  # M1 + M2
    assert r["vision"] == "Build the thing, a traceable spec to plan to execute discipline."


def test_parse_roadmap_table_done_counted_inside_details():
    """#3-lite folds done rows into <details>; they are still table rows in the
    doc, so a doc-wide scan must still count them (not just the first table)."""
    md = (
        "## The one-sentence goal\n\nGoal here.\n\n"
        "## Milestones\n\n"
        "| # | Milestone | What | Dep | Status |\n"
        "|---|---|---|---|---|\n"
        "| X2 | active | x | — | ▶ current |\n"
        "| X3 | planned | y | — | ☐ planned |\n\n"
        "<details><summary>Done</summary>\n\n"
        "| # | Milestone | What | Dep | Status |\n"
        "|---|---|---|---|---|\n"
        "| M1 | groundwork | z | — | ✅ done |\n"
        "| M2 | hardening | w | — | ✅ done |\n"
        "</details>\n"
    )
    r = sc.parse_roadmap(md)
    assert len(r["done"]) == 2
    assert r["doing"] == ["X2 active"]
    assert [m["name"] for m in r["mainline"]] == ["X3 planned"]


def test_parse_roadmap_table_malformed_row_skipped_no_crash():
    """A row with too few cells degrades (skipped), never raises."""
    md = (
        "## Milestones\n\n"
        "| # | Milestone | What | Dep | Status |\n"
        "|---|---|---|---|---|\n"
        "| X2 | good | x | — | ▶ current |\n"
        "| oops | ✅ done |\n"
        "| X3 | good2 | y | — | ☐ planned |\n"
    )
    r = sc.parse_roadmap(md)  # must not raise
    assert r["doing"] == ["X2 good"]
    assert [m["name"] for m in r["mainline"]] == ["X3 good2"]
    assert r["done"] == []  # the 2-cell glyph row is below the 4-cell floor, skipped


def test_parse_roadmap_table_layout_does_not_disturb_fisheye():
    """AC2 guard: the emoji-fisheye fixture still parses via the fisheye path
    (the table path is a fallback, reached only when fisheye yields nothing)."""
    r = sc.parse_roadmap(_ROADMAP_MD)
    assert r["vision"] == "cross-agent memory"
    assert r["mainline"][0]["name"] == "Brain"


def _bare_run():
    return _fake_run({
        "rev-parse --abbrev-ref HEAD": "main\n",
        "status --porcelain": "",
        "log origin/main --oneline -8 --pretty=%s": "\n",
    })


def test_gather_roadmap_table_layout_is_present(tmp_path):
    """AC1: this repo's Milestones-table layout makes sources_present.roadmap True."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ROADMAP.md").write_text(_ROADMAP_TABLE_MD)
    facts = sc.gather_card_facts(tmp_path, _bare_run(), resume_runner=lambda root: {"found": False})
    assert facts["sources_present"]["roadmap"] is True
    assert facts["sources_present"]["roadmap_unparseable"] is False


def test_gather_roadmap_present_but_unparseable_is_flagged(tmp_path):
    """AC3: a ROADMAP.md that exists but matches no known layout is reported as
    present-but-unparseable, distinct from a genuinely absent ROADMAP."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ROADMAP.md").write_text(
        "# Roadmap\n\nprose only, no milestones table and no emoji sections.\n"
    )
    facts = sc.gather_card_facts(tmp_path, _bare_run(), resume_runner=lambda root: {"found": False})
    assert facts["sources_present"]["roadmap"] is False
    assert facts["sources_present"]["roadmap_unparseable"] is True
    assert "unrecognized layout" in sc.render_facts_text(facts)


def test_gather_roadmap_absent_is_not_flagged_unparseable(tmp_path):
    """AC3 negative half: no ROADMAP.md at all → not flagged unparseable."""
    facts = sc.gather_card_facts(tmp_path, _bare_run(), resume_runner=lambda root: {"found": False})
    assert facts["sources_present"]["roadmap"] is False
    assert facts["sources_present"]["roadmap_unparseable"] is False


def test_parse_roadmap_table_glyph_must_lead_last_cell():
    """The glyph must LEAD the last cell. A different table whose
    final column merely MENTIONS a glyph mid-prose must not be miscounted as a
    milestone row (structural anchor, not 'a glyph appears somewhere')."""
    md = (
        "## The one-sentence goal\n\nGoal.\n\n"
        "## Milestones\n\n"
        "| # | Milestone | What | Dep | Status |\n"
        "|---|---|---|---|---|\n"
        "| X2 | real | x | — | ▶ current |\n\n"
        "## Relationship to other docs\n\n"
        "| Doc | Scope | Note |\n"
        "|---|---|---|\n"
        "| RESUME | now | mostly ✅ implemented already |\n"
    )
    r = sc.parse_roadmap(md)
    assert r["doing"] == ["X2 real"]
    assert r["done"] == []  # the 'mostly ✅ …' note cell is not a milestone row


def test_parse_roadmap_table_vision_only_before_first_table():
    """Review M5: vision is the pre-table one-sentence goal; prose appearing
    only AFTER the first table must not be picked up as vision."""
    md = (
        "# Roadmap\n\n"
        "## Milestones\n\n"
        "| # | Milestone | What | Dep | Status |\n"
        "|---|---|---|---|---|\n"
        "| X2 | real | x | — | ▶ current |\n\n"
        "## Notes\n\nthis prose is after the table and is not the goal.\n"
    )
    r = sc.parse_roadmap(md)
    assert r["vision"] is None
    assert r["doing"] == ["X2 real"]  # still present via the table
