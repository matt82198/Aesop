// Orchestration Refinement Monitor — deterministic signal collector (no LLM).
// Walks known roots and emits a compact BRIEF.md + SIGNALS.json the Haiku monitor reads
// each cycle, so its reasoning stays cheap and focused. Node built-ins only.

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { execSync, spawnSync } from 'node:child_process';

// === Configuration ===
// Load from environment or aesop.config.json; fall back to safe defaults.
const AESOP_ROOT = process.env.AESOP_ROOT || '.';
const BRAIN_ROOT = process.env.BRAIN_ROOT || path.join(AESOP_ROOT, '..', '.claude');
const SCRIPTS_ROOT = process.env.SCRIPTS_ROOT || path.join(AESOP_ROOT, '..', 'scripts');
const TEMP_ROOT = process.env.TEMP_ROOT || path.join(os.tmpdir(), 'claude');
const MON = path.join(AESOP_ROOT, 'monitor');
const STATE_DIR = path.join(AESOP_ROOT, 'state');

// Optional: load aesop.config.json for repo list
let repos = [];
let logThresholds = { maxLines: 500, maxKb: 40 };
try {
  const configPath = path.join(AESOP_ROOT, 'aesop.config.json');
  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  if (config.repos && Array.isArray(config.repos)) {
    repos = config.repos.map(r => r.path);
  }
  if (config.monitor && config.monitor.log_max_lines) {
    logThresholds.maxLines = config.monitor.log_max_lines;
  }
  if (config.monitor && config.monitor.log_max_kb) {
    logThresholds.maxKb = config.monitor.log_max_kb;
  }
} catch {
  // No config file or parse error; use defaults
}

const now = Date.now();
const HOUR = 3600e3;
const DAY = 24 * HOUR;

// === Utilities ===
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

const walk = (dir, test, out = [], depth = 0) => {
  if (depth > 6) return out;
  let ents;
  try {
    ents = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of ents) {
    const fp = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (/node_modules|\.git|target|\.venv|__pycache__/.test(e.name)) continue;
      walk(fp, test, out, depth + 1);
    } else if (test(e.name, fp)) {
      out.push(fp);
    }
  }
  return out;
};

// === Signal Collectors ===

// 1) Heartbeat check
function checkHeartbeats() {
  const staleLoops = [];
  const beatsDir = path.join(MON, '.heartbeats');
  const thresholds = { watchdog: 300e3, monitor: 3600e3, default: 1800e3 };
  let beatFiles = [];
  try {
    beatFiles = fs.readdirSync(beatsDir).map(f => path.join(beatsDir, f));
  } catch {
    // no .heartbeats dir
  }
  const legacyBeats = [
    path.join(MON, '.monitor-heartbeat'),
    path.join(STATE_DIR, '.watchdog-heartbeat'),
  ];
  beatFiles = beatFiles.concat(legacyBeats.filter(f => fs.existsSync(f)));
  for (const fp of beatFiles) {
    try {
      const content = fs.readFileSync(fp, 'utf8').trim();
      const epoch = parseInt(content.split('\n')[0], 10);
      if (!epoch) continue;
      const beatAge = now - epoch * 1000;
      const name = path.basename(fp);
      let threshold = thresholds.default;
      if (name.includes('watchdog')) threshold = thresholds.watchdog;
      if (name.includes('monitor')) threshold = thresholds.monitor;
      if (beatAge > threshold) {
        staleLoops.push({ name, ageMs: beatAge, threshold });
      }
    } catch {
      // skip invalid heartbeat file
    }
  }
  return staleLoops;
}

// 2) Git state check
function checkGitState() {
  const gitState = [];
  for (const repoPath of repos) {
    if (!fs.existsSync(repoPath)) continue;
    const branch = sh('git rev-parse --abbrev-ref HEAD', repoPath);
    const lastCommit = sh('git log -1 --pretty=%h·%cr·%s', repoPath);
    const dirty = sh('git status --porcelain', repoPath)
      .split('\n')
      .filter(l => l.trim()).length;
    const ahead = sh('git rev-list --count @{u}..HEAD', repoPath) || '?';
    gitState.push({
      repo: path.basename(repoPath),
      branch,
      lastCommit,
      dirty,
      ahead,
    });
  }
  return gitState;
}

// 3) Memory freshness check
function checkMemoryFreshness() {
  const memoryDir = path.join(BRAIN_ROOT, 'projects', '*', 'memory');
  const staleMemories = [];
  let memoryCount = 0;
  try {
    const baseDir = path.join(BRAIN_ROOT, 'projects');
    if (!fs.existsSync(baseDir)) return { count: 0, staleMemories: [], staleCount: 0 };
    const projDirs = fs.readdirSync(baseDir, { withFileTypes: true })
      .filter(d => d.isDirectory())
      .map(d => path.join(baseDir, d.name, 'memory'));
    for (const memDir of projDirs) {
      if (!fs.existsSync(memDir)) continue;
      const memFiles = fs.readdirSync(memDir)
        .filter(f => f.endsWith('.md') && f !== 'MEMORY.md' && f !== 'INBOX.md')
        .map(f => path.join(memDir, f));
      memoryCount += memFiles.length;
      for (const fp of memFiles) {
        const st = stat(fp);
        if (st && now - st.mtimeMs > 30 * DAY) {
          staleMemories.push(path.basename(fp));
        }
      }
    }
  } catch {
    // no memory dir
  }
  return { count: memoryCount, staleMemories, staleCount: staleMemories.length };
}

// 4) Log file status check
function checkLogFiles() {
  const logFiles = [
    path.join(STATE_DIR, 'FLEET-BACKUP.log'),
    path.join(STATE_DIR, 'SECURITY-ALERTS.log'),
    path.join(MON, 'ACTIONS.log'),
  ];
  const logs = [];
  for (const logPath of logFiles) {
    const st = stat(logPath);
    let sizeKb = 0;
    let lineCount = 0;
    if (st) {
      sizeKb = (st.size / 1024).toFixed(1);
      try {
        const content = fs.readFileSync(logPath, 'utf8');
        lineCount = content.split('\n').filter(l => l.trim()).length;
      } catch {
        // skip
      }
    }
    logs.push({
      name: path.basename(logPath),
      exists: !!st,
      sizeKb,
      lineCount,
      needsRotation: st && (lineCount > logThresholds.maxLines || st.size / 1024 > logThresholds.maxKb),
    });
  }
  return logs;
}

// 5) Junk-script sprawl detection
function detectJunkScripts() {
  if (!fs.existsSync(TEMP_ROOT)) return { total: 0, quarantinable: 0, bytes: 0, oldest: [], recentCount: 0 };
  const sessionDirs = (() => {
    try {
      return fs.readdirSync(TEMP_ROOT, { withFileTypes: true })
        .filter(d => d.isDirectory())
        .map(d => path.join(TEMP_ROOT, d.name));
    } catch {
      return [];
    }
  })();
  const liveDirs = new Set();
  for (const root of sessionDirs) {
    const files = walk(root, () => true);
    const newest = Math.max(0, ...files.map(fp => (stat(fp) || { mtimeMs: 0 }).mtimeMs));
    if (now - newest < 2 * HOUR) {
      liveDirs.add(root.replace(/\\/g, '/'));
    }
  }
  const inLiveDir = (fp) => [...liveDirs].some(d => fp.replace(/\\/g, '/').startsWith(d));
  const tempScripts = walk(TEMP_ROOT, n => /\.(py|mjs|js)$/.test(n))
    .map(fp => ({ fp, st: stat(fp) }))
    .filter(x => x.st)
    .map(x => ({
      fp: x.fp,
      ageMs: now - x.st.mtimeMs,
      size: x.st.size,
      quarantinable: now - x.st.mtimeMs > DAY && !inLiveDir(x.fp),
    }));
  const junk = {
    total: tempScripts.length,
    quarantinable: tempScripts.filter(x => x.quarantinable).length,
    bytes: tempScripts.reduce((a, x) => a + x.size, 0),
    oldest: tempScripts
      .sort((a, b) => b.ageMs - a.ageMs)
      .slice(0, 8)
      .map(x => `${age(x.ageMs)} ${x.fp.split(/[/\\]/).slice(-2).join('/')}`),
    recentCount: tempScripts.filter(x => now - x.ageMs < HOUR).length,
  };
  return junk;
}

// 6) Stray scripts in repo roots
function detectStrayRepoScripts() {
  const strayRepo = [];
  for (const repoPath of repos) {
    if (!fs.existsSync(repoPath)) continue;
    const recent = sh('git log --since="7 days ago" --name-only --pretty=format: --diff-filter=A', repoPath)
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean);
    for (const f of new Set(recent)) {
      if (/^[^/\\]+\.(py|mjs|js|sql)$/.test(f)) {
        strayRepo.push(`${path.basename(repoPath)}: ${f}`);
      }
    }
  }
  return strayRepo;
}

// 7) Security alert review
function checkSecurityAlerts() {
  const alertLog = path.join(STATE_DIR, 'SECURITY-ALERTS.log');
  const st = stat(alertLog);
  if (!st) return { count: 0, highMedCount: 0 };
  try {
    const content = fs.readFileSync(alertLog, 'utf8');
    const lines = content.split('\n');
    const highMedCount = lines.filter(l => /HIGH|MED/.test(l) && !l.includes('SUPPRESSED-FP')).length;
    return { count: lines.filter(l => l.trim()).length, highMedCount };
  } catch {
    return { count: 0, highMedCount: 0 };
  }
}

// 8) Respawn watch (Rule 6 retry cap)
function detectRespawnWatch() {
  const respawnWatch = [];
  const ledgerPath = path.join(BRAIN_ROOT, 'FLEET-LEDGER.md');
  if (!fs.existsSync(ledgerPath)) return respawnWatch;
  try {
    const content = fs.readFileSync(ledgerPath, 'utf8');
    const lines = content.split('\n').filter(l => l.trim() && !l.startsWith('|'));
    const windowSize = 50;
    const recentStart = Math.max(0, lines.length - windowSize);
    const signatures = {};
    const normalize = (desc) => (desc || '').substring(0, 40).toLowerCase().trim();
    for (let i = recentStart; i < lines.length; i++) {
      const line = lines[i];
      const parts = line.split('|').map(s => s.trim());
      if (parts.length >= 4) {
        const description = parts[3];
        const sig = normalize(description);
        if (sig) signatures[sig] = (signatures[sig] || 0) + 1;
      }
    }
    for (const [sig, count] of Object.entries(signatures)) {
      if (count > 3) {
        respawnWatch.push({
          signature: sig,
          count,
          warning: `RESPAWN CAP: '${sig}' dispatched ${count} times — investigate hang or mark BLOCKED`,
        });
      }
    }
  } catch {
    // fail-open on error
  }
  return respawnWatch;
}

// 9) Cost cadence tracking
function trackCostCadence() {
  const prevStateFile = path.join(MON, '.signal-state.json');
  let prevState = {};
  try {
    prevState = JSON.parse(fs.readFileSync(prevStateFile, 'utf8'));
  } catch {
    // no prev state
  }
  const cycleCount = (prevState.cycleCount || 0) + 1;
  let costTick = null;
  if (cycleCount % 3 === 0) {
    costTick = {
      cycle: cycleCount,
      ts: new Date(now).toISOString(),
      summary: 'Cost cycle tick recorded',
    };
  }
  return { cycleCount, costTick };
}

// 10) Unreviewed prompts count
function checkUnreviewedPrompts() {
  const seenFile = path.join(MON, '.fleet-prompts-seen.json');
  let prevSeen = {};
  try {
    prevSeen = JSON.parse(fs.readFileSync(seenFile, 'utf8'));
  } catch {
    // no prev state
  }
  // Without fleet_prompt_extractor.py available, emit 0
  // In production, invoke spawnSync('python', [...fleet_prompt_extractor.py...])
  return 0;
}

// === Proposal Emission ===
// Append PROPOSE-tier signals to monitor/PROPOSALS.md (idempotent per signal key)
function emitProposal(signalKey, problem, suggestedChange) {
  const proposalsPath = path.join(MON, 'PROPOSALS.md');
  const timestamp = new Date(now).toISOString();

  // Read existing proposals to check for duplicate
  let existingContent = '';
  try {
    existingContent = fs.readFileSync(proposalsPath, 'utf8');
  } catch {
    // File doesn't exist yet; start fresh
    if (!fs.existsSync(MON)) {
      fs.mkdirSync(MON, { recursive: true });
    }
  }

  // Check if this signal key already has an entry (idempotency check)
  if (existingContent.includes(`**Signal:** ${signalKey}`)) {
    // Entry already exists; skip to avoid duplicates
    return;
  }

  // Append new proposal entry
  const proposal = `
## ${signalKey} — ${timestamp}

**Signal:** ${signalKey}

**Problem:**
${problem}

**Suggested change:**
${suggestedChange}

---
`;

  try {
    fs.appendFileSync(proposalsPath, proposal, 'utf8');
  } catch (e) {
    // Fail-open: log to BRIEF instead of crashing
    console.error(`Failed to write PROPOSALS.md: ${e.message}`);
  }
}

// === Main ===
const staleLoops = checkHeartbeats();
const gitState = checkGitState();
const memory = checkMemoryFreshness();
const logFiles = checkLogFiles();
const junk = detectJunkScripts();
const strayRepo = detectStrayRepoScripts();
const alerts = checkSecurityAlerts();
const respawnWatch = detectRespawnWatch();
const { cycleCount, costTick } = trackCostCadence();
const unreviewedPrompts = checkUnreviewedPrompts();

const signals = {
  timestamp: new Date(now).toISOString(),
  cycleCount,
  heartbeats: { staleCount: staleLoops.length, details: staleLoops },
  git: gitState,
  memory,
  logs: logFiles,
  junk,
  strayRepo,
  alerts,
  respawnWatch,
  costTick,
  unreviewedPrompts,
};

const brief = [];
brief.push(`# Aesop Monitor Brief — ${signals.timestamp}`);
brief.push('');
brief.push('## Heartbeat check');
if (staleLoops.length === 0) {
  brief.push('✓ All heartbeats fresh (watchdog 300s, monitor 3600s, others 1800s).');
} else {
  brief.push(`✗ **${staleLoops.length} stale loop(s)** detected:`);
  for (const sl of staleLoops) {
    brief.push(`  - ${sl.name}: ${age(sl.ageMs)} (threshold: ${age(sl.threshold)})`);
  }
}
brief.push('');

brief.push('## Git state');
if (gitState.length === 0) {
  brief.push('No repos configured.');
} else {
  for (const g of gitState) {
    const status = g.dirty === 0 && g.ahead === '0' ? '✓' : '⚠';
    brief.push(`- ${status} **${g.repo}** [${g.branch}] — dirty: ${g.dirty}, ahead: ${g.ahead}`);
    if (g.lastCommit) brief.push(`  ${g.lastCommit}`);
  }
}
brief.push('');

brief.push('## Memory');
brief.push(`- ${memory.count} memory file(s)`);
if (memory.staleCount > 0) {
  brief.push(`  ⚠ **${memory.staleCount} stale** (>30d): ${memory.staleMemories.join(', ')}`);
}
brief.push('');

brief.push('## Log files');
const needsRotation = logFiles.filter(l => l.needsRotation);
if (needsRotation.length === 0) {
  brief.push('✓ All logs within thresholds.');
} else {
  brief.push(`⚠ **${needsRotation.length} log(s) need rotation:**`);
  for (const l of needsRotation) {
    brief.push(`  - ${l.name}: ${l.lineCount} lines, ${l.sizeKb}kb`);
  }
}
brief.push('');

brief.push('## Junk-script sprawl (temp/scratch)');
brief.push(`- ${junk.total} total scripts, ${(junk.bytes / 1024).toFixed(0)}kb`);
brief.push(`  Quarantinable (>24h, not live): ${junk.quarantinable}`);
if (junk.oldest.length > 0) {
  brief.push('  Oldest:');
  for (const o of junk.oldest) {
    brief.push(`    ${o}`);
  }
}
if (strayRepo.length > 0) {
  brief.push('');
  brief.push('## Stray repo scripts (7d)');
  for (const s of strayRepo) {
    brief.push(`- ${s}`);
  }
}
brief.push('');

brief.push('## Security');
brief.push(`- Alert log: ${alerts.count} entries, ${alerts.highMedCount} HIGH/MED`);
brief.push('');

brief.push('## Respawn watch (Rule 6 retry cap)');
if (respawnWatch.length === 0) {
  brief.push('✓ No retry-cap breaches (all signatures ≤3 occurrences).');
} else {
  brief.push(`⚠ **${respawnWatch.length} signature(s) exceeded 3-attempt limit:**`);
  for (const rw of respawnWatch) {
    brief.push(`  - ${rw.warning}`);
  }
  brief.push('  (Note: distinguish legitimate fan-outs from identical retries; manual review recommended.)');
}
brief.push('');

brief.push('## Cost tracking');
brief.push(`- Cycle: ${cycleCount}${costTick ? ' — tick recorded' : ''}`);
if (costTick) {
  brief.push(`  ${costTick.ts}`);
}
brief.push('');

brief.push('## Unreviewed prompts');
brief.push(`- ${unreviewedPrompts} new prompt(s) awaiting semantic review`);
brief.push('');

brief.push('_Refinement points → act per CHARTER.md (AUTO safe, PROPOSE rule changes). Goal is fixed._');

// === Emit PROPOSE-tier proposals ===
// Only emit for signals that warrant user review per CHARTER.md action tiers
if (respawnWatch.length > 0) {
  emitProposal(
    'respawn-watch-breach',
    `Rule 6 retry cap breached: ${respawnWatch.length} agent signature(s) appeared >3 times in recent spawn history. This indicates either an intentional parallel fan-out or a hung-agent loop.`,
    `Review FLEET-LEDGER.md to distinguish legitimate concurrent spawns from identical retries. If retries are unintentional, investigate root cause and add guardrails to prevent re-dispatch. Consider updating monitoring thresholds or retry strategy.`
  );
}

if (strayRepo.length > 0) {
  emitProposal(
    'stray-repo-scripts',
    `${strayRepo.length} script file(s) committed to repo root in past 7 days: ${strayRepo.join(', ')}. Scripts should live in dedicated src/ or scripts/ paths, not repo root.`,
    `Move stray scripts to proper paths per project discipline. Update CONTRIBUTING.md if repo structure is ambiguous. Add pre-commit hook or CI check to enforce.`
  );
}

if (alerts.highMedCount > 0) {
  emitProposal(
    'security-alerts-high-med',
    `${alerts.highMedCount} HIGH/MED security alert(s) in SECURITY-ALERTS.log. These may indicate real vulnerabilities, credential exposure, or false positives requiring review.`,
    `Review each HIGH/MED entry in SECURITY-ALERTS.log. Distinguish real issues (fix immediately) from false positives (mark SUPPRESSED-FP). Update scanning rules if needed to reduce noise.`
  );
}

if (memory.staleCount > 0) {
  emitProposal(
    'stale-memory-files',
    `${memory.staleCount} memory file(s) older than 30 days: ${memory.staleMemories.join(', ')}. Stale memory may indicate obsolete project context or abandoned projects.`,
    `Review stale memory files in keeper. Consolidate, archive, or delete per project lifecycle. Update memory refresh schedule if projects are active but infrequently updated.`
  );
}

// Write outputs
try {
  fs.mkdirSync(MON, { recursive: true });
  fs.writeFileSync(path.join(MON, 'BRIEF.md'), brief.join('\n'), 'utf8');
  fs.writeFileSync(path.join(MON, 'SIGNALS.json'), JSON.stringify(signals, null, 2), 'utf8');
  fs.writeFileSync(path.join(MON, '.monitor-heartbeat'), String(Math.floor(now / 1000)), 'utf8');
  fs.writeFileSync(path.join(MON, '.signal-state.json'), JSON.stringify({ cycleCount }, null, 2), 'utf8');
  const summaryLine = `stale-loops: ${staleLoops.length}, repos-dirty: ${gitState.filter(g => g.dirty > 0).length}, stale-mem: ${memory.staleCount}, logs-need-rotation: ${needsRotation.length}, junk-quarantinable: ${junk.quarantinable}, stray-repo-scripts: ${strayRepo.length}, alerts-high-med: ${alerts.highMedCount}, respawn-watch: ${respawnWatch.length}, cycle: ${cycleCount}`;
  console.log(summaryLine);
} catch (e) {
  console.error('Failed to write signals:', e.message);
  process.exit(1);
}
