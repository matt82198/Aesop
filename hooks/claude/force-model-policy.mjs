#!/usr/bin/env node
// force-model-policy.mjs — Claude Code PreToolUse hook enforcing the
// "subagents are always Haiku" cardinal rule as versioned, executable policy.
//
// Wire it in settings.json under hooks.PreToolUse with matcher "Agent|Task"
// (see docs/HOOK-INSTALL.md). For every subagent dispatch:
//
//   - model absent or non-compliant  -> rewritten to the policy model ("haiku",
//     or aesop.config.json cardinal_rules.subagent_model when present)
//   - prompt contains [[ALLOW-NON-HAIKU]] -> deliberate escape hatch, untouched
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
// payload is ever logged.

import fs from 'node:fs';
import path from 'node:path';

const ESCAPE_HATCH = '[[ALLOW-NON-HAIKU]]';
const DEFAULT_MODEL = 'haiku';
const GOVERNED_TOOLS = new Set(['Agent', 'Task']);

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

function readStdin() {
  return new Promise((resolve) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { data += chunk; });
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', () => resolve(''));
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

  // Deliberate, auditable opt-out — visible in the transcript by design.
  if (typeof input.prompt === 'string' && input.prompt.includes(ESCAPE_HATCH)) return;

  const model = policyModel();
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
