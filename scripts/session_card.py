#!/usr/bin/env python3
"""session_card.py — deterministic fact-gatherer for the /catchup welcome-back card.

Reads git + RESUME.md + PLC session digest (+ STATUS.md if present) and prints a
raw-facts blob for the /catchup prose command to render. Read-only; never writes.
Python 3; it reuses the PLC session digest, reads RESUME.md in either of its formats,
and treats STATUS.md as optional.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

_CODE_PATH = re.compile(r"^(src|tests|scripts|\.githooks)/|^public/static/|\.(ts|tsx|js|jsx|cjs|mjs)$")
_CODE_FILE = re.compile(r"^(package\.json|bunfig\.toml|tsconfig.*|biome\.json|\.dependency-cruiser\.cjs)$")
_PR_TRAILING = re.compile(r"\(#(\d+)\)\s*$")
_PR_INLINE = re.compile(r"#(\d+)")

# The `.claude/ci-status.json` contract. The vocabulary is
# PLC's OWN and is deliberately not a forge's enum: no shared cross-tool
# vocabulary exists ("cancelled" has three spellings across GitHub REST / `gh` /
# `glab`, whose enums are 11 and 15 non-overlapping values). Mapping a forge's
# enum onto these three words is the PRODUCER's job; PLC owning a 15-value enum
# it cannot maintain is the failure this avoids.
CI_SCHEMA = "plc.ci-status/1"
CI_STATES = ("green", "red", "unknown")
_CI_SHA = re.compile(r"[0-9a-fA-F]{40}")

# The five situations the CI row decides between. ONE list, exported, because the prose
# contract in `commands/catchup.md` is checked against it in BOTH directions —
# every key documented, and nothing documented that is not a key. Two copies
# would let the prose and the code drift apart one at a time.
CI_ROW_STATES = ("absent", "unreadable", "unknown", "stale", "fresh")


def pr_of(subject: str) -> int | None:
    m = _PR_TRAILING.search(subject) or _PR_INLINE.search(subject)
    return int(m.group(1)) if m else None


def is_code_merge(files: list[str]) -> bool:
    return any(_CODE_PATH.search(f) or _CODE_FILE.search(f) for f in files)


def find_merge_sha(log_output: str, pr: int) -> str | None:
    for line in log_output.split("\n"):
        sp = line.find(" ")
        if sp <= 0:
            continue
        if pr_of(line[sp + 1:]) == pr:
            return line[:sp]
    return None


def classify_save_state(noted_max_pr, merges, is_code):
    if noted_max_pr is None:
        return {"tier": "unknown", "unrecorded": [], "code_count": 0}
    unrecorded = [m for m in merges if m["pr"] is not None and m["pr"] > noted_max_pr]
    code_count = sum(1 for m in unrecorded if is_code(m["pr"]))
    tier = "fresh" if not unrecorded else ("code-behind" if code_count else "doc-behind")
    return {"tier": tier, "unrecorded": unrecorded, "code_count": code_count}


def gather_git_facts(run):
    branch = run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    clean = run(["status", "--porcelain"]).strip() == ""
    raw = run(["log", "origin/main", "--oneline", "-8", "--pretty=%s"])
    merges = [
        {"pr": pr_of(s), "subject": s}
        for s in (ln.strip() for ln in raw.split("\n"))
        if s
    ]
    # The reference commit the CI artifact's `sha` is compared
    # against. Deliberately tolerant of failure and deliberately asymmetric: an
    # unobtainable reference yields None, which read_ci_status treats as STALE.
    # `except` defaulting toward "equal"/fresh is the one change that would
    # silently reintroduce the green-on-a-superseded-commit defect the CI row
    # exists to remove, so the direction is mandated, not chosen
    # here. Reasons it legitimately fails: no `origin` remote, an unfetched
    # clone, or a default branch not named `main` (an assumption this call
    # inherits from `log origin/main` above rather than introducing).
    try:
        head_sha = run(["rev-parse", "origin/main"]).strip() or None
    except Exception:
        head_sha = None
    return {"branch": branch, "clean": clean, "merges": merges, "head_sha": head_sha}


def parse_newest_checkpoint(md: str):
    if not md.strip():
        return None
    lines = md.split("\n")
    # stacked-checkpoint shape: first "## " header containing the ⏳ marker.
    start = next((i for i, l in enumerate(lines) if l.startswith("## ") and "⏳" in l), -1)
    if start != -1:
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].startswith("## "):
                end = i
                break
        block = lines[start:end]
        header = re.sub(r"^##\s*", "", block[0])
    else:
        # PLC single-state shape: whole head down to the first "## " section (exclusive),
        # header = the leading "# " title.
        end = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
        block = lines[:end]
        title = next((l for l in block if l.startswith("# ")), block[0] if block else "")
        header = re.sub(r"^#\s*", "", title)
    body = [l.strip() for l in block[1:] if l.strip()][:15]
    prs = [int(m) for m in re.findall(r"#(\d+)", "\n".join(block))]
    return {"header": header, "lines": body, "noted_max_pr": max(prs) if prs else None}


_DONE_MARKER = re.compile(r"\bDONE\b|\bSHIPPED\b|\bMERGED\b|\bCLOSED\b")


def _section(md: str, starts_with: str, next_prefix: str) -> str:
    lines = md.split("\n")
    s = next((i for i, l in enumerate(lines) if l.startswith(starts_with)), -1)
    if s == -1:
        return ""
    e = len(lines)
    for i in range(s + 1, len(lines)):
        if lines[i].startswith(next_prefix):
            e = i
            break
    return "\n".join(lines[s + 1:e])


def parse_status(md: str) -> dict:
    now = _section(md, "## 🎯 Now", "## ")
    active = next(
        (l for l in now.split("\n")
         if l.startswith("**Track") and not re.search(r"CLOSED|CLOSING|PAUSED", l)),
        None,
    )
    wip = ""
    if active:
        m = re.search(r"\*\*Track \(([^)]*)\)", active)
        wip = (m.group(1).strip() if m else "")
    locked_md = _section(md, "### Locked next", "## ")
    locked_next = []
    for l in locked_md.split("\n"):
        if re.match(r"^\s*\d+\.\s+\*\*", l) and not _DONE_MARKER.search(l):
            m = re.match(r"^\s*\d+\.\s+\*\*(.+?)\*\*", l)
            if m:
                locked_next.append(m.group(1).strip())
    return {"wip": wip, "locked_next": locked_next}


def _section_by_emoji(md: str, emoji: str) -> str:
    """Body of the '## <emoji> ...' section, matched by emoji prefix (not header words)."""
    return _section(md, f"## {emoji}", "## ")


def _split_cells(line: str) -> list[str]:
    """One markdown table line to its cells, ending a cell only on an
    UNESCAPED pipe.

    GFM: "Include a pipe in a cell's content by escaping it, including inside
    other inline spans" — so `\\|` is content, not a boundary, and a backticked
    span earns no exemption. Escapes are resolved here, so cell text carries a
    literal `|` with no backslash left behind.

    Escapedness is the PARITY of the backslash run before the pipe, which is
    why this is a scanner and not a `(?<!\\\\)\\|` regex. A one-character
    lookbehind cannot tell `\\|` (an escape) from `\\\\|` (a literal backslash
    then a real delimiter), so a cell ending in a backslash — a Windows path,
    or GFM's own `\\\\` — would swallow the delimiter after it. The tests pin
    both parities.
    """
    cells: list[str] = []
    buf: list[str] = []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if ch == "\\" and i + 1 < n and line[i + 1] in ("|", "\\"):
            buf.append(line[i + 1])   # consume BOTH: the run's parity is what decides
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf))
    return cells


def _table_rows(section_text: str) -> tuple[list[list[str]], int]:
    """First markdown table in a section body: its data rows as cell-lists, and
    the column count its HEADER declares.

    Skips the header row and the '|---|' separator row STRUCTURALLY (by
    position + character-class, never by matching header words), so it
    stays language-agnostic.

    The declared width is returned rather than assumed by the caller.
    Hard-coding 4 means that widening the table to five real columns
    makes EVERY well-formed row look over-split: recovery then fires on all of
    them, rewrites the whole table, and still reports zero unreadable rows —
    a mistake that corrupts everything while reporting health. Header and body
    are measured by the same splitter here, so the declared width can never be
    computed under different rules than the rows it judges.
    """
    lines = section_text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip().startswith("|")), None)
    if start is None:
        return [], 0
    rows = []
    for l in lines[start:]:
        if not l.strip().startswith("|"):
            break
        rows.append(l)
    if len(rows) < 2:
        return [], 0
    declared = len(_split_cells(rows[0].strip())[1:-1])
    body_rows = rows[1:]  # drop header row (position 0)
    if body_rows and set(body_rows[0].strip()) <= set("-:| "):
        body_rows = body_rows[1:]  # drop separator row (all dashes/colons/pipes/space)
    # Cells are returned UNSTRIPPED. Stripping here would be lossy for the one
    # consumer that has to put a row back together: recovery re-joins the middle
    # cells of an over-split row, and pre-stripped cells rejoin as `a|b` where
    # the author wrote `a | b`. Each consumer strips the field it assigns.
    return [_split_cells(r.strip())[1:-1] for r in body_rows], declared


# Status-legend glyphs (references/roadmap.md §"Status legend"): ✅ done · ▶ current
# · ☐ planned · ⏸ paused · ✗ dropped, plus ◐ partial from the fisheye legend. Used to
# recognize + bucket Milestones-table rows by STRUCTURE, never by header words.
_G_DONE = "✅"                       # ✅
_G_DOING = ("▶", "◐")          # ▶ current · ◐ partial
_G_PLANNED = "☐"                    # ☐
_LEGEND_GLYPHS = (_G_DONE, "▶", "◐", _G_PLANNED, "⏸", "✗")  # + ⏸ ✗


def _milestone_table_rows(md: str) -> list[tuple[str, str, str]]:
    """Every markdown-table row ANYWHERE in the doc whose LAST cell carries a
    status-legend glyph → (glyph, name, what). Structure only (never header
    words); ≥4 cells required; robust to rows folded inside <details>. This is
    the Milestones-table layout `references/roadmap.md` §"Required structure"
    mandates — read as a fallback when the emoji-fisheye parse yields nothing.

    Shares `_split_cells` with the fisheye path, so an escaped `\\|` is content
    here too. It deliberately does NOT get right-anchored recovery: this
    layout is `# | name | what | … | status` with a VARIABLE middle, so an
    over-split is indistinguishable from a legitimately wider table, and
    guessing would produce the confidently-wrong output this parser exists to avoid.

    For the same reason it contributes NO unreadable count: a count it cannot
    compute honestly would be a number that means nothing, which is the class
    of defect this parser is built to avoid."""
    rows = []
    for line in md.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in _split_cells(s)[1:-1]]
        if len(cells) < 4:
            continue
        # Glyph must LEAD the last cell (that is how a Status cell renders:
        # "✅ done", "▶ current"). A glyph merely mentioned mid-prose in some
        # other table's final column is not a milestone row — the structural
        # anchor the fallback needs, not just "a glyph appears somewhere".
        glyph = next((g for g in _LEGEND_GLYPHS if cells[-1].lstrip().startswith(g)), None)
        if glyph is None:
            continue  # header / separator / non-milestone table row
        name = re.sub(r"\*\*(.+?)\*\*", r"\1", f"{cells[0]} {cells[1]}").strip().strip("`").strip()
        rows.append((glyph, name, cells[2]))
    return rows


def _first_prose_paragraph(md: str) -> str | None:
    """First run of plain-prose lines (structural: skip headers / blockquotes /
    tables / lists / html), joined. In the Milestones-table layout this is the
    `## The one-sentence goal` body — derived without matching the header text."""
    para = []
    for line in md.split("\n"):
        s = line.strip()
        if s.startswith("|"):
            break  # the one-sentence goal lives BEFORE the first table
        if not s or re.match(r"^([-*+]\s|#|>|<)", s):
            if para:
                break
            continue
        para.append(s)
    return " ".join(para) if para else None


def _roadmap_has_signal(rm: dict) -> bool:
    """A parsed roadmap carries usable content (vs an all-empty parse). ONE
    definition so parse_roadmap's fisheye-vs-table gate and gather_card_facts'
    presence verdict cannot desync — adding a bucket to one and not the other
    would silently split them."""
    return bool(rm["vision"] or rm["mainline"] or rm["doing"] or rm["done"]
                or rm["mainline_done"])


def _cross_read(mainline_done: list[str], current: str | None) -> tuple[list[str], int]:
    """Finished stations the `current` prose still talks about → (their tokens, rows skipped).

    The card answers "where are we" three times — the current-phase prose, the focal station, and
    the finished list — and nothing used to compare them. `current` can therefore go stale while
    `doing` is right, which reads like a rendering bug rather than a document that needs an edit.

    The token is read from the ADOPTER's own table, never pattern-matched out of it: extracting
    `B\\d+` would write one repo's numbering dialect into a portable tool.

    Two guards, and their costs point in opposite directions:

    - Not-a-word-character on either side, rather than `\\b`. As plain
      substrings `M4` and `M15` both hit `M49, M152, M153`, and both are correctly rejected once
      bounded. `\\b` is the obvious way to write that and is **unsound for exactly the token shape
      the second guard below admits** — one whose last character is `-`, `_` or `.`. `\\b` asks for
      a word/non-word transition, so a token ending in punctuation fails to match where it should
      (`1.` is missed in `1. Setup auth`, because the following space is also a non-word character)
      and matches where it should not (`AUTH-` hits inside `AUTH-2`, which is the substring defect
      this guard exists to close, re-opened for the other half of the token space).
    - A token with no digit and no `-_.` does not take part. A station called `Fix login bug`
      yields `Fix`, and any prose contains that. This UNDER-detects on purpose: a false alarm
      costs the reader's trust in the whole card, while a missed one costs one stale line.

    It is tempting to justify the second guard with "every token here carries a digit, so it is free" —
    which is a fact about one repo's numbering, not about the roadmap format. An adopter naming
    stations `MVP` / `GA` / `AUTH` gets every row skipped and the cross-read silently does nothing.
    So the skipped count is returned unconditionally and 0 is a value: the guard stays, the
    under-detection does not get to be invisible.
    """
    conflicts, skipped = [], 0
    for name in mainline_done:
        # A row written in the leading-glyph form starts with the glyph, so the station's first
        # token is what follows it. Without this the token IS the glyph, which carries no digit
        # and would file every such row as skipped — a guard reporting its own parse mistake.
        head = name.lstrip()
        if head.startswith(_G_DONE):
            head = head[len(_G_DONE):].lstrip()
        token = head.split()[0] if head.split() else ""
        if not token:
            continue
        if not (re.search(r"\d", token) or re.search(r"[-_.]", token)):
            skipped += 1
            continue
        if (current and token not in conflicts
                and re.search(rf"(?<!\w){re.escape(token)}(?!\w)", current)):
            # Deduplicated: one station can legitimately hold two rows (a batch
            # reopened for a partial fix), and the card
            # would otherwise name it twice in one sentence. It is one
            # observation about one name, however many rows carry it.
            conflicts.append(token)
    return conflicts, skipped


def parse_roadmap(md: str) -> dict:
    """Fact-gatherer for docs/ROADMAP.md's fisheye view.

    Parses by emoji prefix + positional structure only — never by matching
    header words. A ROADMAP.md may use non-English header labels; that's
    fine, the parser never looks at the label text, only its position relative
    to '**bold**' markers and '## <emoji>' section starts.
    """
    lines = md.split("\n")
    head_end = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))

    # Only lines that start with "**" at column 0 count as real bold-value
    # lines. A blockquote intro (`> **What this is** — ...`) puts bold markers
    # BEFORE the real vision/current lines, but those lines start with ">",
    # never "**" — so this naturally skips quoted intro prose without ever
    # reading the label text itself.
    bold_values = []
    for l in lines[:head_end]:
        if not l.startswith("**"):
            continue
        m = re.match(r"\*\*.+?\*\*\s*(.+)", l)
        if m:
            bold_values.append(m.group(1).strip())
    vision = bold_values[0] if len(bold_values) > 0 else None
    current = bold_values[1] if len(bold_values) > 1 else None

    def _dotlist(emoji: str) -> list[str]:
        body = _section_by_emoji(md, emoji)
        if not body:
            return []
        # done/backlog can be the file's LAST section, so the shared _section()
        # boundary slice lands on EOF rather than a "## " header and swallows a
        # trailing `---`/`***` horizontal rule + whatever footer prose follows
        # it (e.g. a closing "*Maintenance: ...*" italic line). Truncate at the
        # first standalone rule line BEFORE splitting on the middot — scoped to
        # this dot-list path only, never touching _section() itself (parse_status
        # relies on _section() preserving mid-body `---` dividers untouched).
        body_lines = body.split("\n")
        for i, l in enumerate(body_lines):
            if l.strip() in ("---", "***"):
                body_lines = body_lines[:i]
                break
        body = "\n".join(body_lines)
        return [p.strip() for p in body.split("·") if p.strip()] if body else []

    def _clean_name(text: str) -> str:
        """Strip markup from ANYWHERE inside a captured name, not just its ends.

        The old form was `.strip().strip("`")`, which only touches the two ends
        of the span — so `**`p13`** —— ...` kept its interior closing backtick
        and rendered as ``p13` —— ...`` on the card. Shared by mainline,
        backlog and doing so the three cannot disagree about the same cell.
        """
        return re.sub(r"\*\*(.+?)\*\*", r"\1", text).replace("`", "").strip()

    def _table_dicts(cells_rows: list[list[str]], declared: int) -> tuple[list[dict], int]:
        """Rows to dicts, plus a count of the rows that could not be read.

        Three cases, and the asymmetry between the last two is the decision:

        - exactly `declared` cells: read as written.
        - MORE than declared: right-anchored recovery. A stray unescaped pipe
          lands in the free-text column, which `references/roadmap.md` mandates
          is neither first nor last — so the name is still the first cell, eta
          the last, weight the second-to-last, and everything between rejoins
          into `what`.
          A left-anchored rule would put prose in
          `weight` and a pipe-bearing blob in `eta`, and GFM's truncate-the-
          excess discards the real weight and eta outright.
        - FEWER than declared: NOT recovered. A short row is not an over-split,
          and right-anchoring it would read `what` as `weight`. Counted, not
          guessed at — the count is the honest answer where the shape is not.

        The count is returned unconditionally, including as 0. Silence is the
        defect this closes: GFM nowhere sanctions dropping a row, and pandas'
        `read_csv` makes silent skipping (`on_bad_lines='skip'`) something a
        caller must ask for, its default being `'error'`.
        """
        out: list[dict] = []
        unreadable = 0
        for cells in cells_rows:
            # A table declaring anything other than four columns has no shape
            # this consumer can fill, so EVERY row of it is unreadable —
            # including a row that happens to split into four. Without this the
            # declared width would only ever gate recovery, and a 3-column table
            # with a stray pipe in one row would hand that row over as
            # fabricated name/what/weight/eta with the count still reading 0:
            # the mirror image of the failure the declared width exists to
            # prevent.
            if declared != 4:
                unreadable += 1
                continue
            if len(cells) > declared:
                cells = [cells[0], "|".join(cells[1:-2]), cells[-2], cells[-1]]
            if len(cells) != declared:
                unreadable += 1
                continue
            out.append({"name": _clean_name(cells[0]), "what": cells[1].strip(),
                        "weight": cells[2].strip(), "eta": cells[3].strip()})
        return out, unreadable

    def _table_or_dotlist(emoji: str) -> list[dict]:
        """Parse an emoji section as a table (reusing the same table-row
        helper mainline uses) with a dotlist fallback for adopters who kept
        a bare '·' list instead of upgrading to a table.

        The branch is decided by TABLE STRUCTURE, not by row count: a section
        that IS a table (header + separator, even with zero data rows, or a
        malformed non-4-column table) must go through the table path and
        return [] on no valid rows — same as mainline — rather than falling
        through to the dotlist parser, which would swallow the raw pipe/dash
        markup into one garbage name string.
        """
        body = _section_by_emoji(md, emoji)
        if not body:
            return [], 0
        has_table = any(l.strip().startswith("|") for l in body.split("\n"))
        if has_table:
            rows, declared = _table_rows(body)
            return _table_dicts(rows, declared)
        return [{"name": item, "what": "", "weight": "", "eta": ""} for item in _dotlist(emoji)], 0

    done = _dotlist("✅")
    backlog, backlog_unreadable = _table_or_dotlist("\U0001f5c2")

    # doing + mainline both come from the ONE 🛣 table. The 🔄 section is
    # no longer read for any field: it is prose, and prose leads paragraphs with
    # bold topic sentences, so the old "line-leading bold = an item" rule turned
    # journal sentences into stations.
    # A station is now marked where the parser looks: a
    # doing GLYPH LEADING the name cell, the same discipline
    # `_milestone_table_rows` applies to its status cell.
    doing: list[str] = []
    mainline_done: list[str] = []
    future_rows: list[list[str]] = []
    # Rows whose state cannot be read honestly. Counted, never guessed —
    # they join `unreadable_rows` rather than defaulting into a band.
    undecidable = 0
    mainline_rows, mainline_declared = _table_rows(_section_by_emoji(md, "\U0001f6e3"))
    for cells in mainline_rows:
        if not cells:
            continue
        # The width test belongs to _table_dicts, NOT here: markdown splits on
        # every unescaped `|`, so a row whose prose carries one parses as 5-6
        # cells and is dropped. A doing row must not
        # be able to disappear that way — that would leave the focal
        # field silently empty.
        #
        # STRIP FIRST, THEN look for the glyph. The other order fails on
        # `**▶ Name**` — a whole-cell bold, which is exactly how the convention
        # of earlier bold-item roadmaps was written, so it is the shape a migrating author
        # is most likely to type. Worse than a miss: the row then falls through
        # to the Future band carrying a raw `▶` in its rendered name, i.e. a
        # second focus marker in the wrong band.
        cleaned = _clean_name(cells[0])
        glyph = next((g for g in _G_DOING if cleaned.startswith(g)), None)
        if glyph is None:
            # Finished stations leave the Future band. Two layers, and
            # both carry weight: in a typical roadmap the
            # done glyph sits INSIDE the name cell rather than leading it,
            # so a leading-glyph rule
            # alone would miss most rows — while the leading form is what a
            # migrating author types, so dropping it would strand them.
            #
            # Scoped to `cells[0]`, never across cells: a glyph in `what` says
            # something about the work, not about the row's state. And
            # scoped to the ROAD band only — in
            # the backlog band, a glyph is also used for "a prerequisite
            # lifted" and for "dropped".
            #
            # Gated on a four-column table: when the header declares another
            # width every row is unreadable (see _table_dicts), and bucketing
            # rows out of a table nobody can read would shrink that count while
            # claiming stations are finished.
            if mainline_declared == 4:
                if _G_DONE in cleaned:
                    mainline_done.append(cleaned)
                    continue
                # The shape that would leak a finished row back into Future.
                # The doing test above runs on the raw cell because the
                # doing glyph LEADS the name, so a stray pipe cannot hide it.
                # The done glyph sits at the name's END, so an unescaped pipe
                # in the name cell truncates it away and the row would fall
                # into Future — the very defect being closed. The glyph is then
                # somewhere in the middle cells recovery would merge, and there
                # is no way to tell whether it came from the name or from the
                # free-text column. Do not guess: hand it to the honest
                # unreadable counter.
                if len(cells) > mainline_declared and any(
                    _G_DONE in c for c in cells[1:-2]
                ):
                    undecidable += 1
                    continue
            future_rows.append(cells)
            continue
        name = cleaned[len(glyph):].strip()
        # A cell that is ONLY a glyph marks a station and names none. It is not
        # a Future row (it is marked as current), and an empty string in `doing`
        # is worse than an absent one: the card's "is doing empty" test is a
        # list check, so `[""]` renders a blank focal row instead of dropping
        # the segment. Named here rather than left to the renderer to survive.
        if name:
            doing.append(name)

    # The focal station is rendered as its own band, so it must not ALSO appear
    # in the Future table.
    mainline, mainline_unreadable = _table_dicts(future_rows, mainline_declared)
    conflicts, crossread_skipped = _cross_read(mainline_done, current)

    fisheye = {
        "vision": vision, "current": current,
        "done": done, "doing": doing,
        # A field of its own, deliberately NOT folded into `done`. The two are
        # different abstraction levels, not two lists of the same kind of thing:
        # `done` is theme/batch-level (one entry swallows a dozen stations)
        # while this is station-level. Folding with name-dedup
        # does not help:
        # the name formats have no overlap, so dedup matches zero rows and stops
        # none of the double-count it was proposed to prevent.
        "mainline_done": mainline_done,
        "mainline": mainline, "backlog": backlog,
        # Both emitted always, both computed from the two halves the card reads
        # independently. `crossread_skipped` is 0 far more often than not, and
        # that is exactly why it is unconditional: the day it is not 0 is the
        # day the cross-read is quietly doing nothing for its reader.
        "current_conflicts": conflicts,
        "crossread_skipped": crossread_skipped,
        # Emitted whether or not anything was recovered: 0 is a value, not an
        # absence. A row the parser could not read is reported, never dropped
        # in silence.
        "unreadable_rows": mainline_unreadable + backlog_unreadable + undecidable,
    }
    if _roadmap_has_signal(fisheye):
        return fisheye

    # Fallback: PLC's own Milestones-table layout. Reached ONLY when the emoji
    # -fisheye parse above found nothing, so the fisheye path stays untouched.
    # Selected by structure (a table row carrying a status-legend glyph).
    trows = _milestone_table_rows(md)
    if trows:
        t_done = [name for g, name, _ in trows if g == _G_DONE]
        t_doing = [name for g, name, _ in trows if g in _G_DOING]
        t_mainline = [
            {"name": name, "what": what, "weight": "", "eta": ""}
            for g, name, what in trows if g == _G_PLANNED
        ]
        return {
            "vision": _first_prose_paragraph(md),
            "current": t_doing[0] if t_doing else None,
            "done": t_done, "doing": t_doing,
            # Empty on purpose, not unset: this layout's `done` is ALREADY
            # station-level, so the same rows in both fields would be the
            # double-count the split exists to avoid. The key is always present
            # so a consumer never has to ask which parse path produced the dict.
            "mainline_done": [],
            # Nothing to cross-read against: this layout's finished rows go to
            # `done`, and `current` here is the focal station's own name, so a
            # hit would be the two fields agreeing, not disagreeing.
            "current_conflicts": [], "crossread_skipped": 0,
            "mainline": t_mainline, "backlog": [],
            # This layout has a variable middle, so an over-split cannot be
            # told from a wider table and the count would be meaningless here.
            # 0 is what this path can say honestly.
            "unreadable_rows": 0,
        }
    return fisheye


def _run_resume(root: Path) -> dict:
    """Real seam: call the read-only digest reader (session_card.py's sibling),
    with cwd=root so it derives the right repo; never writes, never raises."""
    script = Path(__file__).resolve().parent / "save_session.py"
    try:
        out = subprocess.run(
            ["python3", str(script), "resume"],
            capture_output=True, text=True, timeout=15, cwd=str(root),
        ).stdout.strip()
        return json.loads(out) if out else {"found": False}
    except Exception:
        return {"found": False}


def _digest_section(md: str, header: str) -> list[str]:
    lines = md.split("\n")
    s = next((i for i, l in enumerate(lines) if l.strip() == header), -1)
    if s == -1:
        return []
    out = []
    for l in lines[s + 1:]:
        if l.startswith("## "):
            break
        t = l.strip()
        if t.startswith("- "):
            out.append(t[2:].strip())
    return out


def read_digest(root: Path, runner=_run_resume) -> dict | None:
    info = runner(root)
    if not info.get("found") or info.get("cross_project"):
        return None
    md = Path(info["path"]).read_text()
    tools_lines = [l.strip() for l in md.split("\n")]
    ti = next((i for i, l in enumerate(tools_lines) if l == "## Tools Used"), -1)
    tools = tools_lines[ti + 1].strip() if ti != -1 and ti + 1 < len(tools_lines) else ""
    return {
        "project": info.get("project", ""),
        "stale": info.get("stale", False),
        "stale_days": info.get("stale_days", 0),
        "tasks": _digest_section(md, "## Tasks"),
        "files": _digest_section(md, "## Files Modified"),
        "tools": tools,
    }


def _files_of_pr(run, pr: int) -> list[str]:
    """Look up which files a PR's merge touched, to classify code- vs doc-only.
    Best-effort: any shell failure (shallow log, no matching sha, no remote,
    caller-supplied `run` that only stubs the commands it cares about) degrades
    to "no files found" rather than raising — callers (is_code below,
    gather_card_facts) must never crash the card over a file-list lookup.
    """
    try:
        sha = find_merge_sha(run(["log", "origin/main", "--oneline", "-40"]), pr)
        if not sha:
            return []
        return [f for f in run(["show", "--name-only", "--pretty=format:", sha]).split("\n") if f.strip()]
    except Exception:
        return []


def _parse_iso_utc(ts):
    """Parse the artifact's `ts`. Returns None when it is not a timestamp —
    callers treat that as unreadable, never as "age unknown, render anyway"."""
    if not isinstance(ts, str):
        return None
    try:
        # `fromisoformat` grew Z support in 3.11; normalising keeps the reader
        # working on the older interpreters PLC's portability thesis targets.
        dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    except Exception:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _ci_age(ts_dt, now_dt):
    """A coarse, honest age. A `ts` AHEAD of now is reported as such rather than
    clamped to "just now" — producer clock skew is a real condition and hiding
    it behind a plausible-looking age is the failure mode the CI row exists to prevent."""
    secs = (now_dt - ts_dt).total_seconds()
    if secs < 0:
        return "in the future"
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def read_ci_status(root, head_sha, now=None):
    """Read `.claude/ci-status.json` — the CI state a producer put on record.

    Returns exactly one of three shapes (there is no fourth, and no
    partial-credit path — a half-valid file is unreadable, not "mostly fine"):

      * `None`                — no file at all
      * `{"unreadable": True}` — a file that failed validation
      * the artifact fields + `stale: bool`

    PLC never queries a forge and never runs an adopter-supplied command;
    this function reads one file and does arithmetic on strings.
    """
    p = Path(root) / ".claude" / "ci-status.json"
    if not p.is_file():
        return None
    try:
        art = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"unreadable": True}
    if not isinstance(art, dict):
        return {"unreadable": True}
    if art.get("schema") != CI_SCHEMA:
        return {"unreadable": True}
    sha, state, ts = art.get("sha"), art.get("state"), art.get("ts")
    if not isinstance(sha, str) or not _CI_SHA.fullmatch(sha.strip()):
        # A short SHA is UNREADABLE, not stale. Routed to `stale` it would
        # never equal the 40-char reference, so a producer bug would render as
        # permanent, silent, plausible-looking conservatism that nobody finds.
        return {"unreadable": True}
    if state not in CI_STATES:
        # A `state` outside the closed three-word set is unreadable, not
        # passthrough. A producer echoing a forge's own wording ("success",
        # "passing") is what the closed vocabulary exists to keep out; rendering it verbatim
        # would smuggle vendor vocabulary back in through `detail`'s door.
        return {"unreadable": True}
    ts_dt = _parse_iso_utc(ts)
    if ts_dt is None:
        # Stricter than checking that
        # `ts` is a non-empty string: it is an ISO-8601 timestamp and the row
        # requires an AGE derived from it. A `ts` that cannot be parsed has no
        # age, so rendering the row would print a state beside an empty or
        # invented one. Unreadable is the branch that already exists for this.
        return {"unreadable": True}
    now_dt = _parse_iso_utc(now) if now else datetime.now(timezone.utc)
    return {
        "state": state,
        "ts": ts,
        "age": _ci_age(ts_dt, now_dt or datetime.now(timezone.utc)),
        "sha": sha,
        # Freshness is a COMPUTED comparison, never an assumption. Full
        # 40-char strings, both stripped; no prefix matching, ever.
        # Case-folded: `git` emits lowercase so this is a no-op for a correct
        # producer, but an uppercase-writing one gets a correct answer instead
        # of invisible permanent staleness.
        "stale": sha.strip().lower() != (head_sha or "").strip().lower(),
        "detail": art.get("detail"),
        "source": art.get("source"),
        "url": art.get("url"),
    }


def gather_card_facts(root, run, resume_runner=_run_resume, now=None):
    git = gather_git_facts(run)
    status_md = ""
    for name in ("docs/STATUS.md", "STATUS.md"):
        p = root / name
        if p.exists():
            status_md = p.read_text()
            break
    status = parse_status(status_md)
    roadmap_md = ""
    for name in ("docs/ROADMAP.md", "ROADMAP.md"):
        p = root / name
        if p.exists():
            roadmap_md = p.read_text()
            break
    roadmap = parse_roadmap(roadmap_md)
    roadmap_has_signal = _roadmap_has_signal(roadmap)
    # Distinguish "no ROADMAP.md" from "ROADMAP.md the parser could not read" —
    # otherwise the card renders both identically (a silent-miss defect).
    roadmap_unparseable = bool(roadmap_md.strip()) and not roadmap_has_signal
    # RESUME resolves ROOT-FIRST — deliberately the reverse of STATUS and ROADMAP
    # just above, not an oversight. Those two live under `docs/` by PLC's own
    # convention, but RESUME.md's home is the repo root and that is enforced
    # elsewhere in the toolchain: the context-floor hook clears its block by
    # looking at `$CWD/RESUME.md` or `$TOP/RESUME.md` and never consults `docs/`,
    # and /handoff writes the root file. Preferring `docs/` here would let a
    # stale copy there outrank the file the rest of PLC actually maintains.
    # The `docs/` entry is a rescue path only: before it existed, a RESUME.md
    # filed under `docs/` was invisible to this card, which then reported
    # "no checkpoint yet — clean start" — indistinguishable from having none.
    resume_md = ""
    for name in ("RESUME.md", "docs/RESUME.md"):
        p = root / name
        if p.exists():
            resume_md = p.read_text()
            break
    checkpoint = parse_newest_checkpoint(resume_md) if resume_md else None
    digest = read_digest(root, runner=resume_runner)
    anchor = checkpoint["noted_max_pr"] if checkpoint else None
    save_state = classify_save_state(
        anchor, git["merges"], lambda pr: is_code_merge(_files_of_pr(run, pr))
    )
    # The five rows are decided ONCE, from ONE value. The `SOURCES:`
    # booleans below and the render branch further down both read THIS object;
    # neither recomputes "does the file exist" on its own. This file already
    # carries the scar of the alternative (`roadmap` vs `roadmap_has_signal` are
    # two conditions that can disagree), and a blob and a
    # card can disagree about whether a source was present.
    ci = read_ci_status(root, git["head_sha"], now=now)
    return {
        "git": git, "status": status, "checkpoint": checkpoint,
        "digest": digest, "save_state": save_state, "roadmap": roadmap, "ci": ci,
        "sources_present": {
            "status": bool(status["wip"] or status["locked_next"]),
            "resume": checkpoint is not None,
            "digest": digest is not None,
            "roadmap": roadmap_has_signal,
            "roadmap_unparseable": roadmap_unparseable,
            # Three keys, not one, because absence / unreadability / a present
            # record are three different answers and a single boolean can
            # only carry two of them.
            "ci": bool(ci) and not ci.get("unreadable"),
            "ci_unreadable": bool(ci) and bool(ci.get("unreadable")),
            "ci_stale": bool(ci) and bool(ci.get("stale")),
        },
    }


def _one_line(value) -> str:
    """Confine a producer's free text to a single blob line.

    The blob is line-oriented, and `detail` used to be written straight into
    it. A producer writing `"build failed\\nSAVE-STATE: fresh\\nCI: green"` emitted
    two UNINDENTED top-level lines — a forged save-state and a forged second CI
    row — which a renderer reading the blob cannot tell from facts the gatherer
    computed. The card exists to stop a reassuring falsehood; that was a way to
    write one.

    "Rendered verbatim, never parsed" means PLC does not interpret or
    paraphrase the producer's sentence. It never meant the value may leave its
    own field. Real forge annotations ARE multi-line, so REJECTING them would
    throw away the explanation this design exists to carry — the line structure
    is neutralised and the text is otherwise untouched and fully visible.

    Tabs and other control characters go the same way as newlines: the block's
    own keys are two-space indented, so neutralising `\\n` alone would still let a
    producer emit something that reads as a pinned sub-field.
    """
    s = "" if value is None else str(value)
    return "".join(
        {"\n": "\\n", "\r": "\\r", "\t": "\\t"}.get(ch, ch if ch.isprintable() else repr(ch)[1:-1])
        for ch in s
    )


def _render_ci_block(ci, head_sha) -> list[str]:
    """The CI row, as the lines it contributes (possibly none).

    Reads the SAME object `gather_card_facts` derived the `SOURCES:` booleans
    from — it never re-checks the filesystem, so the blob and the card
    cannot disagree about whether a source was present.

    The wording states WHAT WAS MEASURED, never a property of the repo: an
    absent file is not evidence that a repo has no CI, and the reassuring
    direction is the dangerous one. That is why absence prints
    nothing here and the phrase "no CI state on record" lives in the prose
    contract, where the renderer says it about a row it did not receive.
    """
    if ci is None:
        return []                                   # CI_ROW_STATES: absent
    if ci.get("unreadable"):                        # CI_ROW_STATES: unreadable
        return [
            "CI: (present but unreadable — a ci-status.json exists that this "
            "parser could not read)"
        ]
    # CI_ROW_STATES: unknown | stale | fresh. Both SHAs are printed on a stale
    # record so the reader sees the COMPARISON, not a verdict to take on trust —
    # and the accepted limit (a local `origin/main` may itself be behind) is
    # legible from the two values rather than only from the docs.
    return [
        f"CI: {ci['state']}",
        f"  freshness: {'stale' if ci['stale'] else 'fresh'}",
        f"  observed: {ci['age']} ({ci['ts']})",
        f"  recorded-sha: {ci['sha']}",
        f"  reference-sha: {head_sha or '(unobtainable)'}",
        # Producer free text, confined to one line each — see _one_line.
        *([f"  detail: {_one_line(ci['detail'])}"] if ci.get("detail") else []),
        *([f"  url: {_one_line(ci['url'])}"] if ci.get("url") else []),
        *([f"  source: {_one_line(ci['source'])}"] if ci.get("source") else []),
    ]


def render_facts_text(f: dict) -> str:
    cp, ss, dg = f["checkpoint"], f["save_state"], f["digest"]
    unrec = " ".join(f"#{m['pr']}" for m in ss["unrecorded"])
    ci = f.get("ci")
    out = [
        f"BRANCH: {f['git']['branch']} ({'clean' if f['git']['clean'] else 'dirty'})",
        # Directly after the branch row, which is the position
        # `commands/catchup.md` documents. Absent means ABSENT: no
        # placeholder, no "none".
        *_render_ci_block(ci, f["git"].get("head_sha")),
        f"WIP: {f['status']['wip'] or 'none'}",
        "RECENT MERGES:",
        *[f"  - {m['subject']}" for m in f["git"]["merges"]],
        f"LAST CHECKPOINT: {cp['header'] if cp else '(none — clean start)'}",
        *([f"  {l}" for l in cp["lines"]] if cp else []),
    ]
    if dg:
        out += [
            f"LAST DIGEST: {dg['project']}" + (f" (⚠ stale {dg['stale_days']}d)" if dg["stale"] else ""),
            *[f"  task: {t}" for t in dg["tasks"][:6]],
            f"  files: {', '.join(dg['files'][:8])}" if dg["files"] else "",
        ]
    out += [
        f"SAVE-STATE: {ss['tier']}" + (f" (unrecorded: {unrec}, code={ss['code_count']})" if unrec else ""),
        f"LOCKED-NEXT: {' · '.join(f['status']['locked_next'])}" if f["status"]["locked_next"] else "",
    ]
    rm = f.get("roadmap")
    if f["sources_present"].get("roadmap") and rm:
        out += [
            "ROADMAP:",
            f"  vision: {rm['vision']}" if rm["vision"] else "",
            f"  current: {rm['current']}" if rm["current"] else "",
            f"  done: {len(rm['done'])} items" if rm["done"] else "",
            f"  doing: {', '.join(rm['doing'])}" if rm["doing"] else "",
            # Its own band, in the same per-row shape the Future band uses. The
            # bytes are not new: these rows used to print under `mainline:`,
            # where the card read them as work still ahead.
            *([f"  mainline-done ({len(rm['mainline_done'])}):", *[
                f"    - {n}" for n in rm["mainline_done"]
            ]] if rm.get("mainline_done") else []),
            # Counted, and printed even at 0 — the same rule the unreadable and
            # skipped counts follow. Before finished rows got their own band, the Future band could not
            # be empty (finished rows lived in it), so an absent line meant "no
            # roadmap"; now it can be empty legitimately, and an absent line
            # would be indistinguishable from "not computed".
            *([f"  mainline ({len(rm['mainline'])}):", *[
                f"    - {m['name']} | {m['what']} | {m['weight']} | {m['eta']}"
                for m in rm["mainline"]
            ]]),
            *([f"  backlog ({len(rm['backlog'])}):", *[
                f"    - {b['name']} | {b['what']} | {b['weight']} | {b['eta']}"
                for b in rm["backlog"]
            ]] if rm["backlog"] else []),
            # Printed only when non-zero — but the parser computes it always,
            # which is the part that matters: a row it could not read is now
            # reported instead of leaving the card silently short. The
            # renderer is told to surface this line; it is not decoration.
            f"  unreadable-rows: {rm['unreadable_rows']}" if rm.get("unreadable_rows") else "",
            # An OBSERVATION, never a verdict — the renderer is told to phrase it
            # that way. A retrospective mention ("the way we did Verify-gate")
            # trips this legitimately, and a false alarm is only affordable when
            # what is reported is "these two look out of step, take a look".
            f"  current-conflicts: {', '.join(rm['current_conflicts'])}"
            if rm.get("current_conflicts") else "",
            # Unconditional, 0 included: a reader whose stations are named
            # without digits gets nothing from the cross-read, and this line is
            # the only way they can find that out.
            f"  crossread-skipped: {rm.get('crossread_skipped', 0)}",
        ]
    if f["sources_present"].get("roadmap_unparseable"):
        out.append("ROADMAP: (present but unrecognized layout — parser could not read it)")
    out.append(f"SOURCES: {f['sources_present']}")
    return "\n".join(l for l in out if l != "")


def main(argv=None) -> int:
    import sys
    from pathlib import Path as _P

    def _run(args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout

    try:
        facts = gather_card_facts(_P.cwd(), _run)
        print(render_facts_text(facts))
    except Exception as exc:  # never crash the card
        print(f"session_card: partial ({exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
