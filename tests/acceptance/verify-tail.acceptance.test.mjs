import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

// ─────────────────────────────────────────────────────────────────────────────
// Acceptance harness — exercises verify-tail.mjs from OUTSIDE.
//
// verify-tail.mjs is a Workflow-sandbox orchestration body: below `export const
// meta = {...}` it is plain top-level statements that call the sandbox globals
// `phase` / `agent` / `log`, read `args`, and end in `return merged`. The runtime
// invokes that body inside an async function with those globals in scope (see the
// syntax gate in verify-tail.inline-guard.test.mjs). We reproduce exactly that
// launch shape here: wrap the real body verbatim in an async function that takes
// `args` + injected globals, then drive it with a MOCK `agent` and observe only
// the module's observable contract — the sequence of agent() dispatches and the
// object it returns. We never import or call decideLanes / mergeFindings /
// buildVerifierPrompt etc. directly; the AC is checked against the whole module's
// external behaviour, not an internal function.
// ─────────────────────────────────────────────────────────────────────────────

const ENTRY_URL = new URL('../../.claude/workflows/verify-tail.mjs', import.meta.url)

// Brace-balanced extraction of the `export const meta = {...}` object, so we can
// slice off everything after it — that remainder is the orchestration body the
// sandbox runs. (Same technique the inline-guard test uses to find the body.)
function metaBlockEnd (src) {
  const start = src.indexOf('export const meta')
  assert.notEqual(start, -1, 'could not locate `export const meta` in verify-tail.mjs')
  const open = src.indexOf('{', start)
  let depth = 0
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}' && --depth === 0) return i + 1
  }
  throw new Error('unbalanced braces in meta block')
}

// Materialize the real module body as an importable async function whose only
// dependencies are the injected sandbox globals. This is the sole seam — the body
// itself is byte-for-byte the shipped verify-tail.mjs.
async function loadWorkflow () {
  const src = readFileSync(ENTRY_URL, 'utf8')
  const body = src.slice(metaBlockEnd(src))
  const wrapped = `export async function run (args, agent, phase, log) {\n${body}\n}\n`
  const tmp = join(tmpdir(), `verify-tail-accept-${process.pid}-${Date.now()}-${Math.random().toString(36).slice(2)}.mjs`)
  writeFileSync(tmp, wrapped, 'utf8')
  try {
    const mod = await import(pathToFileURL(tmp).href)
    return mod.run
  } finally {
    rmSync(tmp, { force: true })
  }
}

const WELL_FORMED = {
  verifier: { acs: [{ id: 'AC1', statement: 's', reasoning: 'r', verdict: 'PASS', testFile: 't.mjs' }] },
  cq: { strengths: [], findings: [], bloatSmell: { reasoning: 'r', verdict: 'lean' } },
  validator: { findings: [], lieDetection: { reasoning: 'traced' } }
}

// ── AC1 ──────────────────────────────────────────────────────────────────────
// Given a task WITH a user story, the tail dispatches an acceptance-verifier lane
// in PARALLEL with code-quality, and the validator only starts AFTER the verifier
// report lands. Observed purely through the mock agent's dispatch timeline.
test('AC1: verifier ∥ code-quality fan-out; validator dispatched only after the verifier report lands', async () => {
  const run = await loadWorkflow()

  const dispatched = []            // labels in the order agent() is called
  const promptFor = {}            // label -> prompt string handed to agent()
  const SENTINEL = 'VERIFIER-REPORT-SENTINEL-9f3a'
  const verifierReport = { acs: [{ id: 'AC1', statement: 's', reasoning: SENTINEL, verdict: 'PASS', testFile: 't.mjs' }] }

  let resolveVerifier
  const verifierGate = new Promise(res => { resolveVerifier = res })

  const agent = (prompt, opts) => {
    dispatched.push(opts.label)
    promptFor[opts.label] = prompt
    if (opts.label === 'verify:acceptance') return verifierGate.then(() => verifierReport)
    if (opts.label === 'verify:quality') return Promise.resolve(WELL_FORMED.cq)
    if (opts.label === 'verify:validator') return Promise.resolve(WELL_FORMED.validator)
    throw new Error(`unexpected agent label: ${opts.label}`)
  }
  const phases = []
  const phase = p => phases.push(p)
  const log = () => {}

  // Kick off the workflow but do NOT await — the verifier promise is still gated,
  // so the module is suspended at its `await Promise.all(...)`. Everything before
  // that await has already run synchronously.
  const resultP = run({ storyPath: 'docs/story.md', builderSummary: 'S', prevTaskTip: 'aaa', builderCommitSHA: 'bbb' }, agent, phase, log)

  // Fan-out assertion: at suspend time, BOTH read-only lanes are already in flight
  // and the validator has NOT been dispatched (it is chained off the verifier).
  assert.deepEqual(dispatched, ['verify:acceptance', 'verify:quality'],
    'verifier and code-quality must be dispatched together (parallel fan-out) before anything joins')
  assert.ok(!dispatched.includes('verify:validator'),
    'validator must NOT start before the verifier report has landed')

  // Land the verifier report; the validator may now join.
  resolveVerifier()
  const result = await resultP

  assert.ok(dispatched.includes('verify:validator'),
    'validator must be dispatched once the verifier report lands')
  assert.ok(dispatched.indexOf('verify:validator') > dispatched.indexOf('verify:acceptance'),
    'validator must be dispatched strictly AFTER the verifier lane')
  // Proof it joined ON the report (not the no-story fallback): the actual verifier
  // report content is embedded in the validator's prompt.
  assert.match(promptFor['verify:validator'], new RegExp(SENTINEL),
    'validator prompt must carry the landed verifier report (join-on-report)')
  assert.doesNotMatch(promptFor['verify:validator'], /No acceptance verifier report/,
    'with a story present the validator must not take the skipped-report branch')
  assert.deepEqual(phases, ['Verify'])
  assert.equal(result.verifier?.acs?.[0]?.reasoning, SENTINEL,
    'merged return must surface the verifier report')
})

// ── AC2 ──────────────────────────────────────────────────────────────────────
// The merged return exposes a `holes` array that is EMPTY when every dispatched
// lane returns a well-formed report.
test('AC2: merged return exposes an empty `holes` array when every dispatched lane returns a well-formed report', async () => {
  const run = await loadWorkflow()

  const agent = (prompt, opts) => {
    if (opts.label === 'verify:acceptance') return Promise.resolve(WELL_FORMED.verifier)
    if (opts.label === 'verify:quality') return Promise.resolve(WELL_FORMED.cq)
    if (opts.label === 'verify:validator') return Promise.resolve(WELL_FORMED.validator)
    throw new Error(`unexpected agent label: ${opts.label}`)
  }
  const result = await run(
    { storyPath: 'docs/story.md', builderSummary: 'S', prevTaskTip: 'aaa', builderCommitSHA: 'bbb' },
    agent, () => {}, () => {}
  )

  assert.ok(Array.isArray(result.holes), 'merged return must expose a `holes` array')
  assert.deepEqual(result.holes, [], 'holes must be empty when all dispatched lanes returned well-formed reports')
})
