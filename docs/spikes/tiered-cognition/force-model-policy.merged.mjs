#!/usr/bin/env node
// force-model-policy.merged.mjs — STAGED CANDIDATE (wave 12). NOT ACTIVATED.
//
// This file is the wave-12 merge of two PreToolUse policies into ONE hook so
// that exactly one owner emits `updatedInput` on the `Agent|Task` matcher —
// resolving the wave-11 spike's top risk (FINDINGS.md risk 1: the live
// force-haiku-subagents.mjs and the spike's strip-tools-hook.mjs both rewrote
// the same dispatch with undefined merge order).
//
// It is a drop-in replacement candidate for:
//   ~/.claude/hooks/force-haiku-subagents.mjs        (the live model policy)
// merged with:
//   docs/spikes/tiered-cognition/strip-tools-hook.mjs (the spike tier policy)
// Activation is a deliberate later step — see ACTIVATION.md in this directory.
//
// ─── Decision pipeline (one pass, one updatedInput) ─────────────────────────
//
//   dispatch (Agent|Task)
//     │
//     ├─ [[ALLOW-NON-HAIKU]] in prompt → FULL bypass (model + tools), audited
//     │     to state/MODEL-POLICY-ESCAPES.log (+ TIER log when the kept model
//     │     is cognition-tier — migration grandfathering per DESIGN.md §2.4).
//     ├─ subagent_type fork            → pass (inherits parent, never rewritten)
//     ├─ subagent_type aesop-cognition → pass (already shimmed by dispatcher)
//     │
//     ├─ 1. MODEL POLICY (unchanged from the live hook):
//     │     • bash-pro → ALWAYS claude-sonnet-5 (hard user-ordered exception,
//     │       wins over FORCE_ALL_HAIKU; ALSO exempt from tool stripping —
//     │       its entire job is exec, a shimmed bash-pro is a contradiction).
//     │     • catalog specialist (~/.claude/agents/*.md, non-haiku frontmatter)
//     │       → its model (blank passes through to frontmatter; explicit
//     │       opus/fable capped to claude-sonnet-5 — hands-on opus/fable is
//     │       never a subagent; cognition opus/fable arrives via agent-def
//     │       frontmatter and is shimmed below).
//     │     • everything else → haiku. FORCE_ALL_HAIKU=1 → haiku for all
//     │       (except bash-pro).
//     │
//     ├─ 2. TIER POLICY (Layer 1, from the spike), computed on the FINAL
//     │     post-routing model — "model routing decides the tier; the same
//     │     decision then strips or keeps tools" (DESIGN.md §2.1(4)):
//     │     • tier haiku → pass with the model rewrite only.
//     │     • tier cognition (sonnet/opus/fable) AND family in
//     │       TIER_STRIP_SCOPE → rewrite subagent_type → 'aesop-cognition'
//     │       shim (message-only tools via its frontmatter), prepend the
//     │       [COGNITION CONTRACT v1] header naming the original role, and
//     │       preserve the effective model explicitly (the shim def carries
//     │       no model:).
//     │     • [[ALLOW-TIER-TOOLS]] in prompt → skip the strip ONLY (model
//     │       policy still applies), audited to state/TIER-POLICY-ESCAPES.log.
//     │
//     └─ 3. Emit ONE updatedInput carrying BOTH rewrites (or pass).
//
//   I/O tool call (Read/Write/Edit/Bash/…) — LAYER 2 call-time backstop:
//     Dormant unless TIER_ENFORCE=1 (staged OFF by default) AND the hook is
//     wired to those matchers in settings.json (it is not, today). When live:
//     transcript-sniffed cognition sessions are DENIED with a redirect-to-
//     WORK-ORDER reason; haiku / escaped sessions pass. Fail-open on any
//     unreadable transcript. Kept as the clearly-separable layer2Backstop().
//
// ─── Env knobs ───────────────────────────────────────────────────────────────
//   FORCE_ALL_HAIKU=1        force every dispatch (incl. specialists) to haiku
//                            (bash-pro excepted) — unchanged from live hook.
//   TIER_STRIP_SCOPE         which cognition families get shimmed:
//                            'opus-fable' (DEFAULT — FINDINGS.md Phase A: no
//                            specialist prompt loss), 'all' (Phase B: sonnet
//                            specialists too), 'off' (model policy only).
//   TIER_ENFORCE=1           arm the Layer-2 call-time backstop (DEFAULT OFF).
//   AESOP_ROOT               state root for audit logs (default ~/aesop).
//
// Reliability: fail-open everywhere, stdin raced against a 2s timer, an
// escape-hatch use is NEVER silent (transcript reason + JSON-line audit).
// Self-test: `node force-model-policy.merged.mjs --self-test` (no stdin;
// builds fixtures in a temp dir; exit 0 on PASS / 1 on FAIL).

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

// ---------------------------------------------------------------- constants

export const ESCAPE_MODEL = '[[ALLOW-NON-HAIKU]]';   // full bypass (model + tools, grandfathered)
export const ESCAPE_TIER = '[[ALLOW-TIER-TOOLS]]';   // tool-strip bypass only
export const ESCAPE_TOKENS = [ESCAPE_TIER, ESCAPE_MODEL];
export const SHIM_AGENT = 'aesop-cognition';
export const MODEL_ESCAPE_LOG = 'MODEL-POLICY-ESCAPES.log';
export const TIER_ESCAPE_LOG = 'TIER-POLICY-ESCAPES.log';
export const SONNET_PIN = 'claude-sonnet-5';
const STDIN_TIMEOUT_MS = 2000;

// Cognition tiers KEEP exactly these (reason + message + dispatch):
export const KEEP_TOOLS = ['Agent', 'SendMessage', 'TaskStop', 'Monitor'];

// Cognition tiers are DENIED all I/O + exec + retrieval (Haiku's job).
// Doubles as the Layer-2 matcher set.
export const DENY_TOOLS = [
  'Read', 'Write', 'Edit', 'MultiEdit', 'NotebookEdit',
  'Bash', 'PowerShell', 'BashOutput', 'KillShell',
  'Glob', 'Grep', 'WebFetch', 'WebSearch',
  'Skill', 'Artifact', 'ToolSearch', 'EnterWorktree', 'ExitWorktree',
];

const DISPATCH_TOOLS = new Set(['Agent', 'Task']);
const DENY_SET = new Set(DENY_TOOLS);

// ------------------------------------------------------------------ helpers

function envOf(opts) { return (opts && opts.env) || process.env; }

/** State root, consistent with aesop's `${AESOP_ROOT:-$HOME/aesop}/state/`. */
function stateDir(opts) {
  const root = (opts && opts.stateRoot) || envOf(opts).AESOP_ROOT || path.join(os.homedir(), 'aesop');
  return path.join(root, 'state');
}

/** Best-effort JSON-line audit record; an unwritable log never blocks. */
function audit(logName, event, payload, extra, opts) {
  try {
    const dir = stateDir(opts);
    fs.mkdirSync(dir, { recursive: true });
    const input = payload.tool_input || {};
    const rec = {
      ts: new Date().toISOString(),
      event,
      tool: payload.tool_name,
      session_id: typeof payload.session_id === 'string' ? payload.session_id : null,
      cwd: typeof payload.cwd === 'string' ? payload.cwd : null,
      description: typeof input.description === 'string' ? input.description : null,
      requested_model: typeof input.model === 'string' ? input.model : null,
      prompt_head: typeof input.prompt === 'string' ? input.prompt.slice(0, 200) : null,
      ...extra,
    };
    fs.appendFileSync(path.join(dir, logName), JSON.stringify(rec) + '\n');
  } catch { /* audit is best-effort; never block the harness */ }
}

// --------------------------------------------------------------- tier logic

/** Model family: 'haiku' | 'sonnet' | 'opus' | 'fable' | null (unknown). */
export function modelFamily(model) {
  const m = String(model || '').toLowerCase();
  if (!m) return null;
  if (m.includes('haiku')) return 'haiku';
  if (m.includes('sonnet')) return 'sonnet';
  if (m.includes('opus')) return 'opus';
  if (m.includes('fable')) return 'fable';
  return null;
}

/** Tier of a model string: 'haiku' | 'cognition' | null (no opinion). */
export function tierOf(model) {
  const f = modelFamily(model);
  if (!f) return null;
  return f === 'haiku' ? 'haiku' : 'cognition';
}

/** Look up an installed agent definition by type (basename or `name:` field).
 *  Returns { found, model } where model is the frontmatter `model:` string
 *  or null. Fail-open: unreadable dir => { found: false, model: null }. */
export function agentDefInfo(type, agentsDir) {
  const out = { found: false, model: null };
  if (!type) return out;
  let files = [];
  try { files = fs.readdirSync(agentsDir).filter(f => f.endsWith('.md')); } catch { return out; }
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
      out.found = true;
      const mm = head.match(/^model:\s*(.+)$/m);
      if (mm) out.model = mm[1].trim();
      return out;
    }
  }
  return out;
}

/** Which cognition families get shimmed. Default 'opus-fable' = FINDINGS.md
 *  Phase A (no sonnet-specialist prompt loss). 'all' = Phase B. 'off' = model
 *  policy only. */
export function stripScope(opts) {
  const v = String(envOf(opts).TIER_STRIP_SCOPE || 'opus-fable').toLowerCase();
  if (v === 'off' || v === 'none') return new Set();
  if (v === 'all') return new Set(['sonnet', 'opus', 'fable']);
  return new Set(['opus', 'fable']);
}

export function contractHeader(originalType, family) {
  return (
    `[COGNITION CONTRACT v1] You are a COGNITION-tier agent` +
    (originalType ? ` acting in the role of '${originalType}'` : '') +
    ` (model family: ${family}). You have NO file/exec/retrieval tools. Do not ` +
    `attempt Read/Write/Edit/Bash/Glob/Grep — they are stripped. Produce your ` +
    `technical output as a WORK-ORDER v1 (unified diff + command list + ` +
    `verify steps; schema in docs/spikes/tiered-cognition/DESIGN.md) and ` +
    `dispatch a Haiku executor agent to apply it, or return the work-order ` +
    `to your caller. All facts you need must arrive via your prompt or via ` +
    `Haiku courier briefs you dispatch.\n\n`
  );
}

// ------------------------------------------------------- transcript sniffer

/** Read a Claude Code transcript (JSONL) → { tier, escaped }.
 *  tier: from the LAST assistant entry carrying message.model (robust to
 *  mid-session model switches). escaped: any user entry contains an escape
 *  token (a subagent's dispatch prompt is its first user message).
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
      if (t) out.tier = t;
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

// -------------------------------------------------------------- core policy

/**
 * Pure decision function (testable). payload = parsed hook stdin JSON.
 * opts = { agentsDir, stateRoot, env } — all injectable for tests.
 * Returns { action, output } where output is the object to write to stdout
 * (null = default allow, no opinion).
 * action: 'pass' | 'route' | 'strip' | 'route+strip' | 'escape'
 *       | 'escape-tier' | 'allow' | 'deny'
 */
export function decide(payload, opts = {}) {
  const pass = { action: 'pass', output: null };
  if (!payload || typeof payload !== 'object') return pass;
  const toolName = payload.tool_name;
  if (DISPATCH_TOOLS.has(toolName)) return dispatchGuard(payload, opts);
  if (DENY_SET.has(toolName)) return layer2Backstop(payload, opts);
  return pass; // tool not governed
}

// ---- LAYER 1 + MODEL POLICY: the single updatedInput owner ----------------

function dispatchGuard(payload, opts) {
  const pass = { action: 'pass', output: null };
  const input = payload.tool_input;
  // Timeout / empty / malformed payload: fail-open, and NEVER emit updatedInput
  // built from a missing tool_input (that would wipe the real dispatch input).
  if (!input || typeof input !== 'object') return pass;

  const model = String(input.model || '').toLowerCase();
  const prompt = String(input.prompt || '');
  const type = String(input.subagent_type || input.agentType || '').toLowerCase();
  const agentsDir = opts.agentsDir || path.join(os.homedir(), '.claude', 'agents');

  // FULL bypass: [[ALLOW-NON-HAIKU]] keeps model AND (grandfathered) tools.
  // Never silent — audited to the model log, plus the tier log when the kept
  // model is cognition-tier (DESIGN.md §2.4 migration grandfathering).
  if (prompt.includes(ESCAPE_MODEL)) {
    audit(MODEL_ESCAPE_LOG, 'model_policy_escape', payload, { via: ESCAPE_MODEL }, opts);
    if (tierOf(model) === 'cognition') {
      audit(TIER_ESCAPE_LOG, 'tier_policy_escape', payload,
        { via: `${ESCAPE_MODEL} (grandfathered: tools retained)` }, opts);
    }
    return {
      action: 'escape',
      output: {
        systemMessage: `⛓  model+tier policy BYPASSED via ${ESCAPE_MODEL} — recorded in state/${MODEL_ESCAPE_LOG}`,
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'allow',
          permissionDecisionReason:
            `Model policy BYPASSED via ${ESCAPE_MODEL} escape hatch: this ` +
            `${payload.tool_name || 'Agent'} dispatch keeps model ` +
            `"${typeof input.model === 'string' && input.model ? input.model : '(default)'}" ` +
            `and its full toolset (grandfathered). Use recorded in state/${MODEL_ESCAPE_LOG}.`,
        },
      },
    };
  }

  if (type === 'fork') return pass;       // forks inherit parent model/context
  if (type === SHIM_AGENT) return pass;   // already cognition-shimmed by the dispatcher

  // ---------------- 1. MODEL POLICY: resolve the final model ---------------
  let finalModel = model;      // '' = inherit / frontmatter pass-through
  let modelChanged = false;
  let modelWhy = null;
  let stripExempt = false;     // executor-class agents are never shimmed
  let isSpecialist = false;
  let defModel = null;

  if (type === 'bash-pro') {
    // Hard exception (user-ordered 2026-07-13): bash work degrades badly on
    // haiku — always Sonnet 5, wins over FORCE_ALL_HAIKU. bash-pro exists to
    // EXECUTE, so it is also exempt from the cognition shim.
    stripExempt = true;
    if (model !== SONNET_PIN) {
      finalModel = SONNET_PIN;
      modelChanged = true;
      modelWhy = `bash-pro always runs Sonnet 5 (was: ${model || 'inherit'})`;
    }
  } else {
    const forceAll = envOf(opts).FORCE_ALL_HAIKU === '1';
    const def = agentDefInfo(type, agentsDir);
    defModel = def.model;
    const isHaikuDef = !!def.model && def.model.toLowerCase().includes('haiku');
    isSpecialist = !forceAll && !!type && def.found && !isHaikuDef;

    if (isSpecialist) {
      const fam = modelFamily(model);
      if (fam === 'opus' || fam === 'fable') {
        // Hands-on opus/fable is never a subagent — cap explicit requests to
        // Sonnet 5. (Cognition-tier opus/fable arrives via agent-def
        // frontmatter and is shimmed message-only below.)
        finalModel = SONNET_PIN;
        modelChanged = true;
        modelWhy = `specialist '${type}' capped to Sonnet 5 (was: ${model})`;
      }
      // blank / explicit sonnet / explicit haiku pass through unchanged
    } else if (isHaikuDef && !model) {
      // haiku-frontmatter agent, blank model: the definition already lands it
      // on haiku — no rewrite needed.
    } else if (!model.startsWith('haiku')) {
      // Non-specialist (generic dispatch OR a specialist's own fan-out) → Haiku.
      finalModel = 'haiku';
      modelChanged = true;
      modelWhy = `non-specialist dispatch (was: ${model || 'inherit'})`;
    }
  }

  // ------------- 2. TIER POLICY: tier of the POST-routing model ------------
  // Effective model: the explicit final model; else the agent-def frontmatter;
  // a model-less specialist def is treated as sonnet (the live hook's model:
  // claude-sonnet-5 assumption); everything else defaults haiku.
  const effective = finalModel || defModel || (isSpecialist ? SONNET_PIN : '');
  const tier = tierOf(effective) || 'haiku';
  const family = modelFamily(effective) || 'haiku';

  let strip = tier === 'cognition' && !stripExempt && stripScope(opts).has(family);
  let tierEscaped = false;
  if (strip && prompt.includes(ESCAPE_TIER)) {
    // Tool-strip bypass ONLY — the model policy above still applies.
    strip = false;
    tierEscaped = true;
    audit(TIER_ESCAPE_LOG, 'tier_policy_escape', payload, { via: ESCAPE_TIER }, opts);
  }

  // ------------------- 3. compose ONE updatedInput -------------------------
  if (!modelChanged && !strip) {
    if (tierEscaped) {
      return {
        action: 'escape-tier',
        output: {
          systemMessage: `⛓  tier strip BYPASSED via ${ESCAPE_TIER} — recorded in state/${TIER_ESCAPE_LOG}`,
          hookSpecificOutput: {
            hookEventName: 'PreToolUse',
            permissionDecision: 'allow',
            permissionDecisionReason:
              `Tier policy BYPASSED via ${ESCAPE_TIER}: this cognition-tier ` +
              `(${family}) dispatch keeps its full toolset. Use recorded in ` +
              `state/${TIER_ESCAPE_LOG}.`,
          },
        },
      };
    }
    return pass;
  }

  const updated = { ...input };
  const notes = [];
  if (modelChanged) {
    updated.model = finalModel;
    notes.push(`model → ${finalModel} (${modelWhy})`);
  }
  if (strip) {
    updated.subagent_type = SHIM_AGENT;
    updated.prompt = contractHeader(type, family) + prompt;
    // The shim def carries no model: — keep the effective cognition model
    // explicit so the rewrite never silently changes the tier.
    if (!updated.model) updated.model = defModel || SONNET_PIN;
    notes.push(`cognition tier (${family}) → tools stripped via '${SHIM_AGENT}' shim (kept: ${KEEP_TOOLS.join(', ')})`);
  }
  if (tierEscaped) notes.push(`tier strip BYPASSED via ${ESCAPE_TIER} (audited)`);

  return {
    action: strip ? (modelChanged ? 'route+strip' : 'strip') : 'route',
    strippedTools: strip ? DENY_TOOLS : undefined,
    keptTools: strip ? KEEP_TOOLS : undefined,
    output: {
      systemMessage: `⛓  subagent policy: ${notes.join('; ')}`,
      suppressOutput: true,
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'allow',
        permissionDecisionReason:
          'Merged policy: specialists=Sonnet, bash-pro=Sonnet, everything else=Haiku ' +
          `(${ESCAPE_MODEL} to override); cognition tiers (scope: ` +
          `${[...stripScope(opts)].join('/') || 'off'}) are message-only via the ` +
          `'${SHIM_AGENT}' shim (${ESCAPE_TIER} to override).`,
        updatedInput: updated,
      },
    },
  };
}

// ---- LAYER 2: call-time backstop (clearly separable; staged OFF) ----------
// Only meaningful once (a) settings.json wires this hook to the DENY_TOOLS
// matchers AND (b) TIER_ENFORCE=1. Until both, every call passes untouched.
// See FINDINGS.md condition 2 (validate transcript sniffing on real
// sidechains) and risk 4 (main-thread carve-out) before arming.

export function layer2Backstop(payload, opts = {}) {
  const pass = { action: 'pass', output: null };
  if (envOf(opts).TIER_ENFORCE !== '1') return pass; // staged: default OFF

  const t = payload.transcript_path;
  if (!t || typeof t !== 'string') return pass; // fail-open
  const { tier, escaped } = sniffTranscript(t);
  if (tier === null) return pass; // unreadable/unknown transcript: no opinion
  if (tier === 'haiku' || escaped) return { action: 'allow', output: null };

  return {
    action: 'deny',
    output: {
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason:
          `Tier policy: this session runs on a cognition-tier model, which never ` +
          `touches files/exec directly. Do NOT retry ${payload.tool_name}. Instead emit a ` +
          `WORK-ORDER v1 (unified diff / command list / verify steps — schema in ` +
          `docs/spikes/tiered-cognition/DESIGN.md) and dispatch a Haiku executor ` +
          `agent to apply it and report back an EXEC-BRIEF.`,
      },
    },
  };
}

// ----------------------------------------------------------------- plumbing

/** Read stdin raced against a timer: a never-closing pipe must not hang
 *  Agent/Task dispatch. On timeout, resolve '' (fail-open, no rewrite). */
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
  try { payload = JSON.parse(raw || '{}'); } catch { /* fail-open */ }
  const { output } = decide(payload);
  process.stdout.write(JSON.stringify(output || {
    suppressOutput: true,
    hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'allow' },
  }));
  process.exit(0);
}

// ----------------------------------------------------------------- selftest

function selfTest() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'mergedpolicy-'));
  const agentsDir = path.join(tmp, 'agents');
  fs.mkdirSync(agentsDir);
  fs.writeFileSync(path.join(agentsDir, 'typescript-pro.md'),
    '---\nname: typescript-pro\ndescription: test fixture\nmodel: claude-sonnet-5\n---\nbody\n');
  fs.writeFileSync(path.join(agentsDir, 'hooktest-haiku.md'),
    '---\nname: hooktest-haiku\ndescription: test fixture\nmodel: haiku\n---\nbody\n');
  fs.writeFileSync(path.join(agentsDir, 'plan-architect.md'),
    '---\nname: plan-architect\ndescription: test fixture\nmodel: claude-opus-4-5\n---\nbody\n');
  fs.writeFileSync(path.join(agentsDir, 'mission-cognition.md'),
    '---\nname: mission-cognition\ndescription: test fixture\nmodel: fable\n---\nbody\n');
  fs.writeFileSync(path.join(agentsDir, 'bash-pro.md'),
    '---\nname: bash-pro\ndescription: test fixture\nmodel: claude-sonnet-5\n---\nbody\n');

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
    { type: 'user', message: { role: 'user', content: [{ type: 'text', text: '[[ALLOW-NON-HAIKU]] mission, hands-on' }] } },
    { type: 'assistant', message: { role: 'assistant', model: 'claude-fable-5', content: [] } },
  ]);

  // Baseline opts: isolated env so ambient FORCE_ALL_HAIKU/TIER_* can't skew.
  const base = { agentsDir, stateRoot: tmp, env: {} };
  const withEnv = (env) => ({ ...base, env });
  const dispatch = (input) => ({ tool_name: 'Agent', tool_input: input, session_id: 's1', cwd: tmp });
  const call = (tool, tx) => ({ tool_name: tool, tool_input: { file_path: 'x' }, transcript_path: tx });
  const ui = (r) => r.output && r.output.hookSpecificOutput && r.output.hookSpecificOutput.updatedInput;

  let failures = 0;
  const check = (name, cond, detail) => {
    console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${name}${cond ? '' : '  <-- ' + (detail || '')}`);
    if (!cond) failures++;
  };

  console.log('MODEL POLICY (live-hook parity)');
  // 1. generic/untyped dispatch → haiku
  let r = decide(dispatch({ prompt: 'p', description: 'd' }), base);
  check('untyped dispatch forced to haiku', r.action === 'route' && ui(r).model === 'haiku', JSON.stringify(ui(r)));
  check('  no shim on a haiku-routed dispatch', ui(r).subagent_type === undefined && ui(r).prompt === 'p');
  // 2. generic dispatch requesting cognition models → still haiku
  r = decide(dispatch({ model: 'sonnet', prompt: 'p' }), base);
  check('generic sonnet request forced to haiku', r.action === 'route' && ui(r).model === 'haiku');
  r = decide(dispatch({ model: 'fable', prompt: 'p' }), base);
  check('generic fable request forced to haiku', r.action === 'route' && ui(r).model === 'haiku');
  // 3. explicit haiku passes
  r = decide(dispatch({ model: 'haiku', prompt: 'p' }), base);
  check('explicit haiku passes untouched', r.action === 'pass' && r.output === null, `action=${r.action}`);
  // 4. bash-pro → ALWAYS sonnet-5, never shimmed
  r = decide(dispatch({ prompt: 'p', subagent_type: 'bash-pro' }), base);
  check('bash-pro pinned to claude-sonnet-5', r.action === 'route' && ui(r).model === SONNET_PIN, JSON.stringify(ui(r)));
  r = decide(dispatch({ prompt: 'p', subagent_type: 'bash-pro' }), withEnv({ TIER_STRIP_SCOPE: 'all' }));
  check('bash-pro NEVER shimmed (even scope=all)', r.action === 'route' && ui(r).model === SONNET_PIN && ui(r).subagent_type === 'bash-pro');
  r = decide(dispatch({ model: SONNET_PIN, prompt: 'p', subagent_type: 'bash-pro' }), base);
  check('bash-pro already sonnet-5 passes', r.action === 'pass', `action=${r.action}`);
  r = decide(dispatch({ prompt: 'p', subagent_type: 'bash-pro' }), withEnv({ FORCE_ALL_HAIKU: '1' }));
  check('bash-pro wins over FORCE_ALL_HAIKU', r.action === 'route' && ui(r).model === SONNET_PIN);
  // 5. specialist → its model (blank passes through to frontmatter)
  r = decide(dispatch({ prompt: 'p', subagent_type: 'typescript-pro' }), base);
  check('sonnet specialist keeps its model (default scope)', r.action === 'pass', `action=${r.action}`);
  r = decide(dispatch({ model: 'opus', prompt: 'p', subagent_type: 'typescript-pro' }), base);
  check('specialist explicit opus capped to sonnet-5', r.action === 'route' && ui(r).model === SONNET_PIN);
  check('  cap alone does not shim (default scope)', ui(r).subagent_type === 'typescript-pro', ui(r).subagent_type);
  // 6. haiku-frontmatter agent untouched
  r = decide(dispatch({ prompt: 'p', subagent_type: 'hooktest-haiku' }), base);
  check('haiku-frontmatter agent passes', r.action === 'pass', `action=${r.action}`);
  // 7. FORCE_ALL_HAIKU flattens specialists
  r = decide(dispatch({ prompt: 'p', subagent_type: 'typescript-pro' }), withEnv({ FORCE_ALL_HAIKU: '1' }));
  check('FORCE_ALL_HAIKU flattens specialist to haiku', r.action === 'route' && ui(r).model === 'haiku');
  // 8. [[ALLOW-NON-HAIKU]] full bypass + audit
  r = decide(dispatch({ model: 'opus', prompt: `${ESCAPE_MODEL} mission`, description: 'm' }), base);
  check('ALLOW-NON-HAIKU bypasses (no rewrite)', r.action === 'escape' && !ui(r), `action=${r.action}`);
  let logTxt = '';
  try { logTxt = fs.readFileSync(path.join(tmp, 'state', MODEL_ESCAPE_LOG), 'utf8'); } catch { }
  check('  audited to MODEL-POLICY-ESCAPES.log', logTxt.includes('model_policy_escape'));
  try { logTxt = fs.readFileSync(path.join(tmp, 'state', TIER_ESCAPE_LOG), 'utf8'); } catch { logTxt = ''; }
  check('  grandfathered tier escape audited too', logTxt.includes('grandfathered'));
  // 9. fork untouched
  r = decide(dispatch({ model: 'sonnet', prompt: 'p', subagent_type: 'fork' }), base);
  check('fork dispatch passes untouched', r.action === 'pass', `action=${r.action}`);
  // 10. malformed payloads fail open
  check('malformed payload fails open', decide(null, base).action === 'pass');
  check('missing tool_input fails open', decide({ tool_name: 'Agent' }, base).action === 'pass');

  console.log('TIER POLICY (Layer 1, post-routing tier)');
  // 11. opus-frontmatter def, blank model → shimmed, model preserved explicitly
  r = decide(dispatch({ prompt: 'design it', subagent_type: 'plan-architect', description: 'd' }), base);
  check('opus-frontmatter dispatch shimmed (default scope)', r.action === 'strip', `action=${r.action}`);
  check('  rewritten to shim agent type', ui(r) && ui(r).subagent_type === SHIM_AGENT, JSON.stringify(ui(r)));
  check('  contract header prepended', ui(r) && ui(r).prompt.startsWith('[COGNITION CONTRACT v1]'));
  check('  original role named in header', ui(r) && ui(r).prompt.includes("'plan-architect'"));
  check('  original prompt preserved', ui(r) && ui(r).prompt.endsWith('design it'));
  check('  effective model kept explicit', ui(r) && ui(r).model === 'claude-opus-4-5', ui(r) && ui(r).model);
  // 12. fable-frontmatter def → shimmed
  r = decide(dispatch({ prompt: 'p', subagent_type: 'mission-cognition' }), base);
  check('fable-frontmatter dispatch shimmed', r.action === 'strip' && ui(r).model === 'fable');
  // 13. stripped/kept tool sets
  check('  I/O+exec+retrieval all in stripped set',
    ['Read', 'Write', 'Edit', 'Bash', 'PowerShell', 'Glob', 'Grep', 'NotebookEdit', 'WebFetch', 'Skill']
      .every(t => r.strippedTools.includes(t)));
  check('  messaging/dispatch tools kept, disjoint',
    ['Agent', 'SendMessage', 'TaskStop', 'Monitor'].every(t => r.keptTools.includes(t)) &&
    r.keptTools.every(t => !r.strippedTools.includes(t)));
  // 14. sonnet specialists: untouched in Phase A, shimmed in Phase B (scope=all)
  r = decide(dispatch({ prompt: 'p', subagent_type: 'typescript-pro' }), withEnv({ TIER_STRIP_SCOPE: 'all' }));
  check('scope=all shims sonnet specialist', r.action === 'strip' && ui(r).subagent_type === SHIM_AGENT);
  check('  frontmatter sonnet model kept explicit', ui(r).model === SONNET_PIN, ui(r).model);
  // 15. scope=off disables stripping entirely
  r = decide(dispatch({ prompt: 'p', subagent_type: 'plan-architect' }), withEnv({ TIER_STRIP_SCOPE: 'off' }));
  check('scope=off leaves cognition dispatch untouched', r.action === 'pass', `action=${r.action}`);
  // 16. [[ALLOW-TIER-TOOLS]] bypasses the strip only
  r = decide(dispatch({ prompt: `${ESCAPE_TIER} hands-on`, subagent_type: 'plan-architect' }), base);
  check('ALLOW-TIER-TOOLS keeps tools (no shim)', r.action === 'escape-tier' && !ui(r), `action=${r.action}`);
  try { logTxt = fs.readFileSync(path.join(tmp, 'state', TIER_ESCAPE_LOG), 'utf8'); } catch { logTxt = ''; }
  check('  tier escape audited', logTxt.includes(ESCAPE_TIER));
  // 17. ALLOW-TIER-TOOLS does NOT bypass the model policy
  r = decide(dispatch({ model: 'opus', prompt: `${ESCAPE_TIER} p`, subagent_type: 'typescript-pro' }),
    withEnv({ TIER_STRIP_SCOPE: 'all' }));
  check('ALLOW-TIER-TOOLS still gets model-capped', r.action === 'route' && ui(r).model === SONNET_PIN);
  check('  but keeps its own agent type + prompt', ui(r).subagent_type === 'typescript-pro' && ui(r).prompt === `${ESCAPE_TIER} p`);
  // 18. dispatch already typed to the shim is idempotent
  r = decide(dispatch({ model: 'opus', prompt: 'p', subagent_type: SHIM_AGENT }), base);
  check('dispatch typed aesop-cognition passes (no double-shim)', r.action === 'pass', `action=${r.action}`);

  console.log('COMPOSITION — both policies in ONE updatedInput');
  // 19. specialist + explicit fable + scope=all: model policy caps to sonnet-5
  //     AND tier policy shims — one updatedInput carries BOTH rewrites.
  r = decide(dispatch({ model: 'fable', prompt: 'compose me', subagent_type: 'typescript-pro', description: 'keep-me' }),
    withEnv({ TIER_STRIP_SCOPE: 'all' }));
  check('composed action is route+strip', r.action === 'route+strip', `action=${r.action}`);
  const u = ui(r);
  check('  ONE updatedInput object', !!u && r.output.hookSpecificOutput.updatedInput === u);
  check('  model policy present (fable→sonnet-5 cap)', u && u.model === SONNET_PIN, u && u.model);
  check('  tier policy present (shim + contract header)',
    u && u.subagent_type === SHIM_AGENT && u.prompt.startsWith('[COGNITION CONTRACT v1]') && u.prompt.endsWith('compose me'));
  check('  untouched fields survive the merge', u && u.description === 'keep-me');
  check('  systemMessage announces BOTH rewrites',
    /model →/.test(r.output.systemMessage) && /shim/.test(r.output.systemMessage), r.output.systemMessage);

  console.log('LAYER 2 — call-time backstop (TIER_ENFORCE-gated)');
  // 20. default OFF: dormant even for a cognition transcript
  r = decide(call('Write', sonnetTx), base);
  check('TIER_ENFORCE unset: backstop dormant (pass)', r.action === 'pass', `action=${r.action}`);
  const armed = withEnv({ TIER_ENFORCE: '1' });
  // 21. armed: cognition session denied with work-order redirect
  r = decide(call('Write', sonnetTx), armed);
  check('armed: Write under sonnet session DENIED', r.action === 'deny', `action=${r.action}`);
  check('  deny reason redirects to WORK-ORDER + Haiku executor',
    r.action === 'deny' && /WORK-ORDER/.test(r.output.hookSpecificOutput.permissionDecisionReason) &&
    r.output.hookSpecificOutput.permissionDecision === 'deny');
  r = decide(call('Bash', sonnetTx), armed);
  check('armed: Bash under sonnet session DENIED', r.action === 'deny', `action=${r.action}`);
  // 22. armed: haiku substrate + escaped sessions allowed
  r = decide(call('Write', haikuTx), armed);
  check('armed: Write under haiku session allowed', r.action === 'allow', `action=${r.action}`);
  r = decide(call('Edit', escapedTx), armed);
  check('armed: escape-token session keeps I/O tools', r.action === 'allow', `action=${r.action}`);
  // 23. armed: fail-open on missing transcript; ungoverned tools pass
  r = decide(call('Write', path.join(tmp, 'nope.jsonl')), armed);
  check('armed: missing transcript fails open', r.action === 'pass', `action=${r.action}`);
  r = decide({ tool_name: 'SendMessage', tool_input: {}, transcript_path: sonnetTx }, armed);
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
