// Tests for hooks/claude/force-model-policy.mjs — the Claude Code PreToolUse
// hook that enforces the "subagents are always Haiku" cardinal rule as code.
//
// Contract under test (stdin -> stdout JSON, exit 0 always):
//  - Agent/Task dispatch with absent or non-haiku model  -> rewritten to policy model
//  - prompt containing [[ALLOW-NON-HAIKU]]               -> pass through (no output)
//  - malformed stdin                                     -> no output, exit 0 (fail-open)
//  - aesop.config.json cardinal_rules.subagent_model     -> overrides the "haiku" default
//
// Run: node --test tests/force-model-policy.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HOOK = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  '..', 'hooks', 'claude', 'force-model-policy.mjs'
);

// Every run gets an isolated AESOP_ROOT (and cwd) so the hook never picks up a
// real aesop.config.json from the developer's machine.
function makeRoot(config) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'aesop-hook-test-'));
  if (config !== undefined) {
    fs.writeFileSync(path.join(root, 'aesop.config.json'), JSON.stringify(config));
  }
  return root;
}

function runHook(stdinText, { config } = {}) {
  const root = makeRoot(config);
  const res = spawnSync(process.execPath, [HOOK], {
    input: stdinText,
    cwd: root,
    env: { ...process.env, AESOP_ROOT: root },
    encoding: 'utf8'
  });
  return res;
}

function payload(toolName, toolInput) {
  return JSON.stringify({
    hook_event_name: 'PreToolUse',
    tool_name: toolName,
    tool_input: toolInput
  });
}

test('non-haiku model on an Agent dispatch is rewritten to haiku', () => {
  const res = runHook(payload('Agent', {
    description: 'do a thing',
    prompt: 'Implement the feature.',
    subagent_type: 'general-purpose',
    model: 'opus'
  }));
  assert.equal(res.status, 0, 'hook must exit 0');
  const out = JSON.parse(res.stdout);
  const hso = out.hookSpecificOutput;
  assert.equal(hso.hookEventName, 'PreToolUse');
  assert.equal(hso.permissionDecision, 'allow');
  assert.equal(hso.updatedInput.model, 'haiku');
  // Everything else in tool_input must be preserved verbatim.
  assert.equal(hso.updatedInput.prompt, 'Implement the feature.');
  assert.equal(hso.updatedInput.description, 'do a thing');
  assert.equal(hso.updatedInput.subagent_type, 'general-purpose');
});

test('absent model on a Task dispatch is rewritten to haiku', () => {
  const res = runHook(payload('Task', {
    description: 'search',
    prompt: 'Find all callers.'
  }));
  assert.equal(res.status, 0);
  const out = JSON.parse(res.stdout);
  assert.equal(out.hookSpecificOutput.updatedInput.model, 'haiku');
});

test('model already compliant passes through unchanged (no output)', () => {
  const res = runHook(payload('Agent', {
    description: 'cheap work',
    prompt: 'Grep for a symbol.',
    model: 'haiku'
  }));
  assert.equal(res.status, 0);
  assert.equal(res.stdout.trim(), '', 'compliant dispatch must not be rewritten');
});

test('escape hatch [[ALLOW-NON-HAIKU]] in prompt passes through unchanged', () => {
  const res = runHook(payload('Agent', {
    description: 'heavy reasoning',
    prompt: 'Design the architecture. [[ALLOW-NON-HAIKU]]',
    model: 'opus'
  }));
  assert.equal(res.status, 0);
  assert.equal(res.stdout.trim(), '', 'escape hatch must suppress the rewrite');
});

test('malformed stdin: no output, exit 0 (fail-open, never crash)', () => {
  const res = runHook('this is { not json');
  assert.equal(res.status, 0, 'hook must never crash the harness');
  assert.equal(res.stdout.trim(), '');
});

test('unrelated tool names are ignored', () => {
  const res = runHook(payload('Bash', { command: 'ls', model: 'opus' }));
  assert.equal(res.status, 0);
  assert.equal(res.stdout.trim(), '');
});

test('aesop.config.json cardinal_rules.subagent_model overrides the default', () => {
  const res = runHook(
    payload('Agent', { description: 'x', prompt: 'y', model: 'opus' }),
    { config: { cardinal_rules: { subagent_model: 'haiku-4-5' } } }
  );
  assert.equal(res.status, 0);
  const out = JSON.parse(res.stdout);
  assert.equal(out.hookSpecificOutput.updatedInput.model, 'haiku-4-5');
});

test('config model is also honored as compliant (no rewrite when it matches)', () => {
  const res = runHook(
    payload('Agent', { description: 'x', prompt: 'y', model: 'haiku-4-5' }),
    { config: { cardinal_rules: { subagent_model: 'haiku-4-5' } } }
  );
  assert.equal(res.status, 0);
  assert.equal(res.stdout.trim(), '');
});
