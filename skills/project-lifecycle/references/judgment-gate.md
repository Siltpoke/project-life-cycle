# Judgment Gate (pre-build judgment check)

Before building, if the step hides a decision being made on the user's behalf, the gate stops it. This document is the single source for **what to do once stopped** -- the hook's deny reason points here, and both humans and the AI read it.

In plain words: the gate is not blocking "writing code". It is blocking "you decided something hard to take back for me, and I never saw the options". After a stop, either put the options in front of the user, or show that this step is truly mechanical, do it, and report in detail afterwards.

## A-1: Surfacing format

List every "decision I am about to make for you". Each one has three fixed parts:

1. **What it is** -- say it in plain words, not just jargon.
2. **Several options + the cost of each** -- what each option is and what choosing it costs, explained in plain words first; the options themselves must not be written only in jargon.
3. **An escape option** -- always leave one way out, in one of three wordings:
   - "None of these, I'll tell you" -- none of the options is right; the user says what they want.
   - "I'm not sure, suggest more" -- the user has not figured it out yet and wants the AI to propose more.
   - "You decide" -- the user authorizes the AI to decide.

Options must not be hidden inside a prompt handed to a subagent with only a conclusion shown to the user -- the options must be put directly where the user can see them.

## A-2: Authorization stack and decision-type timing (shadow recording protocol)

**Shadow mode (phase 1): record what you would do; do not block, do not hide, do not release.** This section is a recording protocol. For each decision you are about to make on the user's behalf, you write down what the routing below WOULD do. Nothing here stops a tool call, hides a line from a batch, or releases a human check; the only real block in phase 1 is the action-level hard-stop (`judgment-action-gate.sh`). The recorder is `hooks/judgment-shadow-record.sh`; it always exits 0.

**Authorization stack.** For each decision, name the authorization you are relying on, as three plain facts: **who** gave it, **what** they authorized, and the **scope** it covers. The strength you assign goes in the `authorization_tier` field. A claim with no who/what/scope is a weak claim; record it as such rather than rounding it up.

**Decision-type timing map.** Classify each decision as exactly one of four types and record the routing it would get:

| decision_type | would_action | would_time |
|---|---|---|
| `taste` | `shadow-record` | `at-finish` |
| `product-boundary` | `confirm-before-build` | `before-build` |
| `side-effect` | `hard-stop` | `none` |
| `mechanical` | `do-and-report` | `none` |

In plain words: taste calls are collected and shown to the user when you finish; product-boundary calls would be confirmed before building; side effects would be a hard stop at the moment of the action (cross-checked against the factual trigger in the action gate); mechanical steps would just be done, then reported per "A-3".

**Log line shape.** One JSONL line per decision, appended to `${TMPDIR:-/tmp}/plc-judgment-shadow.$SID.jsonl`, with exactly these fields: `id`, `what`, `authorization_tier`, `decision_type`, `would_action`, `would_time`. `would_action` is one of `shadow-record`, `confirm-before-build`, `hard-stop`, `do-and-report`; `would_time` is one of `before-build`, `at-finish`, `none`. **Declaration channel: PROVISIONAL, NOT YET ACTIVE.** The recorder hook reads declared decisions from a `tool_input.judgment` field (one object or an array), but it is not yet proven that Claude Code passes an unknown `tool_input` key through to a PreToolUse hook (it may strip it, or reject the call). Until a live probe proves the channel, do NOT add this field to your Edit, Write or Bash tool calls; nothing in this protocol asks you to. Unsure of the type -> note your best type and say so in the decision text you show the user.

## A-3: [C] After-the-fact report template

After a mechanical step is done, report exactly three lines, no more, no fewer:

- **Before** -- the state before the change.
- **What changed + which new tests were added** -- the actual change, and the tests added for it (write "none added" explicitly if there are none).
- **Why** -- the reason for changing it this way.

## A-4: mock condition (mock)

If the step changes an interface the user can see, a **confirmed mock** must exist before acting:

- **A mock mechanism exists** -> use it, and take the mock the user confirmed.
- **None** (for example an adopter project without a mock mechanism) -> ask the user in chat for an image or a description, and proceed once confirmed.

This is one rule with an if, not a hard dependency on it: if a mock mechanism is there, use it; if not, fall back to asking in chat.
