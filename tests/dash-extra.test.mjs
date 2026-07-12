// Tests for dash/dash-extra.mjs security-alerts path resolution.
// Contract: alerts live in state/SECURITY-ALERTS.log (canonical location used by
// watchdog-gui.sh, monitor/collect-signals.mjs, and the daemons) — NOT scan/.
// Run: node --test tests/dash-extra.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'dash', 'dash-extra.mjs');
const AGENT_BASENAME = 'agent-fixture0001.jsonl';

// Build a temp fixture: a fake AESOP_ROOT and a fake transcripts root containing
// one fresh agent transcript, so the agent shows up in --json output.
function makeFixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'aesop-dash-test-'));
  const aesopRoot = path.join(root, 'aesop');
  const transcriptsRoot = path.join(root, 'projects');
  fs.mkdirSync(aesopRoot, { recursive: true });
  fs.mkdirSync(transcriptsRoot, { recursive: true });
  fs.writeFileSync(
    path.join(transcriptsRoot, AGENT_BASENAME),
    '{"description":"fixture agent for path test"}\n'
  );
  return { root, aesopRoot, transcriptsRoot };
}

function runScript(fixture) {
  const stdout = execFileSync(process.execPath, [SCRIPT, '--json'], {
    env: {
      ...process.env,
      AESOP_ROOT: fixture.aesopRoot,
      AESOP_TRANSCRIPTS_ROOT: fixture.transcriptsRoot
    },
    encoding: 'utf8'
  });
  return JSON.parse(stdout);
}

test('alerts in state/SECURITY-ALERTS.log are applied to agent status', () => {
  const fixture = makeFixture();
  try {
    const stateDir = path.join(fixture.aesopRoot, 'state');
    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(
      path.join(stateDir, 'SECURITY-ALERTS.log'),
      `2026-07-12T00:00:00Z SUSPICIOUS ${AGENT_BASENAME} test alert\n`
    );

    const agents = runScript(fixture);
    assert.equal(agents.length, 1, 'fixture agent should be detected');
    assert.equal(
      agents[0].status,
      'SUSPICIOUS',
      'alert written to state/SECURITY-ALERTS.log must flag the agent (canonical path is state/, not scan/)'
    );
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('scan/SECURITY-ALERTS.log is never read (non-canonical path)', () => {
  const fixture = makeFixture();
  try {
    const scanDir = path.join(fixture.aesopRoot, 'scan');
    fs.mkdirSync(scanDir, { recursive: true });
    fs.writeFileSync(
      path.join(scanDir, 'SECURITY-ALERTS.log'),
      `2026-07-12T00:00:00Z SUSPICIOUS ${AGENT_BASENAME} decoy alert\n`
    );

    const agents = runScript(fixture);
    assert.equal(agents.length, 1, 'fixture agent should be detected');
    assert.equal(
      agents[0].status,
      'running',
      'a decoy alert in scan/ must have no effect — scan/ is not a canonical location'
    );
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('degrades gracefully when no alerts log exists', () => {
  const fixture = makeFixture();
  try {
    const agents = runScript(fixture);
    assert.equal(agents.length, 1, 'fixture agent should be detected');
    assert.equal(agents[0].status, 'running');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});
