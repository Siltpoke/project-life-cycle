import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, rmSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// verify-tail.mjs inlines the pure logic from verify-tail.lib.mjs because the Workflow
// sandbox has no module resolution (IMPORT_OK=false). This guard fires if the inlined
// copy drifts from the canonical, node-tested lib on any load-bearing semantic.
const entry = readFileSync(new URL('./verify-tail.mjs', import.meta.url), 'utf8')
const lib = readFileSync(new URL('./verify-tail.lib.mjs', import.meta.url), 'utf8')

// Brace-balanced extraction: find `marker`, then walk forward from its first `{`
// (for `function` markers, from the `{` that opens the body, i.e. after the closing
// `)` of the parameter list — so a destructured-param `{...}` isn't mistaken for the
// body) counting `{`/`}` until depth returns to zero. Returns the exact source slice
// from the marker through that closing brace, inclusive.
function extractBlock (src, marker) {
  const start = src.indexOf(marker)
  if (start === -1) throw new Error(`marker not found: ${JSON.stringify(marker)}`)
  const bodyOpen = marker.includes('function')
    ? src.indexOf('{', src.indexOf(')', start))
    : src.indexOf('{', start)
  if (bodyOpen === -1) throw new Error(`no opening brace found for marker: ${JSON.stringify(marker)}`)
  let depth = 0
  let end = -1
  for (let i = bodyOpen; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) { end = i; break }
    }
  }
  if (end === -1) throw new Error(`unbalanced braces extracting marker: ${JSON.stringify(marker)}`)
  return src.slice(start, end + 1)
}

// The lib exports each item (`export const SCHEMAS`, `export function buildX`); the
// entry's inlined copy is plain (no `export `, since the Workflow sandbox can't import).
// That's the ONLY sanctioned difference — strip it, then require verbatim containment.
const INLINED_ITEMS = [
  'const AC',
  'const FINDING',
  'export const SCHEMAS',
  'export function buildVerifierPrompt',
  'export function buildCqPrompt',
  'export function buildValidatorPrompt',
  'export function decideLanes',
  'export function cqScopePin',
  'export function mergeFindings',
  'export function normalizeVerifier'
]

test('every inlined item is byte-for-byte identical to its lib source (entry-vs-lib equality guard)', () => {
  for (const marker of INLINED_ITEMS) {
    const libBlock = extractBlock(lib, marker)
    const expected = libBlock.startsWith('export ') ? libBlock.slice('export '.length) : libBlock
    assert.ok(
      entry.includes(expected),
      `verify-tail.mjs's inlined copy of "${marker}" has drifted from verify-tail.lib.mjs.\n` +
      `Expected this verbatim block (export-stripped) to appear in verify-tail.mjs:\n${expected}`
    )
  }
})

test('the two schema field-order invariants hold in BOTH files (reasoning-first)', () => {
  for (const src of [entry, lib]) {
    // AC required array: reasoning before verdict
    assert.match(src, /required: \['id', 'statement', 'reasoning', 'verdict'\]/)
    // FINDING required array: reasoning before severity
    assert.match(src, /required: \['reasoning', 'severity'\]/)
  }
})

test('inlined body parses as valid standalone JS after Workflow-shim wrapping (syntax gate)', () => {
  // Below `export const meta = {...}`, verify-tail.mjs is a Workflow orchestration body
  // that uses top-level `await`/`return` — a SyntaxError in a standalone .mjs. Wrap that
  // body in an async function (mirroring how the Workflow sandbox actually invokes it)
  // and run `node --check` on the result to catch brace/typo errors locally, before the
  // downstream Workflow launch-parse would.
  const metaBlock = extractBlock(entry, 'export const meta')
  const bodyStart = entry.indexOf(metaBlock) + metaBlock.length
  const body = entry.slice(bodyStart)
  const wrapped = `async function __wf (args) {\n${body}\n}\n`

  const tmpFile = join(tmpdir(), `verify-tail-syntax-check-${process.pid}-${Date.now()}.mjs`)
  writeFileSync(tmpFile, wrapped, 'utf8')
  try {
    execFileSync(process.execPath, ['--check', tmpFile], { stdio: 'pipe' })
  } catch (err) {
    assert.fail(`node --check failed on wrapped inlined body: ${err.stderr?.toString() ?? err.message}`)
  } finally {
    rmSync(tmpFile, { force: true })
  }
})
