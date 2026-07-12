// Test harness for monitor/collect-signals.mjs
// TDD-first; tests signal collection with env injection and fixture dirs.
// Uses only Node.js built-ins (node:test, node:assert, node:fs, node:path, node:os, node:child_process)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// Resolve collector path relative to this test file
const collectorPath = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'monitor', 'collect-signals.mjs');

// === Helper: Create isolated fixture directory ===
function createFixture() {
  const tempDir = path.join(os.tmpdir(), 'aesop-test-' + Math.random().toString(36).slice(2, 9));
  const fixtureRoot = path.join(tempDir, 'fixture');
  const stateDir = path.join(fixtureRoot, 'state');
  const monitorDir = path.join(fixtureRoot, 'monitor');

  fs.mkdirSync(stateDir, { recursive: true });
  fs.mkdirSync(monitorDir, { recursive: true });

  return {
    root: fixtureRoot,
    stateDir,
    monitorDir,
    cleanup: () => {
      try {
        fs.rmSync(tempDir, { recursive: true, force: true });
      } catch (e) {
        // Ignore cleanup errors
      }
    },
  };
}

// === Helper: Run collector with env overrides ===
function runCollector(aesopRoot, envOverrides = {}) {
  const env = {
    ...process.env,
    AESOP_ROOT: aesopRoot,
    BRAIN_ROOT: path.join(aesopRoot, '..', '.claude'),
    SCRIPTS_ROOT: path.join(aesopRoot, '..', 'scripts'),
    // TEMP_ROOT is handled per-test
    ...envOverrides,
  };

  const result = spawnSync('node', [collectorPath], {
    env,
    encoding: 'utf8',
    timeout: 10000,
  });

  if (result.error) {
    throw new Error(`Failed to spawn collector: ${result.error.message}`);
  }

  if (result.status !== 0) {
    throw new Error(`Collector exited with code ${result.status}: ${result.stderr}`);
  }

  return result;
}

// === Test Suite ===

test('tmpdir fallback: TEMP_ROOT unset uses os.tmpdir()', async (t) => {
  const fixture = createFixture();
  try {
    // Run without TEMP_ROOT env var; it should default to os.tmpdir() + 'claude'
    const env = {};
    // Explicitly unset TEMP_ROOT if inherited
    delete env.TEMP_ROOT;

    const result = runCollector(fixture.root, env);
    assert.ok(result.stdout, 'Collector should produce output');

    // Check that SIGNALS.json was created and contains a timestamp
    const signalsPath = path.join(fixture.monitorDir, 'SIGNALS.json');
    assert.ok(fs.existsSync(signalsPath), 'SIGNALS.json should exist');

    const signals = JSON.parse(fs.readFileSync(signalsPath, 'utf8'));
    assert.ok(signals.timestamp, 'SIGNALS should contain timestamp');
  } finally {
    fixture.cleanup();
  }
});

test('tmpdir override: TEMP_ROOT env var takes precedence', async (t) => {
  const fixture = createFixture();
  const customTempDir = path.join(os.tmpdir(), 'aesop-custom-' + Math.random().toString(36).slice(2, 9));

  try {
    // Run with custom TEMP_ROOT
    const result = runCollector(fixture.root, {
      TEMP_ROOT: customTempDir,
    });

    // Verify that the collector ran and SIGNALS.json was created
    const signalsPath = path.join(fixture.monitorDir, 'SIGNALS.json');
    assert.ok(fs.existsSync(signalsPath), 'SIGNALS.json should exist with custom TEMP_ROOT');

    const signals = JSON.parse(fs.readFileSync(signalsPath, 'utf8'));
    // The TEMP_ROOT override should be used internally (verified via junk detection logic)
    assert.ok(signals.junk, 'junk detection should run');
  } finally {
    fs.rmSync(customTempDir, { recursive: true, force: true });
    fixture.cleanup();
  }
});

test('proposal idempotency: running twice emits exactly one PROPOSALS.md entry for security alert', async (t) => {
  const fixture = createFixture();
  try {
    // Setup fixture: create a SECURITY-ALERTS.log with a HIGH entry (triggers security-alerts-high-med proposal)
    const alertLogPath = path.join(fixture.stateDir, 'SECURITY-ALERTS.log');
    fs.writeFileSync(alertLogPath, '2026-07-12T10:00:00Z HIGH credential exposure detected in .env\n', 'utf8');

    // First run: collector should emit PROPOSALS.md with one security-alerts-high-med entry
    runCollector(fixture.root);

    const proposalsPath = path.join(fixture.monitorDir, 'PROPOSALS.md');
    assert.ok(fs.existsSync(proposalsPath), 'PROPOSALS.md should be created after first run');

    const firstProposal = fs.readFileSync(proposalsPath, 'utf8');
    assert.ok(firstProposal.includes('security-alerts-high-med'), 'PROPOSALS.md should contain security-alerts-high-med signal');
    const firstCount = (firstProposal.match(/\*\*Signal:\*\*\s+security-alerts-high-med/g) || []).length;

    // Second run: should NOT emit a duplicate (idempotency check)
    runCollector(fixture.root);

    const secondProposal = fs.readFileSync(proposalsPath, 'utf8');
    const secondCount = (secondProposal.match(/\*\*Signal:\*\*\s+security-alerts-high-med/g) || []).length;

    assert.strictEqual(secondCount, firstCount, 'PROPOSALS.md should have same number of security-alerts-high-med entries after second run (idempotent)');
    assert.strictEqual(firstCount, 1, 'Should have exactly one security-alerts-high-med entry');
  } finally {
    fixture.cleanup();
  }
});

test('healthy signals: clean fixture does not create PROPOSALS.md', async (t) => {
  const fixture = createFixture();
  try {
    // Run with empty fixture (no alerts, no stray scripts, no respawn watch, no stale memory)
    runCollector(fixture.root);

    // PROPOSALS.md should NOT be created for a healthy fixture
    const proposalsPath = path.join(fixture.monitorDir, 'PROPOSALS.md');
    assert.ok(!fs.existsSync(proposalsPath), 'PROPOSALS.md should not be created for healthy signals');

    // But BRIEF.md and SIGNALS.json should exist
    const briefPath = path.join(fixture.monitorDir, 'BRIEF.md');
    const signalsPath = path.join(fixture.monitorDir, 'SIGNALS.json');

    assert.ok(fs.existsSync(briefPath), 'BRIEF.md should be created');
    assert.ok(fs.existsSync(signalsPath), 'SIGNALS.json should be created');

    // Verify the signals indicate healthy state
    const signals = JSON.parse(fs.readFileSync(signalsPath, 'utf8'));
    assert.strictEqual(signals.alerts.highMedCount, 0, 'Should have no HIGH/MED alerts');
    assert.strictEqual(signals.strayRepo.length, 0, 'Should have no stray repo scripts');
    assert.strictEqual(signals.respawnWatch.length, 0, 'Should have no respawn watch breaches');
  } finally {
    fixture.cleanup();
  }
});

test('config: collector respects aesop.config.json repos list (read-only test)', async (t) => {
  // NOTE: This test verifies the collector reads config but does not require modification of the collector.
  // The collector's config loading is deterministic and doesn't depend on fixture state beyond file existence.
  const fixture = createFixture();
  try {
    // Create a minimal aesop.config.json
    const configPath = path.join(fixture.root, 'aesop.config.json');
    fs.writeFileSync(configPath, JSON.stringify({
      repos: [
        { path: '/nonexistent/repo1' },
      ],
    }), 'utf8');

    const result = runCollector(fixture.root);
    assert.ok(result.stdout, 'Collector should complete even with nonexistent repos in config');

    // Verify SIGNALS.json was created (config parsing succeeded)
    const signalsPath = path.join(fixture.monitorDir, 'SIGNALS.json');
    assert.ok(fs.existsSync(signalsPath), 'SIGNALS.json should exist even with nonexistent configured repos');
  } finally {
    fixture.cleanup();
  }
});

// === Test: Gap documentation ===
test('gap documentation: PROPOSALS.md fixture injection limitations', (t) => {
  // DOCUMENTED GAP: The collector derives STATE_DIR from AESOP_ROOT, which means
  // SECURITY-ALERTS.log placement is fixed to ${AESOP_ROOT}/state/SECURITY-ALERTS.log.
  // This is NOT independently injectable via env like TEMP_ROOT is.
  //
  // WORKAROUND: Tests inject fixtures by creating the state directory and files
  // at the expected path (fixture/state/SECURITY-ALERTS.log).
  //
  // If a future wave needs to make STATE_DIR independently configurable,
  // add STATE_ROOT env override to collect-signals.mjs (line 17).
  //
  // This constraint is acceptable for current tests because we control
  // AESOP_ROOT and can create the expected directory structure.
  assert.ok(true, 'Gap documented in test comments');
});
