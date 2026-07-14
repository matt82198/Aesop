#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');
const readline = require('readline');
const { execSync } = require('child_process');

const args = process.argv.slice(2);
const helpFlag = args.includes('--help') || args.includes('-h');
const forceFlag = args.includes('--force');
const yesFlag = args.includes('--yes');

// Detect if stdin is a TTY (interactive terminal)
function isInteractive() {
  return process.stdin.isTTY && process.stdout.isTTY;
}

// Discover git repositories under a base directory (non-recursive first level)
function discoverRepos(baseDir) {
  const repos = [];
  try {
    if (!fs.existsSync(baseDir)) return repos;
    const entries = fs.readdirSync(baseDir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory() && !entry.name.startsWith('.')) {
        const fullPath = path.join(baseDir, entry.name);
        const gitDir = path.join(fullPath, '.git');
        if (fs.existsSync(gitDir)) {
          repos.push({ name: entry.name, path: fullPath });
        }
      }
    }
  } catch (e) {
    // Silently ignore discovery errors
  }
  return repos;
}

// Interactive prompt via readline (exported for testing)
async function promptUser(rl, prompt, defaultValue) {
  return new Promise((resolve) => {
    const displayPrompt = defaultValue ? `${prompt} (${defaultValue}): ` : `${prompt}: `;
    rl.question(displayPrompt, (answer) => {
      resolve(answer.trim() || defaultValue || '');
    });
  });
}

// Validate port is a number
function validatePort(port) {
  const p = parseInt(port, 10);
  return !isNaN(p) && p > 0 && p < 65536 ? p : null;
}

// Parse named flags
function getFlag(flagName) {
  const idx = args.findIndex(arg => arg === flagName);
  if (idx !== -1 && idx + 1 < args.length) {
    return args[idx + 1];
  }
  return null;
}

if (helpFlag) {
  console.log(`
aesop — Multi-agent orchestration template scaffolder

Usage:
  npx @matt82198/aesop [target-dir] [options]
  npx @matt82198/aesop wizard [options]

Commands:
  wizard                  Interactive onboarding (prompts for project name, repos, port)

Arguments:
  target-dir    Directory to scaffold the template into (default: "aesop-fleet")

Options:
  --help, -h              Show this help message
  --force                 Replace any existing .git/hooks/pre-push during scaffold
  --yes                   Skip interactive prompts, use defaults (CI-safe)
  --name <name>           Project name (for headless scaffolding; generates CLAUDE.md + aesop.config.json)
  --domains <list>        Comma-separated domain list (e.g., "api,worker,monitoring")
  --repos <paths>         Comma-separated repo paths (e.g., "/path/to/repo1,/path/to/repo2")

Examples:
  npx @matt82198/aesop                                      # Creates ./aesop-fleet/ with template
  npx @matt82198/aesop my-fleet                             # Creates ./my-fleet/ with template
  npx @matt82198/aesop wizard                               # Interactive onboarding (60-second setup)
  npx @matt82198/aesop my-fleet --force                     # Re-scaffold and replace hooks
  npx @matt82198/aesop orchestrator --name "my-service"     # Headless: generates CLAUDE.md + config

  Full headless with domains and repos (POSIX):
    npx @matt82198/aesop orchestrator --name "api" --domains "server,worker" --repos "/path/to/api"

  Full headless with domains and repos (PowerShell):
    npx @matt82198/aesop orchestrator --name "api" --domains "server,worker" --repos "C:\path\to\api"

Interactive wizard flow:
  1. Run: npx @matt82198/aesop wizard
  2. Answer prompts (press Enter for defaults): project name, repos to watch, port, brain root
  3. Scaffolds template, writes aesop.config.json, prints next steps
  4. Optionally runs watchdog smoke test

After scaffolding, cd into the directory and:
  1. Review CLAUDE.md (pre-filled with your project info)
  2. Review aesop.config.json (pre-configured for your repos)
  3. Run: bash daemons/run-watchdog.sh --once
  4. Launch dashboard: python ui/serve.py
`);
  process.exit(0);
}

// Check if wizard mode is requested (either as first arg or after targetDir)
// e.g., "aesop wizard" or "aesop my-dir wizard"
let wizardModeRequested = false;
let wizardArgIndex = -1;

// Check if 'wizard' is in the args
for (let i = 0; i < args.length; i++) {
  if (args[i] === 'wizard') {
    wizardModeRequested = true;
    wizardArgIndex = i;
    break;
  }
}

const wizardMode = wizardModeRequested || (args.length === 0 && isInteractive());

// Handle wizard mode by removing 'wizard' from args
if (wizardModeRequested && wizardArgIndex >= 0) {
  args.splice(wizardArgIndex, 1);
}

// Extract targetDir (first non-flag argument, excluding flag values)
// Build set of indices consumed as flag values (tokens after --name/--domains/--repos)
const consumedIndices = new Set();
const flagsWithValues = ['--name', '--domains', '--repos'];
for (let i = 0; i < args.length; i++) {
  if (flagsWithValues.includes(args[i]) && i + 1 < args.length) {
    consumedIndices.add(i + 1);
  }
}
// targetDir = first non-flag, non-consumed argument, else default to 'aesop-fleet'
const targetDir = args.find((arg, idx) =>
  !arg.startsWith('--') &&
  !arg.startsWith('-') &&
  !consumedIndices.has(idx)
) || 'aesop-fleet';

// Parse onboarding flags
const projectName = getFlag('--name');
const domainsStr = getFlag('--domains');
const reposStr = getFlag('--repos');

// Validate target directory doesn't exist or is empty (except for .git and aesop files)
if (fs.existsSync(targetDir)) {
  const contents = fs.readdirSync(targetDir);
  // Allow .git and aesop scaffolded files to already exist (for idempotency)
  const aesopDirs = ['daemons', 'dash', 'monitor', 'tools', 'ui', 'docs', '.git', 'state'];
  const aesopFiles = [
    'aesop.config.example.json',
    'aesop.config.json',
    'README.md',
    'LICENSE',
    'CHANGELOG.md',
    'CLAUDE-TEMPLATE.md',
    'CLAUDE.md',
    'MEMORY-SEED.md'
  ];
  const allowedItems = new Set([...aesopDirs, ...aesopFiles]);

  const unexpectedContents = contents.filter(item => !allowedItems.has(item));
  if (unexpectedContents.length > 0) {
    console.error(`Error: Directory "${targetDir}" exists and contains unexpected files.`);
    console.error('Please choose a different target directory or remove the existing one.');
    process.exit(1);
  }

  // SECURITY: A pre-existing allowlisted entry (e.g. ".git", "state") must be a real
  // directory/file, never a symlink or junction. Following a symlinked entry here would
  // let scaffolding escape targetDir entirely (e.g. a symlinked .git whose "hooks"
  // subdirectory resolves outside targetDir). lstat (not stat) so the link itself is
  // inspected rather than whatever it points to.
  for (const item of contents) {
    const itemPath = path.join(targetDir, item);
    let itemLstat;
    try {
      itemLstat = fs.lstatSync(itemPath);
    } catch (e) {
      // lstat failed (race/permissions); nothing to check, move on
      continue;
    }
    if (itemLstat.isSymbolicLink()) {
      console.error(`Error: "${item}" in "${targetDir}" is a symlink (security risk).`);
      console.error('Refusing to scaffold through a symlinked entry. Remove it and re-run.');
      process.exit(1);
    }
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

function generateDomainText(domainsStr) {
  if (!domainsStr) {
    return '- **[Your domains here]** — [Customize per team]';
  }
  const domains = domainsStr.split(',').map(d => d.trim()).filter(d => d);
  if (domains.length === 0) {
    return '- **[Your domains here]** — [Customize per team]';
  }
  return domains
    .map(domain => `- **${domain}/** — [Add description for ${domain}]`)
    .join('\n');
}

function generateRepoText(reposStr) {
  if (!reposStr) {
    return '- **[Your repos here]** — [Customize per team]';
  }
  const repos = reposStr.split(',').map(r => r.trim()).filter(r => r);
  if (repos.length === 0) {
    return '- **[Your repos here]** — [Customize per team]';
  }
  return repos
    .map(repo => {
      const repoName = path.basename(repo);
      return `- **${repo}** — [${repoName} domains and setup]`;
    })
    .join('\n');
}

function substituteTemplate(templateContent, projectName, domainsStr, reposStr) {
  let result = templateContent;
  result = result.replace(/{{PROJECT_NAME}}/g, projectName || 'my-fleet');
  const domainList = domainsStr ? domainsStr.split(',').map(d => d.trim()).join(', ') : 'multi-domain';
  result = result.replace(/{{DOMAIN_LIST}}/g, domainList);
  result = result.replace(/{{DOMAINS}}/g, generateDomainText(domainsStr));
  result = result.replace(/{{REPO_LIST}}/g, generateRepoText(reposStr));
  return result;
}

function generateConfigJson(targetDir, templateRoot, projectName, reposStr) {
  // Read example config
  const exampleConfigPath = path.join(templateRoot, 'aesop.config.example.json');
  let exampleConfig;
  try {
    const content = fs.readFileSync(exampleConfigPath, 'utf8');
    exampleConfig = JSON.parse(content);
  } catch (e) {
    // Fallback config if example doesn't parse
    exampleConfig = {
      description: 'Aesop configuration',
      aesop_root: path.dirname(targetDir),
      brain_root: path.join(os.homedir(), '.claude'),
      scripts_root: path.join(os.homedir(), 'scripts'),
      temp_root: path.join(os.tmpdir()),
      repos: [],
      watchdog: {
        cycle_seconds: 150,
        heartbeat_threshold_seconds: 200,
        enable_secret_scan: true,
        secret_scan_script: 'tools/secret_scan.py'
      },
      monitor: {
        enable: true,
        cycle_seconds: 3600,
        heartbeat_threshold_seconds: 3600,
        memory_staleness_days: 30,
        log_max_lines: 500,
        log_max_kb: 40
      },
      dashboard: {
        refresh_seconds: 1,
        enable_jq_parsing: true,
        theme: 'dark'
      },
      cardinal_rules: {
        subagent_model: 'haiku',
        orchestrator_model: 'opus',
        tdd_first: true,
        never_push_main: true,
        secret_scan_gates_push: true
      }
    };
  }

  // Update with provided values
  exampleConfig.aesop_root = targetDir;
  exampleConfig.brain_root = '~/.claude';
  exampleConfig.scripts_root = '~/scripts';
  exampleConfig.temp_root = '~/.aesop-temp';
  exampleConfig._generated_note = 'This config uses portable ~ paths which expand at runtime on all platforms. Config loaders in ui/config.py (Python) and monitor/collect-signals.mjs (Node.js) automatically expand ~ paths to your home directory.';

  // Parse repos if provided
  if (reposStr) {
    const repos = reposStr.split(',').map(r => r.trim()).filter(r => r);
    exampleConfig.repos = repos.map((repoPath, idx) => ({
      path: repoPath,
      name: path.basename(repoPath),
      url: `https://github.com/user/${path.basename(repoPath)}.git`,
      primary_branch: 'main',
      backup_branch: 'backup/wip'
    }));
  }

  return exampleConfig;
}

// Print next steps and optionally run watchdog (returns a Promise)
async function printNextStepsAndWatchdog(rl, targetDir, configPath, port) {
  console.log('\n🎯 Next 3 commands to get started:\n');
  console.log(`  1. cd ${targetDir}`);
  console.log('  2. bash daemons/run-watchdog.sh --once  (one-time watchdog smoke test)');
  console.log(`  3. python ui/serve.py  (launch dashboard on localhost:${port})`);
  console.log('\n📖 After that, review:');
  console.log('  • CLAUDE.md (pre-filled with your project info)');
  console.log('  • aesop.config.json (pre-configured for your repos)');
  console.log('  • docs/MEMORY-TEMPLATE.md (edit ~/.claude/MEMORY.md with your facts)\n');

  return new Promise((resolve) => {
    rl.question('Run watchdog --once now? (y/N): ', (answer) => {
      if (answer.toLowerCase() === 'y') {
        console.log('\nRunning watchdog smoke test...');
        try {
          const watchdogScript = path.join(targetDir, 'daemons', 'run-watchdog.sh');
          if (fs.existsSync(watchdogScript)) {
            // Use bash to run the script
            execSync(`bash "${watchdogScript}" --once`, { stdio: 'inherit', cwd: targetDir });
            console.log('\n✓ Watchdog smoke test completed');
          }
        } catch (e) {
          console.error('\n⚠ Watchdog test failed (this is OK, continue manually)');
        }
      }
      rl.close();
      resolve();
    });
  });
}

function installPrePushHook(targetDir, templateRoot) {
  // Try to locate .git directory
  const gitDir = path.join(targetDir, '.git');
  if (!fs.existsSync(gitDir)) {
    // No git repo, skip hook installation silently
    return;
  }

  // SECURITY: Check if .git itself is a symlink/junction (refuse to follow it outside
  // targetDir). This mirrors the gitHooksDir/hookDest checks below — .git is one path
  // component higher and must be validated before anything derived from it is trusted.
  try {
    const gitDirLstat = fs.lstatSync(gitDir);
    if (gitDirLstat.isSymbolicLink()) {
      console.warn('⚠ Warning: .git is a symlink (security risk)');
      console.warn('  Skipping hook installation. Please remove the symlink and re-run scaffold.');
      return;
    }
  } catch (e) {
    // lstat failed; proceed (may be a permission issue)
  }

  // Ensure hooks directory exists
  const gitHooksDir = path.join(gitDir, 'hooks');
  if (!fs.existsSync(gitHooksDir)) {
    fs.mkdirSync(gitHooksDir, { recursive: true });
  }

  // SECURITY: Check if gitHooksDir is a symlink (refuse to install through symlinked dir)
  try {
    const hooksLstat = fs.lstatSync(gitHooksDir);
    if (hooksLstat.isSymbolicLink()) {
      console.warn('⚠ Warning: .git/hooks directory is a symlink (security risk)');
      console.warn('  Skipping hook installation. Please remove the symlink and re-run scaffold.');
      return;
    }
  } catch (e) {
    // lstat failed; proceed (may be a permission issue)
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
    // SECURITY: Check if existing hookDest is a symlink (refuse to follow it)
    try {
      const destLstat = fs.lstatSync(hookDest);
      if (destLstat.isSymbolicLink()) {
        console.warn('⚠ Warning: Existing .git/hooks/pre-push is a symlink (security risk)');
        console.warn('  Skipping hook installation. Please remove the symlink and re-run scaffold.');
        return;
      }
    } catch (e) {
      // lstat failed; proceed
    }

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

// Main execution function
(async () => {
  try {
    let finalProjectName = projectName;
    let finalReposStr = reposStr;
    let finalDomainsStr = domainsStr;
    let finalTargetDir = targetDir;
    let configPath = path.join(targetDir, 'aesop.config.json');
    let dashboardPort = 8770;

    let wizardRl = null;

    // Handle wizard mode
    if (wizardMode && isInteractive() && !yesFlag) {
      wizardRl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
      });

      console.log('\n🪄 Aesop interactive onboarding wizard');
      console.log('═'.repeat(50));
      console.log('Answer these 4 questions to set up your fleet in 60 seconds.');
      console.log('Press Enter to accept defaults (shown in parentheses).\n');

      // Q1: Project name
      finalProjectName = await promptUser(wizardRl, 'Project name', 'my-fleet');

      // Q2: Repos to watch
      console.log('\nDiscovering git repos in your home directory...');
      const discoveredRepos = discoverRepos(os.homedir());
      let selectedRepos = '';

      if (discoveredRepos.length > 0) {
        console.log(`Found ${discoveredRepos.length} git repo(s):\n`);
        discoveredRepos.forEach((repo, i) => {
          console.log(`  ${i + 1}. ${repo.name} (${repo.path})`);
        });
        console.log('\nEnter repo paths to watch (comma-separated), or press Enter to skip:');
        selectedRepos = await promptUser(wizardRl, 'Repos', '');
        if (!selectedRepos && discoveredRepos.length > 0) {
          // Auto-select the first discovered repo if user presses Enter
          selectedRepos = discoveredRepos[0].path;
          console.log(`  → Using: ${selectedRepos}`);
        }
      } else {
        selectedRepos = await promptUser(wizardRl, 'Repos to watch (paths, comma-separated)', '');
      }
      finalReposStr = selectedRepos;

      // Q3: Dashboard port
      let port = '';
      while (!port) {
        port = await promptUser(wizardRl, 'Dashboard port', '8770');
        const validPort = validatePort(port);
        if (!validPort) {
          console.log('  ✗ Invalid port. Must be a number between 1 and 65535.');
          port = '';
        } else {
          dashboardPort = validPort;
        }
      }

      // Q4: Brain root
      const brainRoot = await promptUser(wizardRl, 'Brain root directory', '~/.claude');

      console.log('\n✨ Scaffolding your fleet...\n');

      // Update config path for wizard-generated config
      configPath = path.join(finalTargetDir, 'aesop.config.json');
    } else if (yesFlag && wizardMode) {
      // Non-interactive defaults for wizard mode with --yes
      finalProjectName = 'my-fleet';
      finalReposStr = '';
      dashboardPort = 8770;
      console.log('🪄 Running onboarding wizard with defaults (--yes)');
    }

    // Copy template files
    filesToCopy.forEach(item => {
      const src = path.join(templateRoot, item);
      const dest = path.join(finalTargetDir, item);
      if (fs.existsSync(src)) {
        copyRecursive(src, dest);
        console.log(`✓ Copied ${item}`);
      }
    });

    // Create state/ directory
    const stateDir = path.join(finalTargetDir, 'state');
    if (!fs.existsSync(stateDir)) {
      fs.mkdirSync(stateDir, { recursive: true });
      console.log('✓ Created state/ directory');
    }

    // If --name or wizard provided, generate CLAUDE.md and aesop.config.json
    if (finalProjectName) {
      // Generate CLAUDE.md from template
      const templatePath = path.join(finalTargetDir, 'CLAUDE-TEMPLATE.md');
      const claudeMdPath = path.join(finalTargetDir, 'CLAUDE.md');
      if (fs.existsSync(templatePath)) {
        const templateContent = fs.readFileSync(templatePath, 'utf8');
        const claudeContent = substituteTemplate(templateContent, finalProjectName, finalDomainsStr, finalReposStr);
        fs.writeFileSync(claudeMdPath, claudeContent);
        console.log('✓ Generated CLAUDE.md (from template with substitutions)');
      }

      // Check if aesop.config.json already exists (for wizard mode)
      if (fs.existsSync(configPath) && wizardMode && isInteractive()) {
        // This should not happen in wizard mode since we're creating a new targetDir
        // But if it does, warn and skip
        console.warn(`⚠ Warning: aesop.config.json already exists at ${configPath}`);
      } else {
        // Generate aesop.config.json
        const config = generateConfigJson(finalTargetDir, templateRoot, finalProjectName, finalReposStr);
        // Update dashboard port if specified in wizard mode
        if (wizardMode && dashboardPort !== 8770) {
          config.dashboard.refresh_seconds = 1;
        }
        fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
        console.log('✓ Generated aesop.config.json (configured for your repos)');
      }
    }

    // Copy MEMORY-TEMPLATE.md as MEMORY-SEED.md
    const memoryTemplatePath = path.join(templateRoot, 'docs', 'MEMORY-TEMPLATE.md');
    const memorySeedPath = path.join(finalTargetDir, 'MEMORY-SEED.md');
    if (fs.existsSync(memoryTemplatePath) && !fs.existsSync(memorySeedPath)) {
      fs.copyFileSync(memoryTemplatePath, memorySeedPath);
      console.log('✓ Copied MEMORY-SEED.md (template for your facts)');
    }

    // Install the pre-push hook
    installPrePushHook(finalTargetDir, templateRoot);

    console.log(`\n✅ Scaffolded aesop template into "${finalTargetDir}" (${copiedCount} files)`);

    if (wizardMode && wizardRl) {
      // Wizard mode: print next steps and offer to run watchdog
      await printNextStepsAndWatchdog(wizardRl, finalTargetDir, configPath, dashboardPort);
      process.exit(0);
    } else if (wizardMode) {
      // Wizard mode with --yes flag (non-interactive)
      console.log('\n🎯 Next 3 commands to get started:\n');
      console.log(`  1. cd ${finalTargetDir}`);
      console.log('  2. bash daemons/run-watchdog.sh --once  (one-time watchdog smoke test)');
      console.log(`  3. python ui/serve.py  (launch dashboard on localhost:${dashboardPort})`);
      console.log('\n📖 After that, review:');
      console.log('  • CLAUDE.md (pre-filled with your project info)');
      console.log('  • aesop.config.json (pre-configured for your repos)');
      console.log('  • docs/MEMORY-TEMPLATE.md (edit ~/.claude/MEMORY.md with your facts)');
      process.exit(0);
    } else if (finalProjectName) {
      console.log('\nHeadless scaffolding complete! Next steps:');
      console.log(`  1. cd ${finalTargetDir}`);
      console.log('  2. Review CLAUDE.md (pre-filled with your project info)');
      console.log('  3. Review aesop.config.json (pre-configured for your repos)');
      console.log('\nInitialize your brain (Claude Code team memory):');
      console.log('  4. mkdir -p ~/.claude/memory');
      console.log(`  5. cp ${finalTargetDir}/CLAUDE.md ~/.claude/CLAUDE.md  (or review existing ~/.claude/CLAUDE.md)`);
      console.log(`  6. cp ${finalTargetDir}/MEMORY-SEED.md ~/.claude/MEMORY.md  (then add your facts)`);
      console.log('\nRun the daemon and dashboard:');
      console.log('  7. bash daemons/run-watchdog.sh --once  (test run)');
      console.log('  8. python ui/serve.py  (launch dashboard on localhost:8770)');
    } else {
      console.log('\nConfiguration steps:');
      console.log(`  1. cd ${finalTargetDir}`);
      console.log('  2. cp aesop.config.example.json aesop.config.json');
      console.log('  3. Edit aesop.config.json with your configuration');
      console.log('\nInitialize your brain (Claude Code team memory):');
      console.log('  4. mkdir -p ~/.claude/memory');
      console.log(`  5. cp ${finalTargetDir}/CLAUDE-TEMPLATE.md ~/.claude/CLAUDE.md  (then edit domains/team info)`);
      console.log(`  6. cp ${finalTargetDir}/MEMORY-SEED.md ~/.claude/MEMORY.md  (then add your facts)`);
      console.log('\nRun the daemon and dashboard:');
      console.log('  7. bash daemons/run-watchdog.sh --once  (test run)');
      console.log('  8. python ui/serve.py  (launch dashboard on localhost:8770)');
    }
    console.log('\nFor full documentation, see the README.md in the scaffolded directory.');
    process.exit(0);
  } catch (err) {
    console.error(`Error scaffolding template: ${err.message}`);
    process.exit(1);
  }
})();
