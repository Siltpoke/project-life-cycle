# Handoff-snapshot brief — the PLC-native mid-session continuity prompt

This is the discipline behind `commands/handoff.md`: write a **schema-enforced, MOMENT-tense**
mid-session continuity snapshot to `RESUME.md` (the moment half) and, *only when warranted*, a durable
**journal FACT** (the persistent half). It is the third "give the guts a button" command — the PLC-owned
button that replaces reaching for an external end-of-session tool, symmetric with
`/research` and `/review`.

**Delegation — this brief does not fork the journal schema.** The durable half reuses
`references/journal-schema.md`'s FACT schema verbatim; the moment half writes `RESUME.md`, whose shape is
consumed by the SessionStart:resume hook (`hooks/inject-resume.sh.template`). When this brief and
`journal-schema.md` disagree on the FACT shape, `journal-schema.md` wins — fix this brief to match, never
the reverse. This brief only **operationalizes** the write into a dispatchable prompt.

**Why a snapshot at all.** Capture the *invisible* knowledge — what `git` + a test run can't cheaply
recover. A clean session renders light (core fields only); a messy one renders full. The snapshot exists
so the next session (or the next you) resumes with **zero re-derivation**, instead of leaning on
end-of-session discipline.

---

## The snapshot schema

Eight fields, split **core (required)** vs **progressive (omit-if-empty)**. MOMENT-tense throughout.

### Core — required; **refuse to write** the snapshot if any cannot be truthfully filled

1. **Current task + phase** — "I am [X], in [phase]." The orientation anchor; disambiguates a bare
   branch name.
2. **Next concrete action** — the single most load-bearing field: the in-flight pointer. One concrete
   next step, not a plan.
3. **Staleness anchor** — `HEAD <sha> · <branch> · <ISO-timestamp>` captured at write-time. Lets a
   resuming session *trust* the snapshot rather than re-audit, and detect drift by diffing against the
   current HEAD.

### Progressive — render only when non-empty; an empty field is **omitted entirely**, never a literal "None" line

4. **State so far** — logically-done + *uncommitted* work, as a pointer not a transcript. `git` is the
   source of truth for the mechanical file list; this field carries only what git can't show (e.g. "the
   refactor is applied but the callers aren't migrated yet").
5. **Decisions + rationale** — *why* the current approach. If the session reasoned through no explicit
   decision, write **"no explicit decision recorded"** — never an invented post-hoc justification.
6. **What NOT to retry** — failed approaches + why they failed. The highest-value, lowest-coverage field.
   **Actively scan** for it: reverted edits, abandoned branches, "that didn't work" signals — do not
   merely summarize forward progress. Repeating a failed approach costs a whole edit→run→observe loop,
   not just thinking.
7. **Blockers / open questions.**
8. **Gotchas / context** — env quirks, flaky tests, non-obvious constraints.

### MOMENT-tense rule

Record the moment ("I just did X; next is Y"), **never** the state ("the system does X"). A STATE-tense
snapshot rots silently as work continues and becomes a lie. The moment + the staleness timestamp is
honest about being a point-in-time capture.

### Rendered shape (illustrative, not rigid)

```markdown
# RESUME — <date> · <milestone> (<phase status line>)

> snapshot: HEAD <sha> · <branch> · <ISO-ts>        ← staleness anchor (core 3)

## Now
I am <task>, in <phase>.                             ← core 1
**Next:** <next concrete action>                     ← core 2

## State so far        (progressive — omit the whole section if empty)
- <uncommitted / logically-done pointer>

## Decisions           (progressive)
- <decision> — <why>     |  "no explicit decision recorded"

## What NOT to retry     (progressive)
- <failed approach> — <why it failed>

## Blockers / Gotchas    (progressive — fields 7 + 8, co-rendered)
- <blocker or gotcha>
```

The snapshot **overwrites** the prior one in `RESUME.md` — it does not append. (RESUME is the current
moment; history lives in the journal.) If `RESUME.md` does not yet exist (first `/handoff` in a project),
**create it** with the snapshot.

## Generation-time self-validation

Enforcement lives **here, at the point the artifact is born** — not in a downstream close-gate grep. A
grep can only check that field headers are *present* (trivially true from any stale prior snapshot); it
cannot catch the two real failure modes (fabrication, staleness), and a green-but-blind gate launders
confidence. Run these four checks **before writing**:

1. **Core check** — are all 3 core fields truthfully fillable? If any is not → **refuse to write**;
   surface which core field is unresolvable. No partial-core snapshot.
2. **Fabrication guard** — for each progressive field, is the content *actually grounded in this
   session*? If a field would require inventing rationale → mark it absent ("no explicit decision
   recorded") rather than fabricate. **Fabrication is worse than empty.**
3. **Progressive prune** — drop every empty progressive field; never emit a "None" placeholder.
4. **Staleness stamp** — compute the anchor: `git rev-parse HEAD`, `git rev-parse --abbrev-ref HEAD`,
   and a timestamp. If not in a git repo / no HEAD resolvable → record `no-git` and still write core
   fields 1-2.

## The conditional journal FACT

The durable half. The FACT schema already exists (`references/journal-schema.md` §FACT —
`Date / Decision / Why / Backing / Rejected / Gotcha? / Source`) and its `Date / Decision / Why / Backing`
subset is enforced by `phase-done`'s grep. Append a FACT to `docs/journal.d/<date>-<branch-slug>.md`
**only when** the session produced a non-derivable decision or gotcha worth persisting. A zero-decision
session writes **no FACT** — skipping is the correct outcome, emit no warning. The same "fabrication worse
than empty" law applies: do not manufacture a FACT to look thorough.

**Mid-session field applicability (the one place the reuse bends — field *presence*, never a schema
fork).** `Source` (`<sha>:<path the working doc had BEFORE archival>`) and `Rejected` are **track-close
artifacts**: mid-session, before any archival, `Source` has no pre-archival path to point at. Mark them
**absent** on a mid-session FACT rather than fabricate one — the fabrication guard outranks a rote
"all-fields-required" reading. The grep-enforced subset (`Date / Decision / Why / Backing`) is always
truthfully fillable when a real decision occurred, so a mid-session FACT still satisfies `phase-done`
honestly; it is a genuine journal entry, not a gate-gaming stub.

## Commit behavior

Write `RESUME.md` (+ the conditional FACT), then commit **where those paths are tracked**. In a repo where
`RESUME.md` / `docs/` are gitignored, the writes
are **local files**: report the local-only reality ("wrote RESUME.md locally; gitignored, not committed"),
**never a phantom "committed" claim**. Authored generically so downstream projects (tracked docs) get a
real `docs(handoff): snapshot` commit.

## Not this brief's job

- **NOT the phase-delivery handoff** — this is a mid-session *continuity* snapshot (`RESUME.md` + conditional FACT), not the retired standalone phase-delivery handoff doc / PR-body appendix (`references/handoff-template.md`). Same word, different artifact; do not conflate.
- **Modifying the SessionStart:resume hook** — this brief writes what the existing hook already reads;
  the hook is untouched.
- **Auto-firing** — `/handoff` is manual only; no context-pressure / phase-boundary trigger.
- **Replacing `/save-session`** — distinct artifact (in-repo, MOMENT-tense, schema-enforced); no
  migration, no deprecation of the external command.
- **Adding a close-gate grep for the RESUME snapshot** — enforcement is generation-time (above). The
  journal FACT half keeps its existing `phase-done` grep; the moment half is validated at generation.
- **Forking the FACT schema** — the durable half reuses `journal-schema.md`; that file wins on any
  disagreement.
