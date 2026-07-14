# mcp/ — Read-Only Fleet State MCP Server

**Purpose**: Expose Aesop fleet operational status as a Model Context Protocol (MCP) server for Claude Code and other MCP clients.

## Server

**File**: `server.mjs` — Stdio-transport MCP server implementing the JSON-RPC 2.0 protocol.

**Configuration**:
- `AESOP_ROOT` environment variable or `--root <path>` command-line flag (no hardcoded paths)
- `AESOP_STATE_ROOT` environment variable for state directory override (default: `AESOP_ROOT/state`)
- `AESOP_TRANSCRIPTS_ROOT` environment variable for transcript directory override (default: `~/.claude/projects`)
- Reads `aesop.config.json` from AESOP_ROOT for optional config file overrides

**Launch**:
```bash
node mcp/server.mjs [--root /path/to/aesop]
```

The server reads from stdin, writes JSON-RPC responses to stdout. Suitable for direct MCP integration or debugging via manual JSON-RPC frames.

## Tools

All tools are **strictly read-only**: no state mutations, no file writes, no shell-outs except the minimal dash-extra.mjs passthrough for fleet_agents.

### fleet_status

**Description**: Get fleet operational status — daemon heartbeats, monitor heartbeat, orchestrator activity, alert count.

**Input**: No arguments.

**Output** (JSON):
```json
{
  "watchdog": {
    "alive": "ALIVE" | "STALE",
    "age_seconds": <bucketed>,
    "threshold_seconds": 300
  },
  "monitor": {
    "alive": "ALIVE" | "STALE",
    "age_seconds": <bucketed>,
    "threshold_seconds": 3600
  },
  "orchestrator": <parsed orchestrator-status.json> or null,
  "alerts": {
    "count": <int>,
    "sample_lines": [<last 3 unreviewed lines>]
  }
}
```

**Missing files**: If a file doesn't exist, the corresponding field is `null`. The response never crashes; missing state files are reported gracefully with `absent` markers where applicable.

### fleet_agents

**Description**: List active Claude agents from transcript directory. Invokes `dash-extra.mjs --json` with environment variables for path portability.

**Input**: No arguments.

**Output** (JSON):
```json
{
  "absent": <bool>,
  "agents": [
    {
      "project": <string>,
      "taskLabel": <string>,
      "promptFull": <string>,
      "runtimeSeconds": <int>,
      "tokensUsed": <int>,
      "startedAt": <ISO string>,
      "lastActivity": <ISO string>
    },
    ...
  ]
}
```

**Design notes**:
- Passes through `dash-extra.mjs --json` output (no reimplementation).
- Timeout: 5 seconds. On timeout or error, returns empty agents list.
- Environment variables (`AESOP_ROOT`, `AESOP_STATE_ROOT`, `AESOP_TRANSCRIPTS_ROOT`) are set before invoking dash-extra to ensure portable transcript discovery.

### fleet_tracker

**Description**: Get fleet work items from `tracker.json`, grouped by lane.

**Input**: No arguments.

**Output** (JSON):
```json
{
  "absent": <bool>,
  "by_lane": {
    "ranked": [
      {
        "id": <string>,
        "title": <string>,
        "priority": "P0" | "P1" | "P2",
        "status": "todo" | "in-progress" | "done",
        "tags": [<string>, ...]
      },
      ...
    ],
    "in-progress": [ ... ],
    "done": [ ... ],
    ...
  }
}
```

**Lanes**: Each lane is optional and present only if items exist in it. Common lanes: `ranked`, `proposed`, `in-progress`, `done`.

### fleet_cost

**Description**: Get per-model token usage totals from the fleet outcomes ledger (`state/ledger/OUTCOMES-LEDGER.md`).

**Input**: No arguments.

**Output** (JSON):
```json
{
  "absent": <bool>,
  "by_model": {
    "claude-haiku-4": {
      "tokens_in": <int>,
      "tokens_out": <int>,
      "total_tokens": <int>,
      "count": <int>
    },
    "claude-opus": { ... },
    ...
  },
  "total_tokens_in": <int>,
  "total_tokens_out": <int>
}
```

**Design notes**:
- Parses markdown table rows from the ledger file.
- Reports **token counts only** — no invented dollar figures.
- Gracefully handles missing or malformed lines (skips with no error).

## MCP Integration

### Claude Code (claude.json)

To register the server in Claude Code:

```json
{
  "mcp": {
    "aesop-fleet": {
      "command": "node",
      "args": [
        "/path/to/aesop/mcp/server.mjs",
        "--root",
        "/path/to/aesop"
      ],
      "env": {
        "AESOP_ROOT": "/path/to/aesop"
      }
    }
  }
}
```

### Portable Setup

For portable configuration (no hardcoded user paths), use environment variables:

```bash
export AESOP_ROOT=/path/to/aesop
export AESOP_STATE_ROOT=/path/to/state  # optional override
export AESOP_TRANSCRIPTS_ROOT=/path/to/transcripts  # optional override
node /path/to/aesop/mcp/server.mjs
```

Or use the `--root` flag:

```bash
node /path/to/aesop/mcp/server.mjs --root /path/to/aesop
```

## Invariants & Guarantees

1. **Strictly read-only**: All tools are read-only. Zero state mutations, zero file writes.
2. **No shell execution** (except dash-extra.mjs invocation with timeout): Minimizes surface area for injection or performance issues.
3. **Graceful degradation**: Missing state files → empty results with `absent: true` markers, never a crash.
4. **No external dependencies**: Plain Node.js (no npm packages). Server.mjs uses only stdlib modules: `fs`, `path`, `os`, `child_process`, `readline`.
5. **JSON-RPC 2.0 compliant**: Standard request/response format with proper error codes.
6. **Portable paths**: All paths resolved from AESOP_ROOT, AESOP_STATE_ROOT, AESOP_TRANSCRIPTS_ROOT env vars or config file. No hardcoded paths like `/home/user/aesop`.

## Testing

See `tests/mcp-fleet.test.mjs` for end-to-end tests:
- Spawn server over stdio
- Drive JSON-RPC initialize + tools/list + tools/call round-trips
- Validate read-only behavior (no state mutations after calls)
- Verify fixture isolation (temp state root)

Run:
```bash
npm test  # or
node tests/mcp-fleet.test.mjs
```

## Files

- **server.mjs** — Main MCP server implementation (stdio, JSON-RPC 2.0)
- **package.json** — Minimal metadata; no external dependencies
- **CLAUDE.md** — This file
