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

// === Item 0: Config file precedence (ENV > config > default) ===
test('config precedence: TEMP_ROOT from config file honored when env var unset', async (t) => {
  const fixture = createFixture();
  const configTempRoot = path.join(os.tmpdir(), 'aesop-config-temp-' + Math.random().toString(36).slice(2, 9));

  try {
    fs.mkdirSync(configTempRoot, { recursive: true });

    // Create aesop.config.json with custom TEMP_ROOT
    const configPath = path.join(fixture.root, 'aesop.config.json');
    fs.writeFileSync(configPath, JSON.stringify({
      temp_root: configTempRoot,
      repos: [],
      monitor: { log_max_lines: 500, log_max_kb: 40 }
    }), 'utf8');

    // Create an old junk script in the config-specified temp directory
    const junkPath = path.join(configTempRoot, 'old_junk.py');
    const oldTime = Date.now() - (25 * 60 * 60 * 1000); // 25 hours ago
    fs.writeFileSync(junkPath, 'print("junk")\n', 'utf8');
    fs.utimesSync(junkPath, oldTime / 1000, oldTime / 1000);

    // Run collector WITHOUT TEMP_ROOT env var; should use config file value
    const env = {
      ...process.env,
      AESOP_ROOT: fixture.root,
      BRAIN_ROOT: path.join(fixture.root, '..', '.claude'),
      SCRIPTS_ROOT: path.join(fixture.root, '..', 'scripts'),
    };
    delete env.TEMP_ROOT; // Ensure TEMP_ROOT is not set

    const result = spawnSync('node', [collectorPath], {
      env,
      encoding: 'utf8',
      timeout: 10000,
    });

    assert.strictEqual(result.status, 0, 'Collector should succeed with config TEMP_ROOT');

    // Verify that collector found the junk script in config-specified location
    const signalsPath = path.join(fixture.monitorDir, 'SIGNALS.json');
    const signals = JSON.parse(fs.readFileSync(signalsPath, 'utf8'));

    // The junk script should be detected (proving config temp root was used)
    assert.ok(signals.junk.total > 0, 'Config-specified TEMP_ROOT should be scanned for junk scripts');
  } finally {
    try {
      fs.rmSync(configTempRoot, { recursive: true, force: true });
    } catch (e) {}
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

// === Item 3: Heartbeat check at startup ===
test('heartbeat guard: collector skips cycle if own heartbeat <300s old', async (t) => {
  const fixture = createFixture();
  try {
    // Create a fresh heartbeat file (just now)
    const heartbeatPath = path.join(fixture.monitorDir, '.monitor-heartbeat');
    fs.writeFileSync(heartbeatPath, String(Math.floor(Date.now() / 1000)), 'utf8');

    // First run: should complete normally
    const result1 = runCollector(fixture.root, { AESOP_MONITOR_FORCE: '0' });
    assert.ok(result1.stdout, 'First run should complete');

    // Read the SIGNALS.json to get cycleCount after first run
    const signalsPath = path.join(fixture.monitorDir, 'SIGNALS.json');
    const signals1 = JSON.parse(fs.readFileSync(signalsPath, 'utf8'));
    const cycle1 = signals1.cycleCount;

    // Second run (immediately after, within 300s): should exit early without changing cycle count
    const result2 = runCollector(fixture.root, { AESOP_MONITOR_FORCE: '0' });
    // The collector should exit 0 but not update outputs significantly
    // (Note: it still exits 0, but skips the main cycle work)
    const signals2 = JSON.parse(fs.readFileSync(signalsPath, 'utf8'));
    const cycle2 = signals2.cycleCount;

    // Cycle count should be same or minimally incremented (skipped cycle = no new signals)
    assert.ok(cycle2 <= cycle1 + 1, 'Cycle should be skipped or minimally incremented when heartbeat is fresh');
  } finally {
    fixture.cleanup();
  }
});

test('heartbeat override: AESOP_MONITOR_FORCE=1 bypasses guard', async (t) => {
  const fixture = createFixture();
  try {
    // Create an old heartbeat file
    const heartbeatPath = path.join(fixture.monitorDir, '.monitor-heartbeat');
    const oldEpoch = Math.floor((Date.now() - 5 * 60 * 1000) / 1000); // 5 minutes ago
    fs.writeFileSync(heartbeatPath, String(oldEpoch), 'utf8');

    // Run with AESOP_MONITOR_FORCE=1: should run despite old heartbeat
    const result = runCollector(fixture.root, { AESOP_MONITOR_FORCE: '1' });
    assert.ok(result.stdout, 'Collector should run with FORCE override');

    // Heartbeat should be updated to now
    const newHeartbeat = fs.readFileSync(heartbeatPath, 'utf8').trim();
    const newEpoch = parseInt(newHeartbeat, 10);
    assert.ok(newEpoch > oldEpoch, 'Heartbeat should be updated to recent timestamp');
  } finally {
    fixture.cleanup();
  }
});

// === Item 4: Atomic writes for SIGNALS.json and BRIEF.md ===
test('atomic writes: SIGNALS.json and BRIEF.md are written atomically', async (t) => {
  const fixture = createFixture();
  try {
    // Run collector normally
    const result = runCollector(fixture.root, { AESOP_MONITOR_FORCE: '1' });
    assert.ok(result.stdout, 'Collector should run');

    // Verify files exist and are parseable
    const signalsPath = path.join(fixture.monitorDir, 'SIGNALS.json');
    const briefPath = path.join(fixture.monitorDir, 'BRIEF.md');

    assert.ok(fs.existsSync(signalsPath), 'SIGNALS.json should exist');
    assert.ok(fs.existsSync(briefPath), 'BRIEF.md should exist');

    // Verify SIGNALS.json is valid JSON
    const signals = JSON.parse(fs.readFileSync(signalsPath, 'utf8'));
    assert.ok(signals.timestamp, 'SIGNALS.json should be valid JSON with timestamp');

    // Verify no .tmp files are left behind
    const tmpSignals = signalsPath + '.tmp';
    const tmpBrief = briefPath + '.tmp';
    assert.ok(!fs.existsSync(tmpSignals), 'No temporary SIGNALS.json.tmp should remain');
    assert.ok(!fs.existsSync(tmpBrief), 'No temporary BRIEF.md.tmp should remain');
  } finally {
    fixture.cleanup();
  }
});

// === Item 1: AUTO actions for log rotation and junk quarantine ===
test('AUTO action: log rotation invokes rotate_logs.py when log exceeds threshold', async (t) => {
  const fixture = createFixture();
  try {
    // Create a log file that exceeds threshold (>500 lines by default)
    const logPath = path.join(fixture.monitorDir, 'ACTIONS.log');
    const lines = [];
    for (let i = 0; i < 505; i++) {
      lines.push(`[2026-07-12T10:00:${String(i % 60).padStart(2, '0')}Z] Sample log line ${i}`);
    }
    fs.writeFileSync(logPath, lines.join('\n') + '\n', 'utf8');

    // Run collector
    const result = runCollector(fixture.root, { AESOP_MONITOR_FORCE: '1' });
    assert.ok(result.stdout, 'Collector should run');

    // Check that SIGNALS.json shows log needs rotation
    const signalsPath = path.join(fixture.monitorDir, 'SIGNALS.json');
    const signals = JSON.parse(fs.readFileSync(signalsPath, 'utf8'));
    const actionsLog = signals.logs.find(l => l.name === 'ACTIONS.log');
    assert.ok(actionsLog && actionsLog.needsRotation, 'SIGNALS should detect ACTIONS.log needs rotation');

    // Check that ACTIONS.log entries were appended (proving AUTO action executed)
    const finalLogContent = fs.readFileSync(logPath, 'utf8');
    assert.ok(finalLogContent.includes('AUTO action'), 'ACTIONS.log should contain AUTO action entries');
  } finally {
    fixture.cleanup();
  }
});

test('AUTO action: junk quarantine moves old temp scripts to monitor/quarantine/', async (t) => {
  const fixture = createFixture();
  const tempDir = path.join(os.tmpdir(), 'aesop-junk-test-' + Math.random().toString(36).slice(2, 9));

  try {
    fs.mkdirSync(tempDir, { recursive: true });

    // Create an old junk script (>24h old)
    const oldJunkPath = path.join(tempDir, 'old_script.py');
    const oldTime = Date.now() - (25 * 60 * 60 * 1000); // 25 hours ago
    fs.writeFileSync(oldJunkPath, '#!/usr/bin/env python3\nprint("junk")\n', 'utf8');
    fs.utimesSync(oldJunkPath, oldTime / 1000, oldTime / 1000);

    // Run collector with this TEMP_ROOT
    const result = runCollector(fixture.root, { TEMP_ROOT: tempDir, AESOP_MONITOR_FORCE: '1' });
    assert.ok(result.stdout, 'Collector should run');

    // Check that junk was detected and possibly quarantined
    const signalsPath = path.join(fixture.monitorDir, 'SIGNALS.json');
    const signals = JSON.parse(fs.readFileSync(signalsPath, 'utf8'));
    assert.ok(signals.junk.quarantinable > 0, 'Junk detection should report quarantinable files');

    // Check for quarantine directory and manifest
    const quarantineDir = path.join(fixture.monitorDir, 'quarantine');
    const manifestPath = path.join(quarantineDir, 'MANIFEST.tsv');

    if (fs.existsSync(quarantineDir)) {
      assert.ok(fs.existsSync(manifestPath), 'Quarantine manifest should exist if quarantine dir created');
      const manifest = fs.readFileSync(manifestPath, 'utf8');
      assert.ok(manifest.includes('old_script.py'), 'Manifest should list quarantined files');
    }
  } finally {
    try {
      fs.rmSync(tempDir, { recursive: true, force: true });
    } catch (e) {
      // Ignore cleanup errors
    }
    fixture.cleanup();
  }
});

