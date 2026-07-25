import { test } from 'node:test'
import assert from 'node:assert/strict'
import { SCHEMAS, validateAgainstSchema, buildVerifierPrompt, buildCqPrompt, buildValidatorPrompt, decideLanes, cqScopePin, mergeFindings, normalizeVerifier } from './verify-tail.lib.mjs'

test('validator schema orders reasoning before verdict inputs, no approved boolean', () => {
  const keys = Object.keys(SCHEMAS.validator.properties)
  assert.ok(keys.includes('findings'))
  assert.ok(keys.includes('lieDetection'))
  assert.ok(!keys.includes('approved'), 'no reviewer-stated approval boolean')
})

test('validateAgainstSchema accepts a well-formed verifier return', () => {
  const good = { acs: [{ id: 'AC1', statement: 's', verdict: 'PASS', testFile: 't.mjs', reasoning: 'why' }] }
  assert.equal(validateAgainstSchema(good, SCHEMAS.verifier).ok, true)
})

test('validateAgainstSchema rejects a malformed verifier return without throwing', () => {
  const bad = { acs: [{ id: 'AC1', verdict: 'MAYBE' }] } // bad enum + missing keys
  const r = validateAgainstSchema(bad, SCHEMAS.verifier)
  assert.equal(r.ok, false)
  assert.ok(r.errors.length > 0)
})

test('verifier prompt embeds the story path and demands observable-from-outside tests', () => {
  const p = buildVerifierPrompt({ storyPath: 'docs/.../story.md', builderSummary: 'S' })
  assert.match(p, /docs\/\.\.\.\/story\.md/)
  assert.match(p, /observable|from outside|HTTP|UI|side-effect/i)
})

test('verifier prompt demands UNTESTABLE handling for hard-to-test ACs, not silent skip', () => {
  const p = buildVerifierPrompt({ storyPath: 's', builderSummary: 'S' })
  assert.match(p, /UNTESTABLE/)
})

test('verifier prompt forbids editing src to make a test pass (read-only on src)', () => {
  const p = buildVerifierPrompt({ storyPath: 's', builderSummary: 'S' })
  assert.match(p, /read-only on src|do not edit src|not edit src/i)
})

test('verifier prompt runs an unanchored pass over the story before reading the Builder Summary', () => {
  const p = buildVerifierPrompt({ storyPath: 's', builderSummary: 'S' })
  assert.match(p, /unanchored/i)
})

test('cq prompt pins the review scope and demands the bloat-smell pass', () => {
  const p = buildCqPrompt({ builderSummary: 'S', scopePin: 'abc..def' })
  assert.match(p, /abc\.\.def/)
  assert.match(p, /bloat/i)
})

test('cq prompt runs all 7 bloat-smell checklist items explicitly', () => {
  const p = buildCqPrompt({ builderSummary: 'S', scopePin: 'abc..def' })
  assert.match(p, /half the lines/i)
  assert.match(p, /single use|one caller/i)
  assert.match(p, /impossible/i)
  assert.match(p, /overcomplicated/i)
  assert.match(p, /beyond the spec|features beyond/i)
})

test('cq prompt calls out the forward-looking "hurts a downstream task" category explicitly', () => {
  const p = buildCqPrompt({ builderSummary: 'S', scopePin: 'abc..def' })
  assert.match(p, /downstream task/i)
})

test('cq prompt is a distinct craftsmanship lens, not a validator clone', () => {
  const p = buildCqPrompt({ builderSummary: 'S', scopePin: 'abc..def' })
  assert.match(p, /craftsmanship/i)
})

test('validator prompt runs lie-detection and forbids self-stated approval', () => {
  const p = buildValidatorPrompt({ storyPath: 's', specPath: null, planPath: null, builderSummary: 'S', verifierReport: { acs: [] } })
  assert.match(p, /lie|trace|verify.*claim/i)
  assert.match(p, /do not.*approv|no.*approved|verdict.*computed/i)
})

test('validator prompt runs an unanchored pass over the diff before the Builder Summary framing', () => {
  const p = buildValidatorPrompt({ storyPath: 's', specPath: null, planPath: null, builderSummary: 'S', verifierReport: null })
  assert.match(p, /unanchored/i)
})

test('validator prompt runs the 3-part lie-detection sub-checks (claimed-closed, false success, untraceable verified claims)', () => {
  const p = buildValidatorPrompt({ storyPath: 's', specPath: null, planPath: null, builderSummary: 'S', verifierReport: null })
  assert.match(p, /LIE DETECTION FIRST/i)
  assert.match(p, /claimed.{0,20}closed|claims.{0,20}closed/i)
  assert.match(p, /false success/i)
  assert.match(p, /untraceable/i)
})

test('validator prompt requires a quoted snippet for every finding (evidence gate)', () => {
  const p = buildValidatorPrompt({ storyPath: 's', specPath: null, planPath: null, builderSummary: 'S', verifierReport: null, diffRange: 'aaa..bbb' })
  assert.match(p, /snippet|quote/i)
})

test('validator prompt anchors inspection to the passed diffRange', () => {
  const p = buildValidatorPrompt({ storyPath: 's', specPath: null, planPath: null, builderSummary: 'S', verifierReport: null, diffRange: 'aaa..bbb' })
  assert.match(p, /aaa\.\.bbb/)
})

test('validator prompt states the refute-first framing explicitly', () => {
  const p = buildValidatorPrompt({ storyPath: 's', specPath: null, planPath: null, builderSummary: 'S', verifierReport: null, diffRange: 'aaa..bbb' })
  assert.match(p, /refute/i)
})

test('validator prompt references specPath and planPath when given', () => {
  const p = buildValidatorPrompt({ storyPath: 's', specPath: 'docs/spec.md', planPath: 'docs/plan.md', builderSummary: 'S', verifierReport: null })
  assert.match(p, /docs\/spec\.md/)
  assert.match(p, /docs\/plan\.md/)
})

test('validator prompt says no spec/plan provided when specPath/planPath are absent', () => {
  const p = buildValidatorPrompt({ storyPath: 's', specPath: null, planPath: null, builderSummary: 'S', verifierReport: null })
  assert.match(p, /no spec.*provided|no.*spec provided/i)
  assert.match(p, /no plan.*provided|no.*plan provided/i)
})

test('validator prompt tolerates a null verifier report (skipped-1.5 path)', () => {
  const p = buildValidatorPrompt({ storyPath: null, specPath: null, planPath: null, builderSummary: 'S', verifierReport: null })
  assert.ok(p.length > 0)
})

test('null-story validator prompt does NOT leak a raw `null` and gives the no-story guidance (regression)', () => {
  const p = buildValidatorPrompt({ storyPath: null, specPath: null, planPath: null, builderSummary: 'S', verifierReport: null })
  assert.doesNotMatch(p, /User story: null/) // no `${storyPath}` leak
  assert.doesNotMatch(p, /\bnull\b/) // no bare null from any optional field
  assert.match(p, /No user story .* internal-tooling/) // the tailored no-story branch fired
  // a story present still renders the path
  const withStory = buildValidatorPrompt({ storyPath: 'docs/x/story.md', specPath: null, planPath: null, builderSummary: 'S', verifierReport: null })
  assert.match(withStory, /User story: docs\/x\/story\.md/)
})

test('with a story, verifier runs and validator joins on the verifier report', () => {
  assert.deepEqual(decideLanes('docs/x/story.md'), { runVerifier: true, validatorJoinsOnVerifier: true })
})

test('skipped-1.5: no story → no verifier, validator joins the initial batch', () => {
  assert.deepEqual(decideLanes(null), { runVerifier: false, validatorJoinsOnVerifier: false })
})

test('cqScopePin builds the git range', () => {
  assert.equal(cqScopePin('aaa', 'bbb'), 'aaa..bbb')
})

test('mergeFindings records a null lane as a verification hole', () => {
  const m = mergeFindings({ verifier: null, cq: { findings: [] }, validator: { findings: [] } })
  assert.ok(m.holes.includes('verifier'))
  assert.equal(m.holes.length, 1)
})

test('mergeFindings does NOT flag an intentionally-skipped (undefined) verifier lane', () => {
  const m = mergeFindings({ verifier: undefined, cq: { findings: [] }, validator: { findings: [] } })
  assert.equal(m.holes.length, 0)
})

test('mergeFindings flags an always-dispatched cq/validator lane that returns nullish (null OR undefined)', () => {
  // cq/validator are never intentionally skipped, so a nullish return = agent() failure = a hole,
  // regardless of whether agent() returns null or undefined on unrecoverable failure.
  assert.deepEqual(mergeFindings({ verifier: undefined, cq: undefined, validator: { findings: [] } }).holes, ['cq'])
  assert.deepEqual(mergeFindings({ verifier: undefined, cq: null, validator: undefined }).holes, ['cq', 'validator'])
})

test('normalizeVerifier: skipped lane → undefined (no hole); dispatched success → report; dispatched failure → null (hole)', () => {
  assert.equal(normalizeVerifier(undefined, false), undefined) // skipped (no story)
  assert.equal(normalizeVerifier(null, false), undefined) // skipped stays skipped even if raw is null
  const report = { acs: [] }
  assert.equal(normalizeVerifier(report, true), report) // dispatched + succeeded
  assert.equal(normalizeVerifier(null, true), null) // dispatched + agent() returned null → hole
  assert.equal(normalizeVerifier(undefined, true), null) // dispatched + agent() returned undefined → still a hole
})
