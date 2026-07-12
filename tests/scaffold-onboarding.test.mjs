// Tests for CLI onboarding scaffolding
// Contract under test:
//  - cli.js --name flag generates CLAUDE.md and aesop.config.json without placeholders
//  - cli.js creates state/ directory during scaffold
//  - cli.js copies docs/MEMORY-TEMPLATE.md as memory seed
//  - CLAUDE-TEMPLATE.md has no "[Your " style bare placeholders (only {{TOKENS}})
//  - Headless scaffold (with --name/--domains/--repos) produces complete working setup
//
// Run: node --test tests/scaffold-onboarding.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const CLI = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  '..', 'bin', 'cli.js'
);

const CLAUDE_TEMPLATE = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  '..', 'CLAUDE-TEMPLATE.md'
);

const MEMORY_TEMPLATE = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  '..', 'docs', 'MEMORY-TEMPLATE.md'
);

function runCli(targetDir, args = []) {
  const res = spawnSync(process.execPath, [CLI, targetDir, ...args], {
    encoding: 'utf8',
    cwd: path.dirname(targetDir)
  });
  return res;
}

function createTestDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'aesop-onboard-test-'));
}

function gitCmd(cwd, cmd) {
  const bashCmd = `bash -c "cd '${cwd.replace(/'/g, "'\\''")}' && ${cmd}"`;
  return spawnSync('bash', ['-c', bashCmd], { stdio: 'ignore', encoding: 'utf8' });
}

test('CLAUDE-TEMPLATE.md has no "[Your " style bare placeholders', () => {
  const template = fs.readFileSync(CLAUDE_TEMPLATE, 'utf8');
  const barePlaceholderPattern = /\[Your\s+/gi;
  const matches = template.match(barePlaceholderPattern);
  assert.equal(matches, null, `Template should not have "[Your " style placeholders. Found: ${matches}`);
});

test('CLAUDE-TEMPLATE.md contains {{TOKEN}} style placeholders for substitution', () => {
  const template = fs.readFileSync(CLAUDE_TEMPLATE, 'utf8');
  const tokenPattern = /{{[A-Z_]+}}/;
  const matches = template.match(tokenPattern);
  assert.ok(matches, `Template should have {{TOKEN}} style placeholders for machine substitution`);
});

test('CLAUDE-TEMPLATE.md is a filled worked example, not bare template', () => {
  const template = fs.readFileSync(CLAUDE_TEMPLATE, 'utf8');
  // Should have some concrete content (not just sections with no examples)
  assert.ok(template.includes('Cardinal'), 'Template should reference cardinal rules');
  assert.ok(template.length > 500, 'Template should be a substantial worked example');
});

test('--name flag scaffolds without errors', () => {
  const tempDir = createTestDir();
  const targetDir = path.join(tempDir, 'fleet-onboard-1');

  fs.mkdirSync(targetDir, { recursive: true });
  gitCmd(targetDir, 'git init');
  gitCmd(targetDir, 'git config user.email "test@example.com"');
  gitCmd(targetDir, 'git config user.name "Test User"');

  const res = runCli(targetDir, ['--name', 'test-service']);
  assert.equal(res.status, 0, `Scaffold with --name should succeed. stderr: ${res.stderr}`);
});

test('--name --domains --repos scaffolds without errors', () => {
  const tempDir = createTestDir();
  const targetDir = path.join(tempDir, 'fleet-onboard-2');

  fs.mkdirSync(targetDir, { recursive: true });
  gitCmd(targetDir, 'git init');
  gitCmd(targetDir, 'git config user.email "test@example.com"');
  gitCmd(targetDir, 'git config user.name "Test User"');

  const res = runCli(targetDir, [
    '--name', 'my-service',
    '--domains', 'api,worker,monitoring',
    '--repos', '/path/to/repo1,/path/to/repo2'
  ]);
  assert.equal(res.status, 0, `Scaffold with full flags should succeed. stderr: ${res.stderr}`);
});

test('scaffold creates state/ directory', () => {
  const tempDir = createTestDir();
  const targetDir = path.join(tempDir, 'fleet-onboard-3');

  fs.mkdirSync(targetDir, { recursive: true });
  gitCmd(targetDir, 'git init');
  gitCmd(targetDir, 'git config user.email "test@example.com"');
  gitCmd(targetDir, 'git config user.name "Test User"');

  const res = runCli(targetDir, ['--name', 'test-service']);
  assert.equal(res.status, 0);

  const stateDir = path.join(targetDir, 'state');
  assert.ok(fs.existsSync(stateDir), `state/ directory should be created at ${stateDir}`);
  assert.ok(fs.statSync(stateDir).isDirectory(), 'state/ should be a directory');
});

test('scaffold generates CLAUDE.md with no {{UNSUBSTITUTED}} placeholders', () => {
  const tempDir = createTestDir();
  const targetDir = path.join(tempDir, 'fleet-onboard-4');

  fs.mkdirSync(targetDir, { recursive: true });
  gitCmd(targetDir, 'git init');
  gitCmd(targetDir, 'git config user.email "test@example.com"');
  gitCmd(targetDir, 'git config user.name "Test User"');

  const res = runCli(targetDir, ['--name', 'test-service']);
  assert.equal(res.status, 0);

  const claudeMdPath = path.join(targetDir, 'CLAUDE.md');
  assert.ok(fs.existsSync(claudeMdPath), `CLAUDE.md should be generated at ${claudeMdPath}`);

  const claudeContent = fs.readFileSync(claudeMdPath, 'utf8');

  // Check that all {{TOKENS}} have been substituted (none remain)
  const unreplacedPattern = /{{[A-Z_]+}}/g;
  const unreplaced = claudeContent.match(unreplacedPattern);
  assert.equal(unreplaced, null, `Generated CLAUDE.md should have all {{TOKENS}} substituted. Found: ${unreplaced}`);
});

test('scaffold generates valid aesop.config.json', () => {
  const tempDir = createTestDir();
  const targetDir = path.join(tempDir, 'fleet-onboard-5');

  fs.mkdirSync(targetDir, { recursive: true });
  gitCmd(targetDir, 'git init');
  gitCmd(targetDir, 'git config user.email "test@example.com"');
  gitCmd(targetDir, 'git config user.name "Test User"');

  const res = runCli(targetDir, [
    '--name', 'my-api',
    '--repos', '/path/to/api,/path/to/worker'
  ]);
  assert.equal(res.status, 0);

  const configPath = path.join(targetDir, 'aesop.config.json');
  assert.ok(fs.existsSync(configPath), `aesop.config.json should be generated at ${configPath}`);

  const configContent = fs.readFileSync(configPath, 'utf8');

  // Should be valid JSON
  let config;
  try {
    config = JSON.parse(configContent);
  } catch (e) {
    assert.fail(`Generated config should be valid JSON: ${e.message}`);
  }

  // Should have expected fields
  assert.ok(config.aesop_root, 'Config should have aesop_root');
  assert.ok(config.repos, 'Config should have repos array');
});

test('scaffold copies MEMORY-TEMPLATE.md as memory seed', () => {
  const tempDir = createTestDir();
  const targetDir = path.join(tempDir, 'fleet-onboard-6');

  fs.mkdirSync(targetDir, { recursive: true });
  gitCmd(targetDir, 'git init');
  gitCmd(targetDir, 'git config user.email "test@example.com"');
  gitCmd(targetDir, 'git config user.name "Test User"');

  const res = runCli(targetDir, ['--name', 'test-service']);
  assert.equal(res.status, 0);

  const memorySeedPath = path.join(targetDir, 'MEMORY-SEED.md');
  assert.ok(fs.existsSync(memorySeedPath), `MEMORY-SEED.md should be created at ${memorySeedPath}`);

  const memoryContent = fs.readFileSync(memorySeedPath, 'utf8');
  const templateContent = fs.readFileSync(MEMORY_TEMPLATE, 'utf8');

  assert.equal(memoryContent, templateContent, 'MEMORY-SEED.md should be copy of MEMORY-TEMPLATE.md');
});

test('full headless scaffold is complete and valid', () => {
  const tempDir = createTestDir();
  const targetDir = path.join(tempDir, 'fleet-onboard-full');

  fs.mkdirSync(targetDir, { recursive: true });
  gitCmd(targetDir, 'git init');
  gitCmd(targetDir, 'git config user.email "test@example.com"');
  gitCmd(targetDir, 'git config user.name "Test User"');

  // Headless scaffold with all flags
  const res = runCli(targetDir, [
    '--name', 'production-api',
    '--domains', 'api,worker,security,monitoring',
    '--repos', '/home/user/my-api,/home/user/my-worker'
  ]);
  assert.equal(res.status, 0, `Full scaffold should succeed. stderr: ${res.stderr}`);

  // Verify all required files exist
  const claudeMd = path.join(targetDir, 'CLAUDE.md');
  const configJson = path.join(targetDir, 'aesop.config.json');
  const stateDir = path.join(targetDir, 'state');
  const hookPath = path.join(targetDir, '.git', 'hooks', 'pre-push');

  assert.ok(fs.existsSync(claudeMd), 'CLAUDE.md should exist');
  assert.ok(fs.existsSync(configJson), 'aesop.config.json should exist');
  assert.ok(fs.existsSync(stateDir), 'state/ should exist');
  assert.ok(fs.existsSync(hookPath), 'hook should be installed');

  // Verify quality
  const claudeContent = fs.readFileSync(claudeMd, 'utf8');
  assert.ok(!claudeContent.match(/{{[A-Z_]+}}/), 'CLAUDE.md should have no unsubstituted tokens');
  assert.ok(claudeContent.includes('production-api'), 'CLAUDE.md should include project name');

  const config = JSON.parse(fs.readFileSync(configJson, 'utf8'));
  assert.ok(config.repos && config.repos.length > 0, 'Config should have repos');
});
