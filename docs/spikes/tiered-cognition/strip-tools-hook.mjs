#!/usr/bin/env node
// strip-tools-hook.mjs — SPIKE PROTOTYPE (wave 11, NOT wired into live settings).
//
// PreToolUse hook enforcing the tiered cognition/execution architecture:
// Haiku is the ONLY tier that reads/writes/executes; Sonnet/Opus/Fable are
// pure cognition (reason + message + dispatch). Two enforcement layers in
// one script (selected by payload.tool_name):
//
//   LAYER 1 — dispatch guard (matcher "Agent|Task"):
//     A subagent dispatch resolving to a cognition-tier model (sonnet/opus/
//     fable) is rewritten to the `aesop-cognition` shim agent type, whose
//     definition frontmatter allowlists ONLY cognition tools
//     (Agent, SendMessage, TaskStop, Monitor). The original requested type is
//     preserved in a COGNITION CONTRACT header prepended to the prompt.
//     NOTE: the Agent tool input schema has NO `tools` field
//     (additionalProperties: false), so per-dispatch tool lists CANNOT be set
//     via updatedInput — the agent-definition `tools:` frontmatter is the only
//     supported stripping mechanism today. Hence the shim rewrite.
//
//   LAYER 2 — call-time backstop (matcher on the denied tools below):
//     When an I/O/exec tool call fires inside a session whose transcript shows
//     a non-haiku model, the call is DENIED with a reason that redirects the
//     agent to emit a WORK-ORDER v1 and dispatch a Haiku executor instead
//     (see DESIGN.md §3). Haiku sessions pass untouched.
//
// Escape hatch: [[ALLOW-TIER-TOOLS]] in the dispatch prompt keeps the agent's
// tools ([[ALLOW-NON-HAIKU]] is honored too during migration — today's
// escalations are hands-on missions). Never silent: every use is announced via
// permissionDecisionReason and appended as a JSON line to
// ${AESOP_ROOT:-~/aesop}/state/TIER-POLICY-ESCAPES.log.
//
// Reliability: fail-open everywhere (malformed payload / missing transcript /
// unreadable agents dir => no opinion, pass). stdin raced against a 2s timer.
// See FINDINGS.md for the fail-open-vs-fail-closed discussion.
//
// Self-test: `node strip-tools-hook.mjs --self-test` (no stdin needed; builds
// its own fixtures in a temp dir, exits 0 on PASS / 1 on FAIL).

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// ---------------------------------------------------------------- constants

export const ESCAPE_TOKENS = ['[[ALLOW-TIER-TOOLS]]', '[[ALLOW-NON-HAIKU]]'];
export const SHIM_AGENT = 'aesop-cognition';
export const ESCAPE_LOG_NAME = 'TIER-POLICY-ESCAPES.log';
const STDIN_TIMEOUT_MS = 2000;

// Cognition tiers KEEP exactly these (reason + message + dispatch):
export const KEEP_TOOLS = ['Agent', 'SendMessage', 'TaskStop', 'Monitor'];

// Cognition tiers are DENIED all I/O + exec + retrieval (Haiku's job):
export const DENY_TOOLS = [
  'Read', 'Write', 'Edit', 'MultiEdit', 'NotebookEdit',
  'Bash', 'PowerShell', 'BashOutput', 'KillShell',
  'Glob', 'Grep', 'WebFetch', 'WebSearch',
  'Skill', 'Artifact', 'ToolSearch', 'EnterWorktree', 'ExitWorktree',
];

const DISPATCH_TOOLS = new Set(['Agent', 'Task']);
const DENY_SET = new Set(DENY_TOOLS);

// --------------------------------------------------------------- tier logic

/** Map a model string to a tier: 'haiku' | 'cognition' | null (unknown). */
export function tierOf(model) {
  const m = String(model || '').toLowerCase();
  if (!m) return null;
  if (m.includes('haiku')) return 'haiku';
  if (m.includes('sonnet') || m.includes('opus') || m.includes('fable')) return 'cognition';
  return null; // unrecognized model string — no opinion
}

/** Resolve tier from an installed agent definition's `model:` frontmatter
 *  (matches basename or `name:` field). Returns tier or null. */
export function tierFromAgentDef(type, agentsDir) {
  if (!type) return null;
  let files = [];
  try { files = fs.readdirSync(agentsDir).filter(f => f.endsWith('.md')); } catch { return null; }
  for (const f of files) {
    let head = '';
    try { head = fs.readFileSync(path.join(agentsDir, f), 'utf8').slice(0, 600); } catch { continue; }
    const base = f.replace(/\.md$/, '').toLowerCase();
    let match = base === type;
    if (!match) {
      const nm = head.match(/^name:\s*(.+)$/m);
      match = !!nm && nm[1].trim().toLowerCase() === type;
    }
    if (match) {
      const mm = head.match(/^model:\s*(.+)$/m);
      return mm ? tierOf(mm[1].trim()) : null;
    }
  }
  return null;
}

// -------------------------------------------------------------- audit trail

function stateDir(opts) {
  const root = (opts && opts.stateRoot) || process.env.AESOP_ROOT || path.join(os.homedir(), 'aesop');
  return path.join(root, 'state');
}

/** Best-effort JSON-line audit record for escape-hatch use; never blocks. */
function logEscapeUse(payload, opts) {
  try {
    const dir = stateDir(opts);
    fs.mkdirSync(dir, { recursive: true });
    const input = payload.tool_input || {};
    const rec = {
      ts: new Date().toISOString(),
      event: 'tier_policy_escape',
      tool: payload.tool_name,
      session_id: typeof payload.session_id === 'string' ? payload.session_id : null,
      cwd: typeof payload.cwd === 'string' ? payload.cwd : null,
      description: typeof input.description === 'string' ? input.description : null,
      requested_model: typeof input.model === 'string' ? input.model : null,
      prompt_head: typeof input.prompt === 'string' ? input.prompt.slice(0, 200) : null,
    };
    fs.appendFileSync(path.join(dir, ESCAPE_LOG_NAME), JSON.stringify(rec) + '\n');
  } catch { /* audit is best-effort */ }
}

// ------------------------------------------------------- transcript sniffer

/** Read a Claude Code transcript (JSONL) and return { tier, escaped }.
 *  tier: from the LAST assistant entry carrying message.model.
 *  escaped: true if any user entry contains an escape token (the subagent's
 *  dispatch prompt is the first user message of its transcript).
 *  Fail-open: unreadable/unparseable => { tier: null, escaped: false }. */
export function sniffTranscript(transcriptPath) {
  const out = { tier: null, escaped: false };
  let raw = '';
  try { raw = fs.readFileSync(transcriptPath, 'utf8'); } catch { return out; }
  for (const line of raw.split('\n')) {
    if (!line.trim()) continue;
    let j;
    try { j = JSON.parse(line); } catch { continue; }
    const msg = j && j.message;
    if (!msg || typeof msg !== 'object') continue;
    if ((j.type === 'assistant' || msg.role === 'assistant') && typeof msg.model === 'string') {
      const t = tierOf(msg.model);
      if (t) out.tier = t; // keep the LAST seen — model can change mid-session
    }
    if (j.type === 'user' || msg.role === 'user') {
      const text = typeof msg.content === 'string'
        ? msg.content
        : Array.isArray(msg.content)
          ? msg.content.map(c => (c && typeof c.text === 'string') ? c.text : '').join('\n')
          : '';
      if (ESCAPE_TOKENS.some(tok => text.includes(tok))) out.escaped = true;
    }
  }
  return out;
}

// ------------------------------------------------------------ contract text

export function contractHeader(originalType, tier) {
  return (
    `[COGNITION CONTRACT v1] You are a COGNITION-tier agent` +
    (originalType ? ` acting in the role of '${originalType}'` : '') +
    ` (tier: ${tier}). You have NO file/exec/retrieval tools. Do not attempt ` +
    `Read/Write/Edit/Bash/Glob/Grep — they are stripped. Produce your ` +
    `technical output as a WORK-ORDER v1 (unified diff + command list + ` +
    `verify steps; schema in docs/spikes/tiered-cognition/DESIGN.md) and ` +
    `dispatch a Haiku executor agent to apply it, or return the work-order ` +
    `to your caller. All facts you need must arrive via your prompt or via ` +
    `Haiku courier briefs you dispatch.\n\n`
  );
}

// -------------------------------------------------------------- core policy

/**
 * Pure decision function (testable). payload = parsed hook stdin JSON.
 * opts = { agentsDir, stateRoot } (injectable for tests).
 * Returns { action, output } where output is the object to write to stdout
 * (or null for "no opinion").
 * action: 'pass' | 'strip' | 'escape' | 'deny' | 'allow'
 */
export function decide(payload, opts = {}) {
  const pass = { action: 'pass', output: null };
  if (!payload || typeof payload !== 'object') return pass;
  const toolName = payload.tool_name;

  // ---- LAYER 1: dispatch guard --------------------------------------
  if (DISPATCH_TOOLS.has(toolName)) {
    const input = payload.tool_input;
    if (!input || typeof input !== 'object') return pass; // fail-open
    const prompt = String(input.prompt || '');
    const type = String(input.subagent_type || input.agentType || '').toLowerCase();
    if (type === 'fork') return pass; // forks inherit parent context/model

    const agentsDir = opts.agentsDir || path.join(os.homedir(), '.claude', 'agents');
    // Tier resolution order: explicit model > agent-def frontmatter > default
    // haiku (the model-policy hook lands every other dispatch on haiku).
    const tier = tierOf(input.model) || tierFromAgentDef(type, agentsDir) || 'haiku';
    if (tier === 'haiku') return pass;

    if (ESCAPE_TOKENS.some(tok => prompt.includes(tok))) {
      logEscapeUse(payload, opts);
      return {
        action: 'escape',
        output: {
          systemMessage: `⛓  tier policy BYPASSED via escape token — recorded in state/${ESCAPE_LOG_NAME}`,
          hookSpecificOutput: {
            hookEventName: 'PreToolUse',
            permissionDecision: 'allow',
            permissionDecisionReason:
              `Tier policy BYPASSED via escape token: this ${toolName} dispatch ` +
              `keeps its full toolset on model "${input.model || '(default)'}". ` +
              `Use recorded in state/${ESCAPE_LOG_NAME}.`,
          },
        },
      };
    }

    return {
      action: 'strip',
      strippedTools: DENY_TOOLS,
      keptTools: KEEP_TOOLS,
      output: {
        systemMessage:
          `⛓  cognition-tier dispatch (${tier}) → tools stripped via '${SHIM_AGENT}' shim ` +
          `(kept: ${KEEP_TOOLS.join(', ')})`,
        suppressOutput: true,
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'allow',
          permissionDecisionReason:
            'Tier policy: cognition tiers (sonnet/opus/fable) are message-only; ' +
            'Haiku executors perform all I/O ([[ALLOW-TIER-TOOLS]] to override).',
          updatedInput: {
            ...input,
            subagent_type: SHIM_AGENT,
            prompt: contractHeader(type, tier) + prompt,
          },
        },
      },
    };
  }

  // ---- LAYER 2: call-time backstop ----------------------------------
  if (DENY_SET.has(toolName)) {
    const t = payload.transcript_path;
    if (!t || typeof t !== 'string') return pass; // fail-open
    const { tier, escaped } = sniffTranscript(t);
    if (tier === null) return pass; // unreadable/unknown transcript: fail-open, no opinion
    if (tier === 'haiku' || escaped) {
      return { action: 'allow', output: null }; // haiku substrate / escaped session
    }
    return {
      action: 'deny',
      output: {
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'deny',
          permissionDecisionReason:
            `Tier policy: this session runs on a cognition-tier model, which never ` +
            `touches files/exec directly. Do NOT retry ${toolName}. Instead emit a ` +
            `WORK-ORDER v1 (unified diff / command list / verify steps — schema in ` +
            `docs/spikes/tiered-cognition/DESIGN.md) and dispatch a Haiku executor ` +
            `agent to apply it and report back an EXEC-BRIEF.`,
        },
      },
    };
  }

  return pass; // tool not governed
}

// ----------------------------------------------------------------- plumbing

function readStdin(timeoutMs = STDIN_TIMEOUT_MS) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (v) => { if (!settled) { settled = true; clearTimeout(timer); resolve(v); } };
    const timer = setTimeout(() => finish(''), timeoutMs);
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => { data += c; });
    process.stdin.on('end', () => finish(data));
    process.stdin.on('error', () => finish(''));
  });
}

async function runAsHook() {
  const raw = await readStdin();
  let payload = null;
  try { payload = JSON.parse(raw); } catch { /* fail-open */ }
  const { output } = decide(payload);
  if (output) process.stdout.write(JSON.stringify(output) + '\n');
  process.exit(0);
}

// ----------------------------------------------------------------- selftest

function selfTest() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'tiercog-'));
  const agentsDir = path.join(tmp, 'agents');
  fs.mkdirSync(agentsDir);
  fs.writeFileSync(path.join(agentsDir, 'typescript-pro.md'),
    '---\nname: typescript-pro\ndescription: test fixture\nmodel: claude-sonnet-5\n---\nbody\n');
  fs.writeFileSync(path.join(agentsDir, 'hooktest-haiku.md'),
    '---\nname: hooktest-haiku\ndescription: test fixture\nmodel: haiku\n---\nbody\n');

  const mkTranscript = (name, lines) => {
    const p = path.join(tmp, name);
    fs.writeFileSync(p, lines.map(l => JSON.stringify(l)).join('\n') + '\n');
    return p;
  };
  const sonnetTx = mkTranscript('sonnet.jsonl', [
    { type: 'user', message: { role: 'user', content: 'implement the parser' } },
    { type: 'assistant', message: { role: 'assistant', model: 'claude-sonnet-5', content: [] } },
  ]);
  const haikuTx = mkTranscript('haiku.jsonl', [
    { type: 'user', message: { role: 'user', content: 'apply this work-order' } },
    { type: 'assistant', message: { role: 'assistant', model: 'claude-haiku-4-5', content: [] } },
  ]);
  const escapedTx = mkTranscript('escaped.jsonl', [
    { type: 'user', message: { role: 'user', content: [{ type: 'text', text: '[[ALLOW-NON-HAIKU]] mission spike, hands-on' }] } },
    { type: 'assistant', message: { role: 'assistant', model: 'claude-fable-5', content: [] } },
  ]);

  const opts = { agentsDir, stateRoot: tmp };
  const dispatch = (input) => ({ tool_name: 'Agent', tool_input: input, session_id: 's1', cwd: tmp });
  const call = (tool, tx) => ({ tool_name: tool, tool_input: { file_path: 'x' }, transcript_path: tx });

  let failures = 0;
  const check = (name, cond, detail) => {
    console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${name}${cond ? '' : '  <-- ' + (detail || '')}`);
    if (!cond) failures++;
  };

  console.log('LAYER 1 — dispatch guard');
  // 1. sonnet dispatch -> stripped via shim
  let r = decide(dispatch({ model: 'sonnet', prompt: 'design the schema', description: 'd' }), opts);
  check('sonnet dispatch is stripped', r.action === 'strip', `action=${r.action}`);
  const ui = r.output && r.output.hookSpecificOutput.updatedInput;
  check('  rewritten to shim agent type', !!ui && ui.subagent_type === SHIM_AGENT, JSON.stringify(ui));
  check('  contract header prepended', !!ui && ui.prompt.startsWith('[COGNITION CONTRACT v1]'));
  check('  original prompt preserved', !!ui && ui.prompt.endsWith('design the schema'));
  check('  all I/O+exec tools in stripped set',
    ['Read', 'Write', 'Edit', 'Bash', 'PowerShell', 'Glob', 'Grep', 'NotebookEdit', 'WebFetch']
      .every(t => r.strippedTools.includes(t)));
  check('  messaging/dispatch tools kept',
    ['Agent', 'SendMessage'].every(t => r.keptTools.includes(t)) &&
    r.keptTools.every(t => !r.strippedTools.includes(t)));

  // 2. opus + fable dispatches -> stripped
  r = decide(dispatch({ model: 'opus', prompt: 'p' }), opts);
  check('opus dispatch is stripped', r.action === 'strip', `action=${r.action}`);
  r = decide(dispatch({ model: 'fable', prompt: 'p' }), opts);
  check('fable dispatch is stripped', r.action === 'strip', `action=${r.action}`);

  // 3. haiku dispatch -> untouched
  r = decide(dispatch({ model: 'haiku', prompt: 'apply the patch' }), opts);
  check('haiku dispatch passes untouched', r.action === 'pass' && r.output === null, `action=${r.action}`);

  // 4. blank model, generic type -> defaults haiku (model-policy hook lands it there) -> untouched
  r = decide(dispatch({ prompt: 'p', subagent_type: 'general-purpose' }), opts);
  check('blank-model generic dispatch passes (defaults haiku)', r.action === 'pass', `action=${r.action}`);

  // 5. blank model, specialist type with sonnet frontmatter -> stripped
  r = decide(dispatch({ prompt: 'p', subagent_type: 'typescript-pro' }), opts);
  check('blank-model sonnet specialist is stripped', r.action === 'strip', `action=${r.action}`);

  // 6. blank model, haiku-frontmatter agent -> untouched
  r = decide(dispatch({ prompt: 'p', subagent_type: 'hooktest-haiku' }), opts);
  check('haiku-frontmatter agent passes', r.action === 'pass', `action=${r.action}`);

  // 7. escape-token dispatch -> allowed + audited
  r = decide(dispatch({ model: 'sonnet', prompt: '[[ALLOW-TIER-TOOLS]] hands-on mission' }), opts);
  check('escape-token dispatch keeps tools', r.action === 'escape', `action=${r.action}`);
  check('  no updatedInput on escape', !r.output.hookSpecificOutput.updatedInput);
  const logPath = path.join(tmp, 'state', ESCAPE_LOG_NAME);
  let audited = false;
  try { audited = fs.readFileSync(logPath, 'utf8').includes('tier_policy_escape'); } catch { }
  check('  escape use audited to state log', audited, logPath);

  // 8. legacy [[ALLOW-NON-HAIKU]] also escapes (migration grandfathering)
  r = decide(dispatch({ model: 'opus', prompt: '[[ALLOW-NON-HAIKU]] mission' }), opts);
  check('legacy ALLOW-NON-HAIKU token also escapes', r.action === 'escape', `action=${r.action}`);

  // 9. fork passes untouched
  r = decide(dispatch({ model: 'sonnet', prompt: 'p', subagent_type: 'fork' }), opts);
  check('fork dispatch passes untouched', r.action === 'pass', `action=${r.action}`);

  // 10. malformed payloads fail open
  check('malformed payload fails open', decide(null, opts).action === 'pass');
  check('missing tool_input fails open', decide({ tool_name: 'Agent' }, opts).action === 'pass');

  console.log('LAYER 2 — call-time backstop');
  // 11. Write/Bash under a sonnet transcript -> denied with redirect reason
  r = decide(call('Write', sonnetTx), opts);
  check('Write under sonnet session is DENIED', r.action === 'deny', `action=${r.action}`);
  check('  deny reason redirects to WORK-ORDER + Haiku executor',
    r.action === 'deny' && /WORK-ORDER/.test(r.output.hookSpecificOutput.permissionDecisionReason) &&
    r.output.hookSpecificOutput.permissionDecision === 'deny');
  r = decide(call('Bash', sonnetTx), opts);
  check('Bash under sonnet session is DENIED', r.action === 'deny', `action=${r.action}`);

  // 12. same tools under a haiku transcript -> allowed
  r = decide(call('Write', haikuTx), opts);
  check('Write under haiku session is allowed', r.action === 'allow', `action=${r.action}`);
  r = decide(call('Bash', haikuTx), opts);
  check('Bash under haiku session is allowed', r.action === 'allow', `action=${r.action}`);

  // 13. escaped fable session (this spike!) keeps its tools
  r = decide(call('Edit', escapedTx), opts);
  check('escape-token session keeps I/O tools', r.action === 'allow', `action=${r.action}`);

  // 14. missing/unreadable transcript fails open
  r = decide(call('Write', path.join(tmp, 'nope.jsonl')), opts);
  check('missing transcript fails open (pass)', r.action === 'pass', `action=${r.action}`);

  // 15. ungoverned tool passes
  r = decide({ tool_name: 'SendMessage', tool_input: {}, transcript_path: sonnetTx }, opts);
  check('ungoverned tool (SendMessage) passes', r.action === 'pass', `action=${r.action}`);

  console.log(failures === 0 ? '\nSELF-TEST: ALL PASS' : `\nSELF-TEST: ${failures} FAILURE(S)`);
  try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { }
  process.exit(failures === 0 ? 0 : 1);
}

// ----------------------------------------------------------------- dispatch

if (process.argv.includes('--self-test')) {
  selfTest();
} else {
  runAsHook();
}
