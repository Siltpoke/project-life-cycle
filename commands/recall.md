---
description: Brief the current session from the most-recent PLC session digest for THIS repo (written automatically by the save_session Stop hook to ~/.claude/plc-session-data/). Read-only — surfaces where you left off (tasks in flight, files touched, tools used) and stops; never auto-starts work or edits files. PLC's native session-recall command (named /recall, not /resume, to avoid colliding with Claude Code's built-in /resume conversation-picker). Args: none = newest digest for the current repo; a YYYY-MM-DD or a file path = that specific digest.
---

# /recall — session briefing from the automatic save digest, PLC-native

The read half of PLC's automatic session save/recall pair. The `save_session` Stop hook writes
a mechanical digest of every session to `~/.claude/plc-session-data/` with **no typing**; `/recall`
reads the right one back and briefs you — PLC's own session-recall side.

> **Named `/recall`, not `/resume`, on purpose.** Claude Code ships a built-in `/resume` that reopens a
> past *conversation* (the session picker). PLC's command briefs from the mechanical digest — a different
> job — so it carries a distinct name to avoid shadowing or being shadowed by the native command.

**Boundary — two different continuity surfaces, do not conflate:**
- **`/recall` (this)** reads the *mechanical, out-of-repo, auto-written* digest (tasks/files/tools scraped
  from the transcript). Cheap, always-fresh, zero curation.
- **`RESUME.md` + SessionStart:resume** is the *curated, in-repo, human/LLM-written* moment doc (written by
  `/handoff`, auto-injected on resume). Higher-value, hand-authored.
  Use `/recall` for "what was I literally doing"; trust `RESUME.md` for "what matters + what not to retry".

## Interface

```
/recall                # newest digest for the CURRENT repo → briefing
/recall 2026-07-16     # the digest for that date (current repo) → briefing
/recall <path>         # read that specific digest file directly (teammate handoff)
```

## Flow (read-only — you MUST NOT edit files or start work)

The selection logic is a tested, **read-only** helper — do NOT re-derive it in prose. Run the
`resume` subcommand (it derives the current repo from the cwd, resolves the digest, and prints JSON;
it never writes):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/save_session.py" resume            # newest for this repo
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/save_session.py" resume 2026-07-16  # a date
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/save_session.py" resume /path/to.md  # explicit file
```
It prints `{"found": false}` or `{"found": true, "path", "project", "stale_days", "stale",
"cross_project"}`. (Do NOT pipe a Stop payload into the script or run it bare — that is the *write*
hook path; the `resume` subcommand is the read-only side. The subcommand keeps the name `resume`
because it is internal — only the user-facing command is `/recall`.)

1. **`found: false`** → say plainly "no PLC session digest for this repo yet — the save hook may not be
   installed; see `/init-harness`" and stop.
2. **`cross_project: true`** → no digest exists for this repo; name the fallback's `project` and let the
   user confirm before you brief from it (never silently cross projects — the classic wrong-project pick).
3. **`stale: true`** (`stale_days > 7`) → prefix the briefing with `⚠️ stale (N days old)`.
4. Read the `path`; any file under its **Files Modified** that no longer exists → flag `⚠️ missing`.
5. **Emit a fixed briefing** and STOP. Do not run anything, do not open files, do not begin the next task.

```
SESSION RESUMED  ·  <project>  ·  <digest date>  [⚠️ stale N days]
WHAT I WAS DOING   — the Tasks list (verbatim, most-recent last)
FILES TOUCHED      — Files Modified (⚠️ missing flagged)
TOOLS USED         — Tools Used line
NEXT               — "digest is mechanical; for curated next-step + what-NOT-to-retry, read RESUME.md"
```

## Non-goals

- Does NOT write, edit, delete, or start work — read-only, always. (The digest file is left untouched — its
  mtime is unchanged after a `/recall` run.)
- Reads only PLC's own digest dir — not any other tool's session files.
- Does NOT replace `RESUME.md` / the SessionStart:resume auto-injection — it complements them (see Boundary).
- No auto-firing; invoke manually at the start of a session when you want the mechanical recap.
