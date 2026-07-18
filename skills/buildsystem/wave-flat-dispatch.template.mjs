/**
 * Wave Flat-Dispatch Template & Preflight Guard
 *
 * This file is a TEMPLATE for ~/.claude/skills/buildsystem/wave-flat-dispatch.template.mjs
 * (user-local setup, NOT part of the aesop repository).
 *
 * Purpose:
 *   Validate that no two agents in a single wave modify the same file or directory.
 *   This is a critical safety invariant: if agents collide on file ownership, the
 *   merge train will fail due to git conflicts that Haiku cannot resolve.
 *
 * Invoked by:
 *   The /buildsystem orchestrator skill (during Phase 1: preflight).
 *   Refuses to dispatch agents if overlap is detected.
 *
 * Input: Wave backlog with agent assignments
 *   [
 *     { item: "Fix secret-scan gate", agent: "backend-dev", files: ["tools/secret_scan.py"] },
 *     { item: "Add dashboard widget", agent: "frontend-dev", files: ["ui/web/src/components/", "ui/web/src/types.ts"] },
 *     ...
 *   ]
 *
 * Output: { safe: true } or { safe: false, conflicts: [...] }
 *
 * Note: This template assumes:
 *   1. Your CLAUDE.md layer has a "Domain Map" section listing which agent owns which directory
 *   2. Each backlog item references files by path (relative to repo root)
 *   3. You have a function to expand file patterns to actual paths (glob or find)
 */

import fs from 'node:fs';
import path from 'node:path';

/**
 * Parse domain map from CLAUDE.md
 * Example format:
 *   ## Domain Map
 *   - **backend/**: backend-dev, core-dev
 *   - **ui/web/**: frontend-dev
 *   - **tests/**: test-bot
 *   - **docs/**: docs-agent
 */
function parseDomainMap(claudemdPath) {
  const content = fs.readFileSync(claudemdPath, 'utf8');
  const lines = content.split('\n');
  const map = {};
  let inDomainSection = false;

  for (const line of lines) {
    if (line.includes('## Domain Map') || line.includes('# Domain Map')) {
      inDomainSection = true;
      continue;
    }
    if (inDomainSection && line.startsWith('#') && !line.includes('Domain')) {
      // Hit next section
      break;
    }
    if (inDomainSection && line.trim().startsWith('- **')) {
      // Parse: - **backend/**: backend-dev, core-dev
      const match = line.match(/- \*\*([^*]+)\*\*:\s*(.+)/);
      if (match) {
        const dir = match[1];
        const agents = match[2]
          .split(',')
          .map((a) => a.trim())
          .filter((a) => a);
        map[dir] = agents;
      }
    }
  }

  return map;
}

/**
 * Resolve a file pattern (path or glob) to actual files on disk
 * Simplified: just check if file exists or is a directory
 */
function resolveFiles(filePattern, repoRoot) {
  const fullPath = path.join(repoRoot, filePattern);

  // If it's a directory, collect all files under it
  if (fs.existsSync(fullPath) && fs.statSync(fullPath).isDirectory()) {
    const files = [];
    const walk = (dir) => {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.name.startsWith('.')) continue; // Skip hidden
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          walk(fullPath);
        } else {
          files.push(path.relative(repoRoot, fullPath));
        }
      }
    };
    walk(fullPath);
    return files;
  }

  // If it's a file, return it
  if (fs.existsSync(fullPath)) {
    return [path.relative(repoRoot, fullPath)];
  }

  // If it's a glob or pattern, try basic glob expansion
  // (In production, use a proper glob library like 'glob' or 'micromatch')
  if (filePattern.includes('*')) {
    // Simplified: just return as-is (user must ensure pattern matches actual files)
    return [filePattern];
  }

  // Unknown: return as-is and let the validator handle it
  return [filePattern];
}

/**
 * Main preflight guard: validate no file overlaps
 *
 * @param {Object} config
 *   - backlog: Array of { item, agent, files } tuples
 *   - claudemdPath: Path to CLAUDE.md (for domain map)
 *   - repoRoot: Root of the repo (for file path resolution)
 * @returns {{ safe: boolean, conflicts?: Array }}
 */
export function validateWaveDispatch(config) {
  const { backlog, claudemdPath, repoRoot } = config;

  if (!claudemdPath || !fs.existsSync(claudemdPath)) {
    return {
      safe: false,
      message: 'CLAUDE.md not found; cannot validate domain map',
    };
  }

  if (!Array.isArray(backlog) || backlog.length === 0) {
    return {
      safe: true,
      message: 'Empty backlog; no dispatch needed',
    };
  }

  const domainMap = parseDomainMap(claudemdPath);

  // Build a map: normalized file path -> list of agents
  const fileToAgents = new Map();
  const conflicts = [];

  for (const item of backlog) {
    const { item: itemName, agent, files } = item;

    if (!agent || !files) {
      return {
        safe: false,
        message: `Invalid backlog item: missing agent or files. Item: ${itemName}`,
      };
    }

    const filesList = Array.isArray(files) ? files : [files];

    for (const filePattern of filesList) {
      const resolved = resolveFiles(filePattern, repoRoot);

      for (const file of resolved) {
        const normalized = path.normalize(file).replace(/\\/g, '/');

        if (!fileToAgents.has(normalized)) {
          fileToAgents.set(normalized, []);
        }
        fileToAgents.get(normalized).push(agent);
      }
    }
  }

  // Check for conflicts (same file touched by 2+ agents)
  for (const [file, agents] of fileToAgents) {
    const uniqueAgents = [...new Set(agents)];
    if (uniqueAgents.length > 1) {
      conflicts.push({
        file,
        agents: uniqueAgents,
        message: `File touched by multiple agents: ${uniqueAgents.join(', ')}`,
      });
    }
  }

  if (conflicts.length > 0) {
    return {
      safe: false,
      conflicts,
      message: `${conflicts.length} file(s) have overlapping agent ownership. Please reorder or resplit backlog items.`,
      remediation: [
        'Option 1: Merge overlapping items into a single agent assignment',
        'Option 2: Split one item into parts, assign each to different agent, add ordering constraint',
        'Option 3: Rename domain map in CLAUDE.md to reduce overlap',
      ],
    };
  }

  return {
    safe: true,
    message: 'No file overlaps detected; safe to dispatch',
    fileCount: fileToAgents.size,
    agentCount: new Set(backlog.map((i) => i.agent)).size,
  };
}

/**
 * CLI entry point: validate a wave backlog file
 *
 * Usage:
 *   node wave-flat-dispatch.template.mjs state/BACKLOG.md
 */
if (import.meta.url === `file://${process.argv[1]}`) {
  const backlogPath = process.argv[2];
  const claudeMdPath = process.argv[3] || 'CLAUDE.md';
  const repoRoot = process.argv[4] || '.';

  if (!backlogPath) {
    console.error('Usage: node wave-flat-dispatch.template.mjs <backlog-path> [claude-md-path] [repo-root]');
    process.exit(1);
  }

  // Simplified backlog parsing (production should use a proper parser)
  let backlog = [];
  try {
    const backlogContent = fs.readFileSync(backlogPath, 'utf8');
    // Assume format:
    //   - [ ] Item title — agent-type — files: path1, path2
    // Extract agent and files from lines matching this pattern
    const lines = backlogContent.split('\n');
    for (const line of lines) {
      const match = line.match(/- \[\s*\]\s+(.+?)\s+—\s*(\S+)\s+—\s*(.+)/);
      if (match) {
        const [, itemName, agent, filesList] = match;
        const files = filesList
          .split(',')
          .map((f) => f.trim())
          .filter((f) => f);
        backlog.push({ item: itemName, agent, files });
      }
    }
  } catch (e) {
    console.error(`Failed to parse backlog: ${e.message}`);
    process.exit(1);
  }

  const result = validateWaveDispatch({ backlog, claudemdPath: claudeMdPath, repoRoot });

  console.log(JSON.stringify(result, null, 2));
  process.exit(result.safe ? 0 : 1);
}

/**
 * Export for use in orchestrator
 */
export default validateWaveDispatch;
