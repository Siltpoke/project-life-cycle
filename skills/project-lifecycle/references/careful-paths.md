# `careful-paths` — the places this project wants handled carefully, and the three signals that need no declaration

`mode: fast` trades scrutiny for speed. **Its entire justification is the assumption that being
wrong is cheap.** Some changes do not fit that assumption — the login code, the payment code, a new
third-party dependency, a database schema change, the deploy configuration.

This file is the exception channel. When a task's changes touch one of those places, **that task's
verification tail runs at `detailed`**, and it says which rule fired.

**It does not claim to find every risky change. It cannot, and saying it can would be a lie.**
Read §"What this will miss" before relying on it.

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
