// Orchestration Refinement Monitor — deterministic signal collector (no LLM).
// Walks known roots and emits a compact BRIEF.md + SIGNALS.json the Haiku monitor reads
// each cycle, so its reasoning stays cheap and focused. Node built-ins only.

import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';

const AESOP_ROOT = process.env.AESOP_ROOT || '.';
const MON = path.join(AESOP_ROOT, 'monitor');
const now = Date.now();
const HOUR = 3600e3;
const DAY = 24 * HOUR;

const sh = (cmd, cwd) => {
  try {
    return execSync(cmd, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  } catch {
    return '';
  }
};

const stat = (p) => {
  try {
    return fs.statSync(p);
  } catch {
    return null;
  }
};

const age = (ms) => {
  if (ms < HOUR) return `${Math.round(ms / 60e3)}m`;
  if (ms < DAY) return `${(ms / HOUR).toFixed(1)}h`;
  return `${(ms / DAY).toFixed(1)}d`;
};

// Main signal collection
const signals = {
  heartbeats: [],
  rotations: [],
  unreviewedPrompts: 0,
  staleMemories: [],
  respawnWatch: [],
};

const brief = [
  `# Aesop Monitor Brief — ${new Date(now).toISOString()}`,
  '',
  '## Status',
  'Orchestration monitor cycle complete.',
  '',
];

// 1) Heartbeat check
const beatsDir = path.join(MON, '.heartbeats');
let beatFiles = [];
try {
  const files = fs.readdirSync(beatsDir);
  beatFiles = files.map((f) => path.join(beatsDir, f));
} catch {}

const legacyBeats = [
  path.join(MON, '.monitor-heartbeat'),
  path.join(AESOP_ROOT, 'state', '.watchdog-heartbeat'),
];

beatFiles = beatFiles.concat(legacyBeats.filter((f) => fs.existsSync(f)));

for (const fp of beatFiles) {
  try {
    const content = fs.readFileSync(fp, 'utf8').trim();
    const epoch = parseInt(content.split('\n')[0], 10);
    if (!epoch) continue;

    const beatAge = now - epoch * 1000;
    const name = path.basename(fp);
    const thresholds = { watchdog: 300e3, monitor: 3600e3, default: 1800e3 };
    let threshold = thresholds.default;
    if (name.includes('watchdog')) threshold = thresholds.watchdog;
    if (name.includes('monitor')) threshold = thresholds.monitor;

    signals.heartbeats.push({
      name,
      ageMs: beatAge,
      threshold,
      ok: beatAge < threshold,
    });
  } catch {}
}

brief.push('## Heartbeats');
if (signals.heartbeats.length === 0) {
  brief.push('No heartbeats detected yet.');
} else {
  for (const hb of signals.heartbeats) {
    const status = hb.ok ? '✓' : '✗';
    brief.push(`- ${status} ${hb.name}: ${age(hb.ageMs)}`);
  }
}
brief.push('');

// 2) Log file status
brief.push('## Logs');
const logFiles = [
  path.join(AESOP_ROOT, 'state', 'FLEET-BACKUP.log'),
  path.join(AESOP_ROOT, 'state', 'SECURITY-ALERTS.log'),
];

for (const logFile of logFiles) {
  const st = stat(logFile);
  if (st) {
    brief.push(`- ${path.basename(logFile)}: ${st.size} bytes`);
  } else {
    brief.push(`- ${path.basename(logFile)}: (not found)`);
  }
}
brief.push('');

// 3) Placeholder for future signal collectors
brief.push('## Notes');
brief.push('This is a template monitor. Extend collect-signals.mjs to add:');
brief.push('- Junk-script sprawl detection');
brief.push('- Memory gap detection');
brief.push('- Rule friction analysis');
brief.push('- Orchestration health checks');
brief.push('');

// Write outputs
try {
  fs.mkdirSync(MON, { recursive: true });
  fs.writeFileSync(path.join(MON, 'BRIEF.md'), brief.join('\n'), 'utf8');
  fs.writeFileSync(path.join(MON, 'SIGNALS.json'), JSON.stringify(signals, null, 2), 'utf8');
  console.log('Monitor signals collected. See BRIEF.md and SIGNALS.json.');
} catch (e) {
  console.error('Failed to write signals:', e.message);
  process.exit(1);
}
