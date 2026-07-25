#!/usr/bin/env python3
"""session_card.py — deterministic fact-gatherer for the /catchup welcome-back card.

Reads git + RESUME.md + PLC session digest (+ STATUS.md if present) and prints a
raw-facts blob for the /catchup prose command to render. Read-only; never writes.
Adapted from a prior TypeScript fact-gatherer, for PLC (python3, digest reuse,
RESUME dual-format, optional STATUS).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

_CODE_PATH = re.compile(r"^(src|tests|scripts|\.githooks)/|^public/static/|\.(ts|tsx|js|jsx|cjs|mjs)$")
_CODE_FILE = re.compile(r"^(package\.json|bunfig\.toml|tsconfig.*|biome\.json|\.dependency-cruiser\.cjs)$")
_PR_TRAILING = re.compile(r"\(#(\d+)\)\s*$")
_PR_INLINE = re.compile(r"#(\d+)")


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
    return {"branch": branch, "clean": clean, "merges": merges}


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


def _table_rows(section_text: str) -> list[list[str]]:
    """First markdown table in a section body, as a list of cell-lists.

    Skips the header row and the '|---|' separator row STRUCTURALLY (by
    position + character-class, never by matching header words), so it
    stays language-agnostic.
    """
    lines = section_text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip().startswith("|")), None)
    if start is None:
        return []
    rows = []
    for l in lines[start:]:
        if not l.strip().startswith("|"):
            break
        rows.append(l)
    if len(rows) < 2:
        return []
    body_rows = rows[1:]  # drop header row (position 0)
    if body_rows and set(body_rows[0].strip()) <= set("-:| "):
        body_rows = body_rows[1:]  # drop separator row (all dashes/colons/pipes/space)
    return [[c.strip() for c in r.split("|")[1:-1]] for r in body_rows]


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
    mandates — read as a fallback when the emoji-fisheye parse yields nothing."""
    rows = []
    for line in md.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.split("|")[1:-1]]
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
    would silently split them (reviewer forward-look)."""
    return bool(rm["vision"] or rm["mainline"] or rm["doing"] or rm["done"])


def parse_roadmap(md: str) -> dict:
    """Fact-gatherer for docs/ROADMAP.md's fisheye view.

    Parses by emoji prefix + positional structure only — never by matching
    header words — because this repo holds its tracked source and tests to
    ASCII, while the real
    docs/ROADMAP.md may use CJK header labels; that's fine, the parser never
    looks at the label text, only its position relative to '**bold**' markers
    and '## <emoji>' section starts.
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

    def _table_dicts(cells_rows: list[list[str]]) -> list[dict]:
        out = []
        for cells in cells_rows:
            if len(cells) == 4:
                name = re.sub(r"\*\*(.+?)\*\*", r"\1", cells[0]).strip().strip("`").strip()
                out.append({"name": name, "what": cells[1], "weight": cells[2], "eta": cells[3]})
        return out

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
            return []
        has_table = any(l.strip().startswith("|") for l in body.split("\n"))
        if has_table:
            return _table_dicts(_table_rows(body))
        return [{"name": item, "what": "", "weight": "", "eta": ""} for item in _dotlist(emoji)]

    done = _dotlist("✅")
    backlog = _table_or_dotlist("\U0001f5c2")

    doing_body = _section_by_emoji(md, "\U0001f504")
    # Same line-leading rule as above: only a bold span at the very start of a
    # line is a real item name. A mid-sentence bold (a forward-reference to a
    # later section, e.g. "...done before we can start **Other Thing**.") is
    # NOT a second doing item — collecting every bold span in the section
    # fabricated phantom entries out of those forward references.
    doing = []
    for l in doing_body.split("\n"):
        if not l.startswith("**"):
            continue
        m = re.match(r"\*\*(.+?)\*\*", l)
        if m:
            doing.append(m.group(1).strip().strip("`").strip())
    if not doing and doing_body:
        doing = [p.strip() for p in doing_body.split("·") if p.strip()]

    mainline = _table_dicts(_table_rows(_section_by_emoji(md, "\U0001f6e3")))

    fisheye = {
        "vision": vision, "current": current,
        "done": done, "doing": doing,
        "mainline": mainline, "backlog": backlog,
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
            "mainline": t_mainline, "backlog": [],
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


def gather_card_facts(root, run, resume_runner=_run_resume):
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
    resume_p = root / "RESUME.md"
    checkpoint = parse_newest_checkpoint(resume_p.read_text()) if resume_p.exists() else None
    digest = read_digest(root, runner=resume_runner)
    anchor = checkpoint["noted_max_pr"] if checkpoint else None
    save_state = classify_save_state(
        anchor, git["merges"], lambda pr: is_code_merge(_files_of_pr(run, pr))
    )
    return {
        "git": git, "status": status, "checkpoint": checkpoint,
        "digest": digest, "save_state": save_state, "roadmap": roadmap,
        "sources_present": {
            "status": bool(status["wip"] or status["locked_next"]),
            "resume": checkpoint is not None,
            "digest": digest is not None,
            "roadmap": roadmap_has_signal,
            "roadmap_unparseable": roadmap_unparseable,
        },
    }


def render_facts_text(f: dict) -> str:
    cp, ss, dg = f["checkpoint"], f["save_state"], f["digest"]
    unrec = " ".join(f"#{m['pr']}" for m in ss["unrecorded"])
    out = [
        f"BRANCH: {f['git']['branch']} ({'clean' if f['git']['clean'] else 'dirty'})",
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
            *(["  mainline:", *[
                f"    - {m['name']} | {m['what']} | {m['weight']} | {m['eta']}"
                for m in rm["mainline"]
            ]] if rm["mainline"] else []),
            *([f"  backlog ({len(rm['backlog'])}):", *[
                f"    - {b['name']} | {b['what']} | {b['weight']} | {b['eta']}"
                for b in rm["backlog"]
            ]] if rm["backlog"] else []),
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
