#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const helpFlag = args.includes('--help') || args.includes('-h');

if (helpFlag) {
  console.log(`
aesop — Multi-agent orchestration template scaffolder

Usage:
  npx @matt82198/aesop [target-dir]

Arguments:
  target-dir    Directory to scaffold the template into (default: "aesop-fleet")

Examples:
  npx @matt82198/aesop                    # Creates ./aesop-fleet/
  npx @matt82198/aesop my-fleet           # Creates ./my-fleet/
  npx @matt82198/aesop /tmp/my-orchestrator  # Creates /tmp/my-orchestrator/

Options:
  --help, -h    Show this help message

After scaffolding, cd into the directory and:
  1. Copy aesop.config.example.json → aesop.config.json
  2. Edit aesop.config.json with your paths and repos
  3. Run: bash daemons/run-watchdog.sh --once
  4. Launch dashboard: python ui/serve.py
`);
  process.exit(0);
}

const targetDir = args[0] || 'aesop-fleet';

if (args.length > 1) {
  console.error('Error: Too many arguments. Use --help for usage.');
  process.exit(1);
}

// Validate target directory doesn't exist or is empty
if (fs.existsSync(targetDir)) {
  const contents = fs.readdirSync(targetDir);
  if (contents.length > 0) {
    console.error(`Error: Directory "${targetDir}" exists and is not empty.`);
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
  'CHANGELOG.md'
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

try {
  filesToCopy.forEach(item => {
    const src = path.join(templateRoot, item);
    const dest = path.join(targetDir, item);
    if (fs.existsSync(src)) {
      copyRecursive(src, dest);
      console.log(`✓ Copied ${item}`);
    }
  });

  console.log(`\n✅ Scaffolded aesop template into "${targetDir}" (${copiedCount} files)`);
  console.log('\nNext steps:');
  console.log(`  1. cd ${targetDir}`);
  console.log('  2. cp aesop.config.example.json aesop.config.json');
  console.log('  3. Edit aesop.config.json with your configuration');
  console.log('  4. bash daemons/run-watchdog.sh --once  (test run)');
  console.log('  5. python ui/serve.py  (launch dashboard)');
  console.log('\nFor full documentation, see the README.md in the scaffolded directory.');
  process.exit(0);
} catch (err) {
  console.error(`Error scaffolding template: ${err.message}`);
  process.exit(1);
}
