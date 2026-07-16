#!/usr/bin/env node

/**
 * Aesop doctor — preflight checklist for adopter onboarding
 *
 * Runs diagnostic checks and prints a readiness table.
 * Exit code 0 = all checks passed; 1 = at least one failed.
 */

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const net = require('net');

const CURRENT_DIR = process.cwd();

// ANSI color helpers
const COLORS = {
  GREEN: '\x1b[32m',
  RED: '\x1b[31m',
  RESET: '\x1b[0m',
  BOLD: '\x1b[1m'
};

function colorPass() {
  return `${COLORS.GREEN}✓ PASS${COLORS.RESET}`;
}

function colorFail() {
  return `${COLORS.RED}✗ FAIL${COLORS.RESET}`;
}

// Check Node.js version >= 18
function checkNodeVersion() {
  const version = parseInt(process.versions.node.split('.')[0], 10);
  const passed = version >= 18;
  const hint = passed ? '' : `Found Node.js v${process.versions.node}, need >=18`;
  return { passed, hint };
}

// Check Python available (python3 or python)
function checkPython() {
  try {
    // Try python3 first
    spawnSync('python3', ['--version'], { stdio: 'ignore', timeout: 5000 });
    return { passed: true, hint: '' };
  } catch (e) {
    try {
      // Fallback to python
      spawnSync('python', ['--version'], { stdio: 'ignore', timeout: 5000 });
      return { passed: true, hint: '' };
    } catch (e2) {
      return { passed: false, hint: 'python3 or python not found on PATH' };
    }
  }
}

// Check git repo (.git directory exists)
function checkGitRepo() {
  const gitDir = path.join(CURRENT_DIR, '.git');
  const passed = fs.existsSync(gitDir);
  const hint = passed ? '' : 'Not inside a git repository';
  return { passed, hint };
}

// Check aesop.config.json exists and is valid JSON
function checkConfig() {
  const configPath = path.join(CURRENT_DIR, 'aesop.config.json');
  try {
    if (!fs.existsSync(configPath)) {
      return { passed: false, hint: 'aesop.config.json not found' };
    }
    const content = fs.readFileSync(configPath, 'utf8');
    JSON.parse(content);
    return { passed: true, hint: '' };
  } catch (e) {
    return { passed: false, hint: `Config parse error: ${e.message}` };
  }
}

// Check required directories exist
function checkDirectories() {
  const requiredDirs = ['daemons', 'dash', 'monitor', 'tools', 'ui'];
  const missing = requiredDirs.filter(dir => {
    const dirPath = path.join(CURRENT_DIR, dir);
    return !fs.existsSync(dirPath) || !fs.statSync(dirPath).isDirectory();
  });

  if (missing.length === 0) {
    return { passed: true, hint: '' };
  } else {
    return { passed: false, hint: `Missing: ${missing.join(', ')}` };
  }
}

// Check git pre-push hook installed
function checkPrePushHook() {
  const hookPath = path.join(CURRENT_DIR, '.git', 'hooks', 'pre-push');
  const passed = fs.existsSync(hookPath);
  const hint = passed ? '' : 'Pre-push hook not installed at .git/hooks/pre-push';
  return { passed, hint };
}

// Check if port 8770 is free
function checkPort8770() {
  return new Promise((resolve) => {
    const server = net.createServer();

    const onError = (err) => {
      server.close();
      if (err.code === 'EADDRINUSE') {
        resolve({ passed: false, hint: 'Port 8770 is in use' });
      } else {
        resolve({ passed: false, hint: `Port check error: ${err.code}` });
      }
    };

    const onListening = () => {
      server.close(() => {
        resolve({ passed: true, hint: '' });
      });
    };

    server.once('error', onError);
    server.once('listening', onListening);

    // Set a timeout to avoid hanging
    const timeout = setTimeout(() => {
      server.removeListener('error', onError);
      server.removeListener('listening', onListening);
      server.destroy();
      resolve({ passed: false, hint: 'Port check timeout' });
    }, 3000);

    server.on('close', () => {
      clearTimeout(timeout);
    });

    server.listen({ port: 8770, host: '127.0.0.1' });
  });
}

// Format a row in the readiness table
function formatRow(label, status, hint) {
  const statusStr = status ? colorPass() : colorFail();
  const hintStr = hint ? ` — ${hint}` : '';
  // Pad label to 35 chars for alignment
  const paddedLabel = label.padEnd(35);
  return `  ${paddedLabel} ${statusStr}${hintStr}`;
}

// Main execution
(async function main() {
  try {
    console.log(`\n${COLORS.BOLD}Aesop Readiness Check${COLORS.RESET}\n`);

    const syncChecks = [
      { label: 'Node.js version ≥18', fn: checkNodeVersion },
      { label: 'Python (python3 or python)', fn: checkPython },
      { label: 'Git repository', fn: checkGitRepo },
      { label: 'aesop.config.json (valid JSON)', fn: checkConfig },
      { label: 'Required directories (daemons, dash, monitor, tools, ui)', fn: checkDirectories },
      { label: 'Git pre-push hook installed', fn: checkPrePushHook }
    ];

    const results = [];

    // Run sync checks
    for (const check of syncChecks) {
      const result = check.fn();
      results.push({ label: check.label, ...result });
      console.log(formatRow(check.label, result.passed, result.hint));
    }

    // Run async port check
    const portResult = await checkPort8770();
    results.push({ label: 'Port 8770 available', ...portResult });
    console.log(formatRow('Port 8770 available', portResult.passed, portResult.hint));

    const allPassed = results.every(r => r.passed);
    const passCount = results.filter(r => r.passed).length;
    const failCount = results.length - passCount;

    console.log(`\n${COLORS.BOLD}Summary: ${passCount}/${results.length} checks passed${COLORS.RESET}`);

    if (allPassed) {
      console.log(`${COLORS.GREEN}✓ You are ready to run: bash daemons/run-watchdog.sh --once${COLORS.RESET}\n`);
      process.exit(0);
    } else {
      console.log(`${COLORS.RED}✗ Fix the ${failCount} failed check(s) above and try again${COLORS.RESET}\n`);
      process.exit(1);
    }
  } catch (err) {
    console.error(`Error running doctor: ${err.message}`);
    process.exit(1);
  }
})();
