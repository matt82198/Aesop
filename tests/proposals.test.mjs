import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { execSync } from 'node:child_process';

// Helper: create temporary directory for each test
function createTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'proposals-test-'));
}

// Helper: run proposals.mjs command
function runProposals(args, cwd) {
  const cmd = `node ${path.resolve('./tools/proposals.mjs')} ${args}`;
  try {
    const output = execSync(cmd, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
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
