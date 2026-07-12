// Detect and render running Claude agents from transcripts.
// Usage: node dash-extra.mjs [--json]
//   --json: output JSON array of agents (for web dashboard /data endpoint)
//   (default): render TUI text output (for terminal dashboard)

import fs from 'node:fs';
import path from 'node:path';

// Configuration: env var > config file > built-in default
// Helper: load aesop.config.json if it exists
function loadConfigFile(aesopRoot) {
  try {
    const configPath = path.join(aesopRoot, 'aesop.config.json');
    if (fs.existsSync(configPath)) {
      return JSON.parse(fs.readFileSync(configPath, 'utf8'));
    }
  } catch {
    // Parse error or file doesn't exist; ignore
  }
  return {};
}

const AESOP_ROOT = process.env.AESOP_ROOT || path.join(process.env.HOME || '.', 'aesop');
const config = loadConfigFile(AESOP_ROOT);

const TRANSCRIPTS_ROOT = path.resolve(
  process.env.AESOP_TRANSCRIPTS_ROOT ||
  config.transcripts_root ||
  path.join(process.env.HOME || '.', '.claude', 'projects')
);
const SCAN_DIR = path.join(AESOP_ROOT, 'state');
const ALERTS_LOG = path.join(SCAN_DIR, 'SECURITY-ALERTS.log');

// ANSI colors for TUI output
const c = {
  R: '\x1b[31m',
  G: '\x1b[32m',
  Y: '\x1b[33m',
  M: '\x1b[35m',
  C: '\x1b[36m',
  B: '\x1b[1m',
  D: '\x1b[2m',
  X: '\x1b[0m'
};

const now = Date.now();
const out = [];

// Activity window: only include files modified within the last 12 minutes
const ACTIVITY_WINDOW = 12 * 60 * 1000;

// Depth limit to match monitor's equivalent (prevent unbounded recursion on growing tree)
const MAX_DEPTH = 6;

// Read alerts log if present
let slog = [];
try {
  if (fs.existsSync(ALERTS_LOG)) {
    slog = fs.readFileSync(ALERTS_LOG, 'utf8').split('\n');
  }
} catch {}

// Recursively walk directory tree to find agent-*.jsonl files.
// Respects depth limit and prunes old directories (mtime older than activity window).
function walk(dir, accumulator, depth = 0) {
  // Stop recursion if depth exceeds limit
  if (depth > MAX_DEPTH) return;

  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        // Check directory mtime: skip descending into stale directories
        let dirMtime = 0;
        try {
          dirMtime = fs.statSync(fullPath).mtimeMs;
        } catch {}

        // Only descend if directory was modified recently (within activity window)
        if (now - dirMtime < ACTIVITY_WINDOW) {
          walk(fullPath, accumulator, depth + 1);
        }
      } else if (/^agent-.*\.jsonl$/.test(entry.name)) {
        accumulator.push(fullPath);
      }
    }
  } catch {}
}

// Find all agent transcript files
let files = [];
if (fs.existsSync(TRANSCRIPTS_ROOT)) {
  walk(TRANSCRIPTS_ROOT, files);
}

// Filter: active agents in last 12 minutes, sorted by recency
files = files
  .map(f => {
    let mtime = 0;
    try {
      mtime = fs.statSync(f).mtimeMs;
    } catch {}
    return { f, mtime };
  })
  .filter(x => now - x.mtime < 12 * 60 * 1000)
  .sort((a, b) => b.mtime - a.mtime)
  .slice(0, 8);

// Extract description/hint from first ~60KB of agent transcript
function label(filePath) {
  try {
    const fd = fs.openSync(filePath, 'r');
    const buf = Buffer.alloc(60000);
    const n = fs.readSync(fd, buf, 0, 60000, 0);
    fs.closeSync(fd);
    const content = buf.toString('utf8', 0, n);

    // Try to find description or subagent_type in JSON
    let match = content.match(/"description":"([^"]{2,60})"/);
    if (!match) {
      match = content.match(/"subagent_type":"([^"]{2,40})"/);
    }
    return match ? match[1] : '';
  } catch {}
  return '';
}

// TUI output: render heading
out.push(`${c.B}  FLEET AGENTS${c.X} ${c.D}(green=running · severity-colored if flagged)${c.X}`);

if (files.length === 0) {
  out.push(`    ${c.D}(no active fleet agents in last 12 min)${c.X}`);
}

let runningCount = 0;

// Render each agent
for (const { f, mtime } of files) {
  const basename = path.basename(f);
  const ageSeconds = Math.round((now - mtime) / 1000);

  // Check if agent is referenced in alerts log
  const alertsForAgent = slog.filter(line => line.includes(basename));

  let statusColor = ageSeconds < 120 ? c.G : c.D;
  let statusText = ageSeconds < 120 ? 'running' : 'idle';

  if (ageSeconds < 120) runningCount++;

  // Recolor based on alert severity
  if (alertsForAgent.some(l => l.includes('SUSPICIOUS'))) {
    statusColor = c.R;
    statusText = 'SUSPICIOUS';
  } else if (alertsForAgent.some(l => / HIGH /.test(l))) {
    statusColor = c.R;
    statusText = 'HIGH';
  } else if (alertsForAgent.some(l => / DRIFT /.test(l))) {
    statusColor = c.M;
    statusText = 'DRIFT';
  } else if (alertsForAgent.some(l => / MED /.test(l))) {
    statusColor = c.Y;
    statusText = 'MED';
  }

  // Extract agent ID from filename (agent-<id>.jsonl)
  const agentId = basename
    .replace(/^agent-/, '')
    .replace(/\.jsonl$/, '')
    .slice(0, 13);

  const hint = label(f).slice(0, 38);

  out.push(
    `    ${statusColor}●${c.X} ${agentId.padEnd(14)} ${c.D}${String(ageSeconds).padStart(4)}s${c.X}  ${statusColor}${statusText.padEnd(11)}${c.X}${c.D}${hint}${c.X}`
  );
}

if (files.length > 0) {
  out.push(`    ${c.D}${runningCount} running, ${files.length - runningCount} idle (last 12 min)${c.X}`);
}

// Output
if (process.argv.includes('--json')) {
  // JSON mode: emit agents array for web dashboard
  const agents = [];
  for (const { f, mtime } of files) {
    const basename = path.basename(f);
    const ageSeconds = Math.round((now - mtime) / 1000);
    const alertsForAgent = slog.filter(line => line.includes(basename));

    let status = ageSeconds < 120 ? 'running' : 'idle';

    if (alertsForAgent.some(l => l.includes('SUSPICIOUS'))) {
      status = 'SUSPICIOUS';
    } else if (alertsForAgent.some(l => / HIGH /.test(l))) {
      status = 'HIGH';
    } else if (alertsForAgent.some(l => / DRIFT /.test(l))) {
      status = 'DRIFT';
    } else if (alertsForAgent.some(l => / MED /.test(l))) {
      status = 'MED';
    }

    const agentId = basename
      .replace(/^agent-/, '')
      .replace(/\.jsonl$/, '')
      .slice(0, 13);

    agents.push({
      id: agentId,
      age_s: ageSeconds,
      status: status,
      hint: label(f).slice(0, 60)
    });
  }
  process.stdout.write(JSON.stringify(agents) + '\n');
} else {
  // TUI mode: emit colored text
  process.stdout.write(out.join('\n') + '\n');
}
