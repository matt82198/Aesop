---
name: fleet
description: One-shot fleet snapshot (agents, heartbeats, tracker lanes, orchestrator status).
version: 1.0.0
---

# Fleet — Snapshot of live fleet state

One-line status summary for aesop fleet operations, showing active agents, daemon health, tracker backlog, and orchestrator phase.

## Procedure

Run the fleet snapshot tool and parse the JSON output:

```bash
aesop fleet
```

### Output format

JSON object with:

- **timestamp**: ISO 8601 when snapshot was taken
- **aesop_root**: Fleet root directory (from AESOP_ROOT env or process.cwd())
- **heartbeats**: Object with watchdog and monitor pulse status
  - **watchdog**: age_seconds, status (OK/STALE/MISSING), threshold_seconds
  - **monitor**: age_seconds, status (OK/STALE/MISSING), threshold_seconds
- **agents**: Array of active agents OR unavailable message
  - Each agent: id, project, status, age_s, hint, startedAt, lastActivity, runtimeSeconds, tokensUsed, taskLabel, promptFull
- **tracker**: Tracker backlog counts by lane OR unavailable message
  - total_items: sum of all items
  - by_lane: object mapping lane names to counts
- **orchestrator**: Current orchestrator status OR unavailable message
  - activity, phase, timestamp (from state/orchestrator-status.json)

### Graceful degradation

All missing state files produce explicit `unavailable: "<reason>"` entries rather than crashing:

- watchdog heartbeat missing → `unavailable: "MISSING"`
- monitor heartbeat missing → `unavailable: "MISSING"`
- dash-extra.mjs not found → `agents: { unavailable: "dash-extra.mjs not found" }`
- tracker.json missing/malformed → `tracker: { unavailable: "tracker.json not found or malformed" }`
- orchestrator-status.json missing → `orchestrator: { unavailable: "orchestrator-status.json not found or malformed" }`

### Example output

```json
{
  "timestamp": "2024-07-17T14:32:05.123Z",
  "aesop_root": "/path/to/aesop",
  "heartbeats": {
    "watchdog": {
      "age_seconds": 42,
      "status": "OK",
      "threshold_seconds": 300
    },
    "monitor": {
      "age_seconds": 1203,
      "status": "OK",
      "threshold_seconds": 3600
    }
  },
  "agents": {
    "count": 2,
    "agents": [
      {
        "id": "a1b2c3d4e5f6g7h",
        "project": "aesop",
        "status": "running",
        "age_s": 35,
        "hint": "Implement /fleet CLI feature",
        "startedAt": "2024-07-17T14:31:30Z",
        "lastActivity": "2024-07-17T14:32:05Z",
        "runtimeSeconds": 35,
        "tokensUsed": 45000,
        "taskLabel": "FEATURE — fleet skill CLI part",
        "promptFull": "..."
      }
    ]
  },
  "tracker": {
    "total_items": 8,
    "by_lane": {
      "ranked": 3,
      "in-progress": 2,
      "proposed": 3
    }
  },
  "orchestrator": {
    "activity": "dispatching",
    "phase": "wave-14",
    "timestamp": "2024-07-17T14:32:00Z"
  }
}
```

### Integration with orchestrators

Orchestrators invoke `aesop fleet` (instead of ad-hoc state reads) to stay coupled to this canonical format. All data is read-only; the command never mutates state.

### Machine-readable parsing

Parse the JSON and check for `unavailable` fields at each level:

```javascript
const fleet = JSON.parse(output);
if (fleet.heartbeats.watchdog.unavailable) {
  console.log('Watchdog is', fleet.heartbeats.watchdog.unavailable);
} else {
  console.log('Watchdog is', fleet.heartbeats.watchdog.status, 'age', fleet.heartbeats.watchdog.age_seconds + 's');
}
```
