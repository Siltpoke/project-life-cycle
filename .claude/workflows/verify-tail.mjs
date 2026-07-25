export const meta = {
  name: 'verify-tail',
  description: 'Cadence post-implementer verification tail: acceptance verifier ∥ code-quality, validator joining on the verifier report',
  phases: [{ title: 'Verify', detail: 'verifier ∥ cq; validator joins on verifier report' }]
}

// ---- INLINED VERBATIM from verify-tail.lib.mjs ----
// IMPORT_OK=false: the Workflow sandbox has no module resolution (static `import`
// parses as a dynamic-import call → SyntaxError; probed 2026-07-16). The canonical,
// node-tested copy of these functions lives in verify-tail.lib.mjs; this inlined copy
// is drift-guarded by verify-tail.inline-guard.test.mjs. Keep both in sync in ONE commit.

const AC = {
  type: 'object',
  required: ['id', 'statement', 'reasoning', 'verdict'],
  properties: {
    id: { type: 'string' },
    statement: { type: 'string' },
    reasoning: { type: 'string' }, // verbatim, never a summary
    testFile: { type: ['string', 'null'] },
    verdict: { enum: ['PASS', 'FAIL', 'UNTESTABLE'] }
  }
}
const FINDING = {
  type: 'object',
  required: ['reasoning', 'severity'],
  properties: {
    file: { type: ['string', 'null'] },
    line: { type: ['number', 'null'] },
    reasoning: { type: 'string' }, // verbatim, refute-first
    severity: { enum: ['Critical', 'Important', 'Minor'] }
  }
}
const SCHEMAS = {
  verifier: { type: 'object', required: ['acs'], properties: { acs: { type: 'array', items: AC } } },
  // reasoning-bearing fields FIRST; NO `approved` — verdict is controller-computed
  validator: {
    type: 'object',
    required: ['findings', 'lieDetection'],
    properties: {
      findings: { type: 'array', items: FINDING },
      lieDetection: {
        type: 'object',
        required: ['reasoning'],
        properties: { claim: { type: 'string' }, traceResult: { type: 'string' }, reasoning: { type: 'string' } }
      }
    }
  },
  cq: {
    type: 'object',
    required: ['findings', 'bloatSmell'],
    properties: {
      strengths: { type: 'array', items: { type: 'string' } },
      findings: { type: 'array', items: FINDING },
      bloatSmell: { type: 'object', required: ['reasoning', 'verdict'], properties: { reasoning: { type: 'string' }, verdict: { type: 'string' } } }
    }
  }
}

function buildVerifierPrompt ({ storyPath, builderSummary }) {
  return [
    'ROLE: ACCEPTANCE VERIFIER.',
    'You did not write this code — fresh context, same as a first-time user of the feature.',
    'Tools: Read/Grep/Glob + test-running Bash. You may write ONLY under tests/acceptance/* — you are read-only on src/. Do NOT read the implementation source at all; you are testing the feature from OUTSIDE, exactly as the story promises it, not as the code happens to be structured. If a test fails, do NOT edit src to make it pass — a verifier that patches the implementation absorbs the finding into a silent fix instead of reporting it; reject that urge.',
    `Read the user story at: ${storyPath}.`,
    'FIRST pass, unanchored: read the whole story end-to-end and form your own list of what "done" observably looks like BEFORE you read the Builder Summary below — so your test list is not anchored to only what the builder claims it built.',
    'Write ONE acceptance test per AC. Name each test to encode the AC id, e.g. `test_AC3_...`. Reuse the existing test framework and fixtures — do not invent a new harness.',
    'Observable-from-outside bar: exercise the system the way a user or an external caller would — HTTP request, UI interaction, a DB-visible side-effect, or an emitted event. Calling an internal function directly is a UNIT test, not acceptance — that AC is not covered by it.',
    'Prohibited: (1) modifying anything under src/; (2) inventing ACs that are not in the story; (3) marking an AC covered when it is only observable by calling internals; (4) silently skipping a hard-to-test AC — mark it UNTESTABLE with the specific reason instead.',
    'Structure each AC refute-first: state why this AC might NOT be met before concluding, then write the verdict LAST, matching the schema field order (reasoning before verdict). Evidence gate: a FAIL must cite file:line + a quoted snippet of the failing assertion or observed behavior — a finding that cannot quote what it indicts is discarded.',
    'Report a verdict PASS / FAIL / UNTESTABLE per AC, with the testFile path and verbatim reasoning (not a summary). UNTESTABLE surfaces as a spec gap, not a pass — it is never silently dropped. You issue only per-AC verdicts, never an overall approval; overall readiness is computed by the controller.',
    'Routing note for the reader of this report: FAIL because the code is wrong → back to the builder; FAIL because the test itself is wrong → re-verify; UNTESTABLE → spec gap, not a code problem.',
    `Builder Summary (read AFTER you have formed your own AC list):\n${builderSummary}`,
    'Return ONLY the structured object matching the provided schema.'
  ].join('\n\n')
}

function buildCqPrompt ({ builderSummary, scopePin }) {
  return [
    'ROLE: CODE-QUALITY REVIEWER.',
    'You did not write this code — fresh context, same as a first-time reader.',
    'Tools: read-only (Read/Grep/Glob + test-running Bash) — you never Edit or Write; a reviewer that edits absorbs findings into silent fixes instead of reporting them.',
    `Review ONLY the diff in git range: ${scopePin}. Do not review code outside this range.`,
    'FIRST, an unanchored full pass over the whole diff to form your own view of its shape and risks, BEFORE you read the Builder Summary or form any seeded suspicion from it.',
    'Lens: is the implementation well-built — craftsmanship — NOT whether it satisfies the story/spec (that is the validator\'s correctness-vs-promise pass, a different lens; do not duplicate it).',
    'Lenses to apply: design, naming, error handling, security, a11y (for UI changes), performance, and test quality.',
    'Forward-looking category — call this out explicitly, separate from the other lenses: does this work for the spec today but hurt a downstream task? (e.g. an unstably-generated name a future consumer will need to be stable.)',
    'Run the BLOAT-SMELL checklist EXPLICITLY — as its own pass, not folded silently into "design" — all 7 items, each answered: (1) is the line-count delta sane for the task\'s complexity? ("add validation" costing 200+ lines is a flag.) (2) was any abstraction created for a single use — a helper with one caller, a factory for one product, an interface with one implementation? (3) was any configurability or flexibility added that the task did not request — an options object, a strategy pattern, a plugin point? (4) is there error handling for impossible scenarios — internal-only callers, framework-guaranteed invariants? (5) are there features beyond the spec — logging, metrics, retry, caching that nobody asked for? (6) would a senior engineer call this overcomplicated? (7) could this be roughly half the lines and still solve the task — if so, sketch the simpler shape.',
    'Evidence gate: every finding cites file:line and quotes the exact snippet it indicts — a finding that cannot quote the code it indicts is discarded, not reported.',
    'Report strengths, plus findings (severity Critical/Important/Minor, file:line, quoted snippet, verbatim reasoning — refute-first, not a summary), plus an explicit bloatSmell verdict with its own reasoning, reasoning before verdict. Do not self-declare overall approval — the controller computes readiness.',
    `Builder Summary:\n${builderSummary}`,
    'Return ONLY the structured object matching the provided schema.'
  ].join('\n\n')
}

function buildValidatorPrompt ({ storyPath, specPath, planPath, builderSummary, verifierReport, diffRange }) {
  return [
    'ROLE: VALIDATOR.',
    'You did not write this code — fresh context, same bar as a first-time reader.',
    'Tools: read-only on the ENTIRE repo (Read/Grep/Glob + test-running Bash, including git log/git diff to see exactly what this task changed). You never Edit or Write — a validator that edits absorbs findings into silent fixes instead of reporting them.',
    `The diff under review is the git range: ${diffRange}. Inspect exactly that range (git diff ${diffRange}); do not review code outside it.`,
    'FIRST, an unanchored full pass: read the diff for this task top to bottom and form your own view of what changed and why, BEFORE you read the Builder Summary\'s framing or any seeded suspicion drawn from it — so you are not anchored to only what the builder says it did.',
    'Lens: does the implementation satisfy the story and spec, with no scope drift in either direction? This is correctness-vs-promise, NOT code quality (that is a separate pass) — do not re-review craftsmanship here.',
    storyPath ? `User story: ${storyPath}` : 'No user story (pure-refactor / dep-bump / docs / internal-tooling phase) — validate correctness-vs-spec, scope drift, folder-boundary, and security-vs-spec; do not chase ACs that do not exist.',
    specPath ? `Spec: ${specPath}` : 'No spec provided — validate against the story + diff only.',
    planPath ? `Plan: ${planPath}` : 'No plan provided — validate against the story + diff only.',
    verifierReport ? `Acceptance Verifier Report:\n${JSON.stringify(verifierReport)}` : 'No acceptance verifier report (lane skipped) — cross-check the Builder Summary against the diff alone.',
    'First make the strongest case against this diff (refute-first), before the per-check findings below — then let STEP 0 and checks 1-7 confirm or refute that case with evidence.',
    'STEP 0 — LIE DETECTION FIRST (this is your primary job, before anything else): (a) for each AC the Builder Summary claims is closed — does the diff actually touch code that could close it? An AC the summary claims closed with no implementing diff, or one the verifier reported FAIL on, is a CRITICAL finding citing the false claim\'s file:line. (b) for each "success" assertion — does the code DO the asserted thing, or does it only log/print that it succeeded? A false success claim is CRITICAL. (c) for each "verified" / "tested" / "works" claim — trace it to a real, independently re-runnable test result: the verifier report, or a test the diff itself contains. A narrative "tests passing" with nothing to trace is never sufficient. An untraceable claim is CRITICAL — the absence of a verifier report NEVER downgrades this; it still must trace to a real test in the diff.',
    'THEN run checks 1-7: (1) AC coverage — a passing test per AC; an AC marked covered with no test is CRITICAL. (2) Out-of-scope drift — a change that does not trace to any AC is a flag; an item explicitly listed Out-of-Scope that snuck in anyway is CRITICAL. (3) Spec adherence — a spec bullet with nothing implementing it is CRITICAL; infrastructure added that is not in the spec is a flag. (4) Folder boundary — changes land where the folder-map says they should. (5) Convention adherence — duplicate logic where an existing helper should have been reused. (6) Security — auth on new endpoints, tenant isolation, no secrets/PII in logs, no raw errors leaking to callers. (7) Edge cases — the story\'s Edge Cases section, each addressed or explicitly flagged as not.',
    'Prohibited: (1) modifying any file; (2) inventing issues — a clean run is a valid, expected outcome ("No findings. Coverage 100%. No drift." is correct when it is true, do not manufacture findings to look thorough); (3) proposing architectural redesigns; (4) re-doing code-quality review — that is a separate pass with a different lens (craftsmanship), this pass is correctness-vs-promise only.',
    'Evidence gate: every finding cites file:line and quotes the exact snippet it indicts — a finding that cannot quote the code it indicts is discarded, not reported.',
    'Report findings reasoning-first, each with file:line, a quoted snippet, and verbatim reasoning (not a summary), with severity Critical/Important/Minor, in the shape `file:line — problem {fix: ...}`. DO NOT state an "approved" verdict — readiness is computed by the controller from the open-severity counts, not self-declared by you.',
    `Builder Summary:\n${builderSummary}`,
    'Return ONLY the structured object matching the provided schema — reasoning and lie-detection fields first, no self-declared verdict.'
  ].join('\n\n')
}

function decideLanes (storyPath) {
  const runVerifier = storyPath != null
  return { runVerifier, validatorJoinsOnVerifier: runVerifier }
}

function cqScopePin (prevTaskTip, builderCommitSHA) {
  return `${prevTaskTip}..${builderCommitSHA}`
}

function mergeFindings ({ verifier, cq, validator }) {
  const holes = []
  // verifier: `undefined` = intentionally skipped (no story) → not a hole; `null` = dispatched-but-failed
  // → hole. The orchestration normalizes a dispatched-but-nullish verifier to `null` so this holds without
  // assuming agent()'s exact failure-return value.
  if (verifier === null) holes.push('verifier') // DO NOT relax `=== null` to `== null` here: `undefined` means skipped (not a hole)
  // cq + validator are ALWAYS dispatched, so any nullish return (null OR undefined) is a failed lane — this
  // removes the dependency on agent() returning exactly `null` (vs undefined) on unrecoverable failure.
  if (cq == null) holes.push('cq')
  if (validator == null) holes.push('validator')
  return { verifier, cq, validator, holes }
}

// Map a verifier lane result to mergeFindings' contract. Pure so the runVerifier-gated raw→null coercion
// (the load-bearing glue) is unit-tested, not only exercised through the un-importable orchestration body.
function normalizeVerifier (verifierRaw, runVerifier) {
  // skipped lane → undefined (not a hole); dispatched-but-nullish (agent() failure, null OR undefined) → null (hole)
  return runVerifier ? (verifierRaw ?? null) : undefined
}
// ---- end inlined ----

// args = { builderCommitSHA, builderSummary, storyPath, prevTaskTip, folderMapSide, specPath, planPath }.
// specPath/planPath are optional (NEW): threaded into the validator prompt so it can
// compare the diff against spec/plan when they exist; absent → the prompt says so explicitly.
// Defensive: the runtime may hand `args` over as a JSON string (observed in an earlier
// self-test — scriptPath invocation delivered a stringified payload, so a raw destructure
// yielded all-undefined). Parse-if-string so real inputs flow whichever form arrives.
const input = typeof args === 'string' ? JSON.parse(args) : args
if (input == null || typeof input !== 'object') throw new Error(`verify-tail: expected an object (or JSON-string) for args, got ${typeof input}`)
const { builderCommitSHA, builderSummary, storyPath, prevTaskTip, specPath, planPath } = input
const lanes = decideLanes(storyPath)
const scopePin = cqScopePin(prevTaskTip, builderCommitSHA)

phase('Verify')
// Fan-out at implementer-return: verifier (if a story exists) ∥ code-quality. Both read-only → conflict-free.
const verifierP = lanes.runVerifier
  ? agent(buildVerifierPrompt({ storyPath, builderSummary }), { schema: SCHEMAS.verifier, label: 'verify:acceptance', phase: 'Verify' })
  : null
const cqP = agent(buildCqPrompt({ builderSummary, scopePin }), { schema: SCHEMAS.cq, label: 'verify:quality', phase: 'Verify' })
// Dynamic join: validator joins ON the verifier report when a story exists (its lie-detection
// cross-checks that report); when there is no story that dependency disappears and it joins the
// initial batch. This conditional edge is exactly what prose control flow cannot own.
const validatorP = verifierP
  ? verifierP.then(vr => agent(buildValidatorPrompt({ storyPath, specPath, planPath, builderSummary, verifierReport: vr, diffRange: scopePin }), { schema: SCHEMAS.validator, label: 'verify:validator', phase: 'Verify' }))
  : agent(buildValidatorPrompt({ storyPath, specPath, planPath, builderSummary, verifierReport: null, diffRange: scopePin }), { schema: SCHEMAS.validator, label: 'verify:validator', phase: 'Verify' })

const [verifierRaw, cq, validator] = await Promise.all([
  verifierP ?? Promise.resolve(undefined), // skipped lane resolves to undefined (no hole)
  cqP,
  validatorP
])
// Normalize: a DISPATCHED verifier that came back nullish (agent() failure — whether null or undefined) is a
// real failure → coerce to null so mergeFindings flags it as a hole. A SKIPPED verifier stays undefined.
const verifier = normalizeVerifier(verifierRaw, lanes.runVerifier)
const merged = mergeFindings({ verifier, cq, validator })
if (merged.holes.length) log(`verification holes (missing reports): ${merged.holes.join(', ')} — main loop re-dispatches once then surfaces`)
return merged
