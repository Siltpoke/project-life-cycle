# Deploy — putting a non-technical user's project online

Fires at **project finish** to offer help publishing the app. Written for non-technical
vibe coders. Reuses the plain-language voice in `references/audience-tone.md` and is gated
by the `audience:` key: run under `adaptive`/`plain`; **skip entirely under `audience: technical`**
(a technical user deploys their own way).

**The load-bearing reality:** deploy CLIs run in the USER's environment, and every platform
needs an interactive browser login (`vercel login`, `gh auth login`) the agent CANNOT complete
for them. GitHub Pages also needs a GitHub repo. So this is
**offer-to-run, prerequisite-gated, with graceful fallback** — never a naive "run the CLI" that
fails confusingly for exactly this audience.

## When it fires

- At **project finish only** — the terminal state: the final `docs/ROADMAP.md` milestone flips
  to done, OR the user signals the project is complete ("how do I put this online?", "I'm done").
- **Once. NOT at every milestone-done.** Skipped entirely under `audience: technical`.

## The offer

Ask once, in the `audience-tone.md` floor register:

> "Your project works! Want help putting it online so other people can actually use it? (Right
> now it only runs on your computer.)"

- **No** → drop it; note they can ask anytime.
- **Yes** → go to the option compare.

## Stack-aware option compare

Detect the project's shape from the repo, then **recommend 1 best fit + name 2-3 alternatives
(always name GitHub Pages)**, with plain-English differences, and link each platform's own guide.
Keep it to a recommendation + a short "others if you're curious" — never a 5-way menu (it
overwhelms this audience).

| Project shape | Recommend | Name as alternatives | Plain-English difference |
|---|---|---|---|
| Static site (plain HTML/CSS/JS, or a built SPA) | GitHub Pages (free) or Vercel | Netlify, Cloudflare Pages | "GitHub Pages is free and simplest for a plain site; Vercel/Netlify add live previews + custom domains more easily" |
| Framework app (Next.js / React / Vite) | Vercel | Netlify, Cloudflare Pages | "Vercel is made by the Next.js team, so it needs the least setup" |
| Has a backend / server / database | Railway or Render | Fly.io | "these run your server code and database, which the free static hosts above can't" |

Guide links (link the chosen one; do not reproduce steps that rot):
- GitHub Pages — `https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site`
- Vercel — `https://vercel.com/docs/getting-started-with-vercel`
- Netlify — `https://docs.netlify.com/get-started/`
- Railway — `https://docs.railway.com/quick-start`
- Render — `https://render.com/docs`

## Prerequisite-gated run

If the user wants the skill to do it:

1. **Detect prerequisites** for the chosen platform: is the CLI installed (`vercel` / `gh` / …)?
   is the user logged in (`gh auth status`, `vercel whoami`)? does a GitHub repo exist (for
   repo-based deploys like Pages)?
2. **All prereqs met** → run the deploy (the fast path). Report the live URL in plain language.
3. **A prereq missing** → do NOT run-and-fail. Name the ONE missing step plainly and either guide
   them through it or fall back to explain-+-link:
   - *not logged in* → *"You'll need to log in first — run `vercel login`, it opens your browser to
     sign in (free). Tell me when you're back and I'll continue."* (The login is always the user's
     step — the agent cannot sign in for them; say so, don't pretend.)
   - *CLI not installed* → name the one install command, or switch to a platform whose guide they can
     follow in the browser.
   - *no GitHub repo, Pages chosen* → help them create a GitHub repo first, or recommend a host that doesn't need a repo (Vercel / Netlify).
4. **Never leave the user at a raw CLI error.** Every failure path resolves to a plain next step.

## Before / after (voice proof)

| Situation | ✗ Off-layer | ✓ On floor |
|---|---|---|
| Project done, offering deploy | "Ready to deploy. Configure your CI/CD pipeline and provision a host." | "Your project works! Want help putting it online so people can use it? Right now it only runs on your computer." |
| User said yes but `vercel` isn't logged in | (runs `vercel`, prints an auth error, stops) | "Almost there — you just need to log in once. Run `vercel login` (it opens your browser, it's free), and tell me when you're done. Then I'll put it online for you." |
