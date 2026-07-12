#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');

const args = process.argv.slice(2);
const helpFlag = args.includes('--help') || args.includes('-h');
const forceFlag = args.includes('--force');

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

Arguments:
  target-dir    Directory to scaffold the template into (default: "aesop-fleet")

Options:
  --help, -h              Show this help message
  --force                 Replace any existing .git/hooks/pre-push during scaffold
  --name <name>           Project name (for headless scaffolding; generates CLAUDE.md + aesop.config.json)
  --domains <list>        Comma-separated domain list (e.g., "api,worker,monitoring")
  --repos <paths>         Comma-separated repo paths (e.g., "/path/to/repo1,/path/to/repo2")

Examples:
  npx @matt82198/aesop                                      # Creates ./aesop-fleet/ with template
  npx @matt82198/aesop my-fleet                             # Creates ./my-fleet/ with template
  npx @matt82198/aesop my-fleet --force                     # Re-scaffold and replace hooks
  npx @matt82198/aesop orchestrator --name "my-service"     # Headless: generates CLAUDE.md + config
  npx @matt82198/aesop orchestrator --name "api" \\
    --domains "server,worker" --repos "/path/to/api"        # Full headless with domains and repos

After scaffolding with --name, cd into the directory and:
  1. Review CLAUDE.md (pre-filled with your project info)
  2. Review aesop.config.json (pre-configured for your repos)
  3. Run: bash daemons/run-watchdog.sh --once
  4. Launch dashboard: python ui/serve.py
`);
  process.exit(0);
}

// Extract targetDir (first non-flag argument)
const allFlagNames = ['--name', '--domains', '--repos', '--force'];
const targetDir = args.filter(arg =>
  !arg.startsWith('--') &&
  !arg.startsWith('-') &&
  !allFlagNames.some((flag, idx, arr) => idx > 0 && args[idx - 1] === flag && arg === args[args.indexOf(flag) + 1])
)[0] || 'aesop-fleet';

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
  exampleConfig.brain_root = path.join(os.homedir(), '.claude');
  exampleConfig.scripts_root = path.join(os.homedir(), 'scripts');
  exampleConfig.temp_root = path.join(os.tmpdir());

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

  // Create state/ directory
  const stateDir = path.join(targetDir, 'state');
  if (!fs.existsSync(stateDir)) {
    fs.mkdirSync(stateDir, { recursive: true });
    console.log('✓ Created state/ directory');
  }

  // If --name provided, generate CLAUDE.md and aesop.config.json
  if (projectName) {
    // Generate CLAUDE.md from template
    const templatePath = path.join(targetDir, 'CLAUDE-TEMPLATE.md');
    const claudeMdPath = path.join(targetDir, 'CLAUDE.md');
    if (fs.existsSync(templatePath)) {
      const templateContent = fs.readFileSync(templatePath, 'utf8');
      const claudeContent = substituteTemplate(templateContent, projectName, domainsStr, reposStr);
      fs.writeFileSync(claudeMdPath, claudeContent);
      console.log('✓ Generated CLAUDE.md (from template with substitutions)');
    }

    // Generate aesop.config.json
    const configPath = path.join(targetDir, 'aesop.config.json');
    const config = generateConfigJson(targetDir, templateRoot, projectName, reposStr);
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
    console.log('✓ Generated aesop.config.json (configured for your repos)');
  }

  // Copy MEMORY-TEMPLATE.md as MEMORY-SEED.md
  const memoryTemplatePath = path.join(templateRoot, 'docs', 'MEMORY-TEMPLATE.md');
  const memorySeedPath = path.join(targetDir, 'MEMORY-SEED.md');
  if (fs.existsSync(memoryTemplatePath) && !fs.existsSync(memorySeedPath)) {
    fs.copyFileSync(memoryTemplatePath, memorySeedPath);
    console.log('✓ Copied MEMORY-SEED.md (template for your facts)');
  }

  // Install the pre-push hook
  installPrePushHook(targetDir, templateRoot);

  console.log(`\n✅ Scaffolded aesop template into "${targetDir}" (${copiedCount} files)`);

  if (projectName) {
    console.log('\nHeadless scaffolding complete! Next steps:');
    console.log(`  1. cd ${targetDir}`);
    console.log('  2. Review CLAUDE.md (pre-filled with your project info)');
    console.log('  3. Review aesop.config.json (pre-configured for your repos)');
    console.log('\nInitialize your brain (Claude Code team memory):');
    console.log('  4. mkdir -p ~/.claude/memory');
    console.log(`  5. cp ${targetDir}/CLAUDE.md ~/.claude/CLAUDE.md  (or review existing ~/.claude/CLAUDE.md)`);
    console.log(`  6. cp ${targetDir}/MEMORY-SEED.md ~/.claude/MEMORY.md  (then add your facts)`);
    console.log('\nRun the daemon and dashboard:');
    console.log('  7. bash daemons/run-watchdog.sh --once  (test run)');
    console.log('  8. python ui/serve.py  (launch dashboard on localhost:8770)');
  } else {
    console.log('\nConfiguration steps:');
    console.log(`  1. cd ${targetDir}`);
    console.log('  2. cp aesop.config.example.json aesop.config.json');
    console.log('  3. Edit aesop.config.json with your configuration');
    console.log('\nInitialize your brain (Claude Code team memory):');
    console.log('  4. mkdir -p ~/.claude/memory');
    console.log(`  5. cp ${targetDir}/CLAUDE-TEMPLATE.md ~/.claude/CLAUDE.md  (then edit domains/team info)`);
    console.log(`  6. cp ${targetDir}/MEMORY-SEED.md ~/.claude/MEMORY.md  (then add your facts)`);
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
