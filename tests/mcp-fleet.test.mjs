#!/usr/bin/env node
/**
 * MCP Fleet Server End-to-End Test
 *
 * Spawns the server over stdio, drives JSON-RPC initialize + tools/list + one tools/call round-trip.
 * Verifies read-only behavior (no state mutations after calls).
 * Uses temp fixture root to ensure isolation.
 */

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createInterface } from 'node:readline';

// ============================================================================
// Test Harness
// ============================================================================

class MCPTestClient {
  constructor(process) {
    this.process = process;
    this.requestId = 0;
    this.pendingResponses = new Map();

    // Set up readline for reading server output line-by-line
    this.rl = createInterface({
      input: this.process.stdout
    });

    // Handle stderr for debugging
    this.process.stderr.on('data', (data) => {
      console.error(`[server stderr] ${data}`);
    });

    // Listen for lines from server
    this.rl.on('line', (line) => {
      try {
        const response = JSON.parse(line);
        const id = response.id;
        const callbacks = this.pendingResponses.get(id);
        if (callbacks) {
          callbacks.resolve(response);
          this.pendingResponses.delete(id);
        }
      } catch (e) {
        console.error(`Failed to parse server response: ${line}`);
      }
    });
  }

  /**
   * Send a JSON-RPC request and wait for response
   */
  async request(method, params = {}) {
    const id = ++this.requestId;
    const request = {
      jsonrpc: '2.0',
      id,
      method,
      params
    };

    // Set up promise for response
    const responsePromise = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Timeout waiting for response to request ${id}`));
      }, 5000);

      this.pendingResponses.set(id, {
        resolve: (response) => {
          clearTimeout(timeout);
          resolve(response);
        }
      });
    });

    // Send request
    this.process.stdin.write(JSON.stringify(request) + '\n');

    // Wait for response
    const response = await responsePromise;
    return response;
  }

  /**
   * Close the client
   */
  close() {
    this.rl.close();
    this.process.kill();
  }
}

// ============================================================================
// Test Suite
// ============================================================================

async function runTests() {
  console.log('Starting MCP Fleet Server Tests...\n');

  // Create temp fixture root with minimal state structure
  const fixtureRoot = mkdtempSync(join(tmpdir(), 'aesop-mcp-test-'));
  const stateRoot = join(fixtureRoot, 'state');
  const ledgerDir = join(stateRoot, 'ledger');

  console.log(`Fixture root: ${fixtureRoot}`);

  // Set up minimal test state files
  const fs = await import('node:fs');
  fs.mkdirSync(stateRoot, { recursive: true });
  fs.mkdirSync(ledgerDir, { recursive: true });

  // Create heartbeat file (current epoch)
  const now = Math.floor(Date.now() / 1000);
  fs.writeFileSync(join(stateRoot, '.watchdog-heartbeat'), `${now}`);

  // Create tracker.json
  const tracker = {
    version: 1,
    items: [
      {
        id: '123456',
        title: 'Test item 1',
        priority: 'P1',
        status: 'todo',
        lane: 'ranked',
        tags: ['test'],
        created_at: '2024-01-01T00:00:00Z',
        completed_at: null
      },
      {
        id: '789012',
        title: 'Test item 2',
        priority: 'P2',
        status: 'in-progress',
        lane: 'in-progress',
        tags: [],
        created_at: '2024-01-02T00:00:00Z',
        completed_at: null
      }
    ]
  };
  fs.writeFileSync(join(stateRoot, 'tracker.json'), JSON.stringify(tracker, null, 2));

  // Create orchestrator status
  const orchStatus = {
    activity: 'idle',
    phase: 'awaiting-work',
    timestamp: new Date().toISOString()
  };
  fs.writeFileSync(join(stateRoot, 'orchestrator-status.json'), JSON.stringify(orchStatus));

  // Create alerts log
  fs.writeFileSync(join(stateRoot, 'SECURITY-ALERTS.log'), 'ALERT: test alert 1\nNOTE: resolved false positive\nALERT: test alert 2\n');

  // Create ledger with sample data
  const ledgerContent = `| ISO ts | agent_type | model | duration_sec | tokens_in | tokens_out | verdict |
|--------|------------|-------|--------------|-----------|------------|--------|
| 2024-01-01T10:00:00 | Agent | claude-haiku-4 | 30 | 500 | 250 | OK |
| 2024-01-01T10:05:00 | Agent | claude-opus | 60 | 1000 | 500 | OK |
| 2024-01-01T10:10:00 | Agent | claude-haiku-4 | 25 | 400 | 200 | OK |
`;
  fs.writeFileSync(join(ledgerDir, 'OUTCOMES-LEDGER.md'), ledgerContent);

  // Spawn server with fixture root
  console.log('Spawning server...');
  const serverProcess = spawn('node', [
    './mcp/server.mjs',
    '--root',
    fixtureRoot
  ], {
    env: {
      ...process.env,
      AESOP_ROOT: fixtureRoot,
      AESOP_STATE_ROOT: stateRoot
    }
  });

  // Give server a moment to start
  await new Promise(r => setTimeout(r, 100));

  const client = new MCPTestClient(serverProcess);

  let testsPassed = 0;
  let testsFailed = 0;

  try {
    // Test 1: Initialize
    console.log('Test 1: Initialize...');
    const initResp = await client.request('initialize', {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: {
        name: 'test-client',
        version: '1.0.0'
      }
    });

    if (initResp.result && initResp.result.serverInfo) {
      console.log('✓ Initialize succeeded\n');
      testsPassed++;
    } else {
      console.log('✗ Initialize failed\n');
      testsFailed++;
    }

    // Test 2: tools/list
    console.log('Test 2: tools/list...');
    const listResp = await client.request('tools/list', {});

    if (listResp.result && Array.isArray(listResp.result.tools) && listResp.result.tools.length === 4) {
      const toolNames = listResp.result.tools.map(t => t.name).sort();
      const expected = ['fleet_agents', 'fleet_cost', 'fleet_status', 'fleet_tracker'];
      if (JSON.stringify(toolNames) === JSON.stringify(expected)) {
        console.log(`✓ tools/list succeeded, found 4 tools: ${toolNames.join(', ')}\n`);
        testsPassed++;
      } else {
        console.log(`✗ Unexpected tools: ${toolNames.join(', ')}\n`);
        testsFailed++;
      }
    } else {
      console.log('✗ tools/list failed\n');
      testsFailed++;
    }

    // Test 3: fleet_status call
    console.log('Test 3: fleet_status tool call...');
    const statusResp = await client.request('tools/call', {
      name: 'fleet_status',
      arguments: {}
    });

    if (statusResp.result && statusResp.result.content && Array.isArray(statusResp.result.content)) {
      const content = statusResp.result.content[0];
      if (content.type === 'text') {
        const statusData = JSON.parse(content.text);
        if (statusData.watchdog && statusData.watchdog.alive === 'ALIVE') {
          console.log('✓ fleet_status succeeded, watchdog is ALIVE\n');
          testsPassed++;
        } else {
          console.log('✗ Watchdog status unexpected\n');
          testsFailed++;
        }
      } else {
        console.log('✗ Content type unexpected\n');
        testsFailed++;
      }
    } else {
      console.log('✗ fleet_status failed\n');
      testsFailed++;
    }

    // Test 4: fleet_tracker call
    console.log('Test 4: fleet_tracker tool call...');
    const trackerResp = await client.request('tools/call', {
      name: 'fleet_tracker',
      arguments: {}
    });

    if (trackerResp.result && trackerResp.result.content) {
      const content = trackerResp.result.content[0];
      if (content.type === 'text') {
        const trackerData = JSON.parse(content.text);
        if (trackerData.by_lane && trackerData.by_lane.ranked && trackerData.by_lane.ranked.length === 1) {
          console.log(`✓ fleet_tracker succeeded, found ${trackerData.by_lane.ranked.length} ranked items\n`);
          testsPassed++;
        } else {
          console.log('✗ Tracker items unexpected\n');
          testsFailed++;
        }
      } else {
        console.log('✗ Content type unexpected\n');
        testsFailed++;
      }
    } else {
      console.log('✗ fleet_tracker failed\n');
      testsFailed++;
    }

    // Test 5: fleet_cost call
    console.log('Test 5: fleet_cost tool call...');
    const costResp = await client.request('tools/call', {
      name: 'fleet_cost',
      arguments: {}
    });

    if (costResp.result && costResp.result.content) {
      const content = costResp.result.content[0];
      if (content.type === 'text') {
        const costData = JSON.parse(content.text);
        if (costData.by_model && costData.by_model['claude-haiku-4'] && costData.total_tokens_in > 0) {
          console.log(`✓ fleet_cost succeeded, found cost data for ${Object.keys(costData.by_model).length} models\n`);
          testsPassed++;
        } else {
          console.log('✗ Cost data unexpected\n');
          testsFailed++;
        }
      } else {
        console.log('✗ Content type unexpected\n');
        testsFailed++;
      }
    } else {
      console.log('✗ fleet_cost failed\n');
      testsFailed++;
    }

    // Test 6: Read-only verification (verify no mutations after calls)
    console.log('Test 6: Read-only verification...');
    const trackerMtime1 = fs.statSync(join(stateRoot, 'tracker.json')).mtimeMs;
    await client.request('tools/call', {
      name: 'fleet_tracker',
      arguments: {}
    });
    const trackerMtime2 = fs.statSync(join(stateRoot, 'tracker.json')).mtimeMs;

    if (trackerMtime1 === trackerMtime2) {
      console.log('✓ Read-only verified: tracker.json unchanged after tool call\n');
      testsPassed++;
    } else {
      console.log('✗ Read-only check failed: tracker.json was modified\n');
      testsFailed++;
    }

  } catch (err) {
    console.error(`Test error: ${err.message}`);
    testsFailed++;
  } finally {
    // Cleanup
    client.close();
    await new Promise(r => setTimeout(r, 100));
    rmSync(fixtureRoot, { recursive: true, force: true });

    console.log(`\nTest Results: ${testsPassed} passed, ${testsFailed} failed`);
    process.exit(testsFailed > 0 ? 1 : 0);
  }
}

// Run tests
runTests().catch(err => {
  console.error(`Fatal error: ${err.message}`);
  process.exit(1);
});
