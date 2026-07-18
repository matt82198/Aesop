// ============================================================================
// wave-flat-dispatch.template.mjs — REUSABLE one-turn-wave harness
// ----------------------------------------------------------------------------
// Encodes the measured A/B-winning pattern (flat fan-out beat a Sonnet mid-tier 4.3x on cost at equal quality):
// a whole wave's BUILD phase — flat Haiku fan-out (one worker per file-disjoint
// item) + integration verify + bounded repair — collapses into ONE Workflow
// call = ONE orchestrator turn, at flat-dispatch cost (no Sonnet mid-tier).
//
// It is fully parameterized by `args` (no task hardcoded here). Point it at any
// wave by passing a manifest. Hardening baked in from this session's CI cascades:
//   * PREFLIGHT disjoint-file-ownership guard  -> prevents union-drift (the root
//     cause of both red-main incidents this session: two items green vs their own
//     base but the UNION on main breaks).
//   * Fixture honesty gate (optional setup must prove red-on-stubs).
//   * Bounded repair with per-item failure attribution.
//
// args = {
//   base:        string  // sandbox/work root (absolute)
//   workDir:     string  // dir where implementers write + where testCmd runs
//   testCmd:     string  // integration command, e.g. "python -m pytest test_suite.py -q"
//   contractHint:string  // one line telling workers where the shared contract/specs live
//   setup:      { prompt: string } | null   // optional: builds+verifies the sandbox (unmeasured)
//   items:      [ { slug, ownsFiles:[string], prompt:string } ]
//   repairCap:   number  // default 1
//   brake:      { checkCmd: string, cwd?: string } | null  // optional kill-switch/cost-ceiling
//              // gate run BEFORE any worker spawns (wave-26 critique fix — wires .HALT/cost_ceiling
//              // into DISPATCH, not just the backup daemon). Aborts the whole wave if engaged.
//              // Absent => unchanged behavior (generic/non-aesop waves unaffected).
//   ceiling:    { tokens?: number, recheckBrake?: boolean } | null  // optional live cost ceiling
//              // tokens: abort if budget.spent() exceeds this before Build, before each Repair round,
//              // and before Ship. Returns graceful partial result {aborted:true, reason:'cost_ceiling'}
//              // with existing build/integration state included for potential resume.
//              // recheckBrake: if true and args.brake exists, re-run the brake agent before each
//              // Repair round (allows .HALT set mid-wave to stop the next phase).
//              // Absent => unchanged behavior (backward-compatible).
// }
// Returns: { preflight, build, integration:{green,passed,failed}, repairsUsed,
//            tokens:{buildOut,verifyOut,repairOut,totalOut}, mergeReady:boolean, aborted, reason }
//          (may include aborted:true, reason:'cost_ceiling', spent, ceiling when ceiling exceeded)
// ============================================================================

export const meta = {
  name: 'wave-flat-dispatch',
  description: 'One-turn wave: preflight disjoint-ownership guard -> flat Haiku fan-out (1 worker/item) -> integration verify -> bounded repair. Reusable; parameterized by args manifest.',
  phases: [
    { title: 'Preflight', detail: 'disjoint-file-ownership guard + optional sandbox build/verify' },
    { title: 'Build', detail: 'parallel Haiku, one per file-disjoint item' },
    { title: 'Integrate', detail: 'run the integration test command on the union' },
    { title: 'Repair', detail: 'bounded repair round(s) for failing items' },
    { title: 'Report', detail: 'per-item status + merge-readiness + token cost' },
  ],
}

let A = args || {}
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }  // args may arrive as a JSON string
const WORK = A.workDir
const TEST = A.testCmd
const ITEMS = Array.isArray(A.items) ? A.items : []
const CAP = typeof A.repairCap === 'number' ? A.repairCap : 1
const HINT = A.contractHint || `Read the shared contract/spec files in ${WORK} before implementing.`
const CEILING = A.ceiling ? { tokens: A.ceiling.tokens, recheckBrake: A.ceiling.recheckBrake } : null

const DONE = {
  type: 'object', additionalProperties: false,
  properties: {
    slug: { type: 'string' }, wrote: { type: 'boolean' },
    filesWritten: { type: 'array', items: { type: 'string' } }, note: { type: 'string' },
  },
  required: ['slug', 'wrote', 'filesWritten', 'note'],
}
const SETUP = {
  type: 'object', additionalProperties: false,
  properties: {
    ok: { type: 'boolean' }, redOnStubs: { type: 'number' },
    greenOnReference: { type: 'boolean' }, totalTests: { type: 'number' }, note: { type: 'string' },
  },
  required: ['ok', 'redOnStubs', 'greenOnReference', 'totalTests', 'note'],
}
const VERIFY = {
  type: 'object', additionalProperties: false,
  properties: {
    passed: { type: 'number' }, failed: { type: 'number' }, green: { type: 'boolean' },
    failingItems: { type: 'array', items: { type: 'string' } }, detail: { type: 'string' },
  },
  required: ['passed', 'failed', 'green', 'failingItems', 'detail'],
}
const SHIP = {
  type: 'object', additionalProperties: false,
  properties: {
    committed: { type: 'boolean' }, pushed: { type: 'boolean' }, sha: { type: 'string' },
    fileCount: { type: 'number' }, oneCommit: { type: 'boolean' }, note: { type: 'string' },
  },
  required: ['committed', 'pushed', 'sha', 'fileCount', 'oneCommit', 'note'],
}

// ---------------- Preflight ----------------
phase('Preflight')
if (!WORK || !TEST || !ITEMS.length) {
  log('ABORT: args must include workDir, testCmd, and a non-empty items[].')
  return { aborted: true, reason: 'bad_manifest' }
}
// Disjoint-file-ownership guard (union-drift prevention).
const owner = {}
const conflicts = []
for (const it of ITEMS) {
  for (const f of (it.ownsFiles || [])) {
    if (owner[f]) conflicts.push({ file: f, items: [owner[f], it.slug] })
    else owner[f] = it.slug
  }
}
if (conflicts.length) {
  log(`ABORT: file-ownership overlap (union-drift risk): ${conflicts.map(c => `${c.file} <- ${c.items.join(' & ')}`).join('; ')}`)
  return { aborted: true, reason: 'ownership_overlap', conflicts }
}
log(`Preflight OK: ${ITEMS.length} items, ${Object.keys(owner).length} owned files, no overlap.`)

// Check ceiling before any worker spawns (if set).
{
  const spent = budget.spent()
  if (CEILING && typeof CEILING.tokens === 'number' && spent > CEILING.tokens) {
    log(`ABORT: cost ceiling exceeded at preflight (spent ${spent} > ${CEILING.tokens}).`)
    return {
      preflight: { items: ITEMS.length, ownedFiles: Object.keys(owner).length, sandbox: null },
      build: [],
      integration: { green: false, passed: null, failed: null },
      repairsUsed: 0,
      tokens: { buildOut: 0, verifyOut: 0, repairOut: 0, totalOut: spent, model: 'all-haiku (weight 1)' },
      mergeReady: false,
      ship: null,
      aborted: true,
      reason: 'cost_ceiling',
      spent,
      ceiling: CEILING.tokens,
    }
  }
}

// Safety brake (optional): kill-switch (.HALT) + cost-ceiling gate, run BEFORE any worker spawns.
// Wires the aesop brake into the DISPATCH itself (wave-26 critique #1/#5). Workflow scripts have no
// fs/shell access, so the check is delegated to a cheap read-only agent that runs args.brake.checkCmd
// in args.brake.cwd. When args.brake is absent, behavior is exactly as before (backward-compatible).
if (A.brake && A.brake.checkCmd) {
  const BRAKE = {
    type: 'object', additionalProperties: false,
    properties: { halted: { type: 'boolean' }, reason: { type: 'string' } },
    required: ['halted', 'reason'],
  }
  const b = await agent(
    `READ-ONLY safety-brake check — do NOT modify anything. In directory ${A.brake.cwd || WORK}, run:\n${A.brake.checkCmd}\n` +
    `This checks the fleet kill-switch (.HALT sentinel) and/or the token cost-ceiling. Set halted=true if the command exits non-zero OR its output indicates HALTED / ceiling exceeded; set halted=false only if it clearly reports OK/clean/under-ceiling. Report the reason.`,
    { label: 'preflight:brake', phase: 'Preflight', model: 'haiku', schema: BRAKE }
  )
  if (b && b.halted) {
    log(`ABORT: safety brake engaged before dispatch — ${b.reason}. No workers spawned, no tokens spent on build.`)
    return { aborted: true, reason: 'halted', brake: b }
  }
  log(`Safety brake clear: ${b ? b.reason : '(no result — proceeding)'}.`)
}

let setupInfo = null
if (A.setup && A.setup.prompt) {
  const s = await agent(A.setup.prompt, { label: 'preflight:setup', phase: 'Preflight', model: 'sonnet', effort: 'high', schema: SETUP })
  if (!s || !s.ok || !(s.redOnStubs > 0)) {
    log('ABORT: sandbox setup failed its honesty gate (need ok + red-on-stubs > 0).')
    return { aborted: true, reason: 'setup_failed', setup: s }
  }
  setupInfo = s
  log(`Sandbox ready: ${s.totalTests} tests, ${s.redOnStubs} red on stubs${s.greenOnReference ? ', reference proved green' : ''}.`)
}

// Check ceiling before Build.
{
  const spent = budget.spent()
  if (CEILING && typeof CEILING.tokens === 'number' && spent > CEILING.tokens) {
    log(`ABORT: cost ceiling exceeded before Build (spent ${spent} > ${CEILING.tokens}).`)
    return {
      preflight: { items: ITEMS.length, ownedFiles: Object.keys(owner).length, sandbox: setupInfo },
      build: [],
      integration: { green: false, passed: null, failed: null },
      repairsUsed: 0,
      tokens: { buildOut: 0, verifyOut: 0, repairOut: 0, totalOut: spent, model: 'all-haiku (weight 1)' },
      mergeReady: false,
      ship: null,
      aborted: true,
      reason: 'cost_ceiling',
      spent,
      ceiling: CEILING.tokens,
    }
  }
}

// ---------------- Build (flat Haiku fan-out) ----------------
phase('Build')
const buildStart = budget.spent()
const built = await parallel(ITEMS.map((it) => () =>
  agent(
    `FLAT ONE-TURN-WAVE worker for item "${it.slug}". Working dir: ${WORK}. ${HINT}\n` +
    `You OWN and may write ONLY these files: ${(it.ownsFiles || []).join(', ')}. Do NOT create or edit any other file (strict ownership — another worker owns the rest, in parallel).\n` +
    `TASK:\n${it.prompt}\n` +
    `Use the Write tool. Run any quick local self-check you can, but the integration suite is run centrally, not by you. Report which files you wrote.`,
    { label: `build:${it.slug}`, phase: 'Build', model: 'haiku', schema: DONE }
  )
))
const buildOut = budget.spent() - buildStart
log(`Build done: ${built.filter(Boolean).length}/${ITEMS.length} workers reported.`)

// ---------------- Integrate + bounded Repair ----------------
function verify(tag, ph) {
  return agent(
    `Working dir: ${WORK}. Run: ${TEST}  (PowerShell or Git Bash). Report exact passed/failed counts, green=(failed===0), and for each failing test map it to the responsible item slug from this set: ${ITEMS.map(i => i.slug).join(', ')} (infer from the file/module in the traceback; a file is owned by exactly one item). Do not modify files.`,
    { label: `verify:${tag}`, phase: ph, model: 'haiku', schema: VERIFY }
  )
}
phase('Integrate')
let v = await verify('integrate', 'Integrate')
let verifyOut = 0, repairOut = 0, repairsUsed = 0
{
  const vEnd = budget.spent()
  verifyOut += vEnd - (buildStart + buildOut)
}

phase('Repair')
let round = 0
while (v && !v.green && round < CAP) {
  round++

  // Check ceiling before starting a repair round.
  {
    const spent = budget.spent()
    if (CEILING && typeof CEILING.tokens === 'number' && spent > CEILING.tokens) {
      log(`ABORT: cost ceiling exceeded before repair round ${round} (spent ${spent} > ${CEILING.tokens}).`)
      const totalOut = spent
      return {
        preflight: { items: ITEMS.length, ownedFiles: Object.keys(owner).length, sandbox: setupInfo },
        build: (built || []).filter(Boolean).map(b => ({ slug: b.slug, wrote: b.wrote, files: b.filesWritten })),
        integration: v ? { green: v.green, passed: v.passed, failed: v.failed } : { green: false, passed: null, failed: null },
        repairsUsed,
        tokens: { buildOut, verifyOut, repairOut, totalOut, model: 'all-haiku (weight 1)' },
        mergeReady: false,
        ship: null,
        aborted: true,
        reason: 'cost_ceiling',
        spent,
        ceiling: CEILING.tokens,
      }
    }
  }

  // Re-check brake before repair round if recheckBrake is set (allows mid-wave .HALT stops).
  if (CEILING && CEILING.recheckBrake && A.brake && A.brake.checkCmd) {
    const BRAKE = {
      type: 'object', additionalProperties: false,
      properties: { halted: { type: 'boolean' }, reason: { type: 'string' } },
      required: ['halted', 'reason'],
    }
    const b = await agent(
      `READ-ONLY safety-brake re-check before repair round ${round} — do NOT modify anything. In directory ${A.brake.cwd || WORK}, run:\n${A.brake.checkCmd}\n` +
      `This checks the fleet kill-switch (.HALT sentinel) and/or the token cost-ceiling. Set halted=true if the command exits non-zero OR its output indicates HALTED / ceiling exceeded; set halted=false only if it clearly reports OK/clean/under-ceiling. Report the reason.`,
      { label: `repair-${round}:brake`, phase: 'Repair', model: 'haiku', schema: BRAKE }
    )
    if (b && b.halted) {
      log(`ABORT: safety brake re-engaged before repair round ${round} — ${b.reason}. Stopping repairs.`)
      const spent = budget.spent()
      const totalOut = spent
      return {
        preflight: { items: ITEMS.length, ownedFiles: Object.keys(owner).length, sandbox: setupInfo },
        build: (built || []).filter(Boolean).map(b => ({ slug: b.slug, wrote: b.wrote, files: b.filesWritten })),
        integration: v ? { green: v.green, passed: v.passed, failed: v.failed } : { green: false, passed: null, failed: null },
        repairsUsed,
        tokens: { buildOut, verifyOut, repairOut, totalOut, model: 'all-haiku (weight 1)' },
        mergeReady: false,
        ship: null,
        aborted: true,
        reason: 'halted',
        brake: b,
      }
    }
  }

  const failingSlugs = (v.failingItems || []).filter(s => ITEMS.some(i => i.slug === s))
  const targets = failingSlugs.length ? ITEMS.filter(i => failingSlugs.includes(i.slug)) : ITEMS
  log(`Integration red (${v.failed} failed) — repair round ${round}/${CAP} on: ${targets.map(t => t.slug).join(', ')}`)
  repairsUsed = targets.length
  const rStart = budget.spent()
  await parallel(targets.map((it) => () =>
    agent(
      `ONE-TURN-WAVE repair for item "${it.slug}". Working dir: ${WORK}. The integration suite failed: ${v.detail}\n` +
      `You own: ${(it.ownsFiles || []).join(', ')}. You MAY now read sibling files and the full contract/specs to reconcile drift, but still edit ONLY your owned files. Fix them with Edit/Write. Report.`,
      { label: `repair:${it.slug}`, phase: 'Repair', model: 'haiku', schema: DONE }
    )
  ))
  const rEnd = budget.spent()
  repairOut += rEnd - rStart
  v = await verify(`repair-${round}`, 'Repair')
  verifyOut += budget.spent() - rEnd
}

// Check ceiling before Ship.
{
  const spent = budget.spent()
  if (CEILING && typeof CEILING.tokens === 'number' && spent > CEILING.tokens) {
    log(`ABORT: cost ceiling exceeded before Ship (spent ${spent} > ${CEILING.tokens}).`)
    const totalOut = spent
    return {
      preflight: { items: ITEMS.length, ownedFiles: Object.keys(owner).length, sandbox: setupInfo },
      build: (built || []).filter(Boolean).map(b => ({ slug: b.slug, wrote: b.wrote, files: b.filesWritten })),
      integration: v ? { green: v.green, passed: v.passed, failed: v.failed } : { green: false, passed: null, failed: null },
      repairsUsed,
      tokens: { buildOut, verifyOut, repairOut, totalOut, model: 'all-haiku (weight 1)' },
      mergeReady: v && v.green,
      ship: null,
      aborted: true,
      reason: 'cost_ceiling',
      spent,
      ceiling: CEILING.tokens,
    }
  }
}

// ---------------- Ship (batched git boundary — P2: one commit+push per WAVE, not per item) ----------------
let ship = null
if (A.git && v && v.green) {
  phase('Ship')
  const g = A.git
  const repoDir = g.repoDir || WORK
  const origin = g.origin || 'origin'
  const expectTop = g.expectTopLevel || (g.sandboxInit ? repoDir : null)
  // HARDENING (wave-22 incident): a corrupted manifest once passed the literal placeholder
  // "WORKTREE_ROOT_PER_ITEM" as expectTopLevel; the Ship guard then compared toplevel against a
  // non-path string that could never match, and the classifier had to catch the resulting
  // primary-tree/branch-"undefined" Ship prompt. In REAL-REPO mode expectTop MUST be a real
  // absolute path — hard-fail preflight-style here BEFORE assembling any Ship prompt, rather than
  // relying on the in-prompt guard to notice a garbage expected value.
  if (!g.sandboxInit) {
    const looksAbsolute = typeof expectTop === 'string' && /^([a-zA-Z]:[\\/]|\/)/.test(expectTop)
    const looksPlaceholder = typeof expectTop === 'string' && /[A-Z_]{6,}/.test(expectTop) && !/[\\/]/.test(expectTop)
    if (!expectTop || !looksAbsolute || looksPlaceholder || String(expectTop).includes('undefined')) {
      log(`ABORT Ship: args.git.expectTopLevel is not a real absolute path (got ${JSON.stringify(expectTop)}). Pass each item's actual sibling-worktree root, or omit args.git to skip the batched Ship and let the orchestrator run the merge train by hand.`)
      return {
        preflight: { items: ITEMS.length, ownedFiles: Object.keys(owner).length, sandbox: setupInfo },
        build: (built || []).filter(Boolean).map(b => ({ slug: b.slug, wrote: b.wrote, files: b.filesWritten })),
        integration: v ? { green: v.green, passed: v.passed, failed: v.failed } : { green: false, passed: null, failed: null },
        repairsUsed, mergeReady: v && v.green, ship: null,
        aborted: true, reason: 'bad_expectTopLevel', badValue: expectTop,
      }
    }
  }
  const scanLine = g.secretScan ? ` Then gate on secrets: \`python ${g.secretScan} --staged\` (must print CLEAN / exit 0; if it blocks, STOP and report committed=false).` : ''
  ship = await agent(
    `BATCHED GIT BOUNDARY — make ONE commit + ONE push for the WHOLE integrated wave (${ITEMS.length} items), NOT one per item, to amortize CI over the batch. Working tree: ${repoDir}. Use Git Bash.\n` +
    `*** SAFETY GUARD — DO THIS FIRST, before ANY git write: *** run \`git -C ${repoDir} rev-parse --show-toplevel\`.\n` +
    (g.sandboxInit
      ? `  - SANDBOX MODE: the result MUST be empty/error (no repo yet) OR exactly ${repoDir}. If it resolves to ANY ENCLOSING/ANCESTOR repo (a path SHORTER than / a prefix of ${repoDir}), you are inside another repo — ABORT NOW: do NOT init/add/commit/push anything; return committed=false, pushed=false, oneCommit=false, note="ABORT: sandbox inside repo <toplevel>". If safe: \`git -C ${repoDir} init -q\`, set a local user.name/user.email, create a LOCAL bare origin \`git init --bare -q ${g.sandboxInit}\`, then add/point the remote (\`git -C ${repoDir} remote add ${origin} ${g.sandboxInit}\`, or \`remote set-url\` if it exists). NEVER touch a remote named after a real host.\n`
      : `  - REAL-REPO MODE: the result MUST equal exactly ${expectTop}. If it does NOT, ABORT: do NOT add/commit/push; return committed=false, note="ABORT: toplevel <toplevel> != expected ${expectTop}". (This prevents ever committing into an unintended repo.)\n`) +
    `STAGE THE REAL BUILD — do NOT create any placeholder/dummy files: \`git -C ${repoDir} checkout -B ${g.branch}\` ; \`git -C ${repoDir} add -A\` (stages the files the build workers already wrote — the actual package/modules, specs, tests). Before committing, \`git -C ${repoDir} status --short\` and CONFIRM the staged set is the real source (NOT invented item*.txt).${scanLine} \`git -C ${repoDir} commit -q -m "${g.message || 'wave: batched one-turn build'}"\` ; ` +
    (g.push === false ? `do NOT push (report pushed=false).` : `\`git -C ${repoDir} push -q -u ${origin} ${g.branch}\`.`) +
    `\nVERIFY + REPORT: \`git -C ${repoDir} show --stat HEAD\` — report the sha, fileCount (files in that ONE commit), and oneCommit=true ONLY if exactly ONE new commit holds the whole integrated wave. Confirm NO per-item commits and NO invented placeholder files.`,
    { label: 'ship:batched', phase: 'Ship', model: 'haiku', schema: SHIP }
  )
  log(`Ship: committed=${ship && ship.committed} pushed=${ship && ship.pushed} files=${ship && ship.fileCount} oneCommit=${ship && ship.oneCommit}`)
}

// ---------------- Report ----------------
phase('Report')
const totalOut = budget.spent() - buildStart
const result = {
  preflight: { items: ITEMS.length, ownedFiles: Object.keys(owner).length, sandbox: setupInfo },
  build: (built || []).filter(Boolean).map(b => ({ slug: b.slug, wrote: b.wrote, files: b.filesWritten })),
  integration: v ? { green: v.green, passed: v.passed, failed: v.failed } : { green: false, passed: null, failed: null },
  repairsUsed,
  tokens: { buildOut, verifyOut, repairOut, totalOut, model: 'all-haiku (weight 1)' },
  mergeReady: !!(v && v.green),
  ship,
  note: 'One Workflow call = one orchestrator turn. All-Haiku => raw==weighted. Setup tokens excluded. Real-repo wiring: give each item its own sibling git worktree (git worktree add ../aesop-wt-<slug> -b <branch> origin/main), workers write there + push; orchestrator opens PRs + ci_merge_wait after — the async CI/merge boundary stays outside this one turn.',
}
log(`DONE. integration green=${result.mergeReady} passed=${result.integration.passed} repairs=${repairsUsed} buildOut=${buildOut} totalOut=${totalOut}`)
return result
