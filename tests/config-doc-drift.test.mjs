// Config/doc drift detection test.
// Ensures that config keys documented in docs/ and read by code consumers
// are all present in aesop.config.example.json — a tripwire against
// silent orphaning of live config keys during refactoring.
//
// Run: node --test tests/config-doc-drift.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '..');

// List of config key paths that are documented and/or read by live code.
// Format: { file: string (relative path to consumer), keyPath: string (dot-notation path) }
// keyPath 'a.b.c' means config.a.b.c must be present (and non-null for required keys)
const REQUIRED_KEYS = [
  // From hooks/claude/force-model-policy.mjs (line 79):
  //   const m = cfg && cfg.cardinal_rules && cfg.cardinal_rules.subagent_model;
  // Documented at docs/HOOK-INSTALL.md:245-247
  { file: 'hooks/claude/force-model-policy.mjs', keyPath: 'cardinal_rules.subagent_model' },

  // From monitor/collect-signals.mjs (lines 32-46):
  //   config.brain_root, config.scripts_root, config.temp_root, config.state_root
  { file: 'monitor/collect-signals.mjs', keyPath: 'brain_root' },
  { file: 'monitor/collect-signals.mjs', keyPath: 'scripts_root' },
  { file: 'monitor/collect-signals.mjs', keyPath: 'temp_root' },
  { file: 'monitor/collect-signals.mjs', keyPath: 'state_root' },

  // From monitor/collect-signals.mjs (lines 55-71):
  //   config.repos, config.monitor.log_max_lines, config.monitor.log_max_kb, config.monitor.extended_signals
  { file: 'monitor/collect-signals.mjs', keyPath: 'repos' },
  { file: 'monitor/collect-signals.mjs', keyPath: 'monitor.log_max_lines' },
  { file: 'monitor/collect-signals.mjs', keyPath: 'monitor.log_max_kb' },
  { file: 'monitor/collect-signals.mjs', keyPath: 'monitor.extended_signals' },

  // From dash/dash-extra.mjs (lines 26-30):
  //   config.transcripts_root
  { file: 'dash/dash-extra.mjs', keyPath: 'transcripts_root' },

  // From ui/serve.py (lines 49, 57):
  //   config.get("state_root"), config.get("transcripts_root")
  { file: 'ui/serve.py', keyPath: 'state_root' },
  { file: 'ui/serve.py', keyPath: 'transcripts_root' }
];

// Helper: safely get a nested property by dot-notation path
function getByPath(obj, path) {
  const parts = path.split('.');
  let current = obj;
  for (const part of parts) {
    if (current == null) return undefined;
    current = current[part];
  }
  return current;
}

test('config/doc drift: all documented keys exist in aesop.config.example.json', () => {
  const examplePath = path.join(PROJECT_ROOT, 'aesop.config.example.json');
  assert.ok(fs.existsSync(examplePath), `aesop.config.example.json must exist at ${examplePath}`);

  let example;
  try {
    example = JSON.parse(fs.readFileSync(examplePath, 'utf8'));
  } catch (err) {
    throw new Error(`Failed to parse aesop.config.example.json: ${err.message}`);
  }

  const failures = [];
  for (const { file, keyPath } of REQUIRED_KEYS) {
    const value = getByPath(example, keyPath);
    // We check that the path exists in the config (value is not undefined).
    // For collections like 'repos', the example can be empty (e.g., [])
    // but the key must be present.
    if (value === undefined) {
      failures.push(`  ${keyPath} (read by ${file})`);
    }
  }

  if (failures.length > 0) {
    throw new Error(
      `Config keys missing from aesop.config.example.json:\n${failures.join('\n')}\n` +
      `These keys are read by live code or documented as overridable. ` +
      `Add them to aesop.config.example.json with example/default values.`
    );
  }
});
