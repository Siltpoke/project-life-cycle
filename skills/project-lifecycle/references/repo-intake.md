# Repo Intake — GitHub onboarding for non-technical users

Fires at **new-project / first-milestone kickoff** to sort out where the user's code
will live. Written for non-technical vibe coders (some don't know what GitHub is).
Reuses the plain-language voice in `references/audience-tone.md` and is gated by the
`audience:` key: run under `adaptive`/`plain`; **skip entirely under `audience: technical`**
(a technical user already knows GitHub and has their own habits).

**The load-bearing distinction:** LOCAL git (checkpoints on the user's own computer) is
required for this skill's discipline to work at all — the close-gate inspects commits and
diffs. A GITHUB repo (code stored online) is a separate, OPTIONAL backup/share layer. So
this intake ensures local git quietly, and treats GitHub as something it offers, explains,
**offers to create for the user** (via `gh`, degrading to GitHub's own guide), and re-offers —
never a blocker. The only steps left to the user are the two that must be theirs: creating the
account and the one-time `gh auth login` (never faked — same rule as `references/deploy.md`).

## When it fires

- At **new-project / first-milestone kickoff only** — the large-work path of the intent-gate
  (`references/intent-gate.md`), before seeding the brainstorm. Once per project, not per request.
- Skipped entirely under `audience: technical`.

## The intake question

Ask once, in the `audience-tone.md` floor register:

> "Do you already have a GitHub link for this project? (GitHub is a free website that stores
> your code online — like a backup you can't lose, that also lets you share it and undo
> mistakes.) If yes, paste it. If not, no problem — I can set one up for you, or we can start
> right away and add it later."

- **Has a link** → record it, proceed to the normal kickoff.
- **No link / "what's GitHub?"** → go to the explainer + offer-to-create ladder below.

## No repo / doesn't know GitHub

Plain-language, non-blocking, in this order:

1. **Ensure local checkpoints first.** Frame it plainly: *"First I'll set up checkpoints on
   your computer so you can always undo — this lives on your machine, nothing goes online
   yet."* If the project folder is not already a git repo, run `git init` (a local, offline
   action — no GitHub, no account, nothing scary). This is the one non-optional piece, because
   the skill's safety checks need it — but it is local-only.
2. **Explain GitHub + why (2-3 plain sentences).** e.g. *"GitHub is a free website that keeps a
   copy of your code online. It means you can't lose your work if your laptop dies, you can share
   the project with a link, and it keeps a history so you can roll back. You'll also need it later
   if you want to put your app on the internet."*
3. **Offer to create the repo _for_ them** — then walk the prereq ladder below. The old
   behaviour (hand them GitHub's guide URL and let them click through the browser) survives as
   the bottom-rung fallback, not the default.

### Offer-to-create ladder (mirror of `references/deploy.md`)

Same discipline as the deploy offer: **offer, never impose; check prerequisites; degrade
gracefully; the human-only steps stay the human's.** I can automate everything _after_ the
account exists and the CLI is authenticated — I cannot (and must not) fake the two steps that
are irreducibly the user's own.

Offer once, in the floor register: *"Want me to set this up on GitHub for you? I can create the
online project and back up your work in one go — you just need a GitHub account and a one-time
sign-in."* On yes, detect where they are and ask **only** for the missing human step:

1. **No GitHub account** → account sign-up is the user's own step (email verification + a
   captcha + agreeing to the terms — I can't and shouldn't do this for you). Point them plainly
   at `https://github.com/signup`, explain it's free and takes a minute, and wait. *"Make a free
   account here — it takes a minute. Ping me when you're in and I'll do the rest."*
2. **Has account, `gh` not installed** → offer to install GitHub's CLI (`brew install gh` on
   macOS, package manager on Linux, or the Windows installer). If they'd rather not, drop to the
   browser-guide fallback (step 5).
3. **`gh` installed, not signed in** → `gh auth login` is **interactive and the user's own step**
   — never faked, never scripted around (same rule as `deploy.md`'s login). Walk them through it
   plainly: *"Run this and pick 'GitHub.com' → 'HTTPS' → 'login with a browser', then paste the
   code it shows you."* Wait for it to finish.
4. **Signed in** → I create it: `gh repo create <name> --private --source . --push`. This makes
   the online repo, wires it as the `origin` remote, and pushes the local checkpoints in one
   shot. Default **private** (safer for a beginner); ask once if they'd prefer public. Report
   back the repo URL as their project's online home.
5. **Any rung they decline / `gh` unavailable / it errors** → fall back to GitHub's own guide,
   non-blocking, exactly as before: `https://docs.github.com/en/get-started/quickstart/create-a-repo`,
   then *"You can set that up whenever you like — we can start building right now."*

Never block on any of it: local git (step 1 of the outer list) already exists, so building can
start immediately regardless of where they stop on this ladder.

## Re-offer moments

Re-surface the GitHub offer once, low-key, at natural seams — not on every turn. Re-offer the
**create-for-you** path, not just the guide link — if they've since made an account or installed
`gh`, the ladder can now pick up further along:

- Before the first real work, if the project is still GitHub-less: *"Quick reminder — setting up
  GitHub now means your work is backed up online from the start. Want me to create it for you?
  Otherwise we carry on."*
- At first milestone close: *"Good moment to back this up online if you haven't — want me to
  create the GitHub repo and push your work up now?"*

## Local-git-always

Independent of GitHub: if the project directory is not a git repository, the skill ensures
`git init` happens (framed as "checkpoints on your computer"), because the close-gate and the
per-task cadence require local git to inspect commits and diffs. GitHub remains optional; local
git does not. Both are framed non-technically for this audience.

## Before / after (voice proof)

| Situation | ✗ Off-layer | ✓ On floor |
|---|---|---|
| User: "what's GitHub? I don't have that" | "You need to `git remote add origin` a GitHub repo and push." | "No problem! GitHub is a free site that stores your code online so you can't lose it. We don't need it to start — I'll set up undo-checkpoints on your computer now. And if you'd like, I can create the online project for you: just make a free account at https://github.com/signup, then I'll handle the rest." |
| User: "yeah set it up for me" (has account, signed in) | "Run `gh repo create myproj --private --source . --push`." | "Done — I created it and pushed your work up. Your project now lives at github.com/you/myproj. It's private, so only you can see it — say the word if you'd rather make it public." |
| User: "set it up" but `gh` isn't signed in | (runs `gh repo create`, it fails with an auth error) | "One quick one-time step that's yours to do: run `gh auth login`, pick 'login with a browser', paste the code it shows. Ping me when it's done and I'll create the repo." |
| User pastes a github.com link | (silently continues) | "Got it — I'll use that as your project's online home. Let's start." |
