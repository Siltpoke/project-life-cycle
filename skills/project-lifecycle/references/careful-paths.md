# `careful-paths` — the places this project wants handled carefully, and the three signals that need no declaration

`mode: fast` trades scrutiny for speed. **Its entire justification is the assumption that being
wrong is cheap.** Some changes do not fit that assumption — the login code, the payment code, a new
third-party dependency, a database schema change, the deploy configuration.

This file is the exception channel. When a task's changes touch one of those places, **that task's
verification tail runs at `detailed`**, and it says which rule fired.

## Behavior capture (MED+ / careful-paths) -- lock what must not regress

A hit also arms the **Behavior Lock**. A hit makes this a MED+ task; the Lock binds the behavior
that ALREADY worked and is now at risk to the test that proves it, so a regression goes red
instead of slipping through a green suite. This is separate from the acceptance verifier (which
binds the story's ACs to new tests); do it as the Protect step, before the first edit where
practical:

1. **Name the at-risk behaviors the user story does NOT mention.** For a MED+ task, at least one.
2. **Bind each to its carrier** -- the existing test that actually asserts it; add a targeted test
   only where a critical behavior has none (exercise the real behavior, never a mock of the thing
   being changed). The carrier MUST resolve (`scripts/behavior-lock.sh --resolve`), or the
   `behavior-lock-carriers-resolve` invariant (close-gate check #8) is red.
3. **Register the row** in `.claude/behavior-lock.tsv` (`id  class  behavior  carrier  why`, class
   PRESERVE for these). `BL-<n>` is its own id namespace, separate from backlog `B<n>`; the next id
   is one past the max in `--list-ids`, never eyeballed from a stale view.
4. **Baseline it** -- run the carrier on the ORIGINAL code and record it with
   `scripts/behavior-baseline.sh --record <id> before <exit> "<cmd>" "<env>"`; after the change,
   record `after` and run `--check-transition <id>`. PRESERVE must read pass->pass, FIX fail->pass,
   NEW na->pass, or the transition is surfaced as a contradiction, not swallowed.

LOW tasks (no `careful-paths` hit and no higher declaration) add nothing here -- the Behavior Lock
is risk-adaptive, not ceremony on every task. **Graduation:** once a behavior is pinned by a
permanent test in the normal suite, move its row out with `scripts/behavior-lock.sh --graduate <id>`
so the registry stays the churn list, not a whole-codebase inventory; the guarantee then lives in
the test.

**It does not claim to find every risky change. It cannot, and saying it can would be a lie.**
Read §"What this will miss" before relying on it.

## The 3-tier risk call -- what M1's binary hit grew into

M1 was a binary switch: a `careful-paths` hit armed the Lock, nothing else did. M2 makes risk a
three-position dial, and a hard-fail gate (`risk-tier-evidence-floor`, close-gate check #8 family)
enforces that the EVIDENCE on the branch matches the tier -- never that the declared tier is
"correct" (that is your judgment; the gate does not second-guess it).

**Declare the tier** in the phase's qa-log fragment, one line (parsed by `scripts/risk-tier.sh`):

    risk: LOW | reason: <why>
    risk: MEDIUM | reason: <why>
    risk: HIGH | reason: <why>

**The effective tier = max(objective floor, your declaration).**
- The **objective floor** is the `careful-paths` hit: a hit forces at least MEDIUM. A declaration
  cannot drop below it -- calling a careful-paths change LOW does not escape MEDIUM. You may always
  go *higher* than the floor, never lower.
- A **malformed or ambiguous** `risk:` line fails safe to HIGH (never silently to LOW). **No hit
  and no declaration** is LOW -- silence on a quiet branch is not punished into declaring.

**The evidence floor the gate enforces** (the *sizing* column is judgment, not gated):

| Effective tier | What the branch must carry | Sizing (not gated) |
|---|---|---|
| LOW | nothing | implement + one focused check |
| MEDIUM | >=1 behavior-lock row added/changed this branch (the Protect step above) | name the 3-5 behaviors most likely to break; a targeted test only where a critical one has none |
| HIGH | MEDIUM's row AND a recorded before+after baseline for at least one of them | capture failure paths / negative cases before editing; a before-baseline of the critical behaviors |

**Waiver -- the anti-starvation escape.** A floor you genuinely cannot meet (a MEDIUM/HIGH branch
with no behavior to lock) is not a dead end: write one line in the journal,
`SKIP: risk-floor -- <reason>`, and the gate passes and records it. The waiver sits in git, so it
is attributable by commit. The gate refuses an *undeclared, unjustified* gap, not a declared one.

**The tier also sizes the progress checkpoint.** The same effective tier decides how
much a phase reports while it works: LOW owes no progress checkpoint, MEDIUM/HIGH owe one mid-phase
checkpoint recorded in the qa-log. That checkpoint informs, it never blocks -- you post it and keep
going. The shape, the qa-log marker, and the `checkpoint-floor` gate live in
`references/checkpoint-modes.md`.

**Proving it.** What counts as "it works" -- the VERIFIED/FAIL/PARTIAL/UNVERIFIED/BLOCKED
enum, regression-vs-validation, the per-behavior evidence fields, and the Implemented!=Tested!=Verified
!=Accepted ladder -- is one vocabulary in `references/prove.md`. It also carries the `test-weakening-guard`
gate: a net drop in test-function count across all test files reds unless the journal declares a
`SKIP: test-weakening -- <reason>`.

---

## The key

```yaml
# CLAUDE.md
careful-paths: src/auth/, src/billing/, db/
```

A comma-separated list of git pathspecs. Absent or empty = the user has declared nothing, and only
the three signals in the data block below apply.

**A directory pathspec covers everything beneath it.** `src/auth/` matches
`src/auth/session.ts` and `src/auth/oauth/callback.ts` alike.

## The data

Everything the check recognises without a project declaration lives in **exactly one** block. There
is no second copy anywhere — a reader that has to choose between two copies is the drift this shape
exists to prevent, and `scripts/invariants/careful-paths-single-block.sh` fails if a second fenced
block appears between the sentinels.

<!-- plc-careful-data:begin -->
```json
{
  "signals": {
    "dependency": {
      "says": "touched the dependency manifest",
      "paths": [
        "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
        "requirements.txt", "pyproject.toml", "Pipfile", "poetry.lock", "uv.lock",
        "go.mod", "go.sum",
        "Cargo.toml", "Cargo.lock",
        "Gemfile", "Gemfile.lock",
        "mix.exs", "mix.lock",
        "composer.json", "composer.lock",
        "pom.xml", "build.gradle", "build.gradle.kts",
        "Package.swift", "pubspec.yaml"
      ]
    },
    "migration": {
      "says": "added or changed a database schema migration",
      "paths": [
        "migrations/", "db/migrate/", "alembic/", "prisma/migrations/",
        "supabase/migrations/", "priv/repo/migrations/", "src/main/resources/db/migration/"
      ]
    },
    "deploy-ci": {
      "says": "changed deploy or CI configuration",
      "paths": [
        ".github/workflows/", ".gitlab-ci.yml", ".circleci/", "Jenkinsfile",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        "fly.toml", "vercel.json", "netlify.toml", "render.yaml", "railway.toml",
        "Procfile", "serverless.yml", "k8s/", "helm/", "terraform/"
      ]
    }
  },
  "words": [
    "auth", "login", "logout", "signin", "signup", "session", "password", "passwd",
    "credential", "secret", "token", "apikey", "oauth", "jwt", "crypto", "encrypt",
    "payment", "billing", "invoice", "checkout", "subscription", "stripe",
    "permission", "role", "admin", "privilege", "tenant"
  ],
  "extra_words_key": "careful-words"
}
```
<!-- plc-careful-data:end -->

### `signals` — the three that need no declaration

Each is a **path list, matched by path**. That is the whole mechanism, and the `says` string is
worded to match it exactly.

**`says` states what was observed, never what it means.** The dependency signal says *"touched the
dependency manifest"* — **not** *"added a third-party dependency"*. Editing the `scripts` block of a
`package.json` fires the same rule, and the sentence is still true when it does. Telling those two
apart would need a parser per ecosystem, which is exactly the frozen stack knowledge this feature
refuses to carry.

### `words` — the pre-fill vocabulary for the tick-box screen

Matched against **file and directory names only**, never file contents. A project adds its own with
`careful-words:` in `CLAUDE.md`; the shipped list is never edited by a project.

**There is no upper bound on this list, and this skill ships no mechanism to give it one.** Every
future reader with one more word to add will have a reason. Saying so is cheaper than pretending
the incompleteness note below handles it.

---

## When the check runs, and what a hit changes

The check reads the **changed files in the working tree** at the moment the implementer returns —
before anything is committed. It is `git status` territory, not a commit range.

A hit upgrades **`cadence` and nothing else**: that task's verification tail — acceptance,
validation and quality — runs at `cadence: full` (see `references/mode.md` §Dispatch). `brainstorm`
is phase-scoped and is structurally already past by the time a task runs; `autonomy`'s per-task
surface is the human close approval, which the `close-gate` key owns.

Two boundaries, both of which have to be said out loud rather than assumed:

- **The working tree is not "the files this step changed".** Any unrelated uncommitted edit sitting
  in the tree is counted too. That direction is safe — it can only add scrutiny — but the wording
  everywhere says *uncommitted changes in the working tree*, never *the files this step changed*.
- **A fixup commit does not trigger a careful upgrade.** It gets the ordinary final-pass review that
  `references/review-record.md`'s coverage window requires, and **that is not the same thing** as
  raising three verification stages to `cadence: full`. This is a stated gap, not a covered one.

---

## What this will miss

Four sentences, and they belong wherever this feature is shown to a person.

1. **The list is marked by you, so an incomplete marking will miss things.** PLC does not claim to
   detect every high-risk change automatically — it cannot.
2. **An ecosystem the `signals` lists do not name is a miss.** Dependency manifests and migration
   directories look different in every language, and the block above is a fixed list, not a
   judgement made on the spot.
3. **The word list is English.** Files and directories named in another language, or by a
   project-specific convention, will not match.
4. **The decision is by path, never by what the change did.** A step whose danger lies in what it
   **deleted** or **moved** is invisible here.

---

## Anti-patterns

- **Widening a `says` string into a claim.** *"Touched the dependency manifest"* is what the
  mechanism knows. *"Added a risky dependency"* is not.
- **A reason that infers.** The tick-box screen may say *"this folder has files whose names contain
  `password`"*. It may not say *"this looks like it handles sensitive data"*. The first is a fact
  the reader can check and overrule; the second asks them to trust a judgement nothing made.
- **A second copy of the data block.** Route to this file; never restate the lists.
- **Treating zero suggestions as a failure.** It is a legal, and often correct, outcome.
