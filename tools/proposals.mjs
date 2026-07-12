#!/usr/bin/env node
/**
 * proposals.mjs — Proposal lifecycle management tool
 *
 * Commands:
 *   list [--file PATH]              List all pending proposals (signal key + status)
 *   accept <signal-key> [--file PATH]  Move proposal to PROPOSALS-LOG.md as ACCEPTED
 *   reject <signal-key> [--file PATH]  Move proposal to PROPOSALS-LOG.md as REJECTED
 *
 * Default file: monitor/PROPOSALS.md
 * Log file (auto): same directory as PROPOSALS.md, named PROPOSALS-LOG.md
 */

import fs from 'node:fs';
import path from 'node:path';

// === Arg parsing ===
const args = process.argv.slice(2);
let command = '';
let signalKey = '';
let proposalsFile = 'monitor/PROPOSALS.md';

// Parse args: command [arg] [--file path]
if (args.length === 0) {
  usage();
  process.exit(1);
}

command = args[0];

// Find --file flag
let fileIdx = args.indexOf('--file');
if (fileIdx !== -1 && fileIdx + 1 < args.length) {
  proposalsFile = args[fileIdx + 1];
}

// Extract signal key for accept/reject
if (command === 'accept' || command === 'reject') {
  // Find first non-flag arg after command
  for (let i = 1; i < args.length; i++) {
    if (!args[i].startsWith('--')) {
      signalKey = args[i];
      break;
    }
  }
  if (!signalKey) {
    console.error(`Error: ${command} requires a signal-key argument`);
    process.exit(1);
  }
}

if (command !== 'list' && command !== 'accept' && command !== 'reject') {
  console.error(`Error: unknown command '${command}'`);
  usage();
  process.exit(1);
}

// === Core functions ===

/**
 * Parse PROPOSALS.md into proposal objects
 * Format per monitor/collect-signals.mjs:
 * ## <signal-key> — <timestamp>
 * **Signal:** <signal-key>
 * **Problem:** <problem>
 * **Suggested change:** <change>
 * ---
 */
function parseProposals(content) {
  const proposals = [];
  // Split on line containing only "---"
  const blocks = content.split(/\n---\n/);

  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];
    const trimmed = block.trim();
    if (!trimmed) continue;

    // Extract signal key from "**Signal:** <key>" line
    const signalMatch = trimmed.match(/\*\*Signal:\*\*\s+(\S+)/);
    if (!signalMatch) continue;

    const key = signalMatch[1];
    const firstLine = trimmed.split('\n')[0]; // e.g., "## signal-key — timestamp"

    proposals.push({
      key,
      firstLine,
      block: trimmed, // Store trimmed block (without leading/trailing whitespace)
      originalBlock: block, // Store original block with original whitespace
    });
  }

  return proposals;
}

/**
 * List proposals
 */
function listProposals() {
  let content = '';
  try {
    content = fs.readFileSync(proposalsFile, 'utf8');
  } catch {
    console.log('No proposals file found.');
    process.exit(0);
  }

  const proposals = parseProposals(content);
  if (proposals.length === 0) {
    console.log('No proposals.');
    process.exit(0);
  }

  console.log(`Found ${proposals.length} proposal(s):\n`);
  for (const p of proposals) {
    console.log(`  ${p.key}`);
    console.log(`    ${p.firstLine}`);
    console.log(`    Status: PENDING`);
  }
}

/**
 * Move proposal from PROPOSALS.md to PROPOSALS-LOG.md
 */
function moveProposal(status) {
  let content = '';
  try {
    content = fs.readFileSync(proposalsFile, 'utf8');
  } catch {
    console.error(`Error: Could not read ${proposalsFile}`);
    process.exit(1);
  }

  // Check if already in log (idempotency check first)
  const logFile = path.join(path.dirname(proposalsFile), 'PROPOSALS-LOG.md');
  let logContent = '';
  if (fs.existsSync(logFile)) {
    try {
      logContent = fs.readFileSync(logFile, 'utf8');
    } catch {
      // Log file not readable; continue
    }
  }

  if (logContent.includes(`**Signal:** ${signalKey}`)) {
    console.log(`Notice: Signal key '${signalKey}' already moved to log; no-op.`);
    process.exit(0);
  }

  const proposals = parseProposals(content);
  const proposal = proposals.find(p => p.key === signalKey);

  if (!proposal) {
    console.error(`Error: Signal key '${signalKey}' not found in ${proposalsFile}`);
    process.exit(1);
  }

  // Remove proposal from source by rebuilding without this proposal
  // Split on separators and filter out the matching proposal
  const blocks = content.split(/\n---\n/);
  const filteredBlocks = blocks.filter(block => {
    const trimmed = block.trim();
    if (!trimmed) return true; // Keep empty blocks
    const signalMatch = trimmed.match(/\*\*Signal:\*\*\s+(\S+)/);
    if (!signalMatch) return true; // Keep non-proposal blocks
    return signalMatch[1] !== signalKey; // Filter out matching proposal
  });

  // Rebuild content with separators
  const updatedContent = filteredBlocks.map((b, i) => {
    if (i < filteredBlocks.length - 1 && b.trim()) {
      return b.trim();
    }
    return b.trim();
  }).filter(b => b).join('\n\n---\n\n');

  try {
    fs.writeFileSync(proposalsFile, updatedContent.trim() ? updatedContent + '\n' : '', 'utf8');
  } catch (e) {
    console.error(`Error: Could not write ${proposalsFile}: ${e.message}`);
    process.exit(1);
  }

  // Append to log with status heading
  const timestamp = new Date().toISOString();
  const logEntry = `## ${status} ${timestamp}\n\n${proposal.block}\n\n---\n`;

  try {
    if (!logContent) {
      fs.writeFileSync(logFile, logEntry, 'utf8');
    } else {
      fs.appendFileSync(logFile, logEntry, 'utf8');
    }
  } catch (e) {
    console.error(`Error: Could not write ${logFile}: ${e.message}`);
    process.exit(1);
  }

  console.log(`✓ Moved signal '${signalKey}' to ${status} in ${path.basename(logFile)}`);
}

// === Main ===
if (command === 'list') {
  listProposals();
} else if (command === 'accept') {
  moveProposal('ACCEPTED');
} else if (command === 'reject') {
  moveProposal('REJECTED');
}

function usage() {
  console.error(`
Usage:
  node proposals.mjs list [--file <path>]
  node proposals.mjs accept <signal-key> [--file <path>]
  node proposals.mjs reject <signal-key> [--file <path>]

Default file: monitor/PROPOSALS.md
Log file: same directory as PROPOSALS.md, named PROPOSALS-LOG.md
`);
}
