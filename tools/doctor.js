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
  // Try python3 first
  const result3 = spawnSync('python3', ['--version'], { stdio: 'ignore', timeout: 5000 });
  if (result3.error && result3.error.code === 'ENOENT') {
    // python3 not found, try python fallback
    const result = spawnSync('python', ['--version'], { stdio: 'ignore', timeout: 5000 });
    if (result.error && result.error.code === 'ENOENT') {
      // Neither python3 nor python found
      return { passed: false, hint: 'python3 or python not found on PATH' };
    }
    if (result.status !== 0) {
      // python exists but returned non-zero exit code
      return { passed: false, hint: 'python found but returned non-zero exit code' };
    }
    return { passed: true, hint: '' };
  }
  if (result3.status !== 0) {
    // python3 exists but returned non-zero exit code
    return { passed: false, hint: 'python3 found but returned non-zero exit code' };
  }
  return { passed: true, hint: '' };
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

// Check if port 8770 is free (using socket connection test)
function checkPort8770() {
  return new Promise((resolve) => {
    let resolved = false;
    const sock = net.createConnection({ port: 8770, host: '127.0.0.1', timeout: 500 });

    const cleanup = () => {
      try {
        sock.destroy();
      } catch (e) {
        // Ignore cleanup errors
      }
    };

    sock.on('connect', () => {
      if (!resolved) {
        resolved = true;
        cleanup();
        resolve({ passed: false, hint: 'Port 8770 is in use' });
      }
    });

    sock.on('error', () => {
      // Connection failed, port is free
      if (!resolved) {
        resolved = true;
        cleanup();
        resolve({ passed: true, hint: '' });
      }
    });

    sock.on('timeout', () => {
      if (!resolved) {
        resolved = true;
        cleanup();
        resolve({ passed: true, hint: '' });
      }
    });

    // Fallback timeout to ensure we resolve within 2 seconds
    setTimeout(() => {
      if (!resolved) {
        resolved = true;
        cleanup();
        resolve({ passed: true, hint: '' });
      }
    }, 2000);
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
    try {
      const portResult = await checkPort8770();
      results.push({ label: 'Port 8770 available', ...portResult });
      console.log(formatRow('Port 8770 available', portResult.passed, portResult.hint));
    } catch (e) {
      results.push({ label: 'Port 8770 available', passed: false, hint: 'Port check failed' });
      console.log(formatRow('Port 8770 available', false, 'Port check failed'));
    }

    const allPassed = results.every(r => r.passed);
    const passCount = results.filter(r => r.passed).length;
    const failCount = results.length - passCount;

    console.log(`\n${COLORS.BOLD}Summary: ${passCount}/${results.length} checks passed${COLORS.RESET}`);

    if (allPassed) {
      console.log(`${COLORS.GREEN}✓ You are ready to run: bash daemons/run-watchdog.sh --once${COLORS.RESET}\n`);
      process.exitCode = 0;
    } else {
      console.log(`${COLORS.RED}✗ Fix the ${failCount} failed check(s) above and try again${COLORS.RESET}\n`);
      process.exitCode = 1;
    }
  } catch (err) {
    console.error(`Error running doctor: ${err.message}`);
    process.exit(1);
  }
})();
