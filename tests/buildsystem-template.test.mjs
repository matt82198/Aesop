// Static structural tests for the vendored one-turn-wave dispatch template.
// The template is a Workflow script (runs inside the Claude Code harness runtime),
// so it cannot be executed here — these assert its load-bearing structure as text.
import test from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'skills', 'buildsystem', 'wave-flat-dispatch.template.mjs'), 'utf8');

test('meta block is a pure literal export', () => {
  assert.match(src, /export const meta = \{/);
  assert.match(src, /name: 'wave-flat-dispatch'/);
});

test('no runtime-breaking calls (Date.now/Math.random unavailable in workflow scripts)', () => {
  assert.ok(!src.includes('Date.now('), 'Date.now() breaks workflow resume');
  assert.ok(!src.includes('Math.random('), 'Math.random() breaks workflow resume');
});

test('args parse-if-string defense present', () => {
  assert.match(src, /typeof A === 'string'/);
});

test('preflight disjoint-ownership guard aborts before Build', () => {
  assert.ok(src.includes("'ownership_overlap'"), 'ownership_overlap abort missing');
  assert.ok(src.indexOf('ownership_overlap') < src.indexOf("phase('Build')"),
    'guard must precede the Build fan-out');
});

test('safety brake and cost ceiling are wired', () => {
  assert.ok(src.includes('A.brake'), 'brake gate missing');
  assert.ok(src.toLowerCase().includes('ceiling'), 'cost-ceiling support missing');
});

test('real-repo ship guard hard-fails on bad expectTopLevel', () => {
  assert.ok(src.includes('expectTopLevel') && src.includes('bad_expectTopLevel'));
});

test('no personal or private paths ship in the template', () => {
  assert.ok(!/C:[\/]+Users|conductor3|matt8/i.test(src), 'private path leaked into shipped template');
});

test('selfCheckCmd per-item validation support present', () => {
  assert.ok(src.includes('selfCheckCmd'), 'selfCheckCmd field missing');
  assert.ok(src.includes("it.selfCheckCmd"), 'selfCheckCmd usage missing');
  assert.ok(src.includes("'Self-Check'"), 'Self-Check phase missing');
});

test('build-report existence check code present', () => {
  assert.ok(src.includes('filesWritten'), 'filesWritten validation missing');
  assert.ok(src.includes('selfCheckResults'), 'selfCheckResults tracking missing');
});

test('testCmds array support implemented', () => {
  assert.ok(src.includes('A.testCmds'), 'testCmds array support missing');
  assert.ok(src.includes('Array.isArray(A.testCmds)'), 'testCmds array check missing');
  assert.ok(src.includes('testCommands.map'), 'testCmds iteration missing');
});

test('postBuild pipeline action support present', () => {
  assert.ok(src.includes('A.postBuild'), 'postBuild config missing');
  assert.ok(src.includes("'PostBuild'"), 'PostBuild phase missing');
  assert.ok(src.includes('afterItems'), 'postBuild afterItems missing');
});

test('tail-cap output requirement in verify agents', () => {
  assert.ok(src.includes('tail -n 40'), 'output tail-cap instruction missing');
});

test('pipefail / EXIT CODE handling documented', () => {
  assert.ok(src.includes('EXIT CODE'), 'EXIT CODE requirement missing');
  assert.ok(src.includes('set -o pipefail'), 'pipefail guidance missing');
});

test('absolute path requirement in worker prompts', () => {
  assert.ok(src.includes('absolute paths'), 'absolute path requirement missing in worker prompt');
  assert.ok(src.includes('IMPORTANT: All file writes MUST use absolute paths'), 'absolute path requirement not emphasized');
});

test('selfCheckCmd and postBuild do not use Date.now/Math.random', () => {
  const selfCheckSection = src.substring(src.indexOf("'Self-Check'"), src.indexOf("'Integrate'"));
  const postBuildSection = src.substring(src.indexOf("'PostBuild'"), src.indexOf("'Ship'"));
  assert.ok(!selfCheckSection.includes('Date.now('), 'Date.now() in selfCheck phase');
  assert.ok(!selfCheckSection.includes('Math.random('), 'Math.random() in selfCheck phase');
  assert.ok(!postBuildSection.includes('Date.now('), 'Date.now() in postBuild phase');
  assert.ok(!postBuildSection.includes('Math.random('), 'Math.random() in postBuild phase');
});

test('deterministic label counter used instead of random', () => {
  assert.ok(src.includes('_labelCounter'), 'deterministic counter missing');
  assert.ok(src.includes('nextLabel'), 'nextLabel function missing');
  assert.ok(!src.includes('Math.random()'), 'Math.random() should not appear');
});

test('selfCheckFailed items included in repair targets', () => {
  assert.ok(src.includes('selfCheckFailed'), 'selfCheckFailed tracking missing');
  assert.ok(src.includes('allFailingItems'), 'combined failing items tracking missing');
  assert.ok(src.includes('[...failingSlugs, ...selfCheckFailed]'), 'self-check failures not merged with integration failures');
});

test('existing backward compatibility: single testCmd still works', () => {
  assert.ok(src.includes('testCmd:'), 'single testCmd support removed');
  assert.ok(src.includes('verify('), 'verify function still exists');
});
