# Aesop Web Dashboard

A lightweight, self-contained web dashboard for real-time fleet monitoring. Replaces the bash TUI with a modern, responsive HTML interface that displays heartbeats, active agents, security alerts, and inbox status.

## Launch

```bash
export AESOP_ROOT=$HOME/aesop
python $AESOP_ROOT/ui/serve.py
```

Prints `Dashboard: http://localhost:8770` and serves until Ctrl-C.

### Configuration

The dashboard reads configuration from `aesop.config.json` if present. Key paths:

- **`AESOP_ROOT`** (env var): Path to aesop installation (default: `$HOME/aesop`)
- **`PORT`** (env var): Dashboard port (default: `8770`)
- **`AESOP_TRANSCRIPTS_ROOT`** (env var): Path to Claude session transcripts (default: `~/.claude/projects`)

Example with custom paths:

```bash
export AESOP_ROOT=/opt/aesop
export AESOP_TRANSCRIPTS_ROOT=/home/user/.claude/projects
export PORT=9000
python $AESOP_ROOT/ui/serve.py
```

## Features

### Header Status
- **Watchdog Status**: Daemon heartbeat age + ALIVE/STALE (300s threshold)
- **Monitor Status**: Orchestration monitor liveness + age (3600s threshold)
- **Security Alerts**: Count of unreviewed alerts
- **Running Agents**: Number of active subagents (<2 min old)

### Panels

1. **Inbox** (top): Text input → Send button appends to `state/ui-inbox.md`. Orchestrator reads each turn.
2. **Fleet Agents**: Currently-running subagents with status and hint text (refreshed every 3s)
3. **Repos Status**: Repository sync status from `state/.watchdog-repos.json`
4. **Recent Events**: Last 8 lines from `state/FLEET-BACKUP.log`
5. **Security Alerts**: Unreviewed lines from `scan/SECURITY-ALERTS.log` (skips NOTE:/RESOLVED-FP)
6. **Main-Thread Prompts**: Last ~12 messages from newest session JSONL in transcripts root

### Inbox Contract

POST `/submit` appends timestamped line to `state/ui-inbox.md`:

```markdown
# UI Inbox — orchestrator reads each turn / on /power

- [2026-07-11T14:23:45.123456] user's task here
- [2026-07-11T14:24:12.654321] another task
```

## Requirements

- **Python 3.10+**: stdlib-only (no external dependencies)
- **Node.js v18+** (optional): required for agent detection via `dash/dash-extra.mjs`

## Robustness

- Every data source is wrapped with exception handling
- Missing or locked files → placeholder text (never 500 error)
- `/data` endpoint always returns valid JSON
- Auto-refresh every 3s via client-side fetch

## Path Configuration

If you have a non-standard setup, set paths in `aesop.config.json`:

```json
{
  "state_root": "/path/to/state",
  "scan_root": "/path/to/scan",
  "transcripts_root": "/path/to/transcripts"
}
```

Or use environment variables:

```bash
export AESOP_TRANSCRIPTS_ROOT=/my/custom/transcripts/path
python ui/serve.py
```

## Troubleshooting

### "Agents panel unavailable"
- Ensure `node` is on PATH and `dash/dash-extra.mjs` exists
- Install Node.js v18+

### Dashboard shows no data
- Verify `AESOP_ROOT` is set correctly: `echo $AESOP_ROOT`
- Check that `state/` directory exists and is readable
- Verify `aesop.config.json` is valid JSON (if present)

### Can't connect to http://localhost:8770
- Check port is not in use: `lsof -i :8770` (macOS/Linux) or `netstat -ano | findstr :8770` (Windows)
- Try a different port: `export PORT=9000`

## Integration with Claude Code

To display main-thread transcripts, ensure `AESOP_TRANSCRIPTS_ROOT` points to your Claude session directory. Example:

```bash
export AESOP_TRANSCRIPTS_ROOT=$HOME/.claude/projects/my-project
python $AESOP_ROOT/ui/serve.py
```

See the main Aesop README for full orchestration setup.
