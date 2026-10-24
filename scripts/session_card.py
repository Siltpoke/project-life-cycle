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

# The ONE shared reconciliation module. /catchup reads it from here; /handoff invokes its
# CLI. Two callers, one code path, so the two commands cannot disagree about what "stale" means.
import handoff_reconcile as hr

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


def _unverified_state(check: str, cause: str) -> dict:
    """One shape for "a handoff exists and I could not check it", built in one place.

    There were three hand-copied literals of this dict — the unreadable-anchor branch, the
    no-git branch, and the no-runner branch — so a fourth consumer or a new key meant editing
    three sites and the third copy had already drifted a blank line out of shape.
    """
    return {"tier": "unverified", "rows": [], "exit_code": 4, "has_code": None,
            "unverified": [{"check": check, "cause": cause}]}


def classify_save_state(*, has_handoff, anchor, rec, files, anchor_absent_cause=None):
    """The SAVE-STATE row, derived from the ANCHOR the handoff writes.

    This replaced the previous derivation, which extracted `max(#N)` from the handoff's newest
    block and compared it against PR numbers in the last 8 subjects of `git log origin/main`.
    Two measured defects killed it. A handoff carrying no `#N` at all returned `unknown`, which
    `commands/catchup.md` rendered as "no checkpoint yet - clean start" over a correct, current
    handoff; and nothing in the old derivation could express where the WORKING TREE sat, so a
    checkout behind the upstream read as `fresh`. The second one was an ABSENT
    comparison rather than a wrong one, which is why more care with PR numbers could not fix it.

    `has_handoff` and `anchor` are separate arguments on purpose: "there is no handoff" and
    "there is a handoff I could not read" are opposite truths, and the old single `unknown`
    covered both. Only the first may render as a clean start.

    `files=None` means the code-vs-docs question could not be answered. It is NOT `files=[]`;
    turning "I could not look" into the verdict "docs only" is the substitution this phase
    exists to remove, so it yields `unverified` instead.

    `anchor_absent_cause` — WHO DECIDES WHICH KIND OF ABSENCE, stated because the name alone does
    not say it. `anchor=None` covers two situations with different causes: the handoff has no
    `snapshot:` line at all (every older handoff), or it has one that did not parse. **Telling
    them apart needs the block text, which this function does not have and deliberately does not
    take** — it is handed facts, not sources. So the CALLER decides, using
    `handoff_reconcile.snapshot_line_present`, and passes the sentence. Omitting it falls back to
    the absent-line wording, which is the right default for a caller that genuinely cannot tell.

    It was `_anchor_absent_cause` in the first version. The leading underscore said "internal",
    which was false in the only way that matters: the one caller that must pass it lives in
    another module. A private name on a parameter the contract requires is a claim about the API
    that the API contradicts (so: keep the parameter, drop the
    pretence).
    """
    anchor_absent_cause = (anchor_absent_cause
                            or "the handoff carries no `snapshot: HEAD <sha>` line")
    if not has_handoff:
        # DELEGATED, not decided here. The first version returned the string itself, which made
        # `classify_tier`'s `has_handoff` branch unreachable in production -- a path the module
        # offered and its only caller bypassed. One function owns the vocabulary or no function
        # does.
        return {"tier": hr.classify_tier(upstream_advance=None, has_code=None,
                                         has_handoff=False),
                "rows": [], "unverified": [], "exit_code": 0, "has_code": None}
    if anchor is None:
        # Two different situations, and reporting them with one sentence was wrong in the second:
        # the line may be absent (an older handoff), or
        # present and unparseable (a branch name carrying the format's own separator).
        return _unverified_state("anchor", anchor_absent_cause)
    if rec is None or rec.no_git:
        return _unverified_state("anchor", "no git repository to compare against")
    has_code = None if files is None else is_code_merge(files)
    unverified = [{"check": r.check, "cause": r.cause} for r in rec.unverified]
    exit_code = rec.exit_code

    # `files is None` means the range lookup was ATTEMPTED and failed, and it is not one of
    # `rec.rows` — so neither the cause list nor the exit status knew about it. The tier went
    # `unverified` while the `UNVERIFIED:` block stayed empty and the status stayed 0: a state
    # word with no cause and no signal, on the one path where that must not happen.
    # The guard is the reason it is reported HERE: this is the only place that knows the lookup was needed.
    #
    # Only when it was needed. With `upstream_advance == 0` the code question does not arise
    # (`classify_tier` returns `fresh` without consulting it), so inventing a cause there would
    # be the mirror defect — a cause for a check that was never asked.
    if files is None and rec.upstream_advance:
        unverified = unverified + [{
            "check": "changed-files",
            "cause": "the commits the upstream gained could not be read, so docs-only vs "
                     "code-touching could not be decided",
        }]
        exit_code = 4

    return {
        "tier": hr.classify_tier(upstream_advance=rec.upstream_advance, has_code=has_code),
        "rows": rec.rows,
        "unverified": unverified,
        "exit_code": exit_code,
        "has_code": has_code,
    }


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


def _clean_cell(text: str) -> str:
    """Strip markup from ANYWHERE inside a cell, not just its ends.

    The old form was `.strip().strip("`")`, which only touches the two ends of
    the span — so `**`p13`** —— ...` kept its interior closing backtick and
    rendered as ``p44` —— ...`` on the card.

    MODULE LEVEL, AND SHARED WITH `_milestone_table_rows`, as of the station-position change. It used
    to be nested inside `parse_roadmap`, so the two glyph readers in this file
    normalised differently and disagreed about the same bytes. MEASURED, not
    inferred: `| 1 | Name | what | **✅ done** |` was read as a finished milestone
    by the fisheye path and as NOTHING by the table fallback, because only one of
    them stripped bold before looking for the glyph. A whole-cell bold is exactly
    what a migrating author types, and the fallback is what runs when the fisheye
    parse yields nothing — so the disagreement was worst precisely where the
    fallback is the only reader.
    """
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).replace("`", "").strip()


def _bound_station(facts: dict, cleaned_name: str) -> str | None:
    """The station id whose `binds-to` names this row, or None.

    Compared against the CLEANED name, because that is the form every other consumer of
    this row already works with; comparing raw would make a row bind or not depending on
    whether somebody bolded it.
    """
    for sid, b in facts.get("blocks", {}).items():
        if _clean_cell(b["binds_to"]) == cleaned_name:
            return sid
    return None


def _station_facts(root: Path) -> dict:
    """Station plans, the active list, and which steps the corpus says are closed.

    NOTHING HERE PARSES EITHER FORMAT. The station-block grammar is read by
    `scripts/lib/station-blocks.awk` and the closure grammar by
    `scripts/closure-declaration.sh`, both shelled out to, because a Python copy of
    either would be a second implementation of a grammar this repo already ships one
    reader for — the encoder-divergence class the p36 design forbids by name.

    ONE shell-out SITE, not two, and that is why both commands go through the local `_sh`
    helper below. `scripts/invariants/session-card-no-network.sh` counts those sites and
    says in its own header that moving its baseline is a design decision belonging to a
    phase with a story. This is that phase and that story: the design defines a station's
    position as derived from the closure declarations (the closure design), so reading them is the
    feature rather than a convenience. That guard also refuses a mention of the module
    name it counts even inside a docstring — deliberately, since a prose mention hides a
    real one from its own arithmetic — which is why this paragraph does not spell it.

    DEGRADES, NEVER RAISES, AND SAYS WHICH. A missing reader, an unreadable corpus or a
    non-zero exit gives `available: False` with a reason, and the caller renders the
    position as unknown rather than as zero. Zero is a claim; unknown is the truth when
    the deriver could not run, and this phase exists because those two were the same
    thing on a card.
    """
    here = Path(__file__).resolve().parent
    awk_prog = here / "lib" / "station-blocks.awk"
    extractor = here / "closure-declaration.sh"
    corpus_lib = here / "lib" / "closure-corpus.sh"
    roadmap = next((root / n for n in ("docs/ROADMAP.md", "ROADMAP.md")
                    if (root / n).exists()), None)

    out: dict = {"blocks": {}, "active": [], "closed": {},
                 "available": False, "why": ""}
    if roadmap is None:
        out["why"] = "no ROADMAP.md"
        return out
    for needed in (awk_prog, extractor, corpus_lib):
        if not needed.exists():
            out["why"] = "reader missing: %s" % needed.name
            return out

    def _sh(argv: list[str]) -> tuple[int, str]:
        try:
            r = subprocess.run(argv, capture_output=True, text=True,
                               timeout=20, cwd=str(root))
            return r.returncode, r.stdout
        except Exception as exc:                       # noqa: BLE001 - degrade, never raise
            return 255, "%s: %s" % (type(exc).__name__, exc)

    rc, blocks_out = _sh(["awk", "-f", str(awk_prog), str(roadmap)])
    if rc != 0:
        out["why"] = "station-blocks.awk exited %d" % rc
        return out
    for line in blocks_out.split("\n"):
        f = line.split("\t")
        if f[0] == "BLOCK" and len(f) >= 4:
            out["blocks"][f[1]] = {"binds_to": f[2], "nsteps": int(f[3]), "steps": [],
                                   # Field 6 is the RAW `depends-on` value, `none` included.
                                   # Absent on an older parser, so it is read defensively
                                   # rather than indexed: a reader that crashes on a shorter
                                   # record turns a missing field into a missing card.
                                   "depends_on": f[5] if len(f) >= 6 else ""}
        elif f[0] == "STEP" and len(f) >= 3 and f[1] in out["blocks"]:
            out["blocks"][f[1]]["steps"].append(f[2])
        elif f[0] == "ACTIVE" and len(f) >= 2:
            out["active"].append(f[1])

    # The corpus half, through the shipped helper rather than a glob written here: what
    # counts as "the corpus" is defined once, in scripts/lib/closure-corpus.sh.
    script = (
        '. "$1" || exit 3\n'
        'files=$(closure_corpus_files "$2") || exit 4\n'
        '[ -n "$files" ] || exit 0\n'
        'closure_step_records "$3" $files\n'
    )
    rc, recs = _sh(["/bin/bash", "-c", script, "_", str(corpus_lib),
                    "docs", str(extractor)])
    if rc != 0:
        out["why"] = "closure corpus read exited %d" % rc
        return out
    for line in recs.split("\n"):
        tok = line.split("\t")[0].strip()
        if not tok or "." not in tok:
            continue
        sid, _, num = tok.rpartition(".s")
        if sid and num.isdigit():
            out["closed"].setdefault(sid, set()).add(num)

    out["available"] = True
    return out


def station_state(facts: dict, sid: str) -> dict:
    """The three states, from the three sources the design gives them.

    `done` is fraction-equals-one and nothing else: DISTINCT closed steps equal the
    declared count, with the count at least 1. A step touched by two phases is one step
    done. `doing` is the declared active list and is never inferred from a trace.
    `future` is the difference and has no source of its own.
    """
    b = facts["blocks"].get(sid)
    if b is None:
        return {"state": "unknown", "closed": 0, "total": 0, "position": None}
    total = b["nsteps"]
    closed = len({n for n in facts["closed"].get(sid, set()) if n in b["steps"]})
    if not facts["available"]:
        return {"state": "unknown", "closed": 0, "total": total, "position": None}
    if total >= 1 and closed == total:
        state = "done"
    elif sid in facts["active"]:
        state = "doing"
    else:
        state = "future"
    return {"state": state, "closed": closed, "total": total,
            "position": "%d/%d" % (closed, total)}


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
        # `_clean_cell`, not `.lstrip()`: one normalisation for every glyph test in
        # this file (the station-plan work). See that function for the measurement.
        glyph = next((g for g in _LEGEND_GLYPHS if _clean_cell(cells[-1]).startswith(g)), None)
        if glyph is None:
            continue  # header / separator / non-milestone table row
        name = _clean_cell(f"{cells[0]} {cells[1]}")
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


def parse_roadmap(md: str, facts: dict | None = None) -> dict:
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
            out.append({"name": _clean_cell(cells[0]), "what": cells[1].strip(),
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
    facts = facts if facts is not None else {"blocks": {}, "active": [], "closed": {},
                                             "available": False, "why": "not supplied"}
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
        cleaned = _clean_cell(cells[0])
        # ------------------------------------------------------------------ T7b, THE SPLIT
        # A row some plan block BINDS TO takes its state from the derivation and from the
        # declared active list — the glyph in its name cell plays no part at all. Every
        # other row keeps the inclusive test below, untouched.
        #
        # THIS IS A SPLIT AND NOT A DELETE, and the plan says so because deleting was the
        # first proposal. Measured on a real roadmap: most finished rows
        # carry the done glyph INSIDE the name cell and 0 carry it leading, so removing the
        # inclusive test zeroes `mainline_done` for all of them — and no test would have gone
        # red, because the new mechanism is only exercised by rows that have a plan block
        # and those rows never will (a station id exists only where a block does).
        #
        # The boundary is `binds-to`, nothing else. Not the glyph, not the position in the
        # table, not whether the row looks new.
        sid = _bound_station(facts, cleaned)
        if sid is not None:
            st = station_state(facts, sid)
            if st["state"] == "done":
                mainline_done.append(cleaned)
                continue
            if st["state"] == "doing":
                doing.append(cleaned)
                continue
            if st["state"] == "unknown":
                # The deriver could not run. Not future, not done — undecidable, which this
                # parser already has an honest bucket for.
                undecidable += 1
                continue
            future_rows.append(cells)
            continue
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
        # Per-station derived state, emitted whether or not any station exists: an absent
        # key and an empty one read differently to a renderer, and "no stations yet" is a
        # real answer.
        "stations": {
            sid: dict(station_state(facts, sid),
                      binds_to=_clean_cell(b["binds_to"]),
                      depends_on=b.get("depends_on", ""))
            for sid, b in facts.get("blocks", {}).items()
        },
        "station_facts_available": bool(facts.get("available")),
        "station_facts_why": facts.get("why", ""),
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


def gather_card_facts(root, run, resume_runner=_run_resume, now=None, run_git=None, refresh=False):
    """`run_git` is the returncode-aware runner this needs and `run` cannot be.

    It is NOT defaulted to the real one. A caller that does not inject it gets `unverified`
    with "no git runner was provided" as the cause -- fail-closed AND visible, rather than a
    default that quietly executes git in whatever directory the process happens to be in and
    lets a test pass for the wrong reason. Production injects it in `main()`.
    """
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
    roadmap = parse_roadmap(roadmap_md, _station_facts(root))
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
        # `and p.read_text().strip()`, not just `exists()`: an EMPTY root RESUME.md used to
        # shadow a real `docs/RESUME.md`, so the tier became `no-handoff` — which this makes the
        # one tier allowed to say "clean start" — while a handoff sat in the rescue location.
        # The shadowing predates the current work; what is new is that it can now produce exactly the
        # earlier sentence.
        if p.exists():
            body = p.read_text()
            if body.strip():
                resume_md = body
                break
    checkpoint = parse_newest_checkpoint(resume_md) if resume_md else None
    digest = read_digest(root, runner=resume_runner)
    # The anchor is the sha `/handoff` writes, read out of the block
    # `parse_newest_checkpoint` already selected. The block is handed over rather than
    # re-selected: a second selector could pair one block's header with another block's sha.
    anchor = rec = files = None
    block = ""          # bound unconditionally: the cause-selection below reads it on every path
    if checkpoint:
        block = "\n".join([checkpoint.get("header") or ""] + list(checkpoint.get("lines") or []))
        anchor = hr.read_anchor(block)
    if anchor is not None and run_git is not None:
        rec = hr.reconcile(anchor, run_git, refresh=refresh)
        files = hr.files_changed(run_git, rec.upstream_range)
    if anchor is not None and run_git is None:
        save_state = _unverified_state(
            "anchor", "no git runner was provided to gather_card_facts")
    else:
        save_state = classify_save_state(
            has_handoff=bool(resume_md), anchor=anchor, rec=rec, files=files,
            anchor_absent_cause=(
                "the handoff's `snapshot: HEAD <sha>` line could not be parsed"
                if hr.snapshot_line_present(block) else
                "the handoff carries no `snapshot: HEAD <sha>` line"),
        )
    save_state["anchor"] = anchor
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
    # The ANCHOR block. One call produces both comparisons, so `fresh` can never be
    # printed without the `checkout` row beside it: that is held structurally rather than by
    # a rule someone has to remember.
    _OUTCOME_GLOSS = {
        "unchanged": "",
        "ahead": "the {subj} has commits the anchor lacks",
        "behind": "the {subj} lacks commits the anchor has",
        "diverged": "each side has commits the other lacks",
        "unavailable": "",
        "not-attempted": "",
    }
    _SUBJ = {"checkout": "working tree", "upstream": "upstream", "remote": "real remote"}

    def _anchor_rows():
        a, rows = ss.get("anchor"), ss.get("rows") or []
        if not a and not rows:
            return []
        head = "ANCHOR: HEAD {} · {} · {}".format(
            a.sha[:7] if a else "-", (a.branch if a else None) or "-",
            (a.taken_at if a else None) or "-")
        lines = [head]
        for r in rows:
            n = r.subject_advance if r.outcome == "ahead" else r.anchor_only
            if r.outcome == "diverged":
                dist = "subject +{}, anchor +{}".format(r.subject_advance, r.anchor_only)
            elif r.outcome in ("ahead", "behind") and n is not None:
                dist = "{} commit{}".format(n, "" if n == 1 else "s")
            else:
                dist = ""
            note = r.cause or _OUTCOME_GLOSS.get(r.outcome, "").format(
                subj=_SUBJ.get(r.check, r.check))
            # `_one_line`, not str(): a cause is a producer's free text and the blob is
            # line-oriented. This is the same defect class a cross-family review caught in this
            # file once already (see _one_line's own docstring) -- and it was reproduced here
            # before the test below went red. No reachable input carries a newline today; that
            # is luck, and luck is not a property.
            lines.append("  {:<10} {:<14} {:<22} {}".format(
                _one_line(r.check), _one_line(r.outcome), _one_line(dist),
                _one_line(note)).rstrip())
        return lines

    def _unverified_rows():
        uv = ss.get("unverified") or []
        if not uv:
            return []
        # One line per check, each carrying its OWN cause. Never one collapsed bucket: as checks
        # multiply, a single `unverified` stops saying which one could not run.
        return ["UNVERIFIED:"] + [
            "  - check: {:<10} cause: {}".format(_one_line(u["check"]), _one_line(u["cause"]))
            for u in uv]
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
        f"SAVE-STATE: {ss['tier']}",
        *_anchor_rows(),
        *_unverified_rows(),
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
            # ------------------------------------------------------------ p36 T7c
            # One `station:` line per plan block, and a `station-facts:` line saying
            # whether the derivation ran at all.
            #
            # THE DERIVATION'S AVAILABILITY IS PRINTED WHETHER OR NOT IT SUCCEEDED. An
            # absent line and a successful run would otherwise look the same, and the
            # difference is the whole point of the phase: `0/3` is a claim about history,
            # `-` is the truth when nothing could be read.
            #
            # `blocked-by:` AND `next:` ARE SEPARATE FIELDS. Merging them would let a
            # reader take a dependency for a priority — a station can be blocked by work
            # nobody plans to start, and the roadmap declares dependencies, never order
            #. `next:` is deliberately NOT emitted here: no source in this format
            # declares it, and inventing one from dependency order is the thing the design says
            # this document does not do. The field is named in this comment so the next
            # person meets the reason rather than reading the absence as an oversight.
            *([
                "  station-facts: available"
                if rm.get("station_facts_available")
                else f"  station-facts: UNAVAILABLE ({rm.get('station_facts_why') or 'no reason recorded'}) — positions below read `-`, which is not the same as 0"
            ] if rm.get("stations") else []),
            *([f"  stations ({len(rm['stations'])}):", *[
                "    - %s | steps %s | %s | blocked-by: %s | binds-to: %s" % (
                    sid,
                    st["position"] if st.get("position") else "-",
                    st["state"],
                    st.get("depends_on") or "-",
                    st.get("binds_to", ""),
                )
                for sid, st in sorted(rm["stations"].items())
            ]] if rm.get("stations") else []),
        ]
    if f["sources_present"].get("roadmap_unparseable"):
        out.append("ROADMAP: (present but unrecognized layout — parser could not read it)")
    out.append(f"SOURCES: {f['sources_present']}")
    return "\n".join(l for l in out if l != "")


def main(argv=None) -> int:
    import sys
    from pathlib import Path as _P

    # `argv=None` means sys.argv[1:], not "no flags". It used to mean the latter by accident --
    # the parameter was declared and never read -- so `--refresh` was unreachable from the only
    # surface a user has, while being fully implemented and tested one layer down.
    args = list(sys.argv[1:] if argv is None else argv)
    refresh = False
    for a in args:
        if a == "--refresh":
            refresh = True
        else:
            # Refused, not ignored. A silently-dropped flag is a request the user believes was
            # honoured, and here it would mean a confident offline card where a live check was
            # asked for.
            print("session_card: unknown argument %r (known: --refresh)" % a, file=sys.stderr)
            return 2

    def _run(args):
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout

    try:
        # `run_git=hr.run_git` is the PRODUCTION injection, and it is load-bearing rather than
        # tidy. `gather_card_facts` deliberately does not default it (a default would let a test
        # pass by running git in whatever directory the process is in), so a `main()` that forgets
        # it leaves the whole reconciliation reporting `unverified / no git runner was provided`
        # -- fail-closed and honest, and completely non-functional. That is exactly what shipped
        # for one commit, and only running the real command found it.
        facts = gather_card_facts(_P.cwd(), _run, run_git=hr.run_git, refresh=refresh)
        print(render_facts_text(facts))
    except Exception as exc:
        # STILL never a traceback -- but no longer exit 0. Nothing was printed, so returning 0
        # would report a verified-clean run for a card that does not exist. "Never crash" was
        # always about not raising at the user; it was never a reason to claim success.
        print(f"session_card: could not produce a card ({exc})", file=sys.stderr)
        return 2
    # 0 when no check was ATTEMPTED and left inconclusive; 4 when one was. A `not-attempted`
    # row -- the offline `remote` check on every default run -- does not count, or the status
    # would fire every single time and carry no information.
    #
    # 4, NOT 3. `scripts/plc-python.sh` already exits 3 for "no working Python interpreter",
    # `commands/catchup.md` documents that 3, and the wrapper `exec`s this script so this
    # number passes straight through to the caller. One number with two meanings is the defect
    # class this work exists to remove; reproducing it in its own exit status was the trap.
    return int(facts["save_state"].get("exit_code", 0) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
