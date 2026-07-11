# Contributing to Aesop

Thank you for your interest in contributing to Aesop! We welcome improvements, bug fixes, documentation enhancements, and new features that strengthen the orchestration harness.

## Getting Started

### Prerequisites

- **Git** v2.40 or later
- **Bash** v4.0 or later
- **Python** 3.10+ (for dashboard and tools)
- **Node.js** v18+ (optional; required for monitor and dashboard extras)
- **Claude Code CLI** (to test orchestration workflows)

### Setup

1. **Fork and clone** the repository:
   ```bash
   git clone https://github.com/your-username/aesop.git
   cd aesop
   ```

2. **Create a configuration file**:
   ```bash
   cp aesop.config.example.json aesop.config.json
   # Edit aesop.config.json with your local paths
   ```

3. **Test the watchdog locally** (one-shot mode):
   ```bash
   bash daemons/run-watchdog.sh --once
   ```

4. **Launch the web dashboard**:
   ```bash
   python ui/serve.py
   ```
   Visit `http://localhost:8770` to verify the interface.

## Development Workflow

### Branch Discipline

- Create feature branches from `main`: `git checkout -b feature/your-feature`
- Use `docs/` prefix for documentation: `git checkout -b docs/update-guides`
- Use `fix/` prefix for bug fixes: `git checkout -b fix/watchdog-stall`
- Never push directly to `main`; use pull requests only.

### Commit Messages

Follow conventional commit format:

```
type(scope): short summary

Optional longer explanation of the change. Describe the why, not just the what.

Co-Authored-By: Your Name <your-email@example.com>
```

**Type** should be one of:
- `feat`: New feature or capability
- `fix`: Bug fix
- `docs`: Documentation only
- `refactor`: Code refactoring (no behavioral change)
- `perf`: Performance improvement
- `test`: Test additions or fixes
- `chore`: Tooling, CI/CD, dependencies

**Scope** is optional but recommended (e.g., `watchdog`, `dashboard`, `monitor`, `docs`).

### Testing

Aesop is designed for integration testing rather than extensive unit tests. Before submitting:

1. **Test watchdog backup locally** (`--once` mode):
   ```bash
   bash daemons/run-watchdog.sh --once
   ```
   Verify `state/FLEET-BACKUP.log` for success.

2. **Test the dashboard**:
   ```bash
   python ui/serve.py
   # Visit http://localhost:8770
   # Verify all panels load and refresh every 3s
   ```

3. **Test monitor signal collection** (if changes affect monitor):
   ```bash
   node monitor/collect-signals.mjs
   ```

4. **Manual orchestration test** (if changes affect dispatch):
   - Use Claude Code with the modified Aesop configuration
   - Spawn a test Haiku subagent and verify heartbeat updates

## Security & Code Review

### Secret Scanning

This repository has **zero tolerance for credentials, API keys, or private paths**. Before submitting a PR:

1. **Review your changes** for any hardcoded secrets, local paths, or private identifiers.
2. **Run your own secret scanner** (e.g., `git secrets`, `truffleHog`):
   ```bash
   git diff HEAD~1 | my-secret-scanner
   ```
3. **Never commit** `aesop.config.json` or `.env` files (they are git-ignored for this reason).

### Code Style

- **Shell scripts** (bash): POSIX-compatible where possible; include comments for complex logic.
- **Python**: Follow PEP 8; prefer readability over cleverness.
- **JavaScript**: Use modern ES6+ features; Node.js 18+.
- **Markdown**: Hard-wrap at 100 characters; use clear headings and code blocks.

### Documentation

- Update README.md if you add new features or change usage patterns.
- Add entries to CHANGELOG.md (Unreleased section) for user-facing changes.
- Write inline comments for non-obvious logic.
- Link to related docs/guides when relevant.

## Submitting a Pull Request

1. **Push your branch** to your fork:
   ```bash
   git push origin feature/your-feature
   ```

2. **Open a pull request** against `main`:
   - Write a clear title and description.
   - Reference any related issues (e.g., "Fixes #123").
   - Explain the motivation and design decisions.

3. **Respond to review feedback**:
   - Address comments and suggestions.
   - Push updates to the same branch (don't force-push unless requested).

4. **Merge**: Once approved, the maintainer will merge your PR.

## Areas for Contribution

### High-Priority
- **Bug fixes**: Any issue blocking watchdog, dashboard, or orchestration.
- **Documentation**: Guides for specific workflows, troubleshooting, or extend patterns.
- **Dashboard enhancements**: New panels, better data visualization, improved UX.

### Medium-Priority
- **Monitor enhancements**: Custom signal collectors, better drift detection.
- **Daemon optimizations**: Faster backup cycles, better error handling.
- **Test coverage**: Integration tests for key workflows.

### Lower-Priority
- **Cosmetic improvements**: UI refinements, theme customization.
- **Platform-specific workarounds**: Windows-specific paths, macOS-specific issues.

## Questions or Ideas?

- Open an **issue** to discuss a feature or report a bug.
- Post questions in **Discussions** (if enabled).
- Reference relevant documentation (CARDINAL-RULES.md, DISPATCH-MODEL.md, etc.).

## Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please treat all contributors with respect, provide constructive feedback, and help foster a collaborative community.

---

**Thank you for contributing to Aesop!** Your improvements make the orchestration harness more reliable, observable, and cost-effective for everyone.
