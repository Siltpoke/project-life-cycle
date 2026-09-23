# Step -> enforcement: what actually holds each rule up

This skill states many things you must do. Some of them are held up by code that fails when you skip
them. Some are held up by nothing at all. **Until this file existed, those two groups looked
identical when you read the skill**, and the only way to tell them apart was to read the enforcing
scripts yourself.

This file is the map. It is not a defect list.

## How to read this

Rows sit in one of three bands, and **the band changes what the row means**:

- **Band A — nothing enforces this.** The skill requires it; no gate, hook, or CI job checks it. If
  you skip it, everything stays green.
- **Band B — something enforces this, and that something says it cannot be relied on.** A check
  runs. Its own source or documentation states that it fails open, is best-effort, or cannot decide
  the thing it appears to decide. A green run is not evidence the rule held.
- **Band C — the check is sound, but it covers less than the surrounding prose suggests.** These are
  **honest disclosures somebody wrote on purpose**, not bugs. They are here because a limit written
  in one file's comments is invisible to a reader of another file.

Band A is the one that means "you are on your own." Band B is the one that most often produces false
confidence, because a named enforcer reads as a working enforcer. Band C is the one you should be
least alarmed by and most precise about.

**Counts are reported per band and never summed.** Adding them produces a number that invites
"how bad is it", which is the wrong question — a band-C disclosure and a band-A hole are not units of
the same thing.

- Band A rows: **14**
- Band B rows: **12**
- Band C rows: **11**

## What this file does not do

**This table does not verify that a row's claim is true.** It records what the skill's own text says
about enforcement, checked by hand at the cited line. Whether the enforcer named in a row still
enforces what the row claims is not checked by anything — an enforcer could be changed or deleted and
its row would go stale silently. Re-deriving each row from the enforcing code is a separate job.

**A gap in a file that is not on either list below is not watched at all.** If a new unenforced
requirement appears somewhere outside both lists, nothing here will say so, and **the lists are what
have to change** for it to become visible.

## Fingerprinted files

Changing bracketed text in these files without updating this table makes the gate go red. This is
the only automatic protection this table has.

- `skills/project-lifecycle/SKILL.md` — two bracketed regions: the Definition of Done, and the run
  from Per-Phase Workflow through Red Flags. Text **outside** those brackets in the same file is not
  fingerprinted.

## Listed but NOT fingerprinted

These files carry rows in the table above. **Nothing checks whether their text still says what the
row claims.** They are named here so a reader can see where the table's rows come from, and so the
next person to widen the fingerprint knows what the candidates are — not because they are protected.

- `skills/project-lifecycle/references/close-gate.md` — **14 rows, the largest single block**
- `skills/project-lifecycle/references/kickoff-confirmation.md`
- `skills/project-lifecycle/references/comprehension-co-discovery.md`
- `skills/project-lifecycle/references/cognition.md`
- `skills/project-lifecycle/references/retention.md`
- `skills/project-lifecycle/references/cadence.md`
- `skills/project-lifecycle/references/agent-chats-registry.md`
- `skills/project-lifecycle/references/harness-primitives.md`
- `skills/project-lifecycle/references/review-record.md`

**So: 13 of the rows above sit behind a gate; 23 do not.** That split is not a stage on the way to
full coverage — it is the current, deliberate state, chosen because both candidate files change
often enough (measured over 60 days: 76 commits to `SKILL.md`, 39 to `close-gate.md`) that a
whole-file fingerprint would fire on ordinary edits, and a gate that fires on ordinary edits gets
routed around. Widening it means bracketing regions inside `close-gate.md`, where the rows are
spread across sections hundreds of lines long and every bracket boundary would be an arbitrary
choice.

---

## Band A — nothing enforces this

If you skip one of these, no gate fails, no hook fires, no CI job goes red. The risk receiver column
is blank on purpose: **there is nobody**. That blankness is the finding.

| required step / claim | band | enforcer | actual guarantee | known non-guarantee | risk receiver | source |
|---|---|---|---|---|---|---|
| `user-story.md` for a user-observable phase | A | none | none | the phase can close without a story, so the acceptance verifier has nothing to test against | nobody | `SKILL.md:119` |
| Track A / Track B smoke artifacts | A | none | none | a phase can be declared done with neither checklist nor e2e spec | nobody | `SKILL.md:119` |
| the acceptance verifier ran | A | none | none | its absence is indistinguishable from a clean run | nobody | `SKILL.md:119` |
| ADR for a decision passing the 3-criteria gate | A | none | none | a hard-to-reverse decision can ship with no record of what was rejected | nobody | `SKILL.md:119` |
| cognition capture | A | none | none | the "why" is lost with no signal that it was lost | nobody | `SKILL.md:119` |
| one journal entry per task | A | none | the gate reads the newest journal fragment | it does not check there is one per task; N-1 tasks can have none | nobody | `SKILL.md:171` |
| orphan `[DEBUG-` log cleanup | A | none | none | "enforced by nothing but the model" in the skill's own words | nobody | `SKILL.md:182` |
| the explanatory prose behind the `careful` miss markers | A | none | the four markers are required | the prose above them is the user's language and is not checked | nobody | `kickoff-confirmation.md:143` |
| tamper-resistance of the comprehension round | A | none | none | tamper-resistance is via incentive, not enforcement; zero penalty for a gap | nobody | `comprehension-co-discovery.md:36` |
| `test_command` and `test_evidence_inputs` agree | A | none | each is read on its own | nothing checks they agree; the failure is silent in both directions | nobody | `close-gate.md:151` |
| the embedded canonical-gate example stays in sync with the real gate | A | none | none | it is a different gate variant and cannot be byte-compared, so nothing was watching it | nobody | `close-gate.md:262` |
| AC-reference discipline for journal / review-finding / evidence-row | A | none | the test-name kind ships | the other three link-bearing kinds are unshipped (filed) | nobody | `close-gate.md:1388` |
| the grandfathering baseline shrinks over time | A | none | what remains is printed every run | nothing forces it to shrink; printing is the whole mitigation | nobody | `close-gate.md:1595` |
| `turns` / `tokens_est` / `cognition_loaded` accuracy | A | none | none | all three are self-reported estimates | nobody | `cognition.md:341` |

## Band B — an enforcer exists, and it says it cannot be relied on

Something runs. Its own text says a green result is not proof. **The risk receiver here is whoever
reads the enforcer's name and concludes the rule is held.**

| required step / claim | band | enforcer | actual guarantee | known non-guarantee | risk receiver | source |
|---|---|---|---|---|---|---|
| never `--no-verify`, never push direct to main | B | `hooks/guard.sh` | a speed bump on the command string | fails open; lexical analysis of a shell command cannot decide what the command will do (config, aliases, substitution, quoting) | whoever reads "guard" as a wall | `SKILL.md:5` |
| an enumerated task list exists before work starts | B | `hooks/tasklist-first.sh` | blocks once, then reports `UNVERIFIED` | on hosts where it cannot verify, it reports enforcement it is not performing | whoever reads an `UNVERIFIED` line as a pass | `SKILL.md:104` |
| the pre-push gate runs on every push | B | `.git/hooks/pre-push` | rejects an incomplete `feat/phase-*` push | not un-bypassable: `git push --no-verify` skips every pre-push hook | whoever treats the local hook as the last line | `SKILL.md:119` |
| unattended runs stay inside the fence | B | post-round out-of-fence diff check | one real wall after each round | the `PreToolUse` hook fails open and is telemetry, not a wall | whoever counts the hook as a second wall | `SKILL.md:434` |
| protected headings survive the retention drain | B | drain protection declaration | protects declared headings when well-formed | malformed protection fails OPEN: valid JSON of the wrong shape reads as absent and silently reverts to the default | whoever declared a protected heading | `retention.md:398` |
| the ~25-minute task split heuristic | B | implementer time budget | a report-back proposal | best-effort heuristic, not a trusted control; LLM elapsed-time introspection is unreliable even with the `date` proxy | whoever expects long tasks to self-split | `cadence.md:62` |
| the agent-chat resume id gets recorded | B | `SessionEnd` hook | records on a clean end | best-effort; a crash, `kill -9`, or context limit may skip it | whoever expects to resume a chat later | `agent-chats-registry.md:79` |
| the context-saturation floor blocks work | B | `hooks/context-floor.sh` | warns once per session on stderr | fails open on purpose; it does not block | whoever reads "floor" as a stop | `harness-primitives.md:306` |
| task-mode scope via the `Closes:` trailer | B | trailer-based scope tracking | names the closed ACs on the commit | trailers do not survive squash-merge and the scope moves when the merge-base moves; mitigated by disclosure only | whoever reads a squashed history | `close-gate.md:1426` |
| the AC grandfathering baseline is not forged | B | `ac-baseline.sh` | a digest over the blessed set | a DIGEST, not a signature; no secret, so anyone can recompute it and bless new debt as old debt | whoever reads the baseline as authoritative | `close-gate.md:1629` |
| row 7's wording does not over-claim | B | `ROW7_FORBIDDEN_TOKENS` | a tripwire for known regressions | GUIDANCE, NOT ENFORCEMENT; an unlisted synonym passes | whoever reads a green row as an honest row | `close-gate.md:2101` |
| the independent reviewer produced a verdict | B | review-record termination contract | `UNVERIFIED` is its own state | a crashed or unspawned reviewer yields nothing, and nothing on its own is never silently a PASS | whoever counts "the reviewer ran" without checking | `review-record.md:44` |

## Band C — the check is sound, its scope is narrower than it reads

These are deliberate, written-down limits. Nothing here is broken. **The risk receiver is whoever
reads the surrounding prose as wider than the check actually is.**

| required step / claim | band | enforcer | actual guarantee | known non-guarantee | risk receiver | source |
|---|---|---|---|---|---|---|
| an experiment proposal exists for a phase that moves a measurable behaviour | C | close-gate check #12 | under `required`, a file matching the phase glob carrying all nine section headings; under `ask`, that file OR a `SKIP: experiment-proposal — <category>` line whose category is one of six, with a clause required for `no-measurable-behaviour` | **it cannot judge a hypothesis.** Nine headings present is not nine sections filled in, a category token is not a true claim about the diff, and a clause is checked for presence, never for whether it is any good. The row prints all three bounds every run, because a mechanical check reported without its limit gets read as a quality verdict | whoever later asks whether the change helped | `SKILL.md:173` |
| tests ran before this push | C | close-gate check #7 | the evidence file is unchanged since it was generated | not proof a test ran; a hand-authored file with a valid header passes | whoever reads row 7 as "the suite is green" | `SKILL.md:112` |
| risky changes get the careful treatment | C | `careful-paths` | paths you marked, plus three fixed signals | does not claim to find every risky change; decision is by path, never by what the change did | whoever expects risk detection | `SKILL.md:250` |
| the drain lists real entries | C | retention drain | `^## ` matched line-wise | a `## ` line inside a fenced code block lists as an entry; a heading ending in `Index` is excluded file-wide | whoever trusts the entry count | `retention.md:868` |
| docs do not grow unbounded | C | retention size caps | caps on size and a 50K coverage floor | blind to many-small-files growth; measured, 596 of 610 docs sat below every threshold | whoever reads a green cap as "docs are bounded" | `close-gate.md:52` |
| the journal fragment is fresh | C | close-gate check #5 | freshness on the hot path | not asserted on the archive path: the archive's mtime belongs to the drain, not the phase | whoever closes right after a drain | `close-gate.md:34` |
| the journal carries FACT content | C | journal-touched check | some file in the journal range changed | it does not prove that file carries the FACT content | whoever reads the touch as content | `close-gate.md:34` |
| every criterion has a working oracle | C | `ac-oracle-binding` | each criterion HAS an oracle | never proves the oracle is correct; an exclusion self-destructs only when its condition fails, never when its reasoning was wrong | whoever reads "bound" as "verified" | `close-gate.md:61` |
| the context-floor hook is wired | C | gate wiring check | jq was resolvable when the gate ran | may not say the hook works, will run, or is verified; it does not parse the hooks array, so a name in a comment or in `disabledHooks` still prints the same mark | whoever reads the mark as "wired" | `close-gate.md:384` |
| test names carry proper AC references | C | reference-discipline check | the shipped kind is checked | a green row does not mean the repo's test files are clean; measured, 39 carry a bare AC id | whoever reads green as clean | `close-gate.md:1391` |
| a sweep deleted the right thing | C | sweep teeth | net-negative LOC direction | does not check whether the sweep deleted the right thing; the teeth stop a mislabelled add, nothing more | whoever reads a passing sweep as a correct sweep | `close-gate.md:2312` |

---

## Provenance

Every row was verified by opening its cited line, not by accepting a summary. Every row was checked against its cited line. The verification pass,
including five corrections made during it, is recorded outside this repository.

Five rows in band A (`user-story.md`, smoke artifacts, acceptance verifier, ADR, cognition capture)
come from a single sentence at `SKILL.md:119`. They are separate rows because each is an
independently required artifact with its own enforcement status.

Two rows in band C share `close-gate.md:34`, which is one long line carrying two distinct claims.
That shared source is correct, not a duplicate.
