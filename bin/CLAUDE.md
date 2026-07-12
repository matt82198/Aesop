# bin/ — CLI scaffolder

**Purpose**: Node.js CLI entry point that clones the aesop orchestration template into a target directory with idempotent validation.

## Invocation

- **npm registry**: `npx @matt82198/aesop [target-dir]` (default: `aesop-fleet`)
- **Local dev**: `node bin/cli.js [target-dir]`
- **Help**: `npx @matt82198/aesop --help` or `-h`

## What gets copied

Files in `filesToCopy` array (cli.js line 57–69):
- **Directories**: `daemons/`, `dash/`, `monitor/`, `tools/`, `ui/`, `docs/`
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

## Invariants & gotchas

- **Idempotent on empty targets**: Fails if `targetDir` exists and is non-empty (non-destructive). Safe to retry.
- **Adding shipped files**: Any new file/dir added to `filesToCopy` array must also be added to `package.json` `files` array (lines 9–21 in package.json) so npm publish includes it.
- **No machine-specific paths**: Use relative paths only; `__dirname` and `path.join()` handle cross-platform resolution.
- **Help text accuracy**: If invocation steps or output paths change, update help text (lines 27–31).

See ../CLAUDE.md for project principles and domain map.
