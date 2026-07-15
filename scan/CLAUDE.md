# scan/ — Example IOC/secret scanner template

The `fleet-scan.example.mjs` is a config-driven template for scanning committed code and fleet transcripts for security and alignment red-flags during each watchdog cycle.

## Setup

1. Copy `fleet-scan.example.mjs` → `fleet-scan.mjs` (in the same directory)
2. Edit the configuration section to match your fleet setup (REPOS array, PROJECT_ROOTS paths)
3. Configure paths via `aesop.config.json` or environment variables:
   - `AESOP_FLEET_ROOT`: root directory containing your project repositories
   - `AESOP_TRANSCRIPTS_ROOT`: root directory containing `~/.claude/projects` transcripts
4. Ensure `aesop.config.json` contains repo definitions (see `aesop.config.example.json`)

## How it works

When enabled (by copying to `fleet-scan.mjs`), the scanner:
- Runs every watchdog cycle (default: every 150s)
- Scans git repositories and transcript directories for patterns matching your configured IOC/secret rules
- Logs findings to `SECURITY-ALERTS.log` with severity (HIGH/MED/LOW)
- Never blocks the fleet (non-fatal, append-only)
- Marks reviewed findings with `NOTE:` or `RESOLVED-FP` prefix to skip future alerts

## Customization

Edit the `fleet-scan.mjs` rules section to add domain-specific checks:
- Pattern-based secret/credential detection
- Alignment violations (e.g., non-approved libraries, unclosed TODO markers)
- Transcript red-flags (e.g., cost anomalies, stalled agents)

Output findings via the `add(severity, kind, where, detail)` function; the scanner handles deduplication and logging.
