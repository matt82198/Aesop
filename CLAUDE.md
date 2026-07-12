# Aesop — Project CLAUDE.md



**What**: Open-source fable-fleet orchestration harness for Claude Code.



## Domain map



- **daemons/** — Watchdog daemon (repo backup, secret-scan gate, heartbeat) — see § daemons/ below

- **dash/** — TUI dashboard (watchdog-gui.sh, real-time fleet status) — see § dash/ below

- **monitor/** — Orchestration monitor (collect-signals.mjs, CHARTER.md, AUTO/PROPOSE logic) — see § monitor/ below

- **tools/** — Build utilities (secret_scan.py, agent-forensics.sh, launch_tui.py) — see § tools/ below

- **hooks/** — Git pre-push policy enforcement (branch protection, secret scanning) — see § hooks/ below

- **ui/** — Web dashboard (serve.py, realtime SSE, CSRF protection, collector thread) — see § ui/ below
- **bin/** — CLI scaffolder (Node.js entry point for aesop template) — see § bin/ below

- **docs/** — Architecture guides, cardinal rules, tutorials

- **tests/** � Test suites (shell, Node, Python) and fixtures � see � tests/ below
- **state/** — Runtime durable checkpoints (git-ignored, created by daemons)



## Key principles



1. **Subagents are always Haiku** (cost optimization at scale).

2. **Orchestrator on main thread only** (durable, observable).

3. **State committed to git** (STATE.md, BUILDLOG.md survive wipes).

4. **Secret-scan gates every push** (no credentials leak).

5. **Idempotent + append-only** (safe to restart mid-cycle).

6. **Observable machinery** (every action logged, every cost tracked).



## Branch + PR discipline



- Feature/* branch only (never main/master).

- All pushes gated by secret-scan.py (exit 1 blocks).

- NOT a vault repo (credentials → your private remote).



## Setup for development



1. Clone the repo.

2. Copy `aesop.config.example.json` → `aesop.config.json` and customize.

3. Run `bash daemons/run-watchdog.sh --once` to test.

4. Launch `bash dash/watchdog-gui.sh` to verify dashboard.

5. Extend `monitor/collect-signals.mjs` with your custom signal collectors.



See README.md for full context and usage examples.



---



## daemons/ — Watchdog daemon



**Purpose**: Long-running backup and secret-scan daemon machinery for fleet-wide repo safety.



### Files



- **run-watchdog.sh** (1.5K): Interactive daemon supervisor; spawns backup-fleet.sh every 150s, maintains heartbeat guard (200s dedupe window), logs to FLEET-BACKUP.log. Traps INT/TERM cleanly.

- **backup-fleet.sh** (5K): Core backup worker; discovers repos (~/.*, ~/*, ~/dev/*), stashes uncommitted work to backup/* branches, pushes unpushed commits, scans tracked files for secrets. Blocks push if secret-scan fails (marks BLOCKED state).



### Contracts



**Env vars consumed**: `AESOP_ROOT` (defaults to `.`) — root of project; prepends to all state/ and tools/ paths.



**State files written** (git-ignored, ephemeral):

- `$AESOP_ROOT/state/.watchdog-heartbeat` — epoch seconds; dedupe guard (200s window).

- `$AESOP_ROOT/state/.watchdog-repos.json` — per-cycle snapshot: [{repo, state: CLEAN|PUSHED|SNAPSHOTTED|BLOCKED, age}].

- `$AESOP_ROOT/state/FLEET-BACKUP.log` — append-only; cycle start/end, repo statuses, secret-scan blocks.



**Exit behaviors**: run-watchdog exits 0 always (trap handles clean shutdown). backup-fleet exits 0 even on secret-scan block (marks repo BLOCKED, continues).



**Cadence**: 150s cycle; heartbeat dedupe within 200s.



### Invariants & Gotchas



1. **Single-instance guard (atomic lock)**: run-watchdog.sh uses atomic mkdir-based lockfile (`.watchdog-lock/`) to prevent concurrent daemons. The lock mechanism:

   - Atomic acquire: `mkdir $LOCK_DIR` is guaranteed atomic on POSIX systems (returns 0 only to first caller).

   - Stale-lock recovery: Crashed holder won't wedge daemon forever; lock older than 300s is reclaimed atomically.

   - Guards both daemon mode and `--once` mode (no bypass).

2. **Testing override**: Set `AESOP_WATCHDOG_CYCLE_CMD` env var to replace backup-fleet.sh invocation (allows tests to use mock cycle without running real backup).

3. **CRLF-safe, no line continuations**: Use POSIX-safe heredocs; never add `\` for line wrap.

4. **Secret-scan gate**: `scan_tracked_files()` calls `$AESOP_ROOT/tools/secret_scan.py` on staged/modified files; non-0 exit blocks push, marks repo BLOCKED.

5. **Append-only logs**: FLEET-BACKUP.log only grows; rotate via tools/rotate_logs.py.

6. **Path dedup via realpath**: Avoids processing symlinked repos or dot-dir aliases twice.



---



## dash/ — Dashboard TUI



**Purpose**: Real-time TUI fleet monitoring — watchdog daemon + agent activity display.



### Files



- **watchdog-gui.sh** — Read-only terminal UI (4s refresh, double-buffered, no flicker). Displays daemon status, backed-up repos, heartbeats, recent events. Launch in own window; never inside tool shell. CRLF-safe (no line continuations).

- **dash-extra.mjs** — Node.js agent activity detector. Scans AESOP_TRANSCRIPTS_ROOT for agent-*.jsonl files (last 12 min). TUI output by default; --json for web endpoints. Requires node on PATH (unavailable fallback if missing).



### State contracts



**watchdog-gui.sh reads (heartbeat staleness thresholds applied):**

- `state/.watchdog-heartbeat` (epoch, threshold: 300s for watchdog)

- `state/FLEET-BACKUP.log` (append-only, tail 3 lines)

- `state/SECURITY-ALERTS.log` (counts HIGH/MED, grep filtering RESOLVED-FP)

- `state/.watchdog-repos.json` (jq-parsed, status per repo)

- `state/.heartbeats/*` (epoch, per-agent thresholds: 3600s monitor, 300s watchdog, 1800s default)



**dash-extra.mjs reads:**

- `~/.claude/projects/**/ agent-*.jsonl` (modified time, <12min filter, top 8 recent)

- `state/SECURITY-ALERTS.log` (severity classification: HIGH/MED/DRIFT)



**Refresh cadence:**

- watchdog-gui.sh: 4s loop (infinite, Ctrl-C to exit)

- dash-extra.mjs: called on-demand (no built-in loop)



### Invariants & TUI conventions



- **Never modify fleet state** — both tools are read-only dashboards.

- **Infinite loop design** — watchdog-gui.sh runs forever; launch in dedicated terminal window, never inside tool shells.

- **CRLF-safe** — no bash line continuations; portable POSIX.

- **Node optional** — dash-extra.mjs gracefully prints "unavailable" if node missing; doesn't fail watchdog-gui.sh.



---



## monitor/ — Orchestration monitor



**Purpose:** Continuous background signal collector and refinement proposer — watches fleet machinery health deterministically (Node.js, no LLM), emits cycle snapshots, and proposes rule changes via append-only PROPOSALS.md; GOAL IS FIXED (improve machinery, never mission).



### Files



- **CHARTER.md** — Governance document; defines 10 signal checks (4 of them extended/opt-in), action tiers (AUTO/PROPOSE), outputs, single-instance guard, single-writer discipline. Read-only; behavior changes only via PROPOSALS/behavioral-PR flow.

- **collect-signals.mjs** — Deterministic signal collector (Node.js built-ins only); emits BRIEF.md + SIGNALS.json each cycle; reads config from env or aesop.config.json.

- **BRIEF.md** — Human-readable cycle snapshot (heartbeats, git state, memory freshness, log rotation, junk sprawl, stray scripts, security alerts, respawn watch, cost cadence, unreviewed prompts); overwritten each cycle; runtime.

- **SIGNALS.json** — Machine-readable metrics (same signal keys as BRIEF); JSON; overwritten each cycle; runtime.

- **PROPOSALS.md** — Structured inbox for user approval (idempotent per signal key, append-only); never edited by monitor after emission; tracks respawn-watch-breach, stray-repo-scripts, security-alerts-high-med, stale-memory-files; gitignored.

- **ACTIONS.log** — Append-only log of AUTO tier actions taken (heartbeat updates, log rotation invokes, junk quarantine); runtime; gitignored.

- **.monitor-heartbeat** — Epoch timestamp (line 1) for single-instance liveness check (<300s = skip cycle); runtime; gitignored.

- **.signal-state.json** — Sidecar state (cycleCount, etc.); runtime; gitignored.



### Contracts



**Signal keys collected:** heartbeats, git, memory, logs, junk, strayRepo, alerts, respawnWatch, costTick, unreviewedPrompts. Outputs: BRIEF.md (human), SIGNALS.json (machine); both runtime/gitignored. PROPOSALS.md (tracked, append-only); ACTIONS.log (runtime/gitignored).



**Extended signals (opt-in, default OFF):** checks 5 (junk), 6 (strayRepo), 8 (respawnWatch), and 10 (unreviewedPrompts) are extended — disabled by default.

- Config key: `monitor.extended_signals` (boolean, default `false`) in aesop.config.json.

- Env override: `AESOP_EXTENDED_SIGNALS` (`'true'` or `'1'` to enable).

- Precedence: env var > config file > default (false).

- When disabled, extended checks emit `{"skipped": true}` in SIGNALS.json and BRIEF.md notes them as "extended (off)"; their dirs are not walked. PROPOSE-tier signals for extended checks (respawn-watch-breach, stray-repo-scripts) are only emitted when extended_signals is ON.



**AUTO tier actions** (apply immediately, log to ACTIONS.log): heartbeat checks (read-only); log rotation (invoke rotate_logs.py if available, fail-open); heartbeat write (.monitor-heartbeat update); junk script quarantine (move old temp .py/.mjs to monitor/quarantine/ + manifest — only when extended_signals is ON).



**PROPOSE tier actions** (write to PROPOSALS.md, await user approval): rule changes, agent config changes, deletions outside monitor/quarantine/, orchestration policy changes.



**Idempotency rule:** Proposal emission keyed on signal key (e.g., 'respawn-watch-breach'); only emitted if not already present in PROPOSALS.md (check: `**Signal:** <key>` exists). Idempotent + append-only; safe to run repeatedly.



### Invariants & Gotchas



- CHARTER.md is authority; monitor logic is faithful to it; never edit CHARTER.md or collect-signals.mjs directly — propose via PROPOSALS.md.

- Goal is FIXED (improve machinery, never mission); if monitor thinks goal should change, it writes note to PROPOSALS.md and stops.

- Single-instance guard via .monitor-heartbeat; if <300s old, skip cycle.

- Single-writer discipline: only monitor writes BRIEF.md, SIGNALS.json, ACTIONS.log, .monitor-heartbeat, .signal-state.json.

- Config from env (AESOP_ROOT, BRAIN_ROOT, SCRIPTS_ROOT, TEMP_ROOT, AESOP_EXTENDED_SIGNALS) or aesop.config.json; falls back to safe defaults.

- Robust to missing files; treats missing dirs/logs as empty, never crashes.

- Node.js only (no Python, no LLM, no cloud); deterministic + cheap.



---



## tools/ — Build utilities and extension stubs



Local-only Python (stdlib only, no external deps), bash (POSIX, CRLF-safe). Never print secrets—report by pattern name/location only.



### secret_scan.py — Pre-push secret/credential detection gate



Scans staged/history/paths for secrets by regex pattern and credential filenames; blocks pushes on findings.



- `secret_scan.py --staged [--repo PATH]` — scan git staged files

- `secret_scan.py --history [--repo PATH]` — scan all git history blobs

- `secret_scan.py PATH [PATH...]` — scan files/dirs directly (recurse)



Exit: 0=clean, 1=findings, 2=usage error. Output masks secrets as `xxxx...`.



Pragma escape (pattern findings only; credential filenames always fatal):

```

# secretscan: allow-pattern-docs

```

Mark file's first 10 lines to report rule-based findings as ALLOWED-DOC (non-fatal). Use only for deliberate pattern documentation.



### agent-forensics.sh — Incident forensics / behavior reconstruction



Read-only git plumbing; reconstructs agent behavior snapshot or diffs behavior-controlling files.



- `bash tools/agent-forensics.sh <commit>` — print commit header, rules snapshot, CLAUDE.md, STATE.md, last 30 lines of BUILDLOG.md

- `bash tools/agent-forensics.sh --diff <commitA> <commitB>` — diff CLAUDE.md, STATE.md, docs/, monitor/CHARTER.md, hooks/ between commits



Exit: 0=success, 1=error (never raw git traces). Requires: git, head, tail, wc, grep.



### launch_tui.py — Spawn bash TUI script in detached terminal



Finds terminal (prefer Git Bash → Windows Terminal wt.exe), spawns script detached, idempotent via pidfile.



- `python launch_tui.py --script <path> [--title <title>] [--pidfile <path>]`



Exit: 0=success, 1=error. Output: exactly one line (`spawned (pid N)` or `already running (pid N)` or ERROR).



### Invariants



- **Dependency-light**: Python tools must work on base Python 3 (no pip installs).

- **CRLF-safe shell**: no line continuations in .sh scripts; Git Bash + Linux compatible.

- **Never print secrets**: mask as pattern name + masked value only.



---



## hooks/ — Installable org-policy git pre-push enforcement



**Purpose**: Ship executable git hooks that gate pushes with organization security policies (branch protection, secret scanning).



### Hook: pre-push-policy.sh



Runs on `git push` via `.git/hooks/pre-push` symlink or copy.



**Checks & Exit Contract:**

1. `check_branch_policy()` — blocks direct pushes to main/master; exit 1 on violation

2. `check_secret_scan()` — runs `tools/secret_scan.py --staged`; exit 1 on failure

3. Both trigger `log_block()` to append audit record before exit



**Audit-Ledger Contract:**

- Path: `${AESOP_ROOT:-$HOME/aesop}/state/SECURITY-AUDIT.log` (append-only, git-ignored)

- Format: JSON-lines (one record per line)

- Schema: `{"ts":"2025-07-12T14:32:01Z","repo":"aesop","event":"push_blocked","reason":"secret_scan_failure","user":"alice"}`

- All string values must be json_escaped (backslash → `\\`, quote → `\"`)



**Self-Test Convention:**

- `bash hooks/pre-push-policy.sh --test` runs the self-test suite, including:

  1. Branch policy blocks main/master

  2. Branch policy allows feature/* branches

  3. Audit log JSON format is valid

  4. JSON escaping handles special chars (quotes, backslashes)

  5. stdin handling (git pre-push pipe) doesn't crash hook

- Exit 0 = all pass; exit 1 = any fail



**Installation:**

- See `docs/HOOK-INSTALL.md` for symlink (Linux/macOS/Git Bash) and copy (Windows) methods

- Test with `bash hooks/pre-push-policy.sh --test` before org distribution



**Invariants:**

- POSIX sh compatible, CRLF-safe (no line continuations)

- Tolerate git pre-push stdin (ref list) + optional args without choking

- Fail-open only for missing optional tooling (secret_scan.py absent → allow); fail-closed for policy checks

- Use `AESOP_ROOT` env var or `$HOME/aesop` fallback; no hardcoded machine paths/usernames



---



## bin/ — CLI scaffolder



**Purpose**: Node.js CLI entry point that clones the aesop orchestration template into a target directory with idempotent validation.



### Invocation



- **npm registry**: `npx @matt82198/aesop [target-dir]` (default: `aesop-fleet`)

- **Local dev**: `node bin/cli.js [target-dir]`

- **Help**: `npx @matt82198/aesop --help` or `-h`



### What gets copied



Files in `filesToCopy` array (cli.js line 57–69):

- **Directories**: `daemons/`, `dash/`, `monitor/`, `tools/`, `ui/`, `docs/`

- **Files**: `aesop.config.example.json`, `README.md`, `LICENSE`, `CHANGELOG.md`, `CLAUDE-TEMPLATE.md`

- **Brain templates** (in docs/): `MEMORY-TEMPLATE.md` (via docs/ directory copy)



### What does NOT get copied



- `aesop.config.json` (users must `cp aesop.config.example.json` and edit)

- `state/` (runtime durable state, git-ignored, created by daemons)

- `.git/`, `node_modules/`, build artifacts



### Post-scaffold guidance



Scaffolder prints steps for users:

1. `cd target-dir && cp aesop.config.example.json aesop.config.json`

2. Edit config with paths and repos

3. Initialize brain: `cp CLAUDE-TEMPLATE.md ~/.claude/CLAUDE.md` (edit)

4. Initialize memory: `cp docs/MEMORY-TEMPLATE.md ~/.claude/MEMORY.md` (edit)

5. Test daemon: `bash daemons/run-watchdog.sh --once`

6. Launch dashboard: `python ui/serve.py`



### Invariants & gotchas



- **Idempotent on empty targets**: Fails if `targetDir` exists and is non-empty (non-destructive). Safe to retry.

- **Adding shipped files**: Any new file/dir added to `filesToCopy` array must also be added to `package.json` `files` array (lines 9–21 in package.json) so npm publish includes it.

- **No machine-specific paths**: Use relative paths only; `__dirname` and `path.join()` handle cross-platform resolution.

- **Help text accuracy**: If invocation steps or output paths change, update help text (lines 27–31).



---



## ui/ — Web dashboard



**Purpose**: Stdlib-only local observability dashboard. Serves a dark-theme HTML dashboard on a configurable port (realtime via Server-Sent Events), enabling real-time fleet monitoring without external dependencies.



### Files



- **serve.py** — HTTP server (ThreadingHTTPServer, stdlib only). Hosts HTML dashboard; /events endpoint streams realtime SSE updates. Includes CSRF token generation/validation, session persistence, and background collector thread.

- **README.md** — User guide and configuration reference.



### Configuration & Path Precedence



Configuration is resolved in this order (first match wins):

1. **Environment variables** (highest priority):

   - `PORT` — HTTP server port (default: 8770)

   - `AESOP_ROOT` — aesop installation root (default: `$HOME/aesop`)

   - `AESOP_STATE_ROOT` — state directory (overrides config state_root)

   - `AESOP_TRANSCRIPTS_ROOT` — Claude transcript directory (overrides config transcripts_root)

   - `AESOP_UI_COLLECT_INTERVAL` — collector thread poll cadence in seconds (default: 1.0)

2. **Config file** (`aesop.config.json`):

   - `state_root` — path to state/ directory

   - `transcripts_root` — path to Claude transcript directory

3. **Built-in defaults** (lowest priority):

   - `AESOP_ROOT/state` for state directory

   - `~/.claude/projects` for transcripts



### CSRF & Session Protection



**Token model:**

- Per-session CSRF token generated at startup, persisted to `state/.ui-session-token` (mode 0600, readable only by owner)

- Token is 43-character URL-safe base64 string (256 bits)

- Persistent across server restarts (read from file if exists, generate fresh if not)

- Used to validate mutations via /submit endpoint



**Validation on /submit POST:**

1. **Origin/Referer check**: if present, must be local (http://127.0.0.1:<port>, http://localhost:<port>, or http://[::1]:<port>)

2. **X-Aesop-Token header check**: must match SESSION_TOKEN exactly

- Both checks fail-closed (missing header = rejection)

- GET /events (SSE, read-only) requires no token



**Local CLI access:**

- CLI tools read token from `state/.ui-session-token` (0600) to submit to /submit endpoint

- Legitimate browser clients: token injected into HTML template, sent by JavaScript



### Server-Sent Events (SSE) Model



**Realtime streaming via GET /events:**

- ThreadingHTTPServer required (SSE holds one connection per client)

- Streams JSON frames: `event: data|backlog|agents` / `data: <json>`

- Keepalive comment-line (`: keepalive`) sent every ~15s to prevent timeout

- Read-only stream; no mutations



**Sections emitted (only on content change):**

1. **data** — heartbeat status, daemon state, log tail

2. **backlog** — AUDIT-BACKLOG.md parsed into tier buckets (P0/P1/P2/Needs decision)

3. **agents** — fleet agent activity (from Claude transcripts directory)



### Background Collector Thread



**Lifecycle:**

- Started idempotently on first HTTP request (via `start_collector_thread()`)

- Runs as daemon thread (terminates when main process exits)

- Single-instance guard via `_collector_lock` (prevents double-start)



**Polling strategy:**

- Wakes every `COLLECTOR_INTERVAL` seconds (default: 1.0, overridable via `AESOP_UI_COLLECT_INTERVAL`)

- Polls cheap sources: heartbeat file mtimes, log tails, file fingerprints

- Only re-derives sections when underlying input changed (mtime/fingerprint gate)

- Only emits to clients when section content-hash changed (avoids redundant broadcasts)



**Cached data:**

- Last computed hash per section (data/backlog/agents)

- Last mtime of AUDIT-BACKLOG.md

- Last fingerprint of transcripts directory (to detect agent activity changes)

- Cached parsed backlog and agent snapshot (reused until inputs change)



**Content-change detection:**

- Mtime-gated: backlog section re-derived only if AUDIT-BACKLOG.md mtime changed

- Fingerprint-gated: agents section re-derived only if transcripts directory content changed

- Hash-gated: broadcast only sent if content-hash differs from last broadcast

- This avoids expensive operations (subprocess for dash-extra.mjs, directory walk) on every tick



### Invariants & Gotchas



- **Stdlib only**: No external dependencies (requests, flask, etc.). Uses only `http.server`, `json`, `subprocess`, `threading`.

- **ThreadingHTTPServer required**: SSE model requires one thread per client connection. Standard HTTPServer (processes) cannot hold SSE connections open.

- **Collector fail-open**: If collector thread crashes, server continues serving; realtime updates stop but dashboard remains accessible.

- **Token file permissions**: On Unix-like systems, token file is chmod 0600 (user-only). Windows ignores mode bits but respects file permissions via ACLs.

- **Paths git-ignored**: `state/.ui-session-token` is ephemeral (regenerated if missing), never committed.




---

## tests/ — Test suites and fixtures

**Purpose**: Automated test suites across shell, Node.js, and Python to verify daemon machinery, CLI scaffolder, config drift, and security contracts.

### Files & Harnesses

- **test_pre_push_policy.sh** — Hook self-test; verifies branch policy and audit logging (run: `bash tests/test_pre_push_policy.sh`)
- **test-run-watchdog.sh** — Hermetic watchdog daemon test; mocks cycle command (run: `bash tests/test-run-watchdog.sh`)
- **backup-fleet.test.sh** — Backup worker test suite (run: `bash tests/backup-fleet.test.sh`)
- **test_reconstitute.sh** — Reconstitute script self-test suite (run: `bash tests/test_reconstitute.sh`)
- **test_reconstitute_fixes.sh** — Security & architecture fixes regression suite for target validation, URL validation, and legacy space-delimited targets (run: `bash tests/test_reconstitute_fixes.sh`)
- **config-doc-drift.test.mjs** — Node.js test ensuring config keys documented in code are present in aesop.config.example.json (run: `node --test tests/config-doc-drift.test.mjs`)
- **domain-map-drift.test.mjs** — Node.js test ensuring all code directories have domain-map entries in CLAUDE.md (run: `node --test tests/domain-map-drift.test.mjs`)

### Test Harness Integration

**npm scripts orchestration** (package.json):
- `npm run test:node` — runs all `*.test.mjs` files via node --test
- `npm run test:sh` — runs all shell test suites in sequence
- `npm run test:py` — runs all Python unittest suites
- `npm run test:all` — runs all three harnesses in order

**CI integration** (.github/workflows/ci.yml):
- "Run Node.js tests" → `npm run test:node`
- "Run shell test suites" → `npm run test:sh`
- "Run Python tests" → `npm run test:py`
- Plus individual hook and tool self-tests

### Invariants & Conventions

- **Hermetic tests**: Shell tests use mktemp for isolation; no persistent side effects
- **Fixtures**: Dummy secrets assembled at test time (never committed), validated via secret_scan.py pragma
- **HEAD-independent**: All tests run regardless of current git branch (CI runs on HEAD=main)
- **Fail-open on missing tools**: Tests skip if optional tooling unavailable (e.g., node missing)
- **Self-test convention**: Hooks and tools (reconstitute.sh, pre-push-policy.sh) include `--test` mode for inline validation

