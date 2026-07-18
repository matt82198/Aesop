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
