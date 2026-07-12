# Audit backlog — refinement loop (live)

Durable handoff for the continuous refinement loop: survives terminal kills / model
switches. A resuming session (Fable) reads STATE.md → this file → dispatches one Haiku
per unclaimed item on its own branch (branch-per-item, worktree isolation), TDD-first,
ACCEPTANCE = the test gate; flip the box per landed PR.

**Status legend:** ⬜ unclaimed · 🔵 dispatched/in-flight · ✅ merged to main · ⏸ needs user call

## Cleared history (collapsed)

- **Waves 1–4 (2026-07-12): 26/26 items ✅** — 8 P0 security/correctness, all P1, all P2,
  both user decisions (domain-CLAUDE.md collapse; extended_signals gate). Merged to main
  in PR #16 (`f259c4f`). Full itemized list preserved in git history at `cc708c9`.
- **Wave 5 quickstart docs ✅** — README one-command scaffold primary (PR #18).

## P0 — correctness / security (wave 5, from five-lens re-audit)

- ✅ **[bash] NUL protocol destroyed by `$()` capture** — watchdog-repos.json fields corrupted
  in the shipped path; test must drive the REAL loop. Branch fix/backup-fleet-nul-protocol
  (+ control-char json_escape, portable date).
- ✅ **[bash] release_lock lacked ownership check** — slow holder deleted reclaimer's live lock;
  + stale-test fixture fix + array CYCLE_CMD. PR #23.
- ✅ **[js] emitProposal never takes the PROPOSALS lock + AESOP_MONITOR_FORCE=0 bypasses the
  heartbeat gate** — branch fix/monitor-proposals-races (+ stale-lock reclaim, EPERM-safe renames).
- ✅ **[meta] CI never executes the shell/python suites** — bash -n only; defective tests shipped
  unnoticed. Branch fix/ci-run-all-suites.
- ✅ **[sec] /submit CSRF — drive-by write into orchestrator inbox** — origin check + session
  token. PR #21.
- ✅ **[sec] Scanner size/binary skip bypassed ALL rules** — >1MB or NUL-byte file with real key
  scanned CLEAN; now bounded fatal-rule scan + SKIPPED-* notes. PR #22.
- ✅ **[sec] reconstitute validates URL but not TARGET path** — arbitrary-path repo planting;
  branch fix/reconstitute-target-validation (+ real-script e2e, legacy space fallback).

## P1 — hardening (wave 5)

- ✅ **[sec+arch+bash] Audit-log hardening bundle** — write lock around read-hash+append,
  tail-truncation anchor (sidecar tail hash + seq), tty/newline-safe stdin, external Test 6
  drives the real function, control-char escapes, sha256sum fallback. Branch fix/audit-log-hardening.
- ✅ **[arch] Config trim deleted live key cardinal_rules.subagent_model** — restored + config/doc
  drift tripwire test. PR #19.
- ✅ **[js] dash-extra dir-mtime pruning hid ACTIVE agents ("fleet idle" bug) + hardcoded state
  path** — file-level activity now decides; state_root honored. PR #20.
- ✅ **[js] cli targetDir parser hijacked flag values (--repos path scaffolded INTO) + symlinked
  .git/hooks escape** — single-pass parse + lstat guard. PR #24.

## Features (user-requested)

- ✅ **[feat] Agents panel rewrite** — clickable rows: status, runtime, tokens used, task label,
  full dispatch prompt (parsed from agent-*.jsonl, XSS-safe). Branch feat/dash-agents-panel.

## Cross-repo ports (fleet machinery)

- ✅ **[port] ~/scripts/secret_scan.py: size/binary skip fix** (same hole as PR #22; pragma-scoping
  port already landed as claude-scripts 314cb25).
- ✅ **[port] conductor3 run-watchdog: release-lock ownership check** onto branch
  fix/watchdog-atomic-lock (inherits PR #23's P0; branch must not merge without it).

## Wave 5b — UI realtime (user-reported, in flight)

- 🔵 **[feat] Realtime SSE dashboard rebuild** — polling full re-render replaced with /events
  SSE push + keyed in-place DOM patching; clicks/expansion survive; playwright-proven in a
  real browser (console-error-free, live update without reload). Branch feat/dash-realtime-sse.
- ✅ **[test] Post-merge monitor test reconcile** — heartbeat-guard fixture + stale FORCE test
  names; revert-proof assertions. PR #32.

## Needs a user decision (⏸)

- (none open)

---

## Landing log
- 2026-07-12: five-lens re-audit (architect 6, security 5, bash 8, js 6, honest 2-docs findings;
  overlaps deduped into the 9 item-branches + 2 ports above). Honest lens otherwise CLEAN.
- Audit cadence: this is audit #1 after the wave-1–4 clear; loop ends after 2 consecutive clean audits.
