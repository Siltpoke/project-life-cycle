# Proactive Best-Practice Surfacing — app tips for non-technical users

During development, when a genuine **high-value** app-improvement opportunity appears in what the
user is building, surface it inline in plain language and offer to apply it. Written for
non-technical vibe coders who don't know these improvements are possible. Reuses the plain-language
voice in `references/audience-tone.md` and is gated by the `audience:` key: run under
`adaptive`/`plain`; **skip entirely under `audience: technical`** (a technical user already knows these).

**Not to be confused with `references/cost-aware-behaviors.md`** — that governs the *agent's own*
token discipline (how Claude reads files / dispatches subagents). THIS file governs improvements to
the *user's app* (speed, loading, efficiency). Different concern, different file.

**This is the recognition + plain-language-offer layer, not a re-implementation.** When the user says
yes, draw the actual technique from the project's frontend/backend skills (e.g. `frontend-design`,
`vercel-react-best-practices`, `backend-patterns` when available).

## When it fires

- **During development** (the per-task cadence build step), **immediately when a genuine high-value
  opportunity appears** in what's being built — not batched to a checkpoint, not a project-finish dump.
- Skipped entirely under `audience: technical`.
- Governed by the Anti-nag rules below so "immediately" stays high-signal, never a firehose.
- **Where the offer surfaces:** the tip is an offer→wait-for-yes/no handshake, so it belongs wherever the agent has a direct user loop — main-context / single-implementer work. On split phases where a dispatched implementer subagent builds without a user loop, don't stall the subagent; surface the deferred tips at the main-context review seam after the build returns.

## The surfacing pattern

When an opportunity appears, in the `audience-tone.md` floor register: **name the issue plainly →
why it matters (concrete) → offer to apply**. One tip, phrased as a question.

> "Quick heads-up: your list loads all 500 items at once, which makes the page slow to open. I can add
> pagination — load 20 at a time with a 'show more' button — so it opens fast. Want me to?"

- **Yes** → apply it (draw the technique from the relevant frontend/backend skill).
- **No** → drop it; do not raise it again this session.

## Opportunity catalogue

Common high-value opportunities to recognize (examples, not exhaustive):

| Area | Signal in the code | Plain-language offer |
|---|---|---|
| Frontend — images | large unoptimized images | "these photos are big and slow to load — I can shrink and lazy-load them" |
| Frontend — lists | rendering a big list all at once | "load a few at a time (pagination / infinite scroll) so it opens fast" |
| Frontend — loading states | a fetch with no feedback | "show a little spinner so it doesn't look frozen while loading" |
| Frontend — bundle | shipping everything upfront | "load some parts only when needed (code-splitting) so first load is faster" |
| Backend — pagination | returning all rows at once | "return results in pages so the server and page stay fast" |
| Backend — caching | recomputing the same result | "remember the result for a bit (caching) so repeat requests are instant" |
| Backend — DB indexes | slow lookups on a growing table | "add an index so lookups stay fast as your data grows" |
| Backend — N+1 queries | a database query inside a loop | "fetch it all in one go instead of one-per-item, so it's much faster" |

## Anti-nag rules

The operational contract — apply every time before surfacing a tip:

1. **High-value + relevant only** — surface only a meaningful improvement to what's actively being
   built. Never pedantic micro-optimizations.
2. **One tip per opportunity** — don't stack multiple tips into one interruption; don't lecture.
3. **Never re-surface a declined tip** in the same session — "no" means dropped.
4. **Offer, never impose** — always a question the user can wave off in one word.

## Before / after (voice proof)

| Situation | ✗ Off-layer / naggy | ✓ On floor |
|---|---|---|
| User just built a photo gallery with big images | "You should implement responsive `srcset`, WebP conversion, and lazy-loading via IntersectionObserver." | "Quick tip: those photos are large, so the page will load slowly. I can shrink them and load them only as you scroll. Want me to?" |
| User wrote a fine 10-item list | "You could add virtualization and memoization here." (low value — suppress) | (nothing — the list is small; no meaningful win, so no tip per anti-nag rule 1) |
