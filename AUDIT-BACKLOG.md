# Audit backlog — five-lens specialist review (2026-07-12)

Consolidated, priority-ranked TODOs from five specialist analysts of the aesop app
(architect, bash-pro, javascript-pro, honest-opinions, security-auditor). This file is
the durable handoff: it survives a terminal kill / model switch. A resuming session
(Fable) reads this + STATE.md, then dispatches one Haiku per unclaimed TODO, TDD-first.

**Status legend:** ⬜ unclaimed · 🔵 haiku dispatched · ✅ landed+tested · ⏸ needs user call

**How to resume:** read STATE.md → this file → for each ⬜ (P0 first), dispatch a Haiku
with the ACCEPTANCE as its gate; commit per green item; flip the box. Subagents Haiku.

---

## P0 — correctness / security (do first)

- ✅ **[sec] Pragma comment defeats the whole secret scanner, incl. PEM/AWS keys; hook hides it.**
  A `# secretscan: allow-pattern-docs` in a file's first 10 lines flips EVERY finding to
  ALLOWED-DOC with no check the file is docs; pre-push-policy.sh runs the scanner with
  `>/dev/null 2>&1` so the evidence never shows. FILES: tools/secret_scan.py:74-85,180-182;
  hooks/pre-push-policy.sh:22-41. ACCEPTANCE: pragma may only soften the two doc-shaped
  rules (generic_secret_assignment, env_access), NEVER the fatal classes (pem_private_key,
  aws_access_key, github_token, slack_token, openai_anthropic_key, connection_string);
  hook surfaces ALLOWED-DOC lines to stderr; test: PEM key + pragma still exits 1.

- ✅ **[sec] Backup daemon force-pushes UNTRACKED new files unscanned.** scan only inspects
  tracked+modified files, but the snapshot commit is `git add -A` (stages untracked), then
  `git push -qf` — a new credential file in any of ~150 auto-discovered repos ships in one
  150s cycle. FILES: daemons/backup-fleet.sh:27-61,79-90. ACCEPTANCE: enumerate
  `git ls-files --others --exclude-standard` and scan them before any push; test: untracked
  file w/ AWS-key string → cycle reports BLOCKED not SNAPSHOTTED.

- ✅ **[sec] reconstitute.sh passes untrusted URLs to `git clone` → option/transport injection (RCE).**
  `url` read verbatim from --repos-file/config; `ext::sh -c '...'` or a leading `-` runs
  arbitrary commands on reconstitution. FILES: tools/reconstitute.sh:164-191.
  ACCEPTANCE: reject url not matching `^(https://|git@[\w.-]+:|ssh://)`; use `git clone -- "$url" "$target"`;
  test: `ext::` / `-`-prefixed line rejected without invoking git.

- ✅ **[arch] ui/serve.py reads security alerts from wrong dir → web dashboard silently shows zero.**
  Same bug just fixed in dash-extra.mjs; ui/serve.py:44 uses `scan/` but every writer uses
  `state/SECURITY-ALERTS.log`. FILES: ui/serve.py:44. ACCEPTANCE: reads state/SECURITY-ALERTS.log
  by default; test mirrors tests/dash-extra.test.mjs (HIGH alert → nonzero web count).

- ✅ **[arch] reconstitute config path is non-functional — repos[] schema has no url/remote field.**
  Documented config-driven flow clones url="" (silent no-op); only undocumented --repos-file works.
  FILES: tools/reconstitute.sh:33-50,164-172; aesop.config.example.json repos[]. ACCEPTANCE:
  add url/remote to repos[] schema; loader emits it; test: repo absent from disk cloned from
  config alone. (Coordinate with the injection fix above — same clone site.)

- ✅ **[bash] Branch-protection hook checks the WRONG branch — bypassable in one command.**
  check_branch_policy inspects the current local branch via rev-parse HEAD, but git passes the real
  destination ref on stdin; `git push origin HEAD:main` pushes to main and is silently ALLOWED — exactly
  what the hook exists to block. FILES: hooks/pre-push-policy.sh:12-20,213. ACCEPTANCE: parse stdin
  `<local> <lsha> <remote> <rsha>`, block when any remote-ref is refs/heads/main|master regardless of
  local HEAD; Test 6: non-main local → main via explicit refspec asserts block.

- ✅ **[bash] Secret-scan gate defeated by unquoted path expansion → fail-open on the real secret.**
  scan_tracked_files builds a plain string and passes `$file_paths` unquoted to python; a filename with
  a space/glob/leading-dash gets word-split/glob-expanded/argv-injected and the real file is skipped.
  FILES: daemons/backup-fleet.sh:39-52,59. ACCEPTANCE: use a bash array (`"${file_paths[@]}"`); test a
  filename with a space reaches the scanner as one arg and blocks/allows on content.

- ✅ **[arch] Watchdog single-instance guard is TOCTOU-racy → concurrent daemons force-push over each other.**
  read-age→compare→proceed has no lock; two starts in the same window both pass, both run
  backup-fleet.sh `git push -qf` to the same backup/* refs fleet-wide. FILES:
  daemons/run-watchdog.sh:11-17; daemons/backup-fleet.sh:79-116. ACCEPTANCE: atomic guard
  (mkdir lockfile or O_EXCL heartbeat); test: two `--once` back-to-back, only one runs the cycle.
  (MERGED w/ bash-pro's heartbeat-TOCTOU: the lock must ALSO gate `--once`, which currently bypasses
  the guard at run-watchdog.sh:14. js-pro's monitor self-gating gap is the same class — see P1.)

## P1 — hardening / robustness

- ✅ **[arch] Monitor AUTO actions are detection-only — wire rotate + quarantine + ACTIONS.log.**
  CHARTER/CLAUDE.md claim auto log-rotation, junk quarantine, ACTIONS.log writes; collect-signals.mjs
  only MEASURES them. FILES: monitor/collect-signals.mjs (checkLogFiles, detectJunkScripts),
  tools/rotate_logs.py. ACCEPTANCE: over-threshold log → invokes rotate_logs.py + appends ACTIONS.log;
  quarantinable junk → moved to monitor/quarantine/ with manifest; test asserts both.

- ✅ **[arch] PROPOSALS.md multi-writer race + self-contradicting contract.** monitor appends via
  emitProposal(); proposals.mjs accept/reject does full read-modify-rewrite with no lock → a cycle's
  append racing a human accept drops a proposal (breaks pillar 3). FILES: monitor/CHARTER.md,
  monitor/collect-signals.mjs:356-398, tools/proposals.mjs:126-201. ACCEPTANCE: CHARTER states one
  writer model; proposals.mjs uses lockfile or atomic temp+rename; test: append mid-accept, no loss.

- ✅ **[arch] Config layer split-brain — half of aesop.config.example.json is dead.** aesop_root,
  brain_root, scripts_root, temp_root, dashboard.*, most cardinal_rules.* are declared but only
  same-named ENV vars are read; editing the JSON is silently ignored. FILES: aesop.config.example.json,
  collect-signals.mjs:12-15, dash-extra.mjs:10-14, ui/serve.py:31-44. ACCEPTANCE: either every
  consumer falls back to config values when env unset (test per consumer), OR trim the example to
  only keys code reads.

- ✅ **[sec] Model-policy escape hatch is a bare substring match on untrusted prompt text.**
  `[[ALLOW-NON-HAIKU]]` anywhere in input.prompt bypasses Haiku policy with no check who put it there;
  a prompt built from repo/file content lets an attacker smuggle a Sonnet/Opus agent, silently
  (no reason emitted on bypass path). FILES: hooks/claude/force-model-policy.mjs:73-75. ACCEPTANCE:
  emit permissionDecisionReason on the bypass path (visible in transcript) AND log escape-hatch use to
  a reviewable file; test asserts the log entry.

- ✅ **[sec] Secret-scan gate fails open with no audit trail when AESOP_ROOT/script missing.**
  check_secret_scan returns 0 (push allowed) when secret_scan.py isn't found, and never logs — an
  unset/wrong AESOP_ROOT silently disables the gate with zero trace. FILES: hooks/pre-push-policy.sh:22-41.
  ACCEPTANCE: log_block "secret_scan_unavailable" (non-blocking) so the audit log distinguishes
  "clean" from "not scanned"; --test case asserts the event is recorded.

- ✅ **[js] force-model-policy.mjs stdin read has no timeout → hangs EVERY Agent/Task dispatch forever.**
  readStdin only resolves on data/end/error; if stdin never closes (spawn edge, caller doesn't close
  pipe) the hook freezes that dispatch with no recovery — fires fleet-wide. FILES:
  hooks/claude/force-model-policy.mjs:48-56. ACCEPTANCE: race readStdin against a ~2000ms timer that
  resolves '' (fail-open, no rewrite); test pipes input without closing stdin, asserts exit 0 in window.
  (Reliability P0-adjacent — "NEVER WAIT" rule; grouped here as it's low-probability.)

- ✅ **[js] collect-signals.mjs never checks its own heartbeat before running → overlapping cycles double-emit.**
  CHARTER says check .monitor-heartbeat <300s and skip; collector only WRITES it at the end. Concurrent
  cycles + TOCTOU emitProposal → duplicate PROPOSALS entries (breaks idempotency the tests only check
  sequentially). FILES: collect-signals.mjs:88-121,356-398. ACCEPTANCE: at startup read own heartbeat,
  age<300s → log + exit 0 untouched; test spawns two collectors on one fixture, asserts one entry.

- ✅ **[js] Non-atomic SIGNALS.json / BRIEF.md writes → truncated file corrupts downstream JSON.parse.**
  4 sequential writeFileSync; kill mid-write leaves partial SIGNALS.json + inconsistent state files.
  FILES: collect-signals.mjs:554-561. ACCEPTANCE: write .tmp sibling then renameSync for SIGNALS.json
  and BRIEF.md; test asserts prior-cycle file stays parseable until new one fully lands.

  _(MERGED: architect's PROPOSALS.md read-modify-rewrite lost-update finding and js's proposals.mjs
  overwrite finding are the SAME issue — see the [arch] PROPOSALS.md item above; fix once with a
  lockfile/atomic-rename AND a mid-write re-read guard, covering both agents' acceptance tests.)_

- ✅ **[honest] Auto-install pre-push hook from the scaffold.** Pillar 2 ships a real
  hook but `bin/cli.js` never wires it, so nothing enforces it per-repo.
  FILES: bin/cli.js, hooks/pre-push-policy.sh, docs/HOOK-INSTALL.md, README.md.
  ACCEPTANCE: cli.js symlinks (Windows: copies) hooks/pre-push-policy.sh →
  target/.git/hooks/pre-push during scaffold; README states hook is active by default.

- ✅ **[honest] Wire reconstitute.sh into RESTORE + add e2e test.** Pillar 5's
  auto-clone tool exists (224 lines) but RESTORE.md still says "manual clone," so it
  reads as dead code. FILES: docs/RESTORE.md, tools/reconstitute.sh, aesop.config.example.json.
  ACCEPTANCE: RESTORE.md references reconstitute.sh as the bootstrap step; an e2e test
  clones from fixtures → runs reconstitute.sh → asserts all repos present w/ origin remotes.
  (NOTE: reconstitute.sh already reads config repos + fetches; this is doc-wiring + test,
  not a rewrite — the honest agent read a pre-wave snapshot.)

## P2 — honesty / polish / docs

- ✅ **[honest] Improve onboarding-by-clone friction OR reframe the claim.** Clone still
  needs ~6 manual steps (edit template placeholders, copy memory template, make config,
  edit paths, mkdir state, export env). FILES: bin/cli.js, CLAUDE-TEMPLATE.md, README.md.
  ACCEPTANCE: either cli.js prompts for project name/domains/repo-paths and generates a
  working CLAUDE.md + aesop.config.json, OR README gains a copy-paste 5-min quickstart
  whose commands actually run clean; honest pillar naming either way.

- ✅ **[honest] Make CLAUDE-TEMPLATE.md a concrete worked example, not blanks.**
  Placeholder text ("[Your project name]") teaches nothing. FILES: CLAUDE-TEMPLATE.md.
  ACCEPTANCE: replace with a filled example team brain (real cardinal rules + domain map)
  OR have cli.js generate the stub from prompts; no bare "[...]" placeholders remain.

- ✅ **[js] dash-extra.mjs transcript walk has no depth cap; reruns synchronously every refresh.**
  walk() recurses all of ~/.claude/projects unbounded (monitor's equivalent caps depth 6 + prunes);
  GUI re-walks the growing tree each tick → TUI degrades. FILES: dash/dash-extra.mjs:41-59.
  ACCEPTANCE: depth limit + prune subtrees older than the activity window; perf test on nested fixture
  under a fixed threshold.

- ✅ **[js] proposals.mjs block-split breaks on CRLF (Windows target, file is gitignored/un-normalized).**
  Splits on literal /\n---\n/; a Windows editor saving CRLF merges all blocks → list/accept/reject
  silently fail. FILES: tools/proposals.mjs:69-95,161. ACCEPTANCE: normalize \r\n→\n before split
  (or /\r?\n---\r?\n/); test with CRLF-joined blocks resolves keys.

- ✅ **[sec] Document that pre-push hook is a LOCAL gate; pair with server-side branch protection; hash-chain audit log.**
  SECURITY-AUDIT.log has no integrity protection — the blocked user can edit it or `git push --no-verify`.
  FILES: hooks/pre-push-policy.sh:43-58, README/HOOK-INSTALL.md. ACCEPTANCE: docs state local-convenience
  only + require server-side branch protection; optional prev_hash chaining so tampering is detectable.

- ✅ **[bash] reconstitute.sh --test never calls the real reconstruct_fleet() → regressions ship undetected.**
  Self-test reimplements clone/fetch inline instead of invoking the production function. FILES:
  tools/reconstitute.sh:78-139 vs 141-211. ACCEPTANCE: run_test_suite calls reconstruct_fleet/main
  against the fixture and asserts on its real CLONED/FETCHED/FAILED summary incl. a deliberate bad-URL
  failure. (Do together with the P0 injection + config-url fixes — same function.)

- ✅ **[bash] --repos-file parsing breaks on any path with a space (Windows profile paths).**
  awk '{print $2}' truncates target at the first space → clones to wrong location silently. FILES:
  tools/reconstitute.sh:167-168. ACCEPTANCE: tab/quote-aware parse (`read -r url target`); test a spaced
  path round-trips.

- ✅ **[bash] Repo names not JSON/delimiter-escaped → corrupt .watchdog-repos.json + GUI, misparsed state.**
  raw printf builds JSON (unlike json_escape in the hook) and a `|`-delimited internal protocol re-split
  with IFS; a repo dir name with `"` or `|` breaks jq (GUI → "repos unavailable") or misattributes fields.
  FILES: daemons/backup-fleet.sh:36-61,158,165; dash/watchdog-gui.sh:50. ACCEPTANCE: json_escape before
  interpolation + NUL/array-based internal passing; test a dir name containing `|` renders correctly.

## Needs a user decision (⏸)

- ✅ **[honest] Collapse the 6 domain CLAUDE.md files into the root** (USER APPROVED + landed 2026-07-12 @ cc3a716 after one external revert; lossless, 60/60 + smokes green) Honest-opinions
  calls them over-precise (<1K each) and DRY-violating. BUT this DIRECTLY CONTRADICTS
  cardinal rule 2 (recursive smallest-scope domain CLAUDE.md units) — which the user
  explicitly invoked today ("run a recursive haiku domain scope loop"). Genuine tension
  between the OSS-legibility critique and the fleet's operating doctrine. USER CALL.

- ✅ **[honest] Trim/opt-in the monitor's niche signal checks** (USER APPROVED + landed 2026-07-12; monitor.extended_signals flag, default off, skipped markers keep JSON consumers safe) Argues checks 5/6/8/10
  (junk-script sprawl, stray-repo scripts, respawn-watch, unreviewedPrompts) are token-heavy
  cargo-cult vs the load-bearing core 6. Counterpoint: several are cardinal-rule guardrails
  (proactive compliance checkers). Proposal to gate behind monitor.extended_signals flag.
  USER CALL — also stage to conductor3 PROPOSALS.md.

---

## Landing log
- Seeded 2026-07-12 during five-lens review; analysts in flight: architect, bash-pro,
  javascript-pro, honest-opinions, security-auditor.
- honest-opinions LANDED: 6 todos filed (2×P1, 2×P2, 2×⏸). Its pillar-1/5 "incomplete"
  framing partly reflects a pre-wave-2 snapshot (reconstitute.sh + tests already landed).
- architect LANDED: 6 todos (3×P0, 3×P1). Surfaced ui/serve.py alert-dir bug (same class as
  the dash-extra fix), monitor AUTO-actions-are-detection-only, config split-brain, PROPOSALS race,
  watchdog TOCTOU.
- security-auditor LANDED: 6 todos (3×P0: pragma-defeats-scanner, untracked-force-push,
  clone-injection-RCE; 3×P1: escape-hatch substring, fail-open-no-audit, audit-log integrity).
- javascript-pro LANDED: 6 todos (1 hook-hang, 1 monitor self-gating, 1 atomic-writes → P1;
  dash walk + CRLF split → P2; PROPOSALS overwrite MERGED into architect's).
- bash-pro LANDED: 6 todos (2×P0: branch-hook-wrong-branch, unquoted-scan-path; heartbeat-TOCTOU
  MERGED into watchdog item; reconstitute --test/space-parse/json-escape → P1).

## Dispatch plan (for the resuming Fable session)
- **8 P0** (security + correctness) → dispatch FIRST, one Haiku each, TDD-first, disjoint files.
  Coordinate the 3 reconstitute.sh items (clone-injection + config-url + --test) into ONE agent —
  same function. Coordinate the 2 secret-scan items (pragma + unquoted-path) with care — both touch
  the scan path but different files (secret_scan.py vs backup-fleet.sh); can be parallel.
- **~11 P1** → second wave after P0 green.
- **~5 P2** → third wave / opportunistic.
- **2 ⏸** need a user decision (domain-CLAUDE.md collapse contradicts cardinal rule 2; monitor
  niche-signal trimming) — do NOT action without the user; surface at next /power.
- Each item's ACCEPTANCE line is the Haiku's test gate. Flip ⬜→🔵 on dispatch, →✅ on green+push.
  Re-run full suite (npm test + unittest + self-tests) at every commit, even mid-wave.
