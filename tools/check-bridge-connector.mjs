#!/usr/bin/env node
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const root = process.cwd()

function fail(message) {
  console.error(`bridge connector check failed: ${message}`)
  process.exit(1)
}

function read(path) {
  return readFileSync(join(root, path), 'utf8')
}

function readJson(path) {
  try {
    return JSON.parse(read(path))
  } catch (error) {
    fail(`${path}: ${error.message}`)
  }
}

function requireFile(path) {
  if (!existsSync(join(root, path))) fail(`missing ${path}`)
}

function requireText(path, pattern, label) {
  const text = read(path)
  if (!pattern.test(text)) fail(`${path} missing ${label}`)
}

for (const path of [
  'docs/bridge/CLAUDE_HANDOFF.md',
  'docs/bridge/foundry-connector.json',
  'README.md',
  'CLAUDE.md',
  'RYAN.md'
]) {
  requireFile(path)
}

const connector = readJson('docs/bridge/foundry-connector.json')
if (connector.status !== 'CONNECTED_RECEIVER') fail(`unexpected status ${connector.status}`)

const gkn = connector.receives.find((entry) => entry.from === 'SNAPKITTYWEST/gkn-i4-e7-lean')
if (!gkn) fail('missing GKN receiver entry')
if (gkn.delivery_commit !== 'de968509b5fc695f2d33e665959c6b86f5456be1') {
  fail(`unexpected GKN delivery commit ${gkn.delivery_commit}`)
}
if (gkn.handoff_status !== 'READY_FOR_CLAUDE') fail(`unexpected handoff status ${gkn.handoff_status}`)

const intel = connector.receives.find((entry) => entry.from === 'SNAPKITTYWEST/foundry-intel-2026-07-11')
if (!intel) fail('missing Foundry Intel receiver entry')
if (intel.q5_total !== '8 + 3*phi') fail(`unexpected Q(phi) total ${intel.q5_total}`)

requireText('README.md', /docs\/bridge\/CLAUDE_HANDOFF\.md/, 'bridge handoff pointer')
requireText('CLAUDE.md', /GKN-QB-LATCH-20260716/, 'GKN latch pointer')
requireText('docs/bridge/CLAUDE_HANDOFF.md', /OPEN_CRUX/, 'open-crux boundary')
requireText('docs/bridge/CLAUDE_HANDOFF.md', /SILENCE_PENDING/, 'silence-pending boundary')
requireText('docs/bridge/CLAUDE_HANDOFF.md', /Liquid Haskell/, 'Liquid Haskell handoff')

console.log('Foundry F1 bridge connector check passed')
console.log(`receiver: ${connector.receives.map((entry) => entry.from).join(' + ')} -> ${connector.repo}`)
