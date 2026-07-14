#!/usr/bin/env node
/**
 * Aesop Fleet State MCP Server
 *
 * Read-only MCP server (stdio transport) exposing fleet operational status.
 * Resolves AESOP_ROOT from env or --root flag; gracefully handles missing state files.
 *
 * Tools:
 *   fleet_status    - heartbeat ages + orchestrator status + alert count
 *   fleet_agents    - active agents from transcripts via dash-extra.mjs passthrough
 *   fleet_tracker   - open items by lane from state/tracker.json
 *   fleet_cost      - per-model token totals from state/ledger/OUTCOMES-LEDGER.md
 *
 * All tools are read-only; no state mutations, no file writes.
 */

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';

// ============================================================================
// Configuration & Initialization
// ============================================================================

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

function expandPath(pathStr) {
  if (!pathStr) return pathStr;
  if (pathStr.startsWith('~')) {
    return path.join(os.homedir(), pathStr.slice(1));
  }
  return pathStr.replace(/\$\{?([A-Z_]+)\}?/gi, (match, varName) => {
    return process.env[varName] || match;
  });
}

// Parse --root from argv
function parseRootArg() {
  const idx = process.argv.indexOf('--root');
  if (idx !== -1 && idx + 1 < process.argv.length) {
    return process.argv[idx + 1];
  }
  return null;
}

const rootArg = parseRootArg();
const AESOP_ROOT = rootArg || process.env.AESOP_ROOT || path.join(os.homedir(), 'aesop');
const config = loadConfigFile(AESOP_ROOT);

const STATE_ROOT = path.resolve(
  expandPath(
    process.env.AESOP_STATE_ROOT ||
    config.state_root ||
    path.join(AESOP_ROOT, 'state')
  )
);

const TRANSCRIPTS_ROOT = path.resolve(
  expandPath(
    process.env.AESOP_TRANSCRIPTS_ROOT ||
    config.transcripts_root ||
    path.join(os.homedir(), '.claude', 'projects')
  )
);

// File paths
const WATCHDOG_HEARTBEAT = path.join(STATE_ROOT, '.watchdog-heartbeat');
const MONITOR_HEARTBEAT = path.join(STATE_ROOT, '.monitor-heartbeat');
const ALERTS_LOG = path.join(STATE_ROOT, 'SECURITY-ALERTS.log');
const TRACKER_FILE = path.join(STATE_ROOT, 'tracker.json');
const ORCH_STATUS_FILE = path.join(STATE_ROOT, 'orchestrator-status.json');
const LEDGER_FILE = path.join(STATE_ROOT, 'ledger', 'OUTCOMES-LEDGER.md');

// ============================================================================
// MCP Protocol & JSON-RPC Utilities
// ============================================================================

class MCP {
  constructor() {
    this.requestId = 0;
    this.rl = createInterface({ input: process.stdin, output: process.stdout });
  }

  /**
   * Read one JSON-RPC line from stdin, parse, and return
   */
  async readRequest() {
    return new Promise((resolve) => {
      this.rl.once('line', (line) => {
        try {
          const req = JSON.parse(line);
          resolve(req);
        } catch (e) {
          resolve(null);
        }
      });
    });
  }

  /**
   * Write one JSON-RPC response to stdout
   */
  writeResponse(response) {
    process.stdout.write(JSON.stringify(response) + '\n');
  }

  /**
   * Write JSON-RPC error response
   */
  writeError(requestId, code, message, data = null) {
    const response = {
      jsonrpc: '2.0',
      id: requestId,
      error: { code, message }
    };
    if (data !== null) {
      response.error.data = data;
    }
    this.writeResponse(response);
  }

  /**
   * Write JSON-RPC result response
   */
  writeResult(requestId, result) {
    this.writeResponse({
      jsonrpc: '2.0',
      id: requestId,
      result
    });
  }

  /**
   * Close the MCP server
   */
  close() {
    this.rl.close();
  }
}

const mcp = new MCP();

// ============================================================================
// Tool Implementations (Read-Only)
// ============================================================================

/**
 * fleet_status: Expose heartbeat ages, orchestrator status, alert count
 */
function getFleetStatus() {
  const result = {
    watchdog: null,
    monitor: null,
    orchestrator: null,
    alerts: null
  };

  // Read watchdog heartbeat
  try {
    if (fs.existsSync(WATCHDOG_HEARTBEAT)) {
      const content = fs.readFileSync(WATCHDOG_HEARTBEAT, 'utf8').trim();
      if (content) {
        const timestamp = parseInt(content, 10);
        if (!isNaN(timestamp)) {
          const now = Math.floor(Date.now() / 1000);
          const ageSec = now - timestamp;
          const ageBucketed = Math.floor(ageSec / 3) * 3;
          const alive = ageSec < 300 ? 'ALIVE' : 'STALE';
          result.watchdog = {
            alive,
            age_seconds: ageBucketed,
            threshold_seconds: 300
          };
        }
      }
    }
  } catch (e) {
    // Silently ignore errors
  }

  // Read monitor heartbeat
  try {
    let monitorHb = MONITOR_HEARTBEAT;
    if (!fs.existsSync(monitorHb)) {
      const altPath = path.join(AESOP_ROOT, 'monitor', '.monitor-heartbeat');
      if (fs.existsSync(altPath)) {
        monitorHb = altPath;
      }
    }
    if (fs.existsSync(monitorHb)) {
      const content = fs.readFileSync(monitorHb, 'utf8').trim();
      if (content) {
        const timestamp = parseInt(content, 10);
        if (!isNaN(timestamp)) {
          const now = Math.floor(Date.now() / 1000);
          const ageSec = now - timestamp;
          const ageBucketed = Math.floor(ageSec / 3) * 3;
          const alive = ageSec < 3600 ? 'ALIVE' : 'STALE';
          result.monitor = {
            alive,
            age_seconds: ageBucketed,
            threshold_seconds: 3600
          };
        }
      }
    }
  } catch (e) {
    // Silently ignore errors
  }

  // Read orchestrator status if it exists
  try {
    if (fs.existsSync(ORCH_STATUS_FILE)) {
      const content = fs.readFileSync(ORCH_STATUS_FILE, 'utf8').trim();
      if (content) {
        const parsed = JSON.parse(content);
        result.orchestrator = parsed;
      }
    }
  } catch (e) {
    // Silently ignore errors
  }

  // Count alerts (skip NOTE:/RESOLVED-FP lines)
  try {
    if (fs.existsSync(ALERTS_LOG)) {
      const lines = fs.readFileSync(ALERTS_LOG, 'utf8').trim().split('\n');
      const unreviewed = lines.filter(
        line => line.trim() && !line.includes('NOTE:') && !line.includes('RESOLVED-FP')
      );
      result.alerts = {
        count: unreviewed.length,
        sample_lines: unreviewed.slice(-3)
      };
    }
  } catch (e) {
    // Silently ignore errors
  }

  return result;
}

/**
 * fleet_agents: Invoke dash-extra.mjs --json and passthrough result
 */
async function getFleetAgents() {
  return new Promise((resolve) => {
    const dashExtraPath = path.join(AESOP_ROOT, 'dash', 'dash-extra.mjs');

    if (!fs.existsSync(dashExtraPath)) {
      resolve({ absent: true, agents: [] });
      return;
    }

    try {
      const proc = spawn('node', [dashExtraPath, '--json'], {
        cwd: AESOP_ROOT,
        env: {
          ...process.env,
          AESOP_ROOT,
          AESOP_STATE_ROOT: STATE_ROOT,
          AESOP_TRANSCRIPTS_ROOT: TRANSCRIPTS_ROOT
        },
        timeout: 5000
      });

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      proc.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      proc.on('close', (code) => {
        if (code === 0 && stdout.trim()) {
          try {
            const agents = JSON.parse(stdout);
            resolve({ absent: false, agents: Array.isArray(agents) ? agents : [] });
          } catch (e) {
            resolve({ absent: false, agents: [] });
          }
        } else {
          resolve({ absent: false, agents: [] });
        }
      });

      proc.on('error', (err) => {
        resolve({ absent: false, agents: [] });
      });
    } catch (e) {
      resolve({ absent: false, agents: [] });
    }
  });
}

/**
 * fleet_tracker: Read items from tracker.json, grouped by lane
 */
function getFleetTracker() {
  const result = {
    absent: !fs.existsSync(TRACKER_FILE),
    by_lane: {}
  };

  try {
    if (fs.existsSync(TRACKER_FILE)) {
      const content = fs.readFileSync(TRACKER_FILE, 'utf8').trim();
      if (content) {
        const tracker = JSON.parse(content);
        const items = tracker.items || [];

        // Group by lane
        const byLane = {};
        for (const item of items) {
          const lane = item.lane || 'unknown';
          if (!byLane[lane]) {
            byLane[lane] = [];
          }
          byLane[lane].push({
            id: item.id,
            title: item.title,
            priority: item.priority,
            status: item.status,
            tags: item.tags || []
          });
        }
        result.by_lane = byLane;
      }
    }
  } catch (e) {
    // Silently ignore errors
  }

  return result;
}

/**
 * fleet_cost: Parse ledger and aggregate token counts by model
 */
function getFleetCost() {
  const result = {
    absent: !fs.existsSync(LEDGER_FILE),
    by_model: {},
    total_tokens_in: 0,
    total_tokens_out: 0
  };

  try {
    if (fs.existsSync(LEDGER_FILE)) {
      const lines = fs.readFileSync(LEDGER_FILE, 'utf8').split('\n');

      for (const line of lines) {
        // Parse markdown table row: | ts | agent_type | model | dur | tokens_in | tokens_out | verdict |
        const match = line.match(/^\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|/);
        if (!match) continue;

        const model = match[3].trim() || '-';
        const tokensIn = parseInt(match[5], 10) || 0;
        const tokensOut = parseInt(match[6], 10) || 0;

        if (!result.by_model[model]) {
          result.by_model[model] = {
            tokens_in: 0,
            tokens_out: 0,
            total_tokens: 0,
            count: 0
          };
        }

        result.by_model[model].tokens_in += tokensIn;
        result.by_model[model].tokens_out += tokensOut;
        result.by_model[model].total_tokens += tokensIn + tokensOut;
        result.by_model[model].count += 1;

        result.total_tokens_in += tokensIn;
        result.total_tokens_out += tokensOut;
      }
    }
  } catch (e) {
    // Silently ignore errors
  }

  return result;
}

// ============================================================================
// MCP Tool & Resource Definitions
// ============================================================================

const TOOLS = [
  {
    name: 'fleet_status',
    description: 'Get fleet operational status: daemon/monitor heartbeats, orchestrator activity, security alerts',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'fleet_agents',
    description: 'List active Claude agents from transcript directory',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'fleet_tracker',
    description: 'Get fleet work items from tracker.json, grouped by lane (ranked/proposed/in-progress/done)',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  },
  {
    name: 'fleet_cost',
    description: 'Get per-model token usage totals from outcomes ledger',
    inputSchema: {
      type: 'object',
      properties: {}
    }
  }
];

// ============================================================================
// MCP Request Handlers
// ============================================================================

async function handleInitialize(requestId, params) {
  mcp.writeResult(requestId, {
    protocolVersion: '2024-11-05',
    capabilities: {
      tools: {}
    },
    serverInfo: {
      name: 'aesop-fleet',
      version: '1.0.0'
    }
  });
}

async function handleToolsList(requestId, params) {
  mcp.writeResult(requestId, {
    tools: TOOLS
  });
}

async function handleToolCall(requestId, params) {
  const { name, arguments: args } = params;

  try {
    let result;
    switch (name) {
      case 'fleet_status':
        result = getFleetStatus();
        break;
      case 'fleet_agents':
        result = await getFleetAgents();
        break;
      case 'fleet_tracker':
        result = getFleetTracker();
        break;
      case 'fleet_cost':
        result = getFleetCost();
        break;
      default:
        mcp.writeError(requestId, -32601, `Unknown tool: ${name}`);
        return;
    }

    mcp.writeResult(requestId, {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2)
        }
      ]
    });
  } catch (err) {
    mcp.writeError(requestId, -32603, `Tool execution error: ${err.message}`);
  }
}

// ============================================================================
// Main Loop
// ============================================================================

async function main() {
  try {
    while (true) {
      const request = await mcp.readRequest();

      if (!request) {
        continue;
      }

      const { jsonrpc, id, method, params } = request;

      if (jsonrpc !== '2.0') {
        mcp.writeError(id, -32600, 'Invalid JSON-RPC version');
        continue;
      }

      switch (method) {
        case 'initialize':
          await handleInitialize(id, params || {});
          break;
        case 'tools/list':
          await handleToolsList(id, params || {});
          break;
        case 'tools/call':
          await handleToolCall(id, params || {});
          break;
        default:
          mcp.writeError(id, -32601, `Unknown method: ${method}`);
      }
    }
  } catch (err) {
    process.stderr.write(`Fatal error: ${err.message}\n`);
    process.exit(1);
  }
}

main().catch((err) => {
  process.stderr.write(`Fatal error: ${err.message}\n`);
  process.exit(1);
});
