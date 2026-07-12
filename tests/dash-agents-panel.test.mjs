// Tests for enhanced agents panel with clickable details
// Testing: JSONL parsing, token accumulation, status classification, XSS safety
// Run: node --test tests/dash-agents-panel.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'dash', 'dash-extra.mjs');

// Build fixture with custom JSONL agent transcripts
function makeFixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'aesop-agents-panel-test-'));
  const aesopRoot = path.join(root, 'aesop');
  const transcriptsRoot = path.join(root, 'projects');
  const stateDir = path.join(aesopRoot, 'state');
  fs.mkdirSync(aesopRoot, { recursive: true });
  fs.mkdirSync(stateDir, { recursive: true });
  fs.mkdirSync(transcriptsRoot, { recursive: true });
  return { root, aesopRoot, transcriptsRoot, stateDir };
}

function runScript(fixture, extraEnv = {}) {
  const stdout = execFileSync(process.execPath, [SCRIPT, '--json'], {
    env: {
      ...process.env,
      AESOP_ROOT: fixture.aesopRoot,
      AESOP_TRANSCRIPTS_ROOT: fixture.transcriptsRoot,
      ...extraEnv
    },
    encoding: 'utf8',
    timeout: 30000,
    killSignal: 'SIGKILL'
  });
  return JSON.parse(stdout);
}

test('parse agent JSONL: extract dispatch prompt from first user message', () => {
  const fixture = makeFixture();
  try {
    const agentPath = path.join(fixture.transcriptsRoot, 'agent-test001.jsonl');
    const now = Date.now();
    const isoTime = new Date(now).toISOString();

    const jsonl = [
      { type: 'user', message: { role: 'user', content: 'Build a clickable dashboard panel' }, timestamp: isoTime },
      { type: 'assistant', message: { role: 'assistant', content: 'Starting work...' }, model: 'claude-haiku', usage: { input_tokens: 100, output_tokens: 50 }, timestamp: new Date(now + 1000).toISOString() },
      { type: 'assistant', message: { role: 'assistant', content: 'Complete.' }, model: 'claude-haiku', usage: { input_tokens: 200, output_tokens: 75 }, timestamp: new Date(now + 2000).toISOString() }
    ];

    fs.writeFileSync(agentPath, jsonl.map(j => JSON.stringify(j)).join('\n') + '\n');

    const agents = runScript(fixture);
    assert.ok(agents.length > 0, 'agent should be detected');
    const agent = agents.find(a => a.id.includes('test001'));
    assert.ok(agent, 'specific agent should be found');
    assert.ok(agent.promptFull, 'promptFull should be populated');
    assert.ok(agent.promptFull.includes('clickable dashboard panel'), 'prompt should contain task description');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('parse agent JSONL: accumulate tokens from all assistant messages', () => {
  const fixture = makeFixture();
  try {
    const agentPath = path.join(fixture.transcriptsRoot, 'agent-tokens001.jsonl');
    const now = Date.now();
    const isoTime = new Date(now).toISOString();

    const jsonl = [
      { type: 'user', message: { role: 'user', content: 'Test tokens' }, timestamp: isoTime },
      { type: 'assistant', message: { role: 'assistant', content: 'msg1' }, usage: { input_tokens: 100, output_tokens: 50 }, timestamp: new Date(now + 1000).toISOString() },
      { type: 'assistant', message: { role: 'assistant', content: 'msg2' }, usage: { input_tokens: 150, output_tokens: 75 }, timestamp: new Date(now + 2000).toISOString() },
      { type: 'assistant', message: { role: 'assistant', content: 'msg3' }, usage: { input_tokens: 200, output_tokens: 100 }, timestamp: new Date(now + 3000).toISOString() }
    ];

    fs.writeFileSync(agentPath, jsonl.map(j => JSON.stringify(j)).join('\n') + '\n');

    const agents = runScript(fixture);
    const agent = agents.find(a => a.id.includes('tokens001'));
    assert.ok(agent, 'agent should be found');
    assert.ok(agent.tokensUsed !== undefined, 'tokensUsed should be set');
    // Total: (100+150+200) input + (50+75+100) output = 675 total
    assert.equal(agent.tokensUsed, 675, 'tokens should be accumulated from all assistant messages');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('parse agent JSONL: extract task label from first line of prompt', () => {
  const fixture = makeFixture();
  try {
    const agentPath = path.join(fixture.transcriptsRoot, 'agent-task001.jsonl');
    const now = Date.now();
    const isoTime = new Date(now).toISOString();

    const taskPrompt = 'Implement a clickable agent panel with status dots\n\nDetailed requirements:\n1. Parse JSONL files\n2. Extract token counts\n3. Render in dashboard';

    const jsonl = [
      { type: 'user', message: { role: 'user', content: taskPrompt }, timestamp: isoTime }
    ];

    fs.writeFileSync(agentPath, jsonl.map(j => JSON.stringify(j)).join('\n') + '\n');

    const agents = runScript(fixture);
    const agent = agents.find(a => a.id.includes('task001'));
    assert.ok(agent, 'agent should be found');
    assert.ok(agent.taskLabel, 'taskLabel should be extracted');
    assert.ok(agent.taskLabel.includes('clickable agent panel'), 'task label should start with first line of prompt');
    assert.ok(agent.taskLabel.length <= 80, 'task label should be capped at 80 chars');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('calculate runtime: startedAt and lastActivity from timestamps', () => {
  const fixture = makeFixture();
  try {
    const agentPath = path.join(fixture.transcriptsRoot, 'agent-runtime001.jsonl');
    const startTime = Date.now();
    const startIso = new Date(startTime).toISOString();
    const endTime = startTime + 30000; // 30 seconds later
    const endIso = new Date(endTime).toISOString();

    const jsonl = [
      { type: 'user', message: { role: 'user', content: 'test runtime' }, timestamp: startIso },
      { type: 'assistant', message: { role: 'assistant', content: 'complete' }, timestamp: endIso }
    ];

    fs.writeFileSync(agentPath, jsonl.map(j => JSON.stringify(j)).join('\n') + '\n');

    const agents = runScript(fixture);
    const agent = agents.find(a => a.id.includes('runtime001'));
    assert.ok(agent, 'agent should be found');
    assert.ok(agent.startedAt, 'startedAt should be set');
    assert.ok(agent.lastActivity, 'lastActivity should be set');
    assert.ok(agent.runtimeSeconds !== undefined, 'runtimeSeconds should be calculated');
    assert.ok(agent.runtimeSeconds > 0, 'runtime should be > 0');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('status classification: RUNNING if modified < 90s ago', () => {
  const fixture = makeFixture();
  try {
    const agentPath = path.join(fixture.transcriptsRoot, 'agent-running001.jsonl');
    const now = Date.now();

    // Set file mtime to 30 seconds ago
    fs.writeFileSync(agentPath, '{"type":"user"}\n');
    const pastTime = Math.floor((now - 30000) / 1000);
    fs.utimesSync(agentPath, pastTime, pastTime);

    const agents = runScript(fixture);
    const agent = agents.find(a => a.id.includes('running001'));
    assert.ok(agent, 'agent should be found');
    assert.equal(agent.status, 'running', 'status should be "running" when mtime < 90s');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('status classification: IDLE if 90s < mtime < 12min', () => {
  const fixture = makeFixture();
  try {
    const agentPath = path.join(fixture.transcriptsRoot, 'agent-idle001.jsonl');
    const now = Date.now();

    fs.writeFileSync(agentPath, '{"type":"user"}\n');
    // Set mtime to 5 minutes ago
    const pastTime = Math.floor((now - 5 * 60 * 1000) / 1000);
    fs.utimesSync(agentPath, pastTime, pastTime);

    const agents = runScript(fixture);
    const agent = agents.find(a => a.id.includes('idle001'));
    assert.ok(agent, 'agent should be found');
    assert.equal(agent.status, 'idle', 'status should be "idle" when 90s < mtime < 12min');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('tolerate malformed JSONL lines gracefully', () => {
  const fixture = makeFixture();
  try {
    const agentPath = path.join(fixture.transcriptsRoot, 'agent-malformed001.jsonl');
    const now = Date.now();
    const isoTime = new Date(now).toISOString();

    // Mix valid and invalid JSON lines
    const lines = [
      '{"type":"user","message":{"role":"user","content":"test"},"timestamp":"' + isoTime + '"}',
      'THIS IS NOT VALID JSON AT ALL {{{',
      '{"type":"assistant","message":{"role":"assistant","content":"ok"},"usage":{"input_tokens":100,"output_tokens":50},"timestamp":"' + new Date(now + 1000).toISOString() + '"}',
      'another broken line with mismatched braces }',
      '{"type":"assistant","message":{"role":"assistant","content":"done"},"usage":{"input_tokens":150,"output_tokens":75},"timestamp":"' + new Date(now + 2000).toISOString() + '"}'
    ];

    fs.writeFileSync(agentPath, lines.join('\n') + '\n');

    const agents = runScript(fixture);
    const agent = agents.find(a => a.id.includes('malformed001'));
    assert.ok(agent, 'agent should be found despite malformed lines');
    assert.ok(agent.promptFull, 'prompt should still be extracted');
    assert.equal(agent.tokensUsed, 375, 'tokens should be accumulated from valid lines only (100+50+150+75)');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('XSS safety: prompt containing <script> renders inert with textContent', () => {
  const fixture = makeFixture();
  try {
    const agentPath = path.join(fixture.transcriptsRoot, 'agent-xss001.jsonl');
    const now = Date.now();
    const isoTime = new Date(now).toISOString();

    const maliciousPrompt = 'Normal prompt text <script>alert("xss")</script> with script tag';

    const jsonl = [
      { type: 'user', message: { role: 'user', content: maliciousPrompt }, timestamp: isoTime }
    ];

    fs.writeFileSync(agentPath, jsonl.map(j => JSON.stringify(j)).join('\n') + '\n');

    const agents = runScript(fixture);
    const agent = agents.find(a => a.id.includes('xss001'));
    assert.ok(agent, 'agent should be found');
    assert.ok(agent.promptFull, 'prompt should be extracted');
    // The prompt field should contain the literal text, not parsed HTML
    assert.ok(agent.promptFull.includes('<script>'), 'prompt should preserve literal script tag text');
    // Verify no execution happens by checking the prompt is a plain string
    assert.equal(typeof agent.promptFull, 'string', 'prompt should be a string (no HTML object)');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('project extraction: derive project from file path', () => {
  const fixture = makeFixture();
  try {
    const projectPath = path.join(fixture.transcriptsRoot, 'my-project', 'session-123', 'subagents');
    fs.mkdirSync(projectPath, { recursive: true });
    const agentPath = path.join(projectPath, 'agent-proj001.jsonl');
    const now = Date.now();
    const isoTime = new Date(now).toISOString();

    const jsonl = [
      { type: 'user', message: { role: 'user', content: 'test project extraction' }, timestamp: isoTime }
    ];

    fs.writeFileSync(agentPath, jsonl.map(j => JSON.stringify(j)).join('\n') + '\n');

    const agents = runScript(fixture);
    const agent = agents.find(a => a.id.includes('proj001'));
    assert.ok(agent, 'agent should be found');
    assert.ok(agent.project, 'project should be derived from path');
    assert.ok(agent.project.includes('my-project'), 'project should contain project directory name');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('cap JSONL read size: only read first 50 + last 50 lines for large files', () => {
  const fixture = makeFixture();
  try {
    const agentPath = path.join(fixture.transcriptsRoot, 'agent-large001.jsonl');
    const now = Date.now();
    const isoTime = new Date(now).toISOString();

    // Create a large JSONL file with 1000+ lines
    const lines = [];
    lines.push(JSON.stringify({ type: 'user', message: { role: 'user', content: 'test large file' }, timestamp: isoTime }));

    // Add 500 middle lines with tokens
    for (let i = 0; i < 500; i++) {
      lines.push(JSON.stringify({
        type: 'assistant',
        message: { role: 'assistant', content: `msg ${i}` },
        usage: { input_tokens: 10, output_tokens: 5 },
        timestamp: new Date(now + (i + 1) * 1000).toISOString()
      }));
    }

    // Add final line
    lines.push(JSON.stringify({
      type: 'assistant',
      message: { role: 'assistant', content: 'final' },
      usage: { input_tokens: 50, output_tokens: 25 },
      timestamp: new Date(now + 501000).toISOString()
    }));

    fs.writeFileSync(agentPath, lines.join('\n') + '\n');

    const agents = runScript(fixture);
    const agent = agents.find(a => a.id.includes('large001'));
    assert.ok(agent, 'agent should be found');
    assert.ok(agent.promptFull, 'prompt should be extracted from first line');
    // Tokens MUST be the EXACT full-file total, not the sampled first-50+last-50
    // subset (that sampling under-counted long transcripts by >60%).
    // 500 assistant msgs x (10 + 5) + 1 final (50 + 25) = 7575.
    assert.strictEqual(agent.tokensUsed, 7575,
      'tokensUsed must sum ALL assistant usage across the full file, not a sampled subset');
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});

test('BUG4: --json emits ALL active agents (no hard 8-cap) so the web count is the true total', () => {
  const fixture = makeFixture();
  try {
    const N = 12; // more than the old .slice(0, 8) cap
    for (let i = 0; i < N; i++) {
      const p = path.join(fixture.transcriptsRoot, `agent-cap${String(i).padStart(3, '0')}.jsonl`);
      fs.writeFileSync(p, JSON.stringify({
        type: 'user',
        message: { role: 'user', content: `task ${i}` },
        timestamp: new Date().toISOString()
      }) + '\n');
    }
    const agents = runScript(fixture);
    // Old code sliced to 8 -> web header showed "8 active" for 12 real agents.
    assert.strictEqual(agents.length, N,
      `--json must emit all ${N} active agents (was capped at 8), got ${agents.length}`);
  } finally {
    fs.rmSync(fixture.root, { recursive: true, force: true });
  }
});
