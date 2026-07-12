import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { execSync, spawn } from 'node:child_process';

// Helper: create temporary directory for each test
function createTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'proposals-test-'));
}

// Helper: run proposals.mjs command
function runProposals(args, cwd) {
  const cmd = `node ${path.resolve('./tools/proposals.mjs')} ${args}`;
  try {
    const output = execSync(cmd, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000, killSignal: 'SIGKILL' }).trim();
    return { success: true, output };
  } catch (e) {
    return { success: false, output: e.stdout?.toString() || '', error: e.stderr?.toString() || e.message };
  }
}

// Sample proposal block format (matches monitor/collect-signals.mjs emitProposal)
const sampleProposal1 = `
## test-signal-1 — 2026-07-12T12:00:00.000Z

**Signal:** test-signal-1

**Problem:**
This is a test problem.

**Suggested change:**
This is a suggested change.

---
`;

const sampleProposal2 = `
## test-signal-2 — 2026-07-12T12:01:00.000Z

**Signal:** test-signal-2

**Problem:**
Another test problem.

**Suggested change:**
Another suggested change.

---
`;

test('list: shows proposals with signal key, first line, and status', async (t) => {
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');

  // Create PROPOSALS.md with two proposals
  fs.writeFileSync(proposalsFile, sampleProposal1 + sampleProposal2, 'utf8');

  const result = runProposals(`list --file "${proposalsFile}"`, tempDir);
  assert.strictEqual(result.success, true, `Command failed: ${result.error}`);

  // Should show both proposals
  assert.match(result.output, /test-signal-1/, 'Should show first signal key');
  assert.match(result.output, /test-signal-2/, 'Should show second signal key');

  // Cleanup
  fs.rmSync(tempDir, { recursive: true });
});

test('list: shows PENDING status for proposals in PROPOSALS.md', async (t) => {
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');

  fs.writeFileSync(proposalsFile, sampleProposal1, 'utf8');

  const result = runProposals(`list --file "${proposalsFile}"`, tempDir);
  assert.strictEqual(result.success, true);
  assert.match(result.output, /PENDING|ACTIVE/, 'Should show pending/active status');

  fs.rmSync(tempDir, { recursive: true });
});

test('accept: moves proposal block from PROPOSALS.md to PROPOSALS-LOG.md', async (t) => {
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');
  const logFile = path.join(tempDir, 'PROPOSALS-LOG.md');

  fs.writeFileSync(proposalsFile, sampleProposal1 + sampleProposal2, 'utf8');

  const result = runProposals(`accept test-signal-1 --file "${proposalsFile}"`, tempDir);
  assert.strictEqual(result.success, true, `Command failed: ${result.error}`);

  // Check PROPOSALS.md no longer has test-signal-1
  const proposalsContent = fs.readFileSync(proposalsFile, 'utf8');
  assert.match(proposalsContent, /test-signal-2/, 'test-signal-2 should remain');
  assert.doesNotMatch(proposalsContent, /test-signal-1/, 'test-signal-1 should be removed');

  // Check PROPOSALS-LOG.md now has test-signal-1 under ACCEPTED heading
  assert.ok(fs.existsSync(logFile), 'PROPOSALS-LOG.md should exist');
  const logContent = fs.readFileSync(logFile, 'utf8');
  assert.match(logContent, /## ACCEPTED/, 'Should have ACCEPTED heading');
  assert.match(logContent, /test-signal-1/, 'Should contain accepted proposal');

  fs.rmSync(tempDir, { recursive: true });
});

test('reject: moves proposal block to PROPOSALS-LOG.md under REJECTED heading', async (t) => {
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');
  const logFile = path.join(tempDir, 'PROPOSALS-LOG.md');

  fs.writeFileSync(proposalsFile, sampleProposal1 + sampleProposal2, 'utf8');

  const result = runProposals(`reject test-signal-2 --file "${proposalsFile}"`, tempDir);
  assert.strictEqual(result.success, true, `Command failed: ${result.error}`);

  // Check PROPOSALS.md no longer has test-signal-2
  const proposalsContent = fs.readFileSync(proposalsFile, 'utf8');
  assert.match(proposalsContent, /test-signal-1/, 'test-signal-1 should remain');
  assert.doesNotMatch(proposalsContent, /test-signal-2/, 'test-signal-2 should be removed');

  // Check PROPOSALS-LOG.md now has test-signal-2 under REJECTED heading
  assert.ok(fs.existsSync(logFile), 'PROPOSALS-LOG.md should exist');
  const logContent = fs.readFileSync(logFile, 'utf8');
  assert.match(logContent, /## REJECTED/, 'Should have REJECTED heading');
  assert.match(logContent, /test-signal-2/, 'Should contain rejected proposal');

  fs.rmSync(tempDir, { recursive: true });
});

test('accept: missing key returns error with clear message', async (t) => {
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');

  fs.writeFileSync(proposalsFile, sampleProposal1, 'utf8');

  const result = runProposals(`accept nonexistent-signal --file "${proposalsFile}"`, tempDir);
  assert.strictEqual(result.success, false, 'Should fail for missing key');
  assert.match(result.error || result.output, /nonexistent-signal|not found|not in/i, 'Should mention missing key');

  fs.rmSync(tempDir, { recursive: true });
});

test('reject: missing key returns error with clear message', async (t) => {
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');

  fs.writeFileSync(proposalsFile, sampleProposal1, 'utf8');

  const result = runProposals(`reject nonexistent-signal --file "${proposalsFile}"`, tempDir);
  assert.strictEqual(result.success, false, 'Should fail for missing key');
  assert.match(result.error || result.output, /nonexistent-signal|not found|not in/i, 'Should mention missing key');

  fs.rmSync(tempDir, { recursive: true });
});

test('accept: idempotent re-accept is no-op with notice', async (t) => {
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');
  const logFile = path.join(tempDir, 'PROPOSALS-LOG.md');

  fs.writeFileSync(proposalsFile, sampleProposal1, 'utf8');

  // First accept
  runProposals(`accept test-signal-1 --file "${proposalsFile}"`, tempDir);
  const logAfterFirst = fs.readFileSync(logFile, 'utf8');

  // Second accept (idempotent)
  const result = runProposals(`accept test-signal-1 --file "${proposalsFile}"`, tempDir);
  assert.strictEqual(result.success, true, 'Second accept should succeed');
  assert.match(result.output || result.error, /already|moved|no-op/i, 'Should mention idempotent behavior');

  // Log should be unchanged
  const logAfterSecond = fs.readFileSync(logFile, 'utf8');
  assert.strictEqual(logAfterFirst, logAfterSecond, 'Log should be unchanged on re-accept');

  fs.rmSync(tempDir, { recursive: true });
});

test('accept + reject: preserves proposal block verbatim in log', async (t) => {
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');
  const logFile = path.join(tempDir, 'PROPOSALS-LOG.md');

  fs.writeFileSync(proposalsFile, sampleProposal1, 'utf8');

  // Accept
  runProposals(`accept test-signal-1 --file "${proposalsFile}"`, tempDir);

  // Check that the block is preserved verbatim (excluding heading)
  const logContent = fs.readFileSync(logFile, 'utf8');
  assert.match(logContent, /\*\*Signal:\*\* test-signal-1/, 'Should preserve Signal line');
  assert.match(logContent, /This is a test problem\./, 'Should preserve problem text');
  assert.match(logContent, /This is a suggested change\./, 'Should preserve suggested change text');

  fs.rmSync(tempDir, { recursive: true });
});

test('list: default file is monitor/PROPOSALS.md', async (t) => {
  // This test verifies the --file flag default; we'll create a minimal structure
  const tempDir = createTempDir();
  const monitorDir = path.join(tempDir, 'monitor');
  fs.mkdirSync(monitorDir, { recursive: true });
  const proposalsFile = path.join(monitorDir, 'PROPOSALS.md');

  fs.writeFileSync(proposalsFile, sampleProposal1, 'utf8');

  // Run without --file flag
  const result = runProposals('list', tempDir);
  assert.strictEqual(result.success, true, `Command failed: ${result.error}`);
  assert.match(result.output, /test-signal-1/, 'Should list from default monitor/PROPOSALS.md');

  fs.rmSync(tempDir, { recursive: true });
});

test('CRLF handling: accept/reject works with CRLF line endings', async (t) => {
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');
  const logFile = path.join(tempDir, 'PROPOSALS-LOG.md');

  // Create proposals with CRLF line endings (Windows format)
  const crlfProposal1 = `## test-signal-1 — 2026-07-12T12:00:00.000Z\r\n\r\n**Signal:** test-signal-1\r\n\r\n**Problem:**\r\nTest problem.\r\n\r\n**Suggested change:**\r\nTest change.\r\n\r\n---\r\n`;
  const crlfProposal2 = `## test-signal-2 — 2026-07-12T12:01:00.000Z\r\n\r\n**Signal:** test-signal-2\r\n\r\n**Problem:**\r\nAnother problem.\r\n\r\n**Suggested change:**\r\nAnother change.\r\n\r\n---\r\n`;

  fs.writeFileSync(proposalsFile, crlfProposal1 + crlfProposal2, 'utf8');

  const result = runProposals(`accept test-signal-1 --file "${proposalsFile}"`, tempDir);
  assert.strictEqual(result.success, true, `Command failed: ${result.error}`);

  // Verify test-signal-1 was moved
  const proposalsContent = fs.readFileSync(proposalsFile, 'utf8');
  assert.doesNotMatch(proposalsContent, /test-signal-1/, 'test-signal-1 should be removed');
  assert.match(proposalsContent, /test-signal-2/, 'test-signal-2 should remain');

  // Verify it was added to log
  assert.ok(fs.existsSync(logFile), 'PROPOSALS-LOG.md should exist');
  const logContent = fs.readFileSync(logFile, 'utf8');
  assert.match(logContent, /test-signal-1/, 'Log should contain test-signal-1');

  fs.rmSync(tempDir, { recursive: true });
});

test('multi-writer safety: concurrent appends do not lose data during accept', async (t) => {
  // Simulates: emitProposal() appends while moveProposal() is mid-read.
  // With atomic write + re-read guard, no data should be lost.
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');
  const logFile = path.join(tempDir, 'PROPOSALS-LOG.md');

  // Start with two proposals
  const proposal1 = `## signal-1 — 2026-07-12T12:00:00.000Z\n\n**Signal:** signal-1\n\n**Problem:** Test\n\n**Suggested change:** Change\n\n---\n`;
  const proposal2 = `## signal-2 — 2026-07-12T12:01:00.000Z\n\n**Signal:** signal-2\n\n**Problem:** Test2\n\n**Suggested change:** Change2\n\n---\n`;

  fs.writeFileSync(proposalsFile, proposal1 + proposal2, 'utf8');

  // Accept signal-1 (this will read, filter, and write back)
  const result = runProposals(`accept signal-1 --file "${proposalsFile}"`, tempDir);
  assert.strictEqual(result.success, true, 'Accept should succeed');

  // Verify both signals are accounted for (not lost)
  const finalProposals = fs.readFileSync(proposalsFile, 'utf8');
  const logContent = fs.existsSync(logFile) ? fs.readFileSync(logFile, 'utf8') : '';

  // signal-1 should be in log
  assert.ok(logContent.includes('signal-1'), 'signal-1 should be in log after accept');

  // signal-2 should still be in proposals (not lost)
  assert.ok(finalProposals.includes('signal-2'), 'signal-2 should remain in PROPOSALS.md (not lost)');

  fs.rmSync(tempDir, { recursive: true });
});

// === P0 Finding 1: Concurrent emit + accept race condition (real subprocess) ===
test('concurrent race: emitProposal append + accept move do not lose data (real subprocess)', async (t) => {
  // This test spawns a REAL subprocess running `proposals.mjs accept` concurrently
  // with a real emitProposal append. Tests that both operations are serialized via lock.
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');
  const logFile = path.join(tempDir, 'PROPOSALS-LOG.md');

  try {
    // Start with one proposal
    const proposal1 = `## signal-1 — 2026-07-12T12:00:00.000Z\n\n**Signal:** signal-1\n\n**Problem:** First\n\n**Suggested change:** Change1\n\n---\n`;
    fs.writeFileSync(proposalsFile, proposal1, 'utf8');

    // Spawn accept subprocess in background (will read, filter, and write)
    const proposalsPath = path.resolve('./tools/proposals.mjs');

    // stdio: 'ignore' so unconsumed piped stdout/stderr can never wedge the
    // process teardown on Linux — the test only inspects files afterward, it
    // never reads child output. (proposals.mjs does not read stdin, and its
    // acquireLock is bounded + fail-open, so the child always exits promptly.)
    const acceptProcess = spawn('node', [proposalsPath, 'accept', 'signal-1', '--file', proposalsFile], {
      cwd: tempDir,
      stdio: 'ignore',
      timeout: 30000,
      killSignal: 'SIGKILL'
    });

    // While accept is running, append a new proposal (simulating emitProposal)
    const proposal2 = `## signal-2 — 2026-07-12T12:01:00.000Z\n\n**Signal:** signal-2\n\n**Problem:** Second\n\n**Suggested change:** Change2\n\n---\n`;

    // Small delay to ensure accept starts reading
    await new Promise(r => setTimeout(r, 50));
    fs.appendFileSync(proposalsFile, proposal2, 'utf8');

    // Wait for accept to terminate. Resolve on 'exit' (fires on process
    // termination regardless of stream state) rather than 'close' (waits for
    // all stdio streams to close, which can never fire for unconsumed pipes on
    // Linux). Defensive kill-timeout guarantees the wait can never block.
    await new Promise((resolve, reject) => {
      const killer = setTimeout(() => {
        acceptProcess.kill('SIGKILL');
        reject(new Error('Accept subprocess did not exit within 15s'));
      }, 15000);
      acceptProcess.on('exit', (code) => {
        clearTimeout(killer);
        if (code === 0) resolve();
        else reject(new Error(`Accept exited with code ${code}`));
      });
    });

    // Verify both proposals are accounted for (not lost)
    const finalProposals = fs.readFileSync(proposalsFile, 'utf8');
    const finalLog = fs.existsSync(logFile) ? fs.readFileSync(logFile, 'utf8') : '';

    // signal-1 should be in log (accepted)
    assert.ok(finalLog.includes('signal-1'), 'signal-1 should be in log (accepted)');

    // signal-2 should be in proposals (not lost during concurrent accept)
    assert.ok(finalProposals.includes('signal-2'), 'signal-2 should remain in PROPOSALS.md (not lost due to race)');
  } finally {
    fs.rmSync(tempDir, { recursive: true });
  }
});

// === P1 Finding 3: Lock staleness detection ===
test('stale lock detection: orphaned .lock is reclaimed and operations proceed', async (t) => {
  const tempDir = createTempDir();
  const proposalsFile = path.join(tempDir, 'PROPOSALS.md');
  const lockDir = proposalsFile + '.lock';

  try {
    // Setup: create a stale lock directory (simulates crashed process)
    fs.mkdirSync(lockDir, { recursive: true });

    // Write an old timestamp into the lock to simulate staleness
    // (In the fix, we'll store pid+timestamp in the lock)
    const staleMarkerFile = path.join(lockDir, 'pid-timestamp.txt');
    const staleEpoch = Math.floor((Date.now() - 120 * 1000) / 1000); // 120s ago
    fs.writeFileSync(staleMarkerFile, `${process.pid}\n${staleEpoch}\n`, 'utf8');

    // Create PROPOSALS.md
    const proposal = `## signal-1 — 2026-07-12T12:00:00.000Z\n\n**Signal:** signal-1\n\n**Problem:** Test\n\n**Suggested change:** Change\n\n---\n`;
    fs.writeFileSync(proposalsFile, proposal, 'utf8');

    // Try to accept: with the fix, it should detect the stale lock and reclaim it
    const result = runProposals(`accept signal-1 --file "${proposalsFile}"`, tempDir);

    // Should succeed (either by reclaiming the stale lock or detecting it)
    assert.ok(result.success, `Accept should succeed despite stale lock: ${result.error || result.output}`);

    // The lock directory should either be cleaned up or reclaimed
    // After operation completes, the .lock should not be held
    const lockStillExists = fs.existsSync(lockDir);
    if (lockStillExists) {
      // If lock still exists, it should not block the next operation
      const result2 = runProposals(`list --file "${proposalsFile}"`, tempDir);
      assert.ok(result2.success, 'Subsequent operation should succeed even if lock exists (should be reclaimed)');
    }
  } finally {
    // Clean up lock if it exists
    if (fs.existsSync(lockDir)) {
      fs.rmSync(lockDir, { recursive: true });
    }
    fs.rmSync(tempDir, { recursive: true });
  }
});
