#!/usr/bin/env node
// force-model-policy.mjs — Claude Code PreToolUse hook enforcing the
// "subagents are always Haiku" cardinal rule as versioned, executable policy.
//
// Wire it in settings.json under hooks.PreToolUse with matcher "Agent|Task"
// (see docs/HOOK-INSTALL.md). For every subagent dispatch:
//
//   - model absent or non-compliant  -> rewritten to the policy model ("haiku",
//     or aesop.config.json cardinal_rules.subagent_model when present)
//   - prompt contains [[ALLOW-NON-HAIKU]] -> deliberate escape hatch: input is
//     left untouched, but the bypass is announced via permissionDecisionReason
//     (visible in the transcript) AND appended as a JSON-line audit record to
//     ${AESOP_ROOT:-~/aesop}/state/MODEL-POLICY-ESCAPES.log so every use is
//     reviewable — prompts are untrusted text and can smuggle the marker.
//   - anything else (compliant, other tools, malformed input) -> no output
//
// Output contract source: Claude Code hooks reference ("PreToolUse Decision
// Control", https://docs.anthropic.com/en/docs/claude-code/hooks) — a hook may
// emit on stdout:
//   {"hookSpecificOutput":{"hookEventName":"PreToolUse",
//     "permissionDecision":"allow","updatedInput":{...}}}
// where updatedInput replaces tool_input for the dispatched call. Emitting
// nothing (exit 0) means "no opinion" and the call proceeds unchanged.
//
// Reliability rule: this hook NEVER crashes the harness. Any parse or IO
// failure results in no output and exit 0 (fail-open), and nothing from the
// payload is ever logged on failure paths. stdin is raced against a 2s timer
// so a never-closing pipe cannot hang Agent/Task dispatch (fail-open, no
// rewrite). The only deliberate exception to "log nothing" is the escape-hatch
// audit record above.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const ESCAPE_HATCH = '[[ALLOW-NON-HAIKU]]';
const DEFAULT_MODEL = 'haiku';
const GOVERNED_TOOLS = new Set(['Agent', 'Task']);
const STDIN_TIMEOUT_MS = 2000;
const ESCAPE_LOG_NAME = 'MODEL-POLICY-ESCAPES.log';

/** State root, consistent with the repo's resolution pattern
 *  (`${AESOP_ROOT:-$HOME/aesop}/state/` — see hooks/pre-push-policy.sh). */
function stateDir() {
  const root = process.env.AESOP_ROOT || path.join(os.homedir(), 'aesop');
  return path.join(root, 'state');
}

/** Append a JSON-line audit record for an escape-hatch use. Best-effort:
 *  an unwritable log never blocks the dispatch (fail-open). */
function logEscapeUse(payload) {
  try {
    const dir = stateDir();
    fs.mkdirSync(dir, { recursive: true });
    const input = payload.tool_input || {};
    const rec = {
      ts: new Date().toISOString(),
      event: 'model_policy_escape',
      tool: payload.tool_name,
      session_id: typeof payload.session_id === 'string' ? payload.session_id : null,
      cwd: typeof payload.cwd === 'string' ? payload.cwd : null,
      description: typeof input.description === 'string' ? input.description : null,
      requested_model: typeof input.model === 'string' ? input.model : null,
      prompt_head: typeof input.prompt === 'string' ? input.prompt.slice(0, 200) : null
    };
    fs.appendFileSync(path.join(dir, ESCAPE_LOG_NAME), JSON.stringify(rec) + '\n');
  } catch {
    // audit logging is best-effort; never block or crash the harness
  }
}

/** Resolve the policy model: aesop.config.json cardinal_rules.subagent_model,
 *  looked up in $AESOP_ROOT then cwd; falls back to "haiku". */
function policyModel() {
  const roots = [process.env.AESOP_ROOT, process.cwd()].filter(Boolean);
  for (const root of roots) {
    try {
      const cfg = JSON.parse(fs.readFileSync(path.join(root, 'aesop.config.json'), 'utf8'));
      const m = cfg && cfg.cardinal_rules && cfg.cardinal_rules.subagent_model;
      if (typeof m === 'string' && m.trim()) return m.trim();
    } catch {
      // missing or unreadable config in this root — try the next one
    }
  }
  return DEFAULT_MODEL;
}

/** Read stdin raced against a timer: a pipe that never closes must not hang
 *  Agent/Task dispatch. On timeout, resolve '' (fail-open, no rewrite). */
function readStdin(timeoutMs = STDIN_TIMEOUT_MS) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(value);
    };
    const timer = setTimeout(() => finish(''), timeoutMs);
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { data += chunk; });
    process.stdin.on('end', () => finish(data));
    process.stdin.on('error', () => finish(''));
  });
}

async function main() {
  const raw = await readStdin();

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    return; // malformed input: fail-open, no output, log nothing
  }
  if (!payload || typeof payload !== 'object') return;
  if (!GOVERNED_TOOLS.has(payload.tool_name)) return;

  const input = payload.tool_input;
  if (!input || typeof input !== 'object') return;

  const model = policyModel();

  // Deliberate opt-out — but never silent: prompts are untrusted text, so the
  // marker could be smuggled in from repo/file content. Every use is announced
  // in the transcript (permissionDecisionReason) and appended to the audit log.
  if (typeof input.prompt === 'string' && input.prompt.includes(ESCAPE_HATCH)) {
    logEscapeUse(payload);
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'allow',
        permissionDecisionReason:
          `Model policy BYPASSED via ${ESCAPE_HATCH} escape hatch: this ` +
          `${payload.tool_name} dispatch keeps model ` +
          `"${typeof input.model === 'string' ? input.model : '(default)'}" ` +
          `instead of policy model "${model}". Use recorded in ` +
          `state/${ESCAPE_LOG_NAME}.`
      }
    }) + '\n');
    return;
  }

  if (input.model === model) return; // already compliant — no opinion

  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'allow',
      permissionDecisionReason:
        `Model policy: subagent dispatches run on "${model}" (cardinal rule; ` +
        `override with ${ESCAPE_HATCH} in the prompt).`,
      updatedInput: { ...input, model }
    }
  }) + '\n');
}

main().catch(() => { /* never crash the harness */ }).finally(() => process.exit(0));
