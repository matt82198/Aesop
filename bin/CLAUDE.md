# bin/ — CLI scaffolder

**Purpose**: Node.js CLI entry point that clones the aesop orchestration template into a target directory with idempotent validation, plus an interactive onboarding wizard for new adopters.

## Invocation

- **npm registry**: `npx @matt82198/aesop [target-dir]` (default: `aesop-fleet`)
- **Local dev**: `node bin/cli.js [target-dir]`
- **Help**: `npx @matt82198/aesop --help` or `-h`
- **Interactive wizard**: `npx @matt82198/aesop wizard` (on a TTY, prompts; with `--yes`, uses defaults)

## Runtime subcommands

cli.js dispatches runtime management subcommands to `tools/{subcommand}.js`:

- **`aesop doctor`** (or `node bin/cli.js doctor`) — Preflight readiness check; validates Node.js, Python, git, config, directories, hooks, and dashboard port availability.
- **`aesop watch`** (or `node bin/cli.js watch`) — Launch the watchdog daemon; spawns `daemons/run-watchdog.sh` for continuous fleet monitoring.
- **`aesop dash`** (or `node bin/cli.js dash`) — Launch the web dashboard; spawns `python ui/serve.py` to serve realtime fleet status at localhost:8770 (default).
- **`aesop status`** (or `node bin/cli.js status`) — One-shot fleet status snapshot; displays heartbeats, dashboard port, and git branch status.
- **`aesop fleet`** (or `node bin/cli.js fleet`) — One-shot fleet snapshot in JSON; displays active agents, heartbeat ages, tracker lane counts, and orchestrator status. Node STDLIB only; gracefully degrades with `unavailable: <why>` for missing state files.

## What gets copied

Files in `filesToCopy` array (cli.js lines 239–256):
- **Directories**: `daemons/`, `dash/`, `monitor/`, `tools/`, `ui/`, `docs/`, `state_store/`, `skills/`, `mcp/`, `scan/`, `hooks/`
- **Files**: `aesop.config.example.json`, `README.md`, `LICENSE`, `CHANGELOG.md`, `CLAUDE-TEMPLATE.md`
- **Brain templates** (in docs/): `MEMORY-TEMPLATE.md` (via docs/ directory copy)

## What does NOT get copied

- `aesop.config.json` (users must `cp aesop.config.example.json` and edit)
- `state/` (runtime durable state, git-ignored, created by daemons)
- `.git/`, `node_modules/`, build artifacts

## Post-scaffold guidance

Scaffolder prints steps for users:
1. `cd target-dir && cp aesop.config.example.json aesop.config.json`
2. Edit config with paths and repos
3. Initialize brain: `cp CLAUDE-TEMPLATE.md ~/.claude/CLAUDE.md` (edit)
4. Initialize memory: `cp docs/MEMORY-TEMPLATE.md ~/.claude/MEMORY.md` (edit)
5. Test daemon: `bash daemons/run-watchdog.sh --once`
6. Launch dashboard: `python ui/serve.py`

## Interactive wizard (`aesop wizard`)

The wizard mode provides an interactive onboarding flow for new adopters, guiding them through fleet setup in ~60 seconds:

1. **Trigger**: `npx @matt82198/aesop wizard` on a TTY (interactive terminal)
2. **Questions** (all have sensible defaults, press Enter-Enter-Enter to skip):
   - Project name (default: "my-fleet")
   - Repos to watch (auto-discovers git repos under `~`, offers choices)
   - Dashboard port (default: 8770, validates 1–65535)
   - Brain root directory (default: `~/.claude`)
3. **Output**:
   - Scaffolds template files
   - Generates CLAUDE.md (substituted with project name)
   - Generates aesop.config.json (with discovered repos)
   - Prints "next 3 commands" epilogue
   - Offers to run `watchdog --once` smoke test immediately
4. **Non-interactive mode** (`--yes` flag or non-TTY stdin): Uses defaults, zero prompts (CI-safe)

### Wizard implementation details

- **Repo discovery** (`discoverRepos`): Scans `~` for `.git` directories at first level (non-recursive)
- **Port validation** (`validatePort`): Rejects invalid ports, accepts 1–65535
- **Portable paths**: All config paths use `~` form (`~/.claude`, `~/scripts`, etc.) for cross-platform compatibility
- **Defaults**: Every prompt has a default so users can skip it (press Enter)
- **Non-destructive**: Never overwrites existing `aesop.config.json` without user confirmation

## Invariants & gotchas

- **Idempotent on empty targets**: Fails if `targetDir` exists and is non-empty (non-destructive). Safe to retry.
- **Adding shipped files**: Any new file/dir added to `filesToCopy` array must also be added to `package.json` `files` array (lines 9–27 in package.json) so npm publish includes it.
- **No machine-specific paths**: Use relative paths only; `__dirname` and `path.join()` handle cross-platform resolution.
- **Wizard prompts are async**: Main execution is wrapped in async IIFE to support readline prompts
- **Help text accuracy**: If invocation steps or output paths change, update help text
