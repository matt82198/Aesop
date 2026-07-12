#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');

const args = process.argv.slice(2);
const helpFlag = args.includes('--help') || args.includes('-h');
const forceFlag = args.includes('--force');

if (helpFlag) {
  console.log(`
aesop — Multi-agent orchestration template scaffolder

Usage:
  npx @matt82198/aesop [target-dir] [options]

Arguments:
  target-dir    Directory to scaffold the template into (default: "aesop-fleet")

Options:
  --help, -h    Show this help message
  --force       Replace any existing .git/hooks/pre-push during scaffold

Examples:
  npx @matt82198/aesop                    # Creates ./aesop-fleet/
  npx @matt82198/aesop my-fleet           # Creates ./my-fleet/
  npx @matt82198/aesop /tmp/my-orchestrator  # Creates /tmp/my-orchestrator/
  npx @matt82198/aesop my-fleet --force   # Re-scaffold and replace hooks

After scaffolding, cd into the directory and:
  1. Copy aesop.config.example.json → aesop.config.json
  2. Edit aesop.config.json with your paths and repos
  3. Run: bash daemons/run-watchdog.sh --once
  4. Launch dashboard: python ui/serve.py
`);
  process.exit(0);
}

// Extract targetDir (first non-flag argument)
const targetDir = args.filter(arg => !arg.startsWith('--') && !arg.startsWith('-'))[0] || 'aesop-fleet';

// Validate target directory doesn't exist or is empty (except for .git and aesop files)
if (fs.existsSync(targetDir)) {
  const contents = fs.readdirSync(targetDir);
  // Allow .git and aesop scaffolded files to already exist (for idempotency)
  const aesopDirs = ['daemons', 'dash', 'monitor', 'tools', 'ui', 'docs', '.git'];
  const aesopFiles = ['aesop.config.example.json', 'README.md', 'LICENSE', 'CHANGELOG.md', 'CLAUDE-TEMPLATE.md'];
  const allowedItems = new Set([...aesopDirs, ...aesopFiles]);

  const unexpectedContents = contents.filter(item => !allowedItems.has(item));
  if (unexpectedContents.length > 0) {
    console.error(`Error: Directory "${targetDir}" exists and contains unexpected files.`);
    console.error('Please choose a different target directory or remove the existing one.');
    process.exit(1);
  }
} else {
  fs.mkdirSync(targetDir, { recursive: true });
}

// Copy template files
const templateRoot = path.join(__dirname, '..');
const filesToCopy = [
  'daemons',
  'dash',
  'monitor',
  'tools',
  'ui',
  'docs',
  'aesop.config.example.json',
  'README.md',
  'LICENSE',
  'CHANGELOG.md',
  'CLAUDE-TEMPLATE.md'
];

let copiedCount = 0;

function copyRecursive(src, dest) {
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    if (!fs.existsSync(dest)) {
      fs.mkdirSync(dest, { recursive: true });
    }
    const entries = fs.readdirSync(src);
    entries.forEach(entry => {
      const srcFile = path.join(src, entry);
      const destFile = path.join(dest, entry);
      copyRecursive(srcFile, destFile);
    });
  } else {
    fs.copyFileSync(src, dest);
    copiedCount++;
  }
}

function installPrePushHook(targetDir, templateRoot) {
  // Try to locate .git directory
  const gitDir = path.join(targetDir, '.git');
  if (!fs.existsSync(gitDir)) {
    // No git repo, skip hook installation silently
    return;
  }

  // Ensure hooks directory exists
  const gitHooksDir = path.join(gitDir, 'hooks');
  if (!fs.existsSync(gitHooksDir)) {
    fs.mkdirSync(gitHooksDir, { recursive: true });
  }

  const hookSource = path.join(templateRoot, 'hooks', 'pre-push-policy.sh');
  const hookDest = path.join(gitHooksDir, 'pre-push');

  if (!fs.existsSync(hookSource)) {
    // Hook source doesn't exist, skip
    return;
  }

  const hookSourceContent = fs.readFileSync(hookSource, 'utf8');

  // Check if hook already exists
  if (fs.existsSync(hookDest)) {
    const existingContent = fs.readFileSync(hookDest, 'utf8');

    // If content matches, it's idempotent, do nothing
    if (existingContent === hookSourceContent) {
      console.log('✓ Pre-push hook already installed (no changes)');
      return;
    }

    // Different hook exists
    if (!forceFlag) {
      console.warn('⚠ Warning: A different pre-push hook already exists at ' + hookDest);
      console.warn('  Use --force to replace it, or customize manually.');
      return;
    }

    // --force: replace the existing hook
    console.log('✓ Replacing existing pre-push hook with --force');
  }

  // Install the hook
  if (process.platform === 'win32') {
    // Windows: copy the file
    fs.copyFileSync(hookSource, hookDest);
    console.log('✓ Copied pre-push policy hook to .git/hooks/pre-push');
  } else {
    // Unix: symlink for easy updates
    // First remove if exists
    if (fs.existsSync(hookDest)) {
      fs.unlinkSync(hookDest);
    }
    // Create symlink relative to .git/hooks/
    const relPath = path.relative(gitHooksDir, hookSource);
    fs.symlinkSync(relPath, hookDest);
    console.log('✓ Symlinked pre-push policy hook to .git/hooks/pre-push');
  }

  // Ensure hook is executable
  try {
    fs.chmodSync(hookDest, 0o755);
  } catch (e) {
    // On Windows, chmod may fail; that's okay
  }
}

try {
  filesToCopy.forEach(item => {
    const src = path.join(templateRoot, item);
    const dest = path.join(targetDir, item);
    if (fs.existsSync(src)) {
      copyRecursive(src, dest);
      console.log(`✓ Copied ${item}`);
    }
  });

  // Install the pre-push hook
  installPrePushHook(targetDir, templateRoot);

  console.log(`\n✅ Scaffolded aesop template into "${targetDir}" (${copiedCount} files)`);
  console.log('\nConfiguration steps:');
  console.log(`  1. cd ${targetDir}`);
  console.log('  2. cp aesop.config.example.json aesop.config.json');
  console.log('  3. Edit aesop.config.json with your configuration');
  console.log('\nInitialize your brain (Claude Code team memory):');
  console.log('  4. mkdir -p ~/.claude/memory');
  console.log(`  5. cp ${targetDir}/CLAUDE-TEMPLATE.md ~/.claude/CLAUDE.md  (then edit domains/team info)`);
  console.log(`  6. cp ${targetDir}/docs/MEMORY-TEMPLATE.md ~/.claude/MEMORY.md  (then add your facts)`);
  console.log('\nRun the daemon and dashboard:');
  console.log('  7. bash daemons/run-watchdog.sh --once  (test run)');
  console.log('  8. python ui/serve.py  (launch dashboard on localhost:8770)');
  console.log('\nFor full documentation, see the README.md in the scaffolded directory.');
  process.exit(0);
} catch (err) {
  console.error(`Error scaffolding template: ${err.message}`);
  process.exit(1);
}
