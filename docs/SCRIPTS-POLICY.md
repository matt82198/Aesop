# Scripts Policy: Local-only, shared library

This policy governs how auxiliary scripts and automation tools are written, organized, and maintained in Aesop-driven orchestration systems.

## Rule 1: Never run scripts in the cloud

Python, shell, and other ad-hoc scripts execute **LOCALLY on the orchestrator machine only** — never inside:
- Cloud sandboxes or serverless functions
- Remote/scheduled cloud agents
- Remote workflow environments
- Containerized runners without local bind-mounts

**Why?** Local scripts often rely on local state (configuration files, home directory, machine-specific paths, local credentials). Pushing them to cloud breaks those assumptions and risks secret leaks. Local-only keeps boundaries clear and reproducible.

## Rule 2: One common scripts library

Before writing any new script, **check the library first**.

**Workflow**:
1. Look in the shared library (e.g., `aesop/tools/` for core tools, or a dedicated `~/scripts` folder for utility scripts)
2. If the script exists, edit or extend the existing one
3. If it doesn't exist and it's genuinely reusable (useful across tasks/projects/teams), add it to the library
4. If it's task-local and unlikely to be reused, keep it in a temporary scratchpad

**Library conventions**:
- Snake_case filenames (e.g., `secret_scan.py`, `rotate_logs.py`)
- Module docstring at the top explaining purpose, usage, and parameters
- One-line entry in the library's `CLAUDE.md` index
- Python: include a `if __name__ == "__main__":` section with example usage

**Example entry**:
```markdown
- `secret_scan.py` — scan staged files for secrets; blocks push if found. Usage: `python secret_scan.py --staged --repo <path>`
```

## Rule 3: Task-local vs. reusable

**Task-local scripts** not worth keeping are deleted at task end. Examples:
- One-off data transforms for a single feature or bugfix
- Temporary test harnesses
- Ad-hoc debugging helpers for a specific issue

**Reusable scripts** added to the library. Examples:
- Secret scanning (multi-project, multi-task)
- Build validation and health checks
- Linting and format automation
- Data migration templates
- Log rotation and archival

**Decision heuristic**: If you'd use it again in another project or another day on this project, it belongs in the library. If it's solving a one-time problem, delete it.

## Rule 4: Library growth & discovery

The library evolves as new patterns emerge. On every orchestration boot or refresh cycle, the orchestrator can scan the library's `CLAUDE.md` to discover available tools.

**Keep the index current**: Every new reusable script gets a one-line entry so it's discoverable and documented. Entries stay alphabetical and include usage examples.

## Rule 5: Environment & security

Scripts must be idempotent and deterministic.

**DO**:
- Detect and skip if already run (idempotent)
- Use local paths and respect working directory
- Log actions for auditability
- Handle errors explicitly (exit 1 on failure)

**DON'T**:
- Hardcode machine-specific paths (use `$HOME`, relative paths, or environment variables)
- Embed credentials (read from environment variables or secure config files instead)
- Leave large temporary files in `/tmp` or scratchpad (clean up on exit)
- Run cloud-bound commands that phone home

## Rule 6: Version control & archival

Scripts in the library are **checked into git** so they're versioned and auditable. Task-local scripts can be git-ignored or committed temporarily (depending on repo policy).

**Library scripts**:
- Committed to the repo
- Updates are reviewed like any other code
- On removal/deprecation, archive the old version (add date suffix, keep for 3 months for reference)

## Implementation checklist

When adding a new script to the library:
- [ ] Snake_case filename
- [ ] Module docstring explaining purpose and usage
- [ ] Entry in CLAUDE.md with one-line description and usage example
- [ ] Idempotent (safe to run multiple times)
- [ ] Handles errors explicitly (exit 1 on failure)
- [ ] No hardcoded personal paths or credentials
- [ ] Runs locally only (no cloud / scheduled execution)
- [ ] Git-committed and documented

---

**Why this policy matters**: A shared, versioned scripts library reduces duplication, improves discoverability, and ensures automation is auditable and reproducible across team members and machines. Local-only execution keeps secrets safe and performance predictable. Together, they form the **automation core** that enables reliable, maintainable orchestration at scale.
