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

test('walk() respects depth limit of 6 and prunes old branches', () => {
  const fixture = makeFixture();
  try {
    const transcriptsRoot = fixture.transcriptsRoot;
    const now = Date.now();
    const activityWindow = 12 * 60 * 1000; // 12 minutes

    // Create a deep/wide nested structure with both fresh and stale files
    // Depth structure: d0/d1/d2/d3/d4/d5/d6/d7 (depth 7, should be pruned beyond 6)
    let currentPath = transcriptsRoot;
    for (let depth = 0; depth < 8; depth++) {
      currentPath = path.join(currentPath, `d${depth}`);
      fs.mkdirSync(currentPath, { recursive: true });

      // Write a fresh file at this depth
      const freshAgent = `agent-fresh-d${depth}.jsonl`;
      fs.writeFileSync(path.join(currentPath, freshAgent), `{"description":"fresh d${depth}"}\n`);

      // Write a stale file at this depth (older than activity window)
      const staleAgent = `agent-stale-d${depth}.jsonl`;
      fs.writeFileSync(
        path.join(currentPath, staleAgent),
        `{"description":"stale d${depth}"}\n`
      );
      // Set mtime to 15 minutes ago (outside activity window)
      fs.utimesSync(path.join(currentPath, staleAgent), now / 1000 - 900, now / 1000 - 900);

      // Also set directory mtime to stale for d3 and deeper (to test pruning old directories)
      if (depth >= 3) {
        fs.utimesSync(currentPath, now / 1000 - 900, now / 1000 - 900);
      }
    }

    const startTime = Date.now();
    const agents = runScript(fixture);
    const elapsed = Date.now() - startTime;

    // Performance assertion: walk should complete in under 2 seconds even on deep tree
    assert.ok(elapsed < 2000, `walk should complete in <2s but took ${elapsed}ms`);

    // Should find only fresh agents within activity window
    const freshAgents = agents.filter(a => a.hint.includes('fresh'));
    assert.ok(freshAgents.length > 0, 'should find fresh agents in shallow depths');

    // Stale agents should be filtered out (mtime > 12min old)
    const staleAgents = agents.filter(a => a.hint.includes('stale'));
    assert.equal(staleAgents.length, 0, 'stale agents (>12min old) must be excluded from output');

    // Depth should be limited: files deeper than depth 6 should not appear
    // (fresh-d7, fresh-d6, ... fresh-d0 should only have up to d6 available in tree walk)
    const maxDepthFound = Math.max(
      ...freshAgents.map(a => parseInt(a.hint.match(/d(\d+)/)?.[1] || '0', 10))
    );
    assert.ok(maxDepthFound <= 6, `depth should be capped at 6, found agents at depth ${maxDepthFound}`);
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});
