# Cross-family blind 2nd agent

The brainstorm's blind 2nd agent (`brainstorm-research-protocol.md` §step-4) normally runs on the **same AI family** as the 1st agent. `review-record.md`'s three-mechanism self-review bias names the third mechanism **"family taste"** — a shared-lineage reviewer cannot see it. This feature lets that blind 2nd agent run on a **different CLI family** (codex is the built adapter; gemini/agy are design-contract) for genuine lineage diversity.

**The governing invariant: armed-optional, never a hard dependency.** A repo that has never set `second-agent-family` (or leaves it `auto`) behaves **byte-identical** to a PLC that has never heard of this feature. Cross-family fires ONLY when a foreign family is explicitly armed AND present AND authed AND returns a parseable, non-empty answer — every gate degrades to today's same-family subagent. **Degrades, but no longer silently to a chained caller:** the runner's exit status says which happened (0 answer / 3 fallback / 2 bad invocation / 1 unwritable envelope). The byte-identical guarantee above is unaffected — an un-armed repo never invokes the runner at all.

## The `second-agent-family` policy key

`second-agent-family: auto | same-family | foreign:codex | foreign:<name> | off` (default `auto`).

- **`auto` / `same-family` / unset** → today's same-family subagent. **Byte-identical** — no offer, no consent prompt, no spawn, no timing change.
- **`foreign:codex`** (or another armed family) → the cross-family path below.
- **`off`** → disables **only** the foreign path (equivalent to `same-family` here); it never disables the core Step-4 review, which is not optional.
- The value names the **role** (`same-family` / `foreign:<name>`), NOT a model. This removes the ambiguity a bare `claude` would carry (same-family if the primary agent is Claude, foreign otherwise).

**Scope of "byte-identical":** it applies to the **un-armed** path only. Arming a foreign family is an explicit opt-in that legitimately changes behavior (it introduces the consent prompt, the availability probe, and the spawn). "Byte-identical" is a promise to adopters who do nothing, not a claim that arming is invisible.

## The 4-gate fail-safe flow

The adapter is `scripts/cross-family-review.sh` (built, codex-only). Step-4 invokes it with a **synthesized decision packet** (see Privacy). Every failure sets `status:fallback` with a reason-class, and the caller then runs the same-family subagent — but **it does not always exit 0**: a fallback exits **3**, a bad invocation exits **2**, and an envelope that could not be written exits **1**. Chaining on it needs `|| true` when a fallback is acceptable, or a test for `3` when it is not.

```
armed foreign:codex →
  gate 0  family supported?         no → fallback: unsupported-family
  gate 1  binary installed?         no → OFFER guided install (below); still absent → fallback: not-installed
          (resolved binary must NOT be inside the repo tree — reject a project-local shim)
  gate 2  authed? (noninteractive)  no → fallback: not-authed
  gate 3  spawn ok? (wall-clock cap, stdin closed, read-only sandbox)
                                    timeout → fallback: timed-out
                                    engine says `usage limit` → fallback: quota-exhausted
                                    any other error → fallback: spawn-failed
  gate 4  output parseable?         no → fallback: unparseable
          required field present?   no → fallback: unparseable
          required field has content?
                                    no → fallback: empty-answer
          (content is emptiness PER TYPE: "" / whitespace-only / [] / {} are empty;
           0, a one-word string and a non-empty array or object are not)
  all pass → status: succeeded, use the foreign pick
```

The proven codex invocation (verified by a real probe run):
`codex exec --json --ephemeral -s read-only --skip-git-repo-check --output-schema <schema-file> -o <lastmsg-file> - < <packet>`. Contract note: codex `--output-schema` takes a **FILE path** (opposite of `claude -p`'s `--json-schema`, which takes INLINE JSON) — this is why each family needs its own adapter, never one universal call.

## Visibility over silence

Fallback is non-blocking, but it is **never invisible**. The qa-log entry records both:
- `2nd-agent engine:` — `same-family` or `foreign:codex`.
- `2nd-agent status:` — `succeeded` or `fallback(<reason-class>)`.

You may not claim "a different family reviewed this" when it silently fell back. Terminal noise stays low; the durable record stays honest. This is the standing `Same family:` field (`brainstorm-research-protocol.md`) made real.

## Privacy is a boundary; consent at ARM time

Sending decision context to a different provider (e.g. codex → ChatGPT, a different retention/policy domain) is a **privacy boundary**, not a footnote. `-s read-only` is a filesystem sandbox, **not privacy isolation** — a foreign CLI can still read whatever you hand it.

- **Consent once, at arm time** (not per-run spam): the first time a foreign family is armed, confirm the cross-provider data flow + cross-billing.
- **Synthesized decision packet, not raw workspace.** The foreign agent receives a composed packet (the question + options + research), never a path into the repo. Redact obvious secret patterns from the packet before spawning.
- **Cross-billing** lands on the user's other account (e.g. their ChatGPT/codex plan). Disclose at arm time; cap wall-clock + input size per run.

## Armed-but-absent → offer guided install

Modeled on `references/repo-intake.md` + `references/deploy.md` (prereq-gated ladder). When a family is armed but not installed/authed:

1. **Offer once, never block.** "You armed `foreign:codex` but codex isn't installed — want help setting it up? (optional; I'll use the Claude reviewer either way.)" Decline → silent same-family fallback, don't re-offer this session.
2. **The install/login is the USER's own step** — PLC may run the documented install command where a package channel exists, but auth/login is never automated or faked (same boundary as `gh auth login` in repo-intake). Bottom rung: link the family's official install guide.
3. **Audience-scaled** (`audience:`): non-technical users get the walk-through; `technical` users get the one-line command.
4. **After install**, re-run the availability probe; still absent (login not completed) → silent fallback, resumable next session.

## Discoverability — installed-but-unarmed offer (the mirror of armed-but-absent)

The section above handles *armed-but-absent* (you asked for a family that isn't installed → offer to install it). The mirror is *installed-but-unarmed*: a user who **has** `codex`/`gemini` installed but never set `second-agent-family` has no way to discover cross-family review exists — the default is `auto` (same-family) and the feature sits only in reference docs. Without this, the feature is invisible to exactly the people who could use it for free.

**Trigger — ask-once, key-absence gated.** At the **first brainstorm step-4 in a project**, if BOTH hold:
1. `second-agent-family` is **absent** from CLAUDE.md (project AND user-global) — the same ask-once mechanism the `archaeology` key uses (unset = offer once; any present value = already engaged, never offer), and
2. a foreign CLI is detected **present + authed** (reuse `scripts/cross-family-review.sh`'s availability probe — `command -v` + the noninteractive auth check),

then make a **one-time** offer before the same-family dispatch. If no foreign CLI is installed, or the key is already set to anything (`auto` / `off` / `foreign:*`), **do nothing** — a user with no second CLI or a decided preference sees the byte-identical same-family path, exactly as today.

**The offer (audience-scaled per `audience:`), informed but not consent-smuggling.** e.g. *"Detected `codex` installed — want the blind 2nd reviewer to run on it (a different AI lineage) for a more independent check? It sends a synthesized decision packet to codex/your ChatGPT account (a small cross-billed spawn per decision). Optional — I'll use the same-family reviewer otherwise."* The one-line data-flow + cross-billing note makes the offer **informed**; it is NOT the formal consent (see below).

**Decline is durable (never re-ask).** On decline, write `second-agent-family: off` to the project `CLAUDE.md` — semantically "no foreign review," which is exactly what a decliner wants, and (being a present value) it suppresses the offer forever. A user who never wants the offer in *any* project sets `second-agent-family` in `~/.claude/CLAUDE.md` (user-global, mirroring `references-log:`) — a present global value suppresses the offer everywhere.

**Accept arms the key; it does NOT grant the privacy consent.** Accepting writes `second-agent-family: foreign:codex`. The arm-time privacy consent (cross-provider data flow) still fires **separately** at the first actual spawn — the offer's one-line note informs, but the formal arm-time consent is never folded into the offer click. Accept → arm → (first spawn) → privacy consent → spawn. The offer never auto-arms without an explicit yes, and never spawns on the strength of the offer alone.

`/init-harness` may also mention the key as a discovery surface, but the actionable offer lives here at step-4 (the moment it is contextual — the blind 2nd agent is about to run).

## Two paths, one set of gates

The 4-gate flow above serves **two** callers. Without a runner for the second one, every
cross-family CODE review is an ad-hoc `codex exec` composed on
the spot, which is exactly as reliable as it sounds. Three failure shapes are typical
(a hang killed by the caller's tool timeout; a refusal —
`Not inside a trusted directory and --skip-git-repo-check was not specified`; and a run that
spent its whole budget printing the files under review). All three are prevented by gates
the runner already applies.

| path | runner | schema | gate-4 field |
|---|---|---|---|
| brainstorm blind 2nd agent | `scripts/cross-family-review.sh` | `cross-family-review.schema.json` | `independent_pick` |
| **code review** | `scripts/cross-family-code-review.sh` | `cross-family-code-review.schema.json` | `verdict` |

The gates are **not duplicated**. The brainstorm runner takes three defaulted flags
(`--schema` / `--require` / `--payload-key`); omitting them gives its brainstorm-path behaviour, which its
own tests cover. A copied guard drifts.

```bash
git diff main...HEAD > /tmp/d.patch
bash scripts/cross-family-code-review.sh \
  --diff /tmp/d.patch --brief /tmp/lens.md --out /tmp/review.json
rc=$?
# exit 3 = the foreign reviewer produced no usable answer (a legitimate fallback, NOT a failure).
# exit 2 = you called this wrong. 0 = a real review is in /tmp/review.json.
# Chaining? `… || true` if a fallback is acceptable; test for 3 if it is not.
```

**`--brief` carries the lens, and one round asks ONE lens.** "Different lens rather than more
reviewers" is the rule: asking
the same three questions a second time returns the same three findings.

**The diff is handed over inline.** The reviewer is never asked to go and find the code, so it
cannot spend its budget discovering the repository instead of reading the change — which is
precisely the third failure shape above.

**`status: fallback` means NO REVIEW HAPPENED.** It is not a clean bill of health, and a caller
that treats it as one has reproduced the failure this runner exists to make visible. A review that
ran and found nothing returns `status: succeeded` with `findings: []`. The two are different
states and the test suite pins the difference.

## Never overrides

The foreign pick and any disagreement surface to the human exactly as the same-family path does. The foreign agent is a **dissent source**, never an authority router — it never silently overrides the 1st agent's decision.

## Mutual independence — borrow the FORMAT, never the runtime

PLC **borrows established design shapes** for a cross-family reviewer — a provider interface, a family→CLI registry, a per-family failure-signature taxonomy — and re-expresses them in PLC's own bash+jq envelope. PLC does **not import** another tool's code; that would be a runtime dependency, which violates PLC's depend-on-nothing-external principle. PLC stays independent: PLC consumes a *format/design*, never a running dependency. Any borrowed schema is locally owned + versioned here.

## DESIGN-ONLY — adopter build contract for a second family

The codex adapter is BUILT because it has a consumer today. A **registry of many families** is deliberately NOT built (that would be machinery without a current consumer). An adopter who later arms `foreign:gemini` / `foreign:agy` builds their adapter following codex's mold + this contract:

- **Per-adapter capability manifest** (design target): binary name · min version · noninteractive auth probe · headless invocation syntax · output channel (file vs stream) · schema input form (file vs inline) · sandbox guarantee · wall-clock timeout · known-failure signatures. gemini's shape is scouted on paper (`gemini -p --approval-mode plan`, stdin composition) but unverified — a real spawn is required before trusting it, exactly as the codex probe did.
- **A registry** mapping `foreign:<name>` → its adapter, with version bounds. Until built, `scripts/cross-family-review.sh` supports `codex` only and returns `unsupported-family` for anything else — envelope `status:fallback`, **exit 2**. This is *not* fail-safe for a chained caller: exit 2 and exit 3 both break an `&&` chain, so neither number would be fail-safe. 2 is deliberate — `foreign:<name>` is a published, armable value, so reaching this line usually means the armed name is one no adapter implements, and that is a configuration error the caller should see rather than a reviewer that had nothing to say.
- **Fallback-frequency metrics** (design target): a local counter of succeeded-vs-fallback so a silently-always-falling-back armed family is detectable, not mistaken for working. Not built now.

These are the parts that only pay off with a second armed family; they are documented so the path exists, not built speculatively.
