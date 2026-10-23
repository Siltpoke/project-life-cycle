# Changelog

All notable changes to the `project-lifecycle` plugin are documented here.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning 2.0.0](https://semver.org/). Newest release is listed first.

**This file records every release; the repository's history is sampled.** The plugin was developed in a private repository and published here from it, and rather than replay every release as a commit, this repository carries a snapshot at a handful of milestones — the tags and releases you can see. So a version documented below may have no tag, no release page and no diff link: `2.0.0` is real and is described here, and there is nothing to click. Comparison links appear only between release points this repository carries a tag for.

---

## [Unreleased]

Nothing yet.

## [5.0.1] - 2026-10-23

### Fixed

- **The close gate that `/init-harness` generates no longer fails a correctly finished task.** Its product-change check read only the last commit, while the check below it requires a separate journal commit written after the code — so the normal order, code then journal, always failed with "changed no product-tree path". It now reads the whole branch range (`origin/main...HEAD`, or the last commit when there is no `origin/main` yet), as the skill's check table already said. Two matching defects went with it: a `product_paths` entry naming a single file (`["calc.py"]`) could never match, and neither could a root entry (`["."]`). A file now matches itself, `.` means any change, and a directory still matches only its contents. The legacy commit-verb fallback reads the same range.
- **The README no longer says the skill's hooks run in CodeBuddy and Qoder.** In an end-to-end run the skill loaded in both, but the task-list guard never intercepted a write and left no state, so the hooks were not running. The README now says so and links to the run's record in `HOST-VERIFICATION.md`, which gains an "End-to-end run" section. Treat the skill's frontmatter hooks as Claude Code-only on those hosts for now; the pre-push close gate is a git hook and is unaffected. The claim that Antigravity has no command-line entry point is corrected too: `agy` exists and loads the plugin, but running a session through it needs an interactive login.
- Internal maintenance of the gate's own test suite; no adopter-visible change.

## [5.0.0] - 2026-10-23

### Added

- **Side discoveries now have somewhere to go.** Something you trip over mid-phase that is neither a fresh request nor a review finding used to have no route at all. New `references/where-does-this-go.md` routes it to one of four outcomes — fix now, backlog entry, main-line candidate, or refused to a human — decided by a gate rather than a score. The main-line test is whether the item has a thesis, not how big it is. The document names the cases it refuses to decide; if more than half of routed items end up refused, treat that as a defect, not a safe default.
- **Capturing one costs one line and asks nothing.** Append `- [untriaged] <what> | ctx: <what made it legible>` to the phase's queue and carry on; deciding happens once, at phase close. The queue is one file per phase, configured in `.claude/close-gate.json`:

  ```json
  "sidelines": ".claude/sidelines/{PHASE}.md"
  ```

  The queue must not be committed; the `sidelines-never-tracked` invariant checks that nothing under the queue directory is tracked at any depth. A value without `{PHASE}` still works, but the gate warns that every phase then shares one queue and the next phase inherits whatever this one left behind.
- **Close-gate row 13 (`sidelines`) checks the queue, differently per mode on purpose.** `task` mode (the pre-push path) checks only that each line opens with a recognised state token, and treats a missing file as fine — otherwise capturing one line would block the next push. `phase` mode requires the file to exist (an absent queue is red, not clean, since a gitignored file is missing in a fresh clone or another worktree), no line left `untriaged` (or an explicit `- [none]`), a `class:` on every `refused` and a `why:` on every `declined`. A capture line that is indented or uses another bullet character is refused in both modes, because every other check in the row was blind to it. With no `sidelines` key the row prints SKIPPED with its reason rather than disappearing.
- **Phase close also checks the journal against the queue.** Row 13 requires the phase's journal fragment to carry a side-discovery outcome section and to name every landing id from the queue, and says so when no fragment exists. Ids are matched on word boundaries, so an id ending in `126` cannot vouch for one ending in `12`; a `landed:fix` commit is matched on its first 7 characters. **Limits the row prints itself:** it reads declarations only, so `- [none]` is a statement, not a verified fact, and the outcome section is recognised by its heading, not its content.
- **Growth on a counted surface now has to say what it cost.** New invariant `scripts/invariants/growth-declares-a-deletion.sh` compares three counters against the merge base — `*.md` directly under `skills/*/references/`, `*.md` directly under `commands/`, and the band total in `references/step-enforcement.md`. A surface that grew needs one line in the branch's journal fragment or a commit message: `GROWTH: <surface> +<N> deleted: <what>` or `GROWTH: <surface> +<N> cannot-delete: <why>`. Declared must be at least measured per surface, and a deletion in one surface never pays for growth in another. It makes growth countable, not smaller; lines are deliberately not counted.
- **`/catchup` and `/handoff` now check your saved handoff against the repository instead of reading it back.** The anchor is the `snapshot: HEAD <sha>` line `/handoff` already writes, and two comparisons are reported as separate rows: `checkout` (your working tree against the anchor) and `upstream` (`origin/main` against the anchor), each `unchanged` / `ahead` / `behind` / `diverged` / `unavailable` with a commit distance. A squash-merged anchor is handled by measuring from the fork point. Previously a current handoff could render as "clean start", and a tree behind could be reported as current.
- **The card says what it did not check.** Every default run prints a `remote  not-attempted` row with the age of your last fetch (`never fetched in this clone` when there is none), because `origin/main` is a local ref that can itself be stale. **`/catchup --refresh`** adds one bounded, read-only `git ls-remote` asking whether your local `origin/main` is still the remote's tip; it fetches nothing and changes no ref, and reports `differs` rather than a direction when the remote tip is not an object you have. The default path stays fully offline.
- **`/handoff` and `/catchup` share one module, `scripts/handoff_reconcile.py`,** so the writer and reader of the snapshot line cannot drift apart. An anchor that has already fallen behind the upstream is recorded, not omitted.
- **New `scripts/plc-python.sh` finds a working Python by running it.** On a default Windows install `python3` can be an App Execution Alias stub that exits 0 and prints nothing. The resolver accepts a candidate only on exit 0 with stdout exactly `major.minor` and a major version of at least 3. Candidates are `$PLC_PYTHON`, `$PYTHON`, `py -3`, `python3`, `python`; a set-but-broken override falls through, and a path containing spaces works. When nothing works it prints `COULD NOT RUN` naming each candidate and exits 3; in `--hook` mode it prints one `systemMessage` line and exits 0, at most once per `PLC_PYTHON_WARN_WINDOW` (default 6h). **Prerequisite: `bash`.**
- **New close-gate invariant `commands-no-bare-python`** keeps every Python call in `commands/*.md` and in `references/init-harness.md` going through the resolver. Exemptions are anchored to the line's text, each costs a written reason, and an exemption that matches nothing, matches two call sites, or has an empty fragment is a hard failure.
- **The brownfield archaeology pass now runs a pre-flight before drafting anything.** `scripts/archaeology-preflight.sh check` asks which tree it is reading and whether the project already keeps these artifacts under other names. On either anomaly it stops, writes zero drafts and hands you the decision; it never switches branches, fetches or writes. Exit codes are `0` no finding, `1` stop, `3` could not run. Previously a checkout far behind its default branch produced confident drafts about a project that had moved on. See `references/archaeology.md` §"Pre-flight".
- **The pre-flight reports which evidence tier fired** for each decision-record directory it finds (a tool-written marker file, a directory name plus `NNNN-*.md` filenames, or a content fingerprint), and every report — including a clean one — states its own false-negative floor. An existing roadmap-shaped file withholds only the `docs/ROADMAP.md` draft, with the caveat that whether it is maintained was not checked. `scripts/archaeology-preflight.sh detect` answers `adoption-entry` or `new-project` and names its evidence.
- **The generator-edges guard now checks that a generated file's content is current**, not only that the table's declarations are honest. The backlog index is regenerated and compared; the roadmap lead-width baseline is checked as a ratchet — no pin may grow beyond the smaller of its value at the merge base and at `HEAD` — because comparing a ratchet to a fresh regeneration silently switched off the guard it backs. Every subject prints a checked or skipped line plus a `note` summary whose four counts add up. **The close gate discards this output** and reads only the exit code, so the lines help when you run the script by hand.
- **`bash scripts/backlog-toc.sh --check`** reports whether `docs/BACKLOG.md` matches what the generator would produce, without modifying it.
- **The backlog index ranks the red priority glyph as `crit`, a tier above `high`.** It used to render a blank priority cell, identical to an entry with no priority. A glyph from the same family that is not one of the four known ones renders `?` and is named on stderr (the run still exits 0); an entry with no priority stays blank and silent. The glyph is read only where it opens a ` — ` segment of the heading, so a glyph mentioned in prose cannot win.
- **`references/ci-cd-gates.md` documents what a green pull-request check does and does not mean.** A `pull_request` run tests a merge with the base as it was when the run was created, so anything landing on the base afterwards leaves a green that describes a tree that will never exist. The section gives a contract for a merge-time staleness check — four outcomes (`fresh` / `stale` / `unverified` / `not-attempted`), five rules including that a run existing is not a green, where the recorded base can be read, and the two cases where `git merge-base --is-ancestor` reports `fresh` about a stale green. PLC ships no executable for this, since forge-specific code cannot be a required step.
- **New invariant `hot-cap-exemption-has-a-reason`.** A `retention.hot_caps.<key>: "none"` exemption must carry a sibling `retention._note_hot_caps_<key>_none` of at least 80 characters. It checks that a reason exists and is not a placeholder, never that the reason is good.

### Changed

- **BREAKING — the bundled `scripts/close-gate.sh` now fails, not warns, when a hot document exceeds its cap.** Caps come from `retention.hot_caps` with built-in defaults when the key is absent (`RESUME.md` 200 lines / 25K, status doc 300 / 30K, journal 100K, qa-log 50K, changelog 50K — including the `CHANGELOG.md` file itself), so a long changelog will now block a push. The gate `/init-harness` generates from `references/close-gate.md` stays warn-only; `references/retention.md` now has a per-key table saying which variant reads each key and how severe it is, and why the two differ. Migration: drain the document, raise the cap, or exempt it with a written reason, for example:

  ```json
  "retention": {
    "hot_caps": { "changelog_hot": "none" },
    "_note_hot_caps_changelog_hot_none": "Replace with your own reason: why this document is exempt and what will let you remove the exemption."
  }
  ```

  An exempt document prints `✓ <doc> exempt (retention.hot_caps: none)` rather than being skipped silently. Directory caps are measured with `du -sk` (allocated blocks, not content bytes).
- **BREAKING (for anyone parsing the card) — the save-state tier `unknown` is split into `no-handoff` and `unverified`.** Only `no-handoff` may render as a clean start; `unverified` means a handoff exists and could not be checked, and lists one line per failed check with its own cause. The card's exit status now says whether it verified anything: `0` every attempted check concluded, `4` at least one could not, `2` no card could be produced (`3` remains the resolver's "no working Python"). The deliberately skipped offline remote row does not move the status.
- **Python calls in the command docs now go through `scripts/plc-python.sh`** — `/catchup`, `/recall`, `/capture`, `/cognition-distill`, `/release`, and the Stop-hook entry `/init-harness` generates. Each edited block names `bash` as its prerequisite. Every site was run in old and new form and compared on exit status, stdout and stderr.
- **`/init-harness` now migrates an existing session-save hook** instead of skipping it because one is present. Run `/init-harness --refresh` once on a project bootstrapped before this release to rewrite the old-form Stop-hook entry in place; an entry that already uses the resolver is left alone.
- **`/recall` names the second reason you might have no session digest:** the hook is installed but could not start an interpreter, which produced the same `found: false` message. It also gives the command that tells the two apart.
- **The adoption-entry lists (anchors, manifests, source extensions, whitelist) live in one block in `scripts/archaeology-preflight.sh`**, and the new `adoption-rule-single-source` invariant keeps them there. They were previously restated in seven places with nothing checking they agreed.
- **The no-network guard over the welcome-back card now also covers the module that makes the git calls**, including a count of network-capable git subcommands named as string literals and a check that the runner is not called under another name. A missing target is `COULD NOT RUN`, never a skip.

### Removed

- **BREAKING — the `/tasklist` reader is removed** (`commands/tasklist.md`, `scripts/tasklist-view.sh` and its test). The contract it read is untouched: `.claude/tasklist.md` with its `- [ ]` / `- [x]` / `- [/]` grammar, `hooks/tasklist-first.sh`, `scripts/tasklist-guard-dir.sh` and the `tasklist-never-tracked` invariant all stay, byte for byte. Migration: read `.claude/tasklist.md` directly, or render it with your own tooling.
- **BREAKING — the test selector is removed:** `scripts/select-tests.sh`, `scripts/gen-test-input-map.sh`, `scripts/blind_spots.py`, `scripts/lib/test_input_tracer.py`, the pinned test-input map and its fingerprint, and the `test-input-map-fresh` invariant. In practice it answered `FULL` for every change, because its map went stale before it could be used and could not be regenerated as a by-product of a suite run. Migration: run your full suite; if your manifest registers `test-input-map-fresh`, delete that entry.

### Fixed

- **The phase token is validated as soon as the gate reads it.** It is substituted into manifest values and the sidelines queue path, so `close-gate.sh phase a/b` used to die with a raw `sed` error and no row, and an `&` would have corrupted the substitution silently. A token must now match `^[A-Za-z0-9][A-Za-z0-9._-]*$`; compound tokens joined by `-` are unaffected.
- **A malformed `Closes:` trailer is reported as malformed, not as a defect in your user story.** Two ids on one `Closes:` line separated by a comma kept the comma on the first id, which was then reported as `ORPHAN … the current story declares no such criterion`. A new `MALFORMED` verdict names the offending token, and the id test now uses the same anchored grammar as the story side (dotted and lettered sub-criterion ids still pass). Commas are still not separators: the convention stays one `Closes:` per line. In the bundled gate, the first fix attempted would have turned this red into a silent green, so the verdict is raised where the gate reads it.
- **A rate-limited cross-family reviewer is reported as `quota-exhausted`, not `spawn-failed`.** `scripts/cross-family-review.sh` discarded the engine's stderr and called every non-zero exit a failed spawn. One measured "usage limit" message is matched; anything unclassifiable stays `spawn-failed`. A quota shape that exits 0 with no output cannot be told apart from an empty answer and is left to the output gate. There is no automatic retry or wait.
- **On a machine without `jq`, `guard.sh` and `tasklist-first.sh` no longer go silent.** They exited 0 with no output, indistinguishable from having checked and found nothing. They now emit a `PreToolUse` envelope with `permissionDecision: defer` and an `additionalContext` carrying `UNVERIFIED` and naming what was not checked, and still exit 0, leaving your own permission prompt untouched. `context-floor.sh` keeps its documented `jq`-absent behaviour.
- **`mode-provenance-recorded` can validate a phase after its qa-log fragment has been drained.** The closing drain moved the fragment into the archive, after which the check reported `COULD NOT RUN`. It now finds drained fragments through the roots the stage registry declares, using the shipped `scripts/lib/fragment-sentinel.awk`; two compiled copies of one phase are refused rather than picked from.
- **The retention undo ring can no longer evict the last copy of a fragment, and is no longer read as permanent evidence.** `docs/archive/.pre-images/` deletes its oldest slots by design, yet the lifecycle ledger treated it as durable, so a drain run as prescribed could destroy the only copy with every gate green. The ledger now reads the marker the drain writes into the archive; the prune refuses to evict a last copy (comparing per `## ` entry against archive streams, so newest-first ordering and `part-??.md` splits do not cause false refusals); each eviction gets an `EVICTED` receipt line; and the ring depth is a declared policy key, `preimage_keep`, readable with `bash scripts/retention-drain.sh config preimage_keep`. Also fixed: a trailing slash in `retention.archive_dir` silently disabled the ring exclusion, `config` (documented read-only) created `docs/archive`, and a roll-over dropped the lines above the first heading.
- **The generator-edges guard no longer reports "stale, regenerate it" when the generator could not run.** Each subject now declares the exit code that means stale; anything else is reported as could-not-run with the generator's stderr. Also fixed: a CRLF checkout turning `--check` into `--check\r`, a short row misreported as an unknown mode, a generator reading stdin and eating the subject list, and a summary whose numbers did not add up.
- **`roadmap-lead-length` can report violations under macOS's bash 3.2.** In a UTF-8 locale bash 3.2 read the `…` after `$pref` as part of the variable name and died under `set -u`, and its `EXIT` trap then laundered the death into exit 0, so the gate printed `ok` against a real violation. Fixed on both halves, and the red paths are now tested in both locales.
- **`backlog-no-title-markers` no longer truncates its diagnostic mid-character.** `cut -c` counts bytes under GNU coreutils, so non-ASCII headings produced invalid UTF-8; it now truncates by character at the same 140 bound.
- **The experiment-proposal template spells `Ground Truth` the way the gate requires.** `references/experiment-gate.md` and `/experiment` wrote `Ground truth`, so following the template verbatim failed with `missing required section(s): Ground Truth`.
- **Command docs call plugin-shipped scripts through `${CLAUDE_PLUGIN_ROOT}`**, so they resolve outside the repository root — including the archaeology pre-flight, which runs before an adopter repo has a `scripts/` directory. `/release` deliberately keeps relative paths and now says why: it acts on the repository you are standing in. Lines naming `close-gate.sh` and `retention-drain.sh`, which you copy into your own repo, stay relative.
- **The five skill-frontmatter hooks run as `bash "<path>"`** instead of bare `.sh` paths, so a checkout without the executable bit (as on Windows) no longer fails with `126 Permission denied`.
- **The README's host claims rest on a record.** It names the four hosts checked with their own validators (Claude Code, Qoder, CodeBuddy, Codex) and marks Antigravity unverified, linking to `HOST-VERIFICATION.md`, which carries each probe, its result, and what it does not cover: discovery and loading, not a phase run end to end, and nothing on Windows.
- **`validate.yml` declares `permissions: contents: read`** instead of inheriting the repository default token scope.

### Known issues

- **`mode: fast` cannot be switched on in a repository whose default branch is protected.** Its own rule (`longterm-candidates-not-in-diff`) refuses any branch commit that touches `CLAUDE.md` once the tree says `mode: fast` — including the commit that sets it — and `plc-longterm-write.sh`, which writes long-term records after merge, commits to the default branch directly, which protection refuses. Workaround: keep `mode: fast` as an uncommitted local setting, and write the long-term records in a separate PR after merge.

## [4.1.1] - 2026-09-24

### Fixed

- A test-only fix, recorded because the version exists: cutting a release used to turn this repository's own release-notice tests red. They read the CHANGELOG's `[Unreleased]` section by name, and cutting a release renames that heading to the version being cut — so the release broke them, on a notice that was written and correct. They now look for the section carrying the key. **Nothing an adopter runs changed in this release.**

## [4.1.0] - 2026-09-23

### Added

- Adds `scripts/select-tests.sh`, which answers "which tests could this change have broken?" — it takes the changed paths and prints the test files to run, or the single word `FULL` when it cannot know. The mapping is derived, not hand-maintained: `scripts/gen-test-input-map.sh` runs each test file under a tracer and records what it reads, and `.claude/generator-edges.tsv` declares by hand the edges a tracer cannot see. **It is not wired into CI** — what ships is the command plus the evidence it can be trusted. On the repository it was measured against it missed no test and skipped about 15% of them, because every test whose inputs cannot be fully known runs every time.
- Two guards keep the selection honest: the gate refuses a map whose own blob does not match its fingerprint, and the selector answers `FULL` as soon as any code input named in that fingerprint has changed since the map was generated. A data file changing does not trigger it, which is what lets a docs-only change be narrowed at all.
- Adds a per-task step before the plan: an experiment proposal, written before the code exists. A change that moves a measurable behaviour has to say in advance what it expects to improve and how you would know. `references/experiment-gate.md` carries the nine-section template, and the Decision Rule has **three** states — pass, fail, and not-measurable — because with only two an unresolvable result is forced into "fail" and then read as "the change did nothing".
- Adds `/experiment`, which walks that proposal section by section and stops for confirmation at each one. It deliberately does not hand you a filled-in draft.
- Adds close-gate check 12 and an `experiment-gate: required | ask | off` policy key. `ask` accepts either a proposal file or a `SKIP: experiment-proposal — <category>` line naming one of six categories, and fails when there is neither. It is **not** warn-only. The row prints its own limit on every pass: it checks that a proposal exists and is structured, and cannot judge whether a hypothesis is any good.
- A roadmap station can now say how it will be done and how far it has got. A station carries an optional plan block in `docs/ROADMAP.md` — a stable id, the mainline row it binds to, its dependencies, and one to seven numbered steps — and a separate list declares what is in flight. **Progress is never written down**: it is derived from the steps each phase declares it closed, so the number cannot drift from the work. The block declares dependencies and never an order; there is no `next:` field, by design. Format contract in `references/roadmap-format.md`, with fifteen golden fixtures beside it.
- Adds `closed-step:`, a fourth closure-declaration entry kind. A phase names the station steps it closed, or states `closed-step: none`. The gate requires one of the two, so silence can no longer mean "closed nothing".
- Adds five gate checks for the above: `station-id-integrity`, `station-deps-acyclic`, `no-stored-position`, `closed-step-refs-resolve`, and `station-state-consistency`.
- Adds `no-cjk-in-shipped-files` to the close gate. The ban on CJK characters in shipped bytes used to be enforced only by an untracked pre-push hook, so it was checked when work left the machine rather than when it was done.
- Adds `references/document-map.md`: one row per document this skill asks you to keep — who writes it, who reads it first, when, whether it is truth or a derived view, and which document it is most confused with. It settles the `RESUME.md` / `docs/STATUS.md` ambiguity: `RESUME.md` is the read-first document, and `docs/STATUS.md` is what you point `status_doc` at — a configuration, not a second convention.
- Adds `references/step-enforcement.md`, which says which of this skill's rules are held up by code and which are held up by nothing. Every required step is mapped to its enforcer in three separately-headed bands: **A** nothing enforces this, **B** an enforcer that admits it fails open, **C** sound but narrower than the prose around it reads. The counts are reported per band and never summed. The page also states what it does not buy: it never checks that a row is *true*.
- Adds a documented producer for `.claude/ci-status.json`, so `/catchup`'s CI row can stop reading `absent`. The plugin still writes nothing forge-specific itself; `references/ci-cd-gates.md` carries an example snippet you copy into your own tooling. Read the notes under it before you do — a blocked run must be recorded `unknown`, never `red`, because `gh run list` reports `conclusion: failure` for runs that never executed.
- A mainline roadmap row now has to open with something a person can read: the name cell and the **lead** of the `what` cell are each bounded at 60 display columns, and the detail after the lead is not capped. The lead ends at the first ideographic full stop (U+3002), `. ` or `<br>`. It is enforced as a ratchet — each existing row is pinned at its current width and may not grow, while a new or renamed row must meet the bound outright.

### Changed

- **BREAKING** — if your `.claude/close-gate.json` narrows `test_evidence_inputs`, you must now say why, in a companion `validator_input_paths_rationale` with `surface_total`, `basis` (one of `tracked-files` / `all-files` / `glob-set` / `explicit-path-list`) and `why`. **`why` is free prose in any language and any script — the gate reads none of it** and only checks that it is there. Do not write `surface_kept`: the gate derives how many files your narrowing matches and refuses a manifest that declares it. **Nothing changes if you do not narrow** — with `test_evidence_inputs` absent or empty the check does not fire. A single blank glob does fire; that is a declared narrowing, merely a broken one. Migration: add the member to your manifest (it is a new JSON property, so the member before it needs a trailing comma) and set `surface_total` to your own number.

  ```json
  "validator_input_paths_rationale": {
    "surface_total": 3020,
    "basis": "tracked-files",
    "why": ["the narrowed set is exactly the validator's inputs; nothing else is read"]
  },
  ```
 There is no migration window; the escape hatch is deleting `test_evidence_inputs`, and it is not free — that also drops the freshness check back to an mtime comparison, which git does not preserve across a checkout and so false-passes on any fresh clone or CI runner. New projects get the key from `/init-harness` with a placeholder the gate deliberately refuses.
- `scripts/local-ci.sh` now starts a container on a Docker Desktop host. It could not before: the runner bind-mounts the host's Docker socket by default, and Docker Desktop keeps that socket at a path its file-sharing layer refuses, so the job died before a single step ran — **printing in the same shape as a finished run**, with a failure line, the usual summary, a real link-check result, and a test tally that was simply empty. **Read the tallies, not the exit code**: an empty tally line means nothing ran. Known gap on Apple Silicon: the containerised markdown link-check step hard-fails, because the pinned link checker covers `x86_64_linux` and `aarch64_darwin` only. Your links are still checked, by the host-native checker this script runs itself.
- `/catchup` prints a station's position as `steps 1/5`, with `blocked-by:` as its own field, never merged with anything that would read as a priority. A roadmap row with no plan block is parsed exactly as before, byte for byte.
- Install commands in both READMEs and all four plugin manifests now name the `Siltpoke` organisation instead of the old personal namespace. Nothing you already installed breaks — the old path redirects — but a redirect is not a guarantee: the old path becomes free for anyone to claim, and an install command that silently starts resolving elsewhere is not a failure you would be told about.

### Fixed

- The context floor no longer tells you to overwrite somebody else's checkpoint. When it blocks inside a worktree, the `RESUME.md` it names is by construction not yours — a worktree exists to isolate one session from another — or, when the checkpoint is untracked, it names a path that was never on disk. The block now points at `PLC_RESUME_PATH`, which was already the correct answer and had never been mentioned. Detected structurally rather than by looking for a path fragment, and silent when `PLC_RESUME_PATH` is already set.
- `SKILL.md` said the close gate "checks exactly these eight things, and nothing else" while the gate announces thirteen. The table is corrected and, for the first time, pinned to the gate by a declared invariant that parses the gate's call sites on one side and the table's rows on the other — neither side written down as a literal, so it cannot drift again in either direction.
- `close-gate.sh` described an unarmed check as one that "does not run, prints nothing, and leaves the check-set line untouched". All three are false of the code beneath that comment. The wrong sentence is quoted in place beside the right one rather than deleted, because it had already been copied as a design precedent.
- The display-width table is checked again — it had not been checked anywhere. Its three comparison tests took their expected answers from the interpreter's own Unicode tables, so they silently skipped on every Python whose Unicode version did not match, which was all of them. The expectations now ship next to the table and the comparisons run on every interpreter; CI fails on any skipped width test rather than printing green over one. If you regenerate the table, regenerate the snapshot in the same command pair.
- The frozen guard protecting the `detailed` mode registration no longer objects to a file merely getting longer. Its stated job was "this registration cannot be edited silently"; what it enforced was "this file may not grow". The position test is replaced by an integrity pin over the guarded blocks' **contents**, with line numbers deliberately excluded — stricter inside the blocks, where any change now moves the digest and must be declared in the same commit, and silent outside them.
- `BACKLOG.md`'s title no longer claims `docs/` is gitignored, and the generator no longer puts it back. The generator printed the title literally, so a correction made in the file produced a diff that read as a fix, reviewed as a fix, merged, and was silently undone by whoever next ran the generator. A new invariant reds if the title claims `docs/` is ignored while git tracks files under it, and it checks the generator as well as the file. If it reds for you, correct the title in `scripts/backlog-toc.sh`, not only in the document — the guard does not ban the sentence, it requires it to be true.
- The test suite can no longer write the repository it is testing. Four places wrote tracked files during a run and restored them in a `finally`, which covers exceptions and not a kill signal, a timeout, an early exit, or a closed terminal; one had already left planted bytes inside two shipped gate scripts. Fixtures now mutate copies, and an interrupted run leaves a temp directory behind instead of a modified shipped file.
- A test was rewriting `docs/BACKLOG.md` on every full-suite run, because it invoked the index generator against the real repository. The write was correct — it refreshed the index — which is why it went unnoticed.

## [4.0.0] - 2026-08-21

### Added

- Adds a `mode: fast | detailed` project setting that controls how often you are stopped for confirmation and how many review agents each task uses. Every behaviour it changes still has its own key, and `detailed` behaves exactly as before.
- In `fast` mode, a change that touches a path you mark under `careful-paths:` (or a dependency manifest, migration, or deploy/CI config) is automatically reviewed at the full setting, and the run names the rule that triggered it.
- Adds `/plc-status`, an append-only record of which process stages each phase actually ran, reported as observed, claimed, missing, not applicable, or unknown. It never blocks anything, and `PLC_LEDGER=0` turns it off.
- `/catchup` can now warn you that your main branch's CI is red, read from a local CI-status file your own tooling writes, and says so when that result belongs to an older commit.
- Adds an acceptance-criteria check to the close-gate: every criterion in a phase's user story needs a runnable check or a written exclusion that still holds (configured with `user_story_glob`, `ac_evidence`, `ac_baseline` and `ac_heading_set`).
- Adds an opt-in close-gate check, `closure_declaration`, that makes a phase state which backlog entries it closed and verifies that against an append-only closure log. The backlog index generator, `scripts/backlog-toc.sh`, now ships too.
- Adds a runner for code review by a second, different AI family, which keeps "the review did not happen" separate from "the review found nothing".
- A retention drain can now be undone: every file a drain changes is saved first, and `retention-drain.sh restore <key>` puts them all back.
- Adds `scripts/gen-test-evidence.sh`, which regenerates test evidence without ever replacing a good evidence file with a failed run. `/init-harness` now sets new projects up with it and with the content-fingerprint evidence check.

### Changed

- **BREAKING** — the close-gate adds a required `ac-oracle-binding` check. Task mode checks only the criteria a branch declares with `Closes:` commit trailers; phase mode checks them all. A project that sets neither `user_story_glob` nor `exempt_user_story` gets a skipped row and is not failed.
- **BREAKING** — the cross-family review runner's exit code now says what happened: `0` a review came back, `3` no answer came back (a normal fallback), `2` the call was misconfigured, `1` a review came back but could not be saved. Its output no longer carries `fallback_reason` on success or the review payload on a fallback. Migration: a shell caller that chained on success should use `|| true` if a fallback is acceptable, or check for exit `3` if not; code that read either key should test whether the key exists.
- **BREAKING** — the pre-push installer now puts the close-gate chain right after the hook's first line, so a hook ending in `exec` no longer skips it. It refuses a non-shell hook and a `core.hooksPath` pointing away from the default hooks folder, and a new standing check verifies the gate is reachable. Migration: in a clone wired by an earlier version, back up `.git/hooks/pre-push`, delete its three-line `# >>> close-gate wrap-up chain … <<<` block, then re-run `install-close-gate-hook.sh` — re-running alone leaves the old block where it is.
- The pre-push gate now runs on any branch whose changes touch your declared product paths, not only on phase branches, and every run lists which checks ran, which were skipped, and why. `/release` regenerates test evidence so a release push still passes it.
- `/catchup` now finds your current station from a `▶` (or `◐`) at the start of its name in the roadmap's stations table, instead of from bold text in the prose. Migration: mark your current station that way, or the card shows no current station.
- The retention drain can be told which end of a document is oldest (`order`, e.g. `newest-first` for a changelog) and which headings are structure rather than entries (`non_entry_headings`). A document whose dates contradict the default order is now refused until you declare it, instead of having the wrong entries archived.
- The context-floor and close-gate reminder hooks no longer need `python3`; `jq` is enough.
- The skill's always-loaded reference index is much shorter, so every invocation uses noticeably less context.

### Fixed

- Fixes many context-floor bugs that could silently switch the guard off for a session or clear it without a real checkpoint — including unusual session ids, a single malformed transcript line, a stray file in its state folder, a directory or special file named `RESUME.md`, and a checkpoint made in another repository. It also no longer blocks on its first fire when your checkpoint is already up to date.
- Fixes the close-gate reporting success for a run that aborted part-way, and asking for a journal entry that its own drain step had just archived.
- Fixes retention-drain problems: a failed archive roll-over that reported success (and could duplicate or lose entries on retry), journal archives filed under the wrong month, an index left pointing at drained entries, and an archive table of contents that was never written.
- `/recall` and `/catchup` no longer pick an empty session over your last real one; `/catchup` now finds a `RESUME.md` kept under `docs/`, and roadmap rows that contain a `|` or are already marked done no longer vanish or show as upcoming work.
- The checklist guard now finds a checklist given by absolute path, and counts the in-progress mark it documents.
- The Codex, Qoder and CodeBuddy plugin manifests now declare the same licence as `LICENSE` (PolyForm Perimeter 1.0.1) instead of MIT.
- Corrects documentation that described enforcement the skill does not actually perform, and three command descriptions that strict YAML parsers rejected.

## [3.7.0] - 2026-07-25

### Added

- Adds an optional per-pull-request verification gate: a reviewer's report is checked against your acceptance criteria before merge, including a check that your code's own safety guards still catch real breakage — not just that tests pass.
- The independent second-opinion review used during brainstorming can now run on a different AI assistant (opt-in), for a genuinely independent perspective.
- Adds `/tasklist`, a terminal reader for the `.claude/tasklist.md` checklist file, so you can see the current task list at two levels of detail without opening the file. Works on every supported CLI.

### Changed

- The close-gate now runs in two modes — a check on every commit, and a stricter check before merge — so the first finished piece of a phase can be pushed right away instead of waiting for the whole phase to close.
- Renames this plugin's `/resume` command to `/recall`, so it no longer collides with Claude Code's own built-in `/resume` (which reopens a past conversation rather than briefing you from the saved digest). Behaviour is unchanged; update anything that invoked the old name.

### Fixed

- Fixes several safety-hook bugs: a push-safety check that matched on the wrong text, a reminder that could re-arm itself even after a failed check, and file "freshness" checks that are now proven from file content rather than a timestamp that file-syncing tools can silently alter.

## [3.6.0] - 2026-07-19

### Added

- Adds `/reconcile`, which finds roadmap or status decisions made in conversation or shipped in merged changes but never written down, and proposes them back into your project's roadmap and status docs for your approval.

## [3.5.0] - 2026-07-18

### Added

- `/catchup` now renders a richer roadmap view — pinned project vision, a "you are here" marker, collapsed completed work, and expanded detail for the current and upcoming stations.

## [3.4.0] - 2026-07-17

### Added

- `/handoff` now archives the previous session snapshot before overwriting it, so a full history of past continuity notes accumulates instead of being lost on every write.

### Fixed

- Fixes `/catchup` and `/resume` failing outright on plugin installations, caused by an incorrect internal file path.

## [3.3.0] - 2026-07-17

### Added

- Adds `/catchup`, a warm "welcome back" summary combining your git state, your saved status file, and your last session's digest.

## [3.2.0] - 2026-07-17

### Added

- Adds a background-agent script for the standard post-implementation review sequence (verify, code-quality, validate), replacing a manual, prose-driven review flow.
- The close-gate can now run declared project-specific checks automatically, not just confirm that required files exist.

## [3.1.0] - 2026-07-16

### Added

- Adds automatic session-save: a digest of every turn's transcript is saved locally, with a `/resume` command that briefs a new session from the latest save for the current project.

### Changed

- Adds a fourth onboarding habit covering session continuity — the automatic save versus the curated handoff file, and when to use each.

## [3.0.0] - 2026-07-15

### Added

- Ships a deterministic close-gate that blocks pushing an incomplete phase branch.
- Adds three standalone commands — `/research`, `/review`, and `/handoff` — so research, code review, and session handoff can each run on their own instead of only inside a full project cycle.

### Removed

- **BREAKING** — the unattended ("AFK") run mode is removed from this plugin and now lives in a separate project; a project that referenced it must point at that project instead. The judgment for whether a request is safe to run unattended stays part of this plugin.

## [2.0.0] - 2026-07-14

### Added

- Adds a required evidence field to the journal's closing entry, so a decision can no longer be recorded without stating what supports it.
- Adds a file-count cap alongside existing size caps for retained project documents, catching growth that many small files caused but no size limit noticed.

### Changed

- **BREAKING** — closing a phase now requires a complete journal entry (decision, reasoning, evidence, rejected alternatives, source). A project upgrading from an earlier version must write one before its next phase close.
- Retires two standing documentation requirements (kept PR-draft bodies, a separate handoff file) in favor of the new journal entry and treating GitHub itself as the source of truth.

## [1.5.0] - 2026-07-11

### Added

- Adds a citation-coverage check for locked research decisions, flagging any decision that carries no supporting link.

### Changed

- Improves guided GitHub repository setup — it can now create the repository for you, instead of only linking to GitHub's own setup guide.
- Strengthens the research protocol: decisions are ordered by dependency, "skip research" is now a named and justified exception rather than a default, and a recommendation with no citation is treated as invalid output.

## [1.4.0] - 2026-07-10

### Added

- Adds a plain-language mode for non-technical users, with adjustable tone, first-use term explanations, and screenshot fallbacks.
- Adds guided GitHub repository setup and a guided deploy offer at project finish, for users without a technical background.
- Adds proactive, opt-in suggestions for high-value best practices as they come up during development.
- Adds an opt-in personal references log that can capture and analyze external material (repos, articles, videos) you share during research.

## [1.3.0] - 2026-07-10

### Added

- Adds project cognition memory: captures the stated intent behind decisions (the "why"), with a capped, cited, auto-distilled summary document.

## [1.2.1] - 2026-07-09

### Fixed

- Fixes task-list enforcement so it reliably requires a real task list (at least three items) on every run, instead of silently accepting a single item or none at all.

## [1.2.0] - 2026-07-09

### Changed

- Documentation cleanup: completes the reference index and folds a duplicate page into its parent document.

## [1.1.0] - 2026-07-09

### Added

- Adds a fragment-based writing convention for shared append-only documents (journal, QA log, changelog), so parallel branches of work stop colliding on the same file.
- Adds document retention: size and line caps on hot documents, an archival step at milestone close, and a human-gated distillation step.
- Adds a context-floor wiring check and a task-boundary reminder to clear context between phases.
- Adds a task-list-first enforcement hook, blocking the first edit of a session until a task list exists.

## [1.0.0] - 2026-07-07

### Added

- Adds native support for Codex, Qoder, CodeBuddy, and Antigravity, alongside Claude Code.
- Splits the README into a short landing page plus a full guide carrying the complete workflow narrative and repository map.

### Changed

- Relicenses from MIT to PolyForm Perimeter 1.0.1 (more restrictive than MIT — review the new terms if you redistribute).

## [0.12.0] - 2026-07-03

### Added

- Internal tooling; no user-facing change.

## [0.11.0] - 2026-06-30

### Added

- Adds an "archetype" classification (Builder / Prototyper / Sweeper / Grower / Maintainer) that shapes which review steps and quality checks a request goes through.
- For cleanup-only work, requires the change to actually shrink the codebase, or an explicit documented reason why not.

## [0.10.0] - 2026-06-26

### Added

- Adds an opt-in percentage-based trigger for the context floor, for models with much larger context windows.

## [0.9.1] - 2026-06-25

### Fixed

- Fixes the context-floor block message to show a percentage that matches what your own status line reports, instead of only raw token counts.

## [0.9.0] - 2026-06-24

### Added

- Adds a hard context-usage floor: past a configurable threshold, edits are blocked until you checkpoint your progress, closing the gap left by softer warnings.

## [0.8.0] - 2026-06-12

### Added

- Adds an unattended ("AFK") run mode with a required goal/stop/budget/report contract, a budget circuit-breaker, and an exit report — merging always stays a human action.

### Fixed

- Fixes enforcement hooks that silently failed to load under a plugin install, caused by an incorrect file path.

## [0.7.0] - 2026-06-11

### Changed

- Extends the hard-bug diagnosis workflow to check past lessons first and record a new one afterward, so the same root cause isn't re-discovered from scratch next time.

## [0.6.0] - 2026-06-11

### Added

- Adds a structured, auditable review record for AI code review: fresh context, read-only tools, evidence quoted per finding, and a verdict computed last rather than self-declared.
- Adds a coverage check confirming every commit since the last review round is actually covered before merge.

## [0.5.0] - 2026-06-11

### Added

- Adds a `close-gate` policy for choosing where human approval happens — every task, or once per pull request with an independent review filling the gap in between.
- Adds `/builder-profile`, a command that reads your own local session history and reports back how you actually use the coding agent — entirely local, nothing uploaded.
- Adds a rolling-archive pattern so a project's status file stays a manageable size instead of growing forever.

### Fixed

- Fixes a safety-guard false positive that blocked commits whose *message* merely mentioned `main` or `--no-verify`, rather than commands that actually did either.

## [0.4.0] - 2026-06-08

### Added

- Ships enforcement hooks: one blocks bypassing commit/push safety checks and direct pushes to the main branch, another reminds you to close out a phase properly.
- Adds an opt-in check that asks one reflection question about your own change after it ships, without keeping a running score.

### Changed

- Every pull request now opens with a short plain-language summary before the technical detail.

## [0.3.0] - 2026-05-28

### Added

- Adds `/init-harness`, which bootstraps a new or existing project with this plugin's conventions and starter documentation in one pass.
- Adds `/release`, which computes the version bump from the changelog, tags, and publishes a release automatically.
- Adds onboarding and verify-loop guides for bringing a new contributor (human or AI) up to speed safely.

### Changed

- The per-task validator now runs a lie-detection pass first, checking a builder's claims against the real diff before accepting them.

## [0.2.0] - 2026-05-27

### Added

- Adds a mandatory user-story and acceptance-criteria file for user-facing work, checked by a new independent acceptance-verifier step.
- Adds `/ship`, a command that runs one feature end-to-end (research, story, spec, build, verify, PR) with a few points where you confirm before continuing.
- Adds quality rules for optional HTML companion documents (accessibility, real data instead of placeholders, consistent styling).

### Changed

- Expands the per-task review cadence from 5 to 6 steps, adding the acceptance-verifier and a stricter, read-only validator.

## [0.1.0] - 2026-05-11

Initial release.

### Added

- Introduces the full spec → plan → execute → journal → milestone-done project workflow, plus a per-task cadence of implement → review → code-quality review → fix → journal.
- Adds a research protocol for locking design decisions, backed by a second, independent reviewer check.
- Adds Architectural Decision Records, a domain glossary convention, and delivery templates (issue breakdown, changelog, PR body).

[Unreleased]: https://github.com/Siltpoke/project-life-cycle/compare/v5.0.1...HEAD
[5.0.1]: https://github.com/Siltpoke/project-life-cycle/compare/v4.1.1...v5.0.1
[4.1.1]: https://github.com/Siltpoke/project-life-cycle/compare/v4.1.0...v4.1.1
[4.1.0]: https://github.com/Siltpoke/project-life-cycle/compare/v4.0.0...v4.1.0
[4.0.0]: https://github.com/Siltpoke/project-life-cycle/compare/v3.7.0...v4.0.0
[3.7.0]: https://github.com/Siltpoke/project-life-cycle/compare/v3.0.0...v3.7.0
[3.0.0]: https://github.com/Siltpoke/project-life-cycle/compare/v1.0.0...v3.0.0
[1.0.0]: https://github.com/Siltpoke/project-life-cycle/compare/v0.4.0...v1.0.0
[0.4.0]: https://github.com/Siltpoke/project-life-cycle/releases/tag/v0.4.0
