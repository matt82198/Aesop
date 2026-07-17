// Wave-26 — ORCHESTRATION CORE tests.
//
// This suite targets the aesop-OWNED orchestration DECISION LOGIC that already exists
// as in-repo code, and is honest about what is NOT ours to test (see the "gap
// documentation" tests at the bottom).
//
// Scope covered here (all live in monitor/collect-signals.mjs, the deterministic
// signal collector the orchestration-refinement monitor reads every cycle):
//   1. checkHeartbeats() — per-loop-name threshold SELECTION (watchdog=300s,
//      monitor=3600s, default=1800s) and the staleness boundary itself. This is
//      genuinely different from (and untested by) the monitor's OWN startup
//      heartbeat guard, which tests/collect-signals.test.mjs already covers well.
//   2. checkGitState() — dirty-file count and ahead-count derived from real git
//      state (not previously exercised against a live repo with a divergent
//      upstream).
//   3. checkLogFiles() — the needsRotation decision must fire on the KB threshold
//      alone, independent of line count (existing tests only exercise the
//      line-count path).
//   4. checkMemoryFreshness() — the 30-day staleness boundary for MEMORY.md
//      sibling files.
//
// These are blackbox-through-the-collector tests (spawn the real script, inspect
// SIGNALS.json) because the collector does not export its internal functions —
// same convention tests/collect-signals.test.mjs already uses.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const collectorPath = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'monitor', 'collect-signals.mjs');

function createFixture() {
  const tempDir = path.join(os.tmpdir(), 'aesop-orch-core-' + Math.random().toString(36).slice(2, 9));
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
      } catch {
        // best effort
      }
    },
  };
}

function runCollector(aesopRoot, envOverrides = {}) {
  const env = {
    ...process.env,
    AESOP_ROOT: aesopRoot,
    BRAIN_ROOT: path.join(aesopRoot, '..', '.claude'),
    SCRIPTS_ROOT: path.join(aesopRoot, '..', 'scripts'),
    AESOP_MONITOR_FORCE: '1', // bypass the monitor's own startup guard by default
    ...envOverrides,
  };
  const result = spawnSync('node', [collectorPath], {
    env,
    encoding: 'utf8',
    timeout: 30000,
    killSignal: 'SIGKILL',
  });
  if (result.error) {
    throw new Error(`Failed to spawn collector: ${result.error.message}`);
  }
  if (result.status !== 0) {
    throw new Error(`Collector exited with code ${result.status}: ${result.stderr}`);
  }
  return result;
}

function writeHeartbeatFile(dir, name, ageSeconds) {
  fs.mkdirSync(dir, { recursive: true });
  const epoch = Math.floor(Date.now() / 1000) - ageSeconds;
  fs.writeFileSync(path.join(dir, name), String(epoch), 'utf8');
}

function readSignals(fixture) {
  return JSON.parse(fs.readFileSync(path.join(fixture.monitorDir, 'SIGNALS.json'), 'utf8'));
}

// === 1) checkHeartbeats(): per-name threshold selection ===

test('checkHeartbeats: watchdog-named loop uses the 300s threshold (fresh at 250s)', async () => {
  const fixture = createFixture();
  try {
    const beatsDir = path.join(fixture.monitorDir, '.heartbeats');
    writeHeartbeatFile(beatsDir, 'watchdog-daemon', 250);

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    const flagged = signals.heartbeats.details.some(d => d.name === 'watchdog-daemon');
    assert.ok(!flagged, 'watchdog loop at 250s (< 300s threshold) must NOT be flagged stale');
  } finally {
    fixture.cleanup();
  }
});

test('checkHeartbeats: watchdog-named loop is stale past its 300s threshold (350s)', async () => {
  const fixture = createFixture();
  try {
    const beatsDir = path.join(fixture.monitorDir, '.heartbeats');
    writeHeartbeatFile(beatsDir, 'watchdog-daemon', 350);

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    const entry = signals.heartbeats.details.find(d => d.name === 'watchdog-daemon');
    assert.ok(entry, 'watchdog loop at 350s (> 300s threshold) MUST be flagged stale');
    assert.strictEqual(entry.threshold, 300000, 'watchdog threshold should resolve to 300000ms');
  } finally {
    fixture.cleanup();
  }
});

test('checkHeartbeats: monitor-named loop uses the 3600s threshold, NOT the watchdog 300s one', async () => {
  const fixture = createFixture();
  try {
    const beatsDir = path.join(fixture.monitorDir, '.heartbeats');
    // 1800s is well past watchdog's threshold but well within monitor's 3600s threshold.
    writeHeartbeatFile(beatsDir, 'refinement-monitor', 1800);

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    const flagged = signals.heartbeats.details.some(d => d.name === 'refinement-monitor');
    assert.ok(!flagged, 'monitor-named loop at 1800s (< 3600s threshold) must NOT be flagged stale — proves per-name threshold selection, not a single global threshold');
  } finally {
    fixture.cleanup();
  }
});

test('checkHeartbeats: monitor-named loop IS stale past its 3600s threshold', async () => {
  const fixture = createFixture();
  try {
    const beatsDir = path.join(fixture.monitorDir, '.heartbeats');
    writeHeartbeatFile(beatsDir, 'refinement-monitor', 3700);

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    const entry = signals.heartbeats.details.find(d => d.name === 'refinement-monitor');
    assert.ok(entry, 'monitor loop at 3700s (> 3600s threshold) MUST be flagged stale');
    assert.strictEqual(entry.threshold, 3600000, 'monitor threshold should resolve to 3600000ms');
  } finally {
    fixture.cleanup();
  }
});

test('checkHeartbeats: unrecognized loop name falls back to the 1800s default threshold', async () => {
  const fixture = createFixture();
  try {
    const beatsDir = path.join(fixture.monitorDir, '.heartbeats');
    writeHeartbeatFile(beatsDir, 'custom-worker-loop', 1000); // < 1800s default: fresh
    writeHeartbeatFile(beatsDir, 'other-worker-loop', 2000); // > 1800s default: stale

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    assert.ok(
      !signals.heartbeats.details.some(d => d.name === 'custom-worker-loop'),
      'unrecognized loop at 1000s (< 1800s default) must NOT be flagged'
    );
    const staleEntry = signals.heartbeats.details.find(d => d.name === 'other-worker-loop');
    assert.ok(staleEntry, 'unrecognized loop at 2000s (> 1800s default) MUST be flagged');
    assert.strictEqual(staleEntry.threshold, 1800000, 'unrecognized-name threshold should resolve to the 1800000ms default');
  } finally {
    fixture.cleanup();
  }
});

test('checkHeartbeats: config-driven thresholds override the built-in defaults', async () => {
  const fixture = createFixture();
  try {
    const configPath = path.join(fixture.root, 'aesop.config.json');
    fs.writeFileSync(configPath, JSON.stringify({
      monitor: { heartbeat_thresholds: { watchdog: 60 } },
    }), 'utf8');

    const beatsDir = path.join(fixture.monitorDir, '.heartbeats');
    // 90s is fresh under the built-in 300s default, but stale under the configured 60s override.
    writeHeartbeatFile(beatsDir, 'watchdog-daemon', 90);

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    const entry = signals.heartbeats.details.find(d => d.name === 'watchdog-daemon');
    assert.ok(entry, 'watchdog loop at 90s MUST be flagged stale once config overrides the threshold to 60s');
    assert.strictEqual(entry.threshold, 60000, 'configured watchdog threshold should resolve to 60000ms');
  } finally {
    fixture.cleanup();
  }
});

// === 2) checkGitState(): dirty-file and ahead-of-upstream counts ===

function initBareRemote(dir) {
  fs.mkdirSync(dir, { recursive: true });
  spawnSync('git', ['init', '--bare'], { cwd: dir, stdio: 'ignore' });
}

function gitConfigIdentity(cwd) {
  spawnSync('git', ['config', 'user.email', 'orch-core-test@example.com'], { cwd, stdio: 'ignore' });
  spawnSync('git', ['config', 'user.name', 'Orch Core Test'], { cwd, stdio: 'ignore' });
}

test('checkGitState: dirty count reflects real uncommitted changes', async () => {
  const fixture = createFixture();
  const repoDir = path.join(fixture.root, '..', 'repo-under-test');
  try {
    fs.mkdirSync(repoDir, { recursive: true });
    spawnSync('git', ['init'], { cwd: repoDir, stdio: 'ignore' });
    gitConfigIdentity(repoDir);
    fs.writeFileSync(path.join(repoDir, 'a.txt'), 'a\n', 'utf8');
    spawnSync('git', ['add', '.'], { cwd: repoDir, stdio: 'ignore' });
    spawnSync('git', ['commit', '-m', 'init'], { cwd: repoDir, stdio: 'ignore' });

    // Two dirty files: one modified, one new+untracked.
    fs.writeFileSync(path.join(repoDir, 'a.txt'), 'a changed\n', 'utf8');
    fs.writeFileSync(path.join(repoDir, 'b.txt'), 'b\n', 'utf8');

    const configPath = path.join(fixture.root, 'aesop.config.json');
    fs.writeFileSync(configPath, JSON.stringify({ repos: [{ path: repoDir }] }), 'utf8');

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    const g = signals.git.find(r => r.repo === path.basename(repoDir));
    assert.ok(g, 'git state entry for repo-under-test should exist');
    assert.strictEqual(g.dirty, 2, `expected 2 dirty entries (modified + untracked), got ${g.dirty}`);
  } finally {
    try { fs.rmSync(repoDir, { recursive: true, force: true }); } catch {}
    fixture.cleanup();
  }
});

test('checkGitState: ahead count reflects real unpushed local commits', async () => {
  const fixture = createFixture();
  const remoteDir = path.join(fixture.root, '..', 'remote-under-test.git');
  const repoDir = path.join(fixture.root, '..', 'repo-ahead-test');
  try {
    initBareRemote(remoteDir);

    fs.mkdirSync(repoDir, { recursive: true });
    spawnSync('git', ['init'], { cwd: repoDir, stdio: 'ignore' });
    gitConfigIdentity(repoDir);
    fs.writeFileSync(path.join(repoDir, 'a.txt'), 'a\n', 'utf8');
    spawnSync('git', ['add', '.'], { cwd: repoDir, stdio: 'ignore' });
    spawnSync('git', ['commit', '-m', 'init'], { cwd: repoDir, stdio: 'ignore' });
    spawnSync('git', ['remote', 'add', 'origin', remoteDir], { cwd: repoDir, stdio: 'ignore' });
    spawnSync('git', ['push', '-u', 'origin', 'HEAD'], { cwd: repoDir, stdio: 'ignore' });

    // Two local commits not yet pushed.
    fs.writeFileSync(path.join(repoDir, 'b.txt'), 'b\n', 'utf8');
    spawnSync('git', ['add', '.'], { cwd: repoDir, stdio: 'ignore' });
    spawnSync('git', ['commit', '-m', 'second'], { cwd: repoDir, stdio: 'ignore' });
    fs.writeFileSync(path.join(repoDir, 'c.txt'), 'c\n', 'utf8');
    spawnSync('git', ['add', '.'], { cwd: repoDir, stdio: 'ignore' });
    spawnSync('git', ['commit', '-m', 'third'], { cwd: repoDir, stdio: 'ignore' });

    const configPath = path.join(fixture.root, 'aesop.config.json');
    fs.writeFileSync(configPath, JSON.stringify({ repos: [{ path: repoDir }] }), 'utf8');

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    const g = signals.git.find(r => r.repo === path.basename(repoDir));
    assert.ok(g, 'git state entry for repo-ahead-test should exist');
    assert.strictEqual(g.ahead, '2', `expected ahead count '2' (two unpushed commits), got ${JSON.stringify(g.ahead)}`);
  } finally {
    try { fs.rmSync(repoDir, { recursive: true, force: true }); } catch {}
    try { fs.rmSync(remoteDir, { recursive: true, force: true }); } catch {}
    fixture.cleanup();
  }
});

// === 3) checkLogFiles(): needsRotation must fire on KB size alone ===

test('checkLogFiles: needsRotation fires on KB threshold even with a low line count', async () => {
  const fixture = createFixture();
  try {
    // Configure a small maxKb (5) but a large maxLines (500) so only the
    // size branch of the OR can trip.
    const configPath = path.join(fixture.root, 'aesop.config.json');
    fs.writeFileSync(configPath, JSON.stringify({
      monitor: { log_max_lines: 500, log_max_kb: 5 },
    }), 'utf8');

    // One giant line ~8KB, well under 500 lines but well over 5KB.
    const bigLine = 'x'.repeat(8 * 1024);
    fs.writeFileSync(path.join(fixture.stateDir, 'FLEET-BACKUP.log'), bigLine + '\n', 'utf8');

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    const log = signals.logs.find(l => l.name === 'FLEET-BACKUP.log');
    assert.ok(log, 'FLEET-BACKUP.log entry should exist');
    assert.ok(log.lineCount < 500, `sanity: lineCount (${log.lineCount}) should be far below maxLines`);
    assert.strictEqual(log.needsRotation, true, 'needsRotation must fire on KB size alone when line count is low');
  } finally {
    fixture.cleanup();
  }
});

test('checkLogFiles: does NOT flag rotation when both line count and size are within thresholds', async () => {
  const fixture = createFixture();
  try {
    const configPath = path.join(fixture.root, 'aesop.config.json');
    fs.writeFileSync(configPath, JSON.stringify({
      monitor: { log_max_lines: 500, log_max_kb: 40 },
    }), 'utf8');

    fs.writeFileSync(path.join(fixture.stateDir, 'FLEET-BACKUP.log'), 'small log\nfine\n', 'utf8');

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    const log = signals.logs.find(l => l.name === 'FLEET-BACKUP.log');
    assert.ok(log, 'FLEET-BACKUP.log entry should exist');
    assert.strictEqual(log.needsRotation, false, 'small log within both thresholds must not be flagged');
  } finally {
    fixture.cleanup();
  }
});

// === 4) checkMemoryFreshness(): 30-day staleness boundary ===

function writeMemoryFile(brainRoot, project, filename, ageDays) {
  const memDir = path.join(brainRoot, 'projects', project, 'memory');
  fs.mkdirSync(memDir, { recursive: true });
  const fp = path.join(memDir, filename);
  fs.writeFileSync(fp, '# memory note\n', 'utf8');
  const ageMs = ageDays * 24 * 60 * 60 * 1000;
  const mtime = (Date.now() - ageMs) / 1000;
  fs.utimesSync(fp, mtime, mtime);
  return fp;
}

test('checkMemoryFreshness: a memory file just under 30 days old is NOT flagged stale', async () => {
  const fixture = createFixture();
  const brainRoot = path.join(fixture.root, '..', '.claude');
  try {
    writeMemoryFile(brainRoot, 'demo-project', 'recent-note.md', 29);

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    assert.strictEqual(signals.memory.staleCount, 0, 'a 29-day-old memory file must not be flagged stale (< 30d threshold)');
  } finally {
    try { fs.rmSync(brainRoot, { recursive: true, force: true }); } catch {}
    fixture.cleanup();
  }
});

test('checkMemoryFreshness: a memory file just over 30 days old IS flagged stale', async () => {
  const fixture = createFixture();
  const brainRoot = path.join(fixture.root, '..', '.claude');
  try {
    writeMemoryFile(brainRoot, 'demo-project', 'old-note.md', 31);

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    assert.strictEqual(signals.memory.staleCount, 1, 'a 31-day-old memory file MUST be flagged stale (> 30d threshold)');
    assert.ok(signals.memory.staleMemories.includes('old-note.md'), 'stale file name should be listed');
  } finally {
    try { fs.rmSync(brainRoot, { recursive: true, force: true }); } catch {}
    fixture.cleanup();
  }
});

test('checkMemoryFreshness: MEMORY.md and INBOX.md are exempt from staleness even when old', async () => {
  const fixture = createFixture();
  const brainRoot = path.join(fixture.root, '..', '.claude');
  try {
    writeMemoryFile(brainRoot, 'demo-project', 'MEMORY.md', 90);
    writeMemoryFile(brainRoot, 'demo-project', 'INBOX.md', 90);

    runCollector(fixture.root);
    const signals = readSignals(fixture);

    assert.strictEqual(signals.memory.staleCount, 0, 'MEMORY.md/INBOX.md must be excluded from the staleness scan regardless of age');
  } finally {
    try { fs.rmSync(brainRoot, { recursive: true, force: true }); } catch {}
    fixture.cleanup();
  }
});

// === Honest gap documentation ===

test('GAP: the disjoint-file-ownership preflight guard is NOT in-repo code', () => {
  // The flat-dispatch pattern's preflight guard ("refuses to run on overlapping
  // files") lives in ~/.claude/skills/buildsystem/wave-flat-dispatch.template.mjs
  // — a file in the user's personal harness config directory, OUTSIDE this repo
  // (aesop/skills/ only ships CLAUDE.md, healthcheck/SKILL.md, power/SKILL.md;
  // there is no buildsystem skill or wave-flat-dispatch template checked into
  // this repository). It is therefore NOT aesop-owned importable code and this
  // suite does NOT fake a test against it.
  //
  // The closest in-repo equivalent is detectIsolationViolations() in
  // monitor/collect-signals.mjs, which distinguishes git-tracked source
  // directories from untracked in-root worktrees (a related but distinct
  // "did an agent step where it shouldn't" guard, not a file-ownership-overlap
  // check). That function is already covered by
  // tests/collect-signals.test.mjs ("isolation violation: ..." tests).
  //
  // If the disjoint-file-ownership guard is ever vendored into this repo (e.g.
  // extracted into tools/ so it can be imported instead of templated per-user),
  // this test should be replaced with real assertions against it.
  assert.ok(true, 'gap documented: disjoint-file-ownership guard lives outside this repo');
});

test('GAP: model-dispatch behavior inside the Claude Code harness is out of scope', () => {
  // "Haiku is sufficient" and actual model selection/dispatch happen inside the
  // Claude Code harness (subagent spawning, model routing) which aesop does not
  // implement — aesop only WRITES prompts/manifests that hint model choice
  // (e.g. "[[ALLOW-NON-HAIKU]]" markers) and reads back transcripts/heartbeats
  // after the fact. There is no in-repo function that decides "run this on
  // Haiku vs Sonnet" for us to unit test; that decision is made by the harness,
  // not by aesop code. This suite does not fabricate a test for it.
  assert.ok(true, 'gap documented: model dispatch is a harness behavior, not aesop-owned code');
});
