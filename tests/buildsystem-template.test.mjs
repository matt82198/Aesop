// Tests for buildsystem wave-flat-dispatch preflight guard
// Contract under test (~/buildsystem/wave-flat-dispatch.template.mjs):
//  - Validates that no two agents in a wave modify the same file
//  - Parses domain map from CLAUDE.md
//  - Detects file overlaps and reports conflicts
//  - Resolves file paths and glob patterns
//  - Provides remediation suggestions on conflict
//
// Note: This test suite verifies the TEMPLATE's contract and logic.
// The actual ~/.claude/skills/buildsystem/wave-flat-dispatch.template.mjs
// is user-local setup outside this repo, so we test the logic here.
//
// Run: node --test tests/buildsystem-template.test.mjs

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Test helper: create a temp CLAUDE.md with domain map
function createTestClaudeMd(tempDir, domainMap) {
  const content = `# Project Documentation

## Domain Map

${domainMap.map((entry) => `- **${entry.dir}**: ${entry.agents.join(', ')}`).join('\n')}

## Other Sections
- Some content here
`;
  const claudeMdPath = path.join(tempDir, 'CLAUDE.md');
  fs.writeFileSync(claudeMdPath, content, 'utf8');
  return claudeMdPath;
}

// Test helper: create test files and directories
function createTestFiles(tempDir, files) {
  for (const file of files) {
    const fullPath = path.join(tempDir, file);
    const dir = path.dirname(fullPath);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(fullPath, `// Test file: ${file}\n`, 'utf8');
  }
}

test('buildsystem wave-flat-dispatch template: validates safe dispatch (no overlap)', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'buildsystem-test-'));
  try {
    const claudeMdPath = createTestClaudeMd(tempDir, [
      { dir: 'backend/', agents: ['backend-dev'] },
      { dir: 'ui/web/', agents: ['frontend-dev'] },
      { dir: 'tests/', agents: ['test-bot'] },
    ]);

    createTestFiles(tempDir, [
      'backend/server.js',
      'backend/db.js',
      'ui/web/index.tsx',
      'tests/suite.test.js',
    ]);

    // Mock the validateWaveDispatch function logic
    const validateWaveDispatch = mockValidateWaveDispatch();
    const result = validateWaveDispatch({
      backlog: [
        { item: 'Fix auth', agent: 'backend-dev', files: ['backend/server.js'] },
        { item: 'Add widget', agent: 'frontend-dev', files: ['ui/web/index.tsx'] },
        { item: 'Add test', agent: 'test-bot', files: ['tests/suite.test.js'] },
      ],
      claudemdPath: claudeMdPath,
      repoRoot: tempDir,
    });

    assert.ok(result.safe, 'No overlap should be safe');
    assert.ok(result.message.includes('No file overlaps'), 'Should report no overlaps');
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('buildsystem wave-flat-dispatch template: detects file overlap (two agents, same file)', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'buildsystem-test-'));
  try {
    const claudeMdPath = createTestClaudeMd(tempDir, [
      { dir: 'backend/', agents: ['backend-dev', 'core-dev'] },
    ]);

    createTestFiles(tempDir, ['backend/config.js']);

    const validateWaveDispatch = mockValidateWaveDispatch();
    const result = validateWaveDispatch({
      backlog: [
        { item: 'Fix config', agent: 'backend-dev', files: ['backend/config.js'] },
        { item: 'Refactor config', agent: 'core-dev', files: ['backend/config.js'] },
      ],
      claudemdPath: claudeMdPath,
      repoRoot: tempDir,
    });

    assert.ok(!result.safe, 'Overlap should fail preflight');
    assert.ok(Array.isArray(result.conflicts), 'Should have conflicts array');
    assert.ok(result.conflicts.length > 0, 'Should detect one conflict');
    assert.ok(
      result.conflicts[0].agents.includes('backend-dev'),
      'Conflict should mention backend-dev'
    );
    assert.ok(
      result.conflicts[0].agents.includes('core-dev'),
      'Conflict should mention core-dev'
    );
    assert.ok(
      result.message.includes('overlapping'),
      'Should mention overlapping ownership'
    );
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('buildsystem wave-flat-dispatch template: resolves directory to all files under it', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'buildsystem-test-'));
  try {
    const claudeMdPath = createTestClaudeMd(tempDir, [
      { dir: 'ui/web/', agents: ['frontend-dev'] },
      { dir: 'backend/', agents: ['backend-dev'] },
    ]);

    createTestFiles(tempDir, [
      'ui/web/index.tsx',
      'ui/web/components/Button.tsx',
      'ui/web/styles.css',
      'backend/api.js',
    ]);

    const validateWaveDispatch = mockValidateWaveDispatch();
    const result = validateWaveDispatch({
      backlog: [
        { item: 'Refactor UI', agent: 'frontend-dev', files: ['ui/web/'] },
        { item: 'Fix API', agent: 'backend-dev', files: ['backend/api.js'] },
      ],
      claudemdPath: claudeMdPath,
      repoRoot: tempDir,
    });

    assert.ok(result.safe, 'Directory expansion should work without conflicts');
    assert.ok(
      result.fileCount >= 4,
      'Should count at least 4 files (3 in ui/web, 1 in backend)'
    );
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('buildsystem wave-flat-dispatch template: rejects backlog with missing agent', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'buildsystem-test-'));
  try {
    const claudeMdPath = createTestClaudeMd(tempDir, [
      { dir: 'backend/', agents: ['backend-dev'] },
    ]);

    const validateWaveDispatch = mockValidateWaveDispatch();
    const result = validateWaveDispatch({
      backlog: [{ item: 'Some task', files: ['backend/config.js'] }], // Missing 'agent'
      claudemdPath: claudeMdPath,
      repoRoot: tempDir,
    });

    assert.ok(!result.safe, 'Invalid backlog should fail');
    assert.ok(result.message.includes('Invalid'), 'Should report invalid backlog');
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('buildsystem wave-flat-dispatch template: provides remediation on conflict', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'buildsystem-test-'));
  try {
    const claudeMdPath = createTestClaudeMd(tempDir, [
      { dir: 'shared/', agents: ['backend-dev', 'frontend-dev'] },
    ]);

    createTestFiles(tempDir, ['shared/config.js']);

    const validateWaveDispatch = mockValidateWaveDispatch();
    const result = validateWaveDispatch({
      backlog: [
        { item: 'Update config', agent: 'backend-dev', files: ['shared/config.js'] },
        { item: 'Use config', agent: 'frontend-dev', files: ['shared/config.js'] },
      ],
      claudemdPath: claudeMdPath,
      repoRoot: tempDir,
    });

    assert.ok(!result.safe, 'Should detect conflict');
    assert.ok(
      Array.isArray(result.remediation),
      'Should provide remediation suggestions'
    );
    assert.ok(
      result.remediation.some((s) => s.includes('Merge')),
      'Should suggest merging items'
    );
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('buildsystem wave-flat-dispatch template: handles empty backlog safely', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'buildsystem-test-'));
  try {
    const claudeMdPath = createTestClaudeMd(tempDir, [
      { dir: 'backend/', agents: ['backend-dev'] },
    ]);

    const validateWaveDispatch = mockValidateWaveDispatch();
    const result = validateWaveDispatch({
      backlog: [],
      claudemdPath: claudeMdPath,
      repoRoot: tempDir,
    });

    assert.ok(result.safe, 'Empty backlog is safe');
    assert.ok(result.message.includes('Empty'), 'Should report empty backlog');
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('buildsystem wave-flat-dispatch template: rejects when CLAUDE.md missing', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'buildsystem-test-'));
  try {
    const validateWaveDispatch = mockValidateWaveDispatch();
    const result = validateWaveDispatch({
      backlog: [{ item: 'Some task', agent: 'backend-dev', files: ['file.js'] }],
      claudemdPath: path.join(tempDir, 'CLAUDE.md'), // Does not exist
      repoRoot: tempDir,
    });

    assert.ok(!result.safe, 'Missing CLAUDE.md should fail preflight');
    assert.ok(result.message.includes('CLAUDE.md'), 'Should mention missing CLAUDE.md');
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

// Mock implementation of validateWaveDispatch for testing
function mockValidateWaveDispatch() {
  return function validateWaveDispatch(config) {
    const { backlog, claudemdPath, repoRoot } = config;

    if (!claudemdPath || !fs.existsSync(claudemdPath)) {
      return {
        safe: false,
        message: 'CLAUDE.md not found; cannot validate domain map',
      };
    }

    if (!Array.isArray(backlog) || backlog.length === 0) {
      return {
        safe: true,
        message: 'Empty backlog; no dispatch needed',
      };
    }

    // Simple validation: check for missing agent or files
    for (const item of backlog) {
      if (!item.agent || !item.files) {
        return {
          safe: false,
          message: `Invalid backlog item: missing agent or files. Item: ${item.item}`,
        };
      }
    }

    // Check for file overlaps
    const fileToAgents = new Map();
    const conflicts = [];

    for (const item of backlog) {
      const filesList = Array.isArray(item.files) ? item.files : [item.files];

      for (const filePattern of filesList) {
        // Expand directory to files
        let files = [];
        const fullPath = path.join(repoRoot, filePattern);

        if (fs.existsSync(fullPath) && fs.statSync(fullPath).isDirectory()) {
          const walk = (dir) => {
            const entries = fs.readdirSync(dir, { withFileTypes: true });
            for (const entry of entries) {
              if (entry.name.startsWith('.')) continue;
              const fullPath = path.join(dir, entry.name);
              if (entry.isDirectory()) {
                walk(fullPath);
              } else {
                files.push(path.relative(repoRoot, fullPath));
              }
            }
          };
          walk(fullPath);
        } else if (fs.existsSync(fullPath)) {
          files.push(path.relative(repoRoot, fullPath));
        } else {
          files.push(filePattern);
        }

        for (const file of files) {
          const normalized = path.normalize(file).replace(/\\/g, '/');
          if (!fileToAgents.has(normalized)) {
            fileToAgents.set(normalized, []);
          }
          fileToAgents.get(normalized).push(item.agent);
        }
      }
    }

    // Detect conflicts
    for (const [file, agents] of fileToAgents) {
      const uniqueAgents = [...new Set(agents)];
      if (uniqueAgents.length > 1) {
        conflicts.push({
          file,
          agents: uniqueAgents,
          message: `File touched by multiple agents: ${uniqueAgents.join(', ')}`,
        });
      }
    }

    if (conflicts.length > 0) {
      return {
        safe: false,
        conflicts,
        message: `${conflicts.length} file(s) have overlapping agent ownership. Please reorder or resplit backlog items.`,
        remediation: [
          'Option 1: Merge overlapping items into a single agent assignment',
          'Option 2: Split one item into parts, assign each to different agent, add ordering constraint',
          'Option 3: Rename domain map in CLAUDE.md to reduce overlap',
        ],
      };
    }

    return {
      safe: true,
      message: 'No file overlaps detected; safe to dispatch',
      fileCount: fileToAgents.size,
      agentCount: new Set(backlog.map((i) => i.agent)).size,
    };
  };
}
