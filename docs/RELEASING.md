# Releasing Aesop

This document covers the release process for Aesop: version bumping, git tagging, GitHub release creation, and npm publishing with beta dist-tag support.

## Release Types

Aesop follows semantic versioning: `MAJOR.MINOR.PATCH[-PRERELEASE]`

- **Stable (0.1.0)**: Core orchestration engine stable; backward-compatible API
- **Beta (0.1.0-beta.N)**: Pre-release builds; may have breaking changes; uses `@beta` npm dist-tag
- **Patch (0.1.0-beta.N+M)**: Fixes within a beta series; increments local version only

## Full Release Workflow

### 1. Version Bump (`npm version`)

```bash
# From repo root, on a `release/*` or `docs/*` branch (never main)
npm version minor       # for 0.1.0 → 0.2.0 (stable)
npm version prerelease  # for 0.1.0 → 0.1.1-rc.0 (next beta)
npm version patch       # for 0.1.0-beta.4 → 0.1.0-beta.5 (current beta)
```

This command:
- Updates `package.json` version field
- Creates a git commit `"v<version>"` (only if git is clean)
- Creates an annotated git tag `v<version>`
- Does NOT push (safe for local preview)

**Pre-check**: Ensure:
- `package.json` files in repo (root + `ui/web/`) are in sync
- No uncommitted changes (git status clean)
- `dist/` is up-to-date (npm run build if needed)

### 2. Verify the Tag Locally

```bash
# Check the tag was created and points to the right commit
git tag -l | tail -5
git show v0.1.0-beta.5
```

### 3. Push to Git Remote

```bash
# Push the branch and the new tag
git push origin docs/wave15-currency
git push origin v0.1.0-beta.5
```

This makes the tag available for GitHub release creation.

### 4. Create GitHub Release

GitHub Actions CI automatically creates a release from the tag when pushed. Or manually via GitHub web UI:

1. Go to [Releases](https://github.com/matt82198/aesop/releases)
2. Click "Create a new release"
3. Select `v0.1.0-beta.5` from the tag dropdown
4. Title: `Aesop 0.1.0-beta.5`
5. Body (auto-generated or manual):
   ```markdown
   ## What's New
   - State-sourced SQLite backing store (Wave-15)
   - Self-building stats via tools/self_stats.py
   - MCP fleet server integration
   - Alert webhook bridge
   - Onboarding wizard (interactive scaffolder)
   - Healthcheck skill for liveness probes
   
   ## Install
   ```bash
   npm install @matt82198/aesop@beta
   ```
   
   See [CHANGELOG.md](CHANGELOG.md) for the full list.
   ```
6. **For beta releases**: Check "This is a pre-release"
7. Click "Publish release"

### 5. Publish to npm

```bash
# Login (if not already authenticated)
npm login

# For stable releases (0.1.0)
npm publish --access public

# For beta releases (0.1.0-beta.5)
npm publish --access public --tag beta

# Verify the tag was set
npm view @matt82198/aesop@0.1.0-beta.5 | grep dist-tags
# Should output:
#   'dist-tags': { latest: '0.1.0', beta: '0.1.0-beta.5' }
```

**Pre-check before publish**:
- `npm run test:all` passes (all test suites green)
- `npm run build` succeeds in ui/web/
- `dist/` is committed and up-to-date
- Changelog is current (CHANGELOG.md updated)
- No local uncommitted changes

## Verification Checklist

After publishing, verify the release is live:

```bash
# Check npm registry
npm view @matt82198/aesop@latest     # Should show latest stable
npm view @matt82198/aesop@beta       # Should show latest beta

# Install in a test dir and verify
mkdir /tmp/aesop-test && cd /tmp/aesop-test
npm install @matt82198/aesop@beta
node -e "console.log(require('./package.json').dependencies)"
```

## Rollback (if needed)

If a release has a critical bug:

1. **npm**: Deprecate the bad version
   ```bash
   npm deprecate @matt82198/aesop@0.1.0-beta.5 "Critical bug; use @beta instead"
   ```

2. **GitHub**: Delete the release from the web UI (Releases → click release → Delete)

3. **Git**: Delete the tag locally and remotely
   ```bash
   git tag -d v0.1.0-beta.5
   git push origin :refs/tags/v0.1.0-beta.5
   ```

4. **Branch**: Reset the version bump commit (if desired)
   ```bash
   git reset --soft HEAD~1
   # Edit package.json back to previous version
   git add package.json
   git commit -m "Revert: v0.1.0-beta.5 (critical bug)"
   git push origin <branch>
   ```

## Notes

- **The `@latest` dist-tag** is reserved for stable releases (no prerelease suffix). Beta releases stay under `@beta`.
- **Semver gaps**: If beta.4 was skipped, beta.5 jumps directly. No backfilling needed.
- **Prereleases don't block stable**: Users on `npm install @matt82198/aesop` get the latest stable, not the latest beta.
- **Local version suffix**: If you need to publish a local build for testing, use `0.1.0-beta.5+local.1` (won't be published to npm, only for local installs).

## References

- [npm version](https://docs.npmjs.com/cli/v8/commands/npm-version)
- [npm publish](https://docs.npmjs.com/cli/v8/commands/npm-publish)
- [npm dist-tags](https://docs.npmjs.com/cli/v8/commands/npm-dist-tag)
- [Semantic Versioning](https://semver.org/)
