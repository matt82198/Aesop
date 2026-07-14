---
name: healthcheck
description: Check fleet health — one colored ball (heartbeats, alerts, orchestrator, tracker items).
version: 1.0.0
---

# Healthcheck — one colored health ball

One-line status indicator for aesop fleet health, driven by aggregated signals.

## Procedure

Run the healthcheck tool and interpret the ball:

```bash
python tools/healthcheck.py
```

### Output interpretation

**🟢 Green**: All heartbeats fresh (watchdog <300s, monitor <3600s), no HIGH alerts

**🟡 Yellow**: Stale heartbeat OR unreviewed MED severity alert

**🔴 Red**: HIGH severity alert OR watchdog dead (>600s) while orchestrator actively dispatching

### Fixing issues

When healthcheck returns non-green, check the bullet-list reasons:

1. **Stale heartbeat**: Restart the relevant daemon (watchdog or monitor). Check `bash daemons/run-watchdog.sh --once` or monitor process.
2. **Unreviewed HIGH alert**: Review SECURITY-ALERTS.log, prefix line with `NOTE:` or `RESOLVED-FP` to mark reviewed.
3. **Unreviewed MED alert**: Same as HIGH — review and mark.
4. **Dead watchdog + active dispatch**: Critical issue — watchdog daemon crashed while orchestrator was dispatching agents. Check logs, restart watchdog, verify orchestrator stability.

### Machine-readable output

For integration with monitoring/dashboards, use `--json`:

```bash
python tools/healthcheck.py --json
```

Returns a JSON object with `ball`, `health` status, issues list, and tracker lane counts.
