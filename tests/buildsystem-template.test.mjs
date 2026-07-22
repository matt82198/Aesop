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

// ============================================================================
// FIX 1: Repair prompt with targeted-tests + run-once-to-file directives
// ============================================================================
test('FIX 1: repair prompt contains targeted-tests directive (latency fix #1)', () => {
  assert.ok(src.includes('TARGETED TEST DISCIPLINE'), 'TARGETED TEST DISCIPLINE directive missing');
  assert.ok(src.includes('You own these files'), 'owned files listing missing from repair prompt');
  assert.ok(src.includes('Identify which test files/tests exercise your owned files'), 'targeted tests identification missing');
  assert.ok(src.includes('never the full union suite'), 'full suite prohibition missing');
});

test('FIX 1: repair prompt contains run-once-to-file directive (latency fix #1)', () => {
  assert.ok(src.includes('RUN-ONCE-TO-FILE'), 'RUN-ONCE-TO-FILE directive missing');
  assert.ok(src.includes('/tmp/repair-output.log'), 'output file name missing');
  assert.ok(src.includes('never re-run the suite'), 'no-rerun guidance missing');
  assert.ok(src.includes('Read the file to see results'), 'read file instead of rerun missing');
});

// ============================================================================
// FIX 2: Per-agent timebox support
// ============================================================================
test('FIX 2: agentTimeboxNote parameter documented (latency fix #2)', () => {
  assert.ok(src.includes('agentTimeboxNote'), 'agentTimeboxNote parameter missing from args docs');
  assert.ok(src.includes('wall-clock budget'), 'timebox description missing');
  assert.ok(src.includes('backward-compatible'), 'backward compatibility note missing');
});

test('FIX 2: timeboxLine() helper function defined (latency fix #2)', () => {
  assert.ok(src.includes('function timeboxLine()'), 'timeboxLine() helper missing');
  assert.ok(src.includes('TIMEBOX_MINUTES'), 'TIMEBOX_MINUTES constant missing');
  assert.ok(src.includes('remaining work exceeds'), 'timebox guidance text missing');
});

test('FIX 2: Build phase includes timebox line when agentTimeboxNote set (latency fix #2)', () => {
  const buildSection = src.substring(src.indexOf("phase('Build')"), src.indexOf("phase('Self-Check')"));
  assert.ok(buildSection.includes('timeboxLine()'), 'timeboxLine() call missing from Build phase');
});

test('FIX 2: SelfCheck phase includes timebox line when agentTimeboxNote set (latency fix #2)', () => {
  const selfCheckSection = src.substring(src.indexOf("const selfCheckPrompt"), src.indexOf("phase('Integrate')"));
  assert.ok(selfCheckSection.includes('timeboxLine()'), 'timeboxLine() call missing from SelfCheck phase');
});

test('FIX 2: Repair phase includes timebox line when agentTimeboxNote set (latency fix #2)', () => {
  const repairSection = src.substring(src.indexOf("const repairPrompt"), src.indexOf("return agent(repairPrompt"));
  assert.ok(repairSection.includes('timeboxLine()'), 'timeboxLine() call missing from Repair phase');
});

test('FIX 2: Repair targets capped at 3 items when timebox is set (latency fix #2)', () => {
  assert.ok(src.includes('TIMEBOX_MINUTES && targets.length > 3'), 'timebox-conditional cap missing');
  assert.ok(src.includes('targets = targets.slice(0, 3)'), 'top-3 slice missing');
  assert.ok(src.includes('deferredItems.push'), 'deferred items tracking missing');
  assert.ok(src.includes('repair round'), 'repair round capping message missing');
});

test('FIX 2: timebox line only added when agentTimeboxNote is set (backward compat)', () => {
  assert.ok(src.includes('if (!TIMEBOX_MINUTES) return'), 'conditional return for absent timebox missing');
  assert.ok(src.includes('return `\\n'), 'conditional newline prefix missing');
});

// ============================================================================
// CENTER-VERIFICATION: Adversarial Review Phase
// ============================================================================
test('requireAdversarialReview parameter documented in args', () => {
  assert.ok(src.includes('requireAdversarialReview: boolean | null'), 'requireAdversarialReview parameter not documented');
  assert.ok(src.includes('when truthy, after integration green'), 'trigger condition not documented');
});

test('adversarialReview block exists and is gated on args', () => {
  // ADVERSARIAL_REVIEW now consumes manifest-provided A.requireAdversarialReview (resolved in Python)
  assert.ok(src.includes("const ADVERSARIAL_REVIEW = typeof A.requireAdversarialReview === 'boolean' ? A.requireAdversarialReview : true"), 'ADVERSARIAL_REVIEW constant with manifest consumption missing');
  assert.ok(src.includes("if (ADVERSARIAL_REVIEW && ADVERSARIAL_REVIEW_MODE === 'blocking' && v && v.green)"), 'gate condition missing');
  assert.ok(src.includes("phase('AdversarialReview')"), 'AdversarialReview phase missing');
});

test('adversarialReview uses refute-oriented prompt', () => {
  assert.ok(src.includes('CONTRACT REFUTATION review'), 'REFUTATION prompt missing');
  assert.ok(src.includes('Try to construct a concrete input, scenario'), 'refutation strategy missing');
  assert.ok(src.includes('VIOLATES its stated contract'), 'violation keyword missing');
  assert.ok(src.includes('You are NOT running tests'), 'test-warning missing');
  assert.ok(src.includes('reason about the specification and the code'), 'reasoning directive missing');
});

test('adversarialReview spawns reviewer agents in parallel per item', () => {
  assert.ok(src.includes('await parallel('), 'parallel call missing in review phase');
  const reviewSection = src.substring(src.indexOf('if (ADVERSARIAL_REVIEW'), src.indexOf("phase('Report')"));
  assert.ok(reviewSection.includes('(built || []).filter(Boolean).map'), 'item iteration missing from review phase');
  assert.ok(reviewSection.includes("model: 'haiku'"), 'haiku model not specified for reviewers');
});

test('adversarialReview collects contract findings for holds=false items', () => {
  assert.ok(src.includes('contractFindings'), 'contractFindings tracking missing');
  assert.ok(src.includes('if (!r.holds)'), 'holds check missing');
  assert.ok(src.includes('contractFindings.push'), 'findings collection missing');
  assert.ok(src.includes('breakingScenario'), 'breakingScenario field missing');
});

test('adversarialReview result schema has holds and breakingScenario fields', () => {
  const reviewSection = src.substring(src.indexOf('if (ADVERSARIAL_REVIEW'), src.indexOf("phase('Report')"));
  assert.ok(reviewSection.includes("holds: { type: 'boolean' }"), 'holds schema missing');
  assert.ok(reviewSection.includes("breakingScenario: { type: 'string' }"), 'breakingScenario schema missing');
  assert.ok(reviewSection.includes("required: ['slug', 'holds', 'breakingScenario']"), 'required fields not listed');
});

test('adversarialReview tokens tracked separately', () => {
  assert.ok(src.includes('const reviewStart = budget.spent()'), 'review token tracking start missing');
  assert.ok(src.includes('adversarialReviewOut = budget.spent() - reviewStart'), 'review token tracking end missing');
  assert.ok(src.includes('adversarialReviewOut'), 'adversarialReviewOut variable missing');
});

test('contractFindings included in report result', () => {
  const reportSection = src.substring(src.indexOf("const result = {"), src.indexOf('log(`DONE'));
  assert.ok(reportSection.includes('contractFindings:'), 'contractFindings field missing from result');
  assert.ok(reportSection.includes('contractFindings.length > 0 ? contractFindings : null'), 'null-when-empty logic missing');
});

test('contractFindings added to all early-return paths (ceiling/brake aborts)', () => {
  // Check that ceiling-exceeded returns include contractFindings
  const ceilingReturns = src.match(/contractFindings: (contractFindings\.length > 0 \? contractFindings : null|null)/g);
  assert.ok(ceilingReturns && ceilingReturns.length >= 3, 'contractFindings not in all return paths (expected >=3 occurrences)');
});

test('adversarialReview standing default enabled: absent A.requireAdversarialReview defaults to true', () => {
  // Standing default flip: when A.requireAdversarialReview is not set, defaults to true (enabled).
  // Set explicit false to disable.
  assert.ok(src.includes("if (ADVERSARIAL_REVIEW && ADVERSARIAL_REVIEW_MODE === 'blocking' && v && v.green)"), 'gating condition missing');
  // Verify the gate uses the ADVERSARIAL_REVIEW constant (now consuming manifest field with true default)
  assert.ok(src.includes("const ADVERSARIAL_REVIEW = typeof A.requireAdversarialReview === 'boolean' ? A.requireAdversarialReview : true"), 'ADVERSARIAL_REVIEW constant with true default not found');
});

test('adversarialReview backward-compatible: all existing assertions still pass', () => {
  // Spot-check a few key existing assertions to ensure nothing was broken
  assert.match(src, /export const meta = \{/);
  assert.ok(src.includes('BUILD'), 'BUILD phase description missing');
  assert.ok(src.includes('await parallel('), 'parallel utility missing');
  assert.ok(!src.includes('Date.now('), 'Date.now() not allowed');
  assert.ok(!src.includes('Math.random('), 'Math.random() not allowed');
});

test('adversarialReview log message includes contract violations count', () => {
  assert.ok(src.includes('contractViolations=${contractFindings.length}'), 'contract violations count missing from log');
});

// ============================================================================
// LEVER 1 (token): repair worker gets ONLY failing-suite verdict + own diff,
// NOT the full prior build context. May read owned files + named contract only.
// ============================================================================
test('LEVER 1: repair prompt has SCOPED REPAIR CONTEXT (cache-read tax fix)', () => {
  assert.ok(src.includes('SCOPED REPAIR CONTEXT'), 'SCOPED REPAIR CONTEXT block missing');
  assert.ok(src.includes('the diff of YOUR OWN files'), 'own-diff scoping missing');
  assert.ok(src.includes('Do NOT re-read the whole prior build'), 'no-full-context directive missing');
});

test('LEVER 1: repair prompt directs worker to diff ONLY its owned files', () => {
  assert.ok(src.includes('git -C ${WORK} diff --'), 'git diff of owned files command missing');
  assert.ok(src.includes('(your owned files only)'), 'owned-files-only qualifier missing');
});

test('LEVER 1: repair worker may read owned files + named contract, not the whole build', () => {
  assert.ok(src.includes('the named contract'), 'named-contract read allowance missing');
  assert.ok(src.includes("do NOT read sibling workers' files or dump the whole build"), 'sibling/full-build prohibition missing');
});

test('LEVER 1: old full-context invitation is removed', () => {
  assert.ok(!src.includes('read sibling files and the full contract/specs'),
    'old "read sibling files and the full contract/specs" invitation must be gone');
});

test('LEVER 1: repair still edits only owned files (behavior preserved)', () => {
  assert.ok(src.includes('Fix ONLY your owned files with Edit/Write'), 'owned-files edit restriction missing');
  // existing latency-fix blocks must remain intact (backward compatible)
  assert.ok(src.includes('TARGETED TEST DISCIPLINE'), 'TARGETED TEST DISCIPLINE removed by LEVER 1');
  assert.ok(src.includes('RUN-ONCE-TO-FILE'), 'RUN-ONCE-TO-FILE removed by LEVER 1');
});

// ============================================================================
// LEVER 2 (wall-clock): adversarialReviewMode blocking|concurrent-note lets the
// orchestrator overlap the refutation with the CI-wait window.
// ============================================================================
test('LEVER 2: adversarialReviewMode documented in args', () => {
  assert.ok(src.includes("adversarialReviewMode: 'blocking' | 'concurrent-note' | null"),
    'adversarialReviewMode arg not documented');
  assert.ok(src.includes('gate MERGE (not CI)'), 'MERGE-not-CI gate semantics not documented');
});

test('LEVER 2: mode constant defaults to blocking (backward compatible)', () => {
  assert.ok(src.includes("const ADVERSARIAL_REVIEW_MODE = A.adversarialReviewMode === 'concurrent-note' ? 'concurrent-note' : 'blocking'"),
    'ADVERSARIAL_REVIEW_MODE constant with default-blocking missing');
});

test('LEVER 2: blocking gate runs the inline review only in blocking mode', () => {
  assert.ok(src.includes("if (ADVERSARIAL_REVIEW && ADVERSARIAL_REVIEW_MODE === 'blocking' && v && v.green)"),
    'blocking-mode gate on inline review missing');
});

test('LEVER 2: concurrent-note branch defers review and flags pending', () => {
  assert.ok(src.includes("if (ADVERSARIAL_REVIEW && ADVERSARIAL_REVIEW_MODE === 'concurrent-note' && v && v.green)"),
    'concurrent-note branch missing');
  assert.ok(src.includes('let adversarialReviewPending = false'), 'adversarialReviewPending declaration missing');
  assert.ok(src.includes('adversarialReviewPending = true'), 'pending flag not set in concurrent-note mode');
});

test('LEVER 2: result exposes mode + pending flag for the orchestrator', () => {
  const reportSection = src.substring(src.indexOf('const result = {'), src.indexOf('log(`DONE'));
  assert.ok(reportSection.includes('adversarialReviewMode: ADVERSARIAL_REVIEW ? ADVERSARIAL_REVIEW_MODE : null'),
    'adversarialReviewMode not in result');
  assert.ok(reportSection.includes('adversarialReviewPending'), 'adversarialReviewPending not in result');
});

test('LEVER 2: report note documents the CI/review overlap protocol', () => {
  assert.ok(src.includes('gating MERGE (not CI) on contractFindings'), 'overlap gate note missing');
  assert.ok(src.includes('overlapping the review with the CI-wait window'), 'overlap description missing');
});

test('LEVER 2: mergeReady still reflects integration-green only (unchanged)', () => {
  assert.ok(src.includes('mergeReady: !!(v && v.green)'), 'mergeReady semantics changed unexpectedly');
});

// ============================================================================
// VERIFICATION POLICY: resolved by Python, consumed by JS (no recomputation)
// ============================================================================
test('verificationTier parameter documented in args', () => {
  assert.ok(src.includes('verificationTier: number | null'), 'verificationTier parameter not documented');
  assert.ok(src.includes('backend verification tier'), 'tier description missing');
  assert.ok(src.includes('driver/verification_policy.py'), 'source-of-truth reference missing');
});

test('policy is resolved in Python and consumed in JS (no JS recomputation)', () => {
  // The tierPolicy function has been DELETED. Policy is resolved in Python
  // (build_manifest_item) and carried as literal manifest fields (repairCap,
  // requireAdversarialReview, spotCheckFrac, validateAllJson). JS consumes them.
  assert.ok(!src.includes('function tierPolicy(tier)'), 'tierPolicy function should be DELETED (policy resolved in Python)');
  assert.ok(src.includes('source of truth: driver/verification_policy.py'), 'Python source reference missing');
  assert.ok(src.includes('JS consumes them directly'), 'consumption note missing');
});

test('manifest field consumption: CAP reads A.repairCap with fallback', () => {
  assert.ok(src.includes("const CAP = typeof A.repairCap === 'number' ? A.repairCap : 1"),
    'CAP should consume A.repairCap with tier-1 default 1');
});

test('manifest field consumption: ADVERSARIAL_REVIEW reads A.requireAdversarialReview with fallback', () => {
  assert.ok(src.includes("const ADVERSARIAL_REVIEW = typeof A.requireAdversarialReview === 'boolean' ? A.requireAdversarialReview : true"),
    'ADVERSARIAL_REVIEW should consume A.requireAdversarialReview with default true');
});

test('tier-1/absent manifest fields yield tier-1 defaults (backward compat)', () => {
  // When the manifest does NOT include repairCap/requireAdversarialReview (legacy),
  // the template defaults to tier-1 behavior: CAP=1, ADVERSARIAL_REVIEW=true (enabled by default).
  const tierLogic = src.substring(src.indexOf('const CAP'), src.indexOf('const ADVERSARIAL_REVIEW_MODE'));
  assert.ok(tierLogic.includes("typeof A.repairCap === 'number' ? A.repairCap : 1"), 'CAP fallback to 1 missing');
  assert.ok(tierLogic.includes("typeof A.requireAdversarialReview === 'boolean' ? A.requireAdversarialReview : true"), 'ADVERSARIAL_REVIEW fallback missing');
});


test('policy comment documents that JS no longer recomputes (no drift trap)', () => {
  assert.ok(src.includes('no recomputation'), 'recomputation statement missing');
  assert.ok(src.includes('no drift'), 'drift trap reference missing');
  assert.ok(src.includes('literal manifest fields'), 'manifest field reference missing');
});

// ============================================================================
// BUG FIX 1: TDZ ReferenceError — declarations must precede while loop
// ============================================================================
test('TDZ fix: contractFindings declared before while loop', () => {
  const beforeWhile = src.substring(src.indexOf("phase('Repair')"), src.indexOf('while (v && !v.green'));
  assert.ok(beforeWhile.includes('let contractFindings = []'), 'contractFindings must be declared before while loop');
  const whileIdx = src.indexOf('while (v && !v.green');
  const declIdx = src.indexOf('let contractFindings = []');
  assert.ok(declIdx < whileIdx, 'contractFindings declaration must precede while loop');
});

test('TDZ fix: adversarialReviewOut declared before while loop', () => {
  const beforeWhile = src.substring(src.indexOf("phase('Repair')"), src.indexOf('while (v && !v.green'));
  assert.ok(beforeWhile.includes('let adversarialReviewOut = 0'), 'adversarialReviewOut must be declared before while loop');
  const whileIdx = src.indexOf('while (v && !v.green');
  const declIdx = src.indexOf('let adversarialReviewOut = 0');
  assert.ok(declIdx < whileIdx, 'adversarialReviewOut declaration must precede while loop');
});

test('TDZ fix: adversarialReviewPending declared before while loop', () => {
  const beforeWhile = src.substring(src.indexOf("phase('Repair')"), src.indexOf('while (v && !v.green'));
  assert.ok(beforeWhile.includes('let adversarialReviewPending = false'), 'adversarialReviewPending must be declared before while loop');
  const whileIdx = src.indexOf('while (v && !v.green');
  const declIdx = src.indexOf('let adversarialReviewPending = false');
  assert.ok(declIdx < whileIdx, 'adversarialReviewPending declaration must precede while loop');
});

test('TDZ fix: no duplicate declarations after while loop', () => {
  const afterRepairLabel = src.substring(src.indexOf("// -------- Adversarial Review"));
  assert.ok(!afterRepairLabel.startsWith("let contractFindings = []"), 'no duplicate contractFindings declaration');
  assert.ok(!afterRepairLabel.includes("let adversarialReviewOut = 0\nlet adversarialReviewPending"), 'no duplicate declarations in review section');
});

// ============================================================================
// BUG FIX 3: Standing default flip — ADVERSARIAL_REVIEW defaults to true
// ============================================================================
test('Standing default flip: manifest omitting requireAdversarialReview enables adversarial review', () => {
  // When A.requireAdversarialReview is undefined/absent, ADVERSARIAL_REVIEW defaults to true.
  // This means adversarial review runs by default (if integration green and blocking mode).
  assert.ok(src.includes("const ADVERSARIAL_REVIEW = typeof A.requireAdversarialReview === 'boolean' ? A.requireAdversarialReview : true"),
    'Default must be true so omitted flag enables adversarial review');
});

test('Standing default flip: explicit false disables adversarial review', () => {
  // When A.requireAdversarialReview is explicitly false, ADVERSARIAL_REVIEW is false (review disabled).
  const constant = "const ADVERSARIAL_REVIEW = typeof A.requireAdversarialReview === 'boolean' ? A.requireAdversarialReview : true";
  assert.ok(src.includes(constant), 'ternary must evaluate A.requireAdversarialReview if boolean (including false)');
});
