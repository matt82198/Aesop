# Seated Shadow Adjudication — Real File-Brain A/B Results

**Models run**: gpt-5.6-sol, gpt-5.5
**Context**: REAL file-brain (STATE.md, tracker.json, real repo code)
**Item 9 focus**: whitelist-gate-weakening with REAL secret_scan.py in pack

## Per-Item Comparison: Baseline vs Seated Real Context

| Item ID | Finding | Baseline | Seated Modal | Stability | Ground Truth | Real Sources Included |
|---------|---------|----------|--------------|-----------|--------------|----------------------|
| vbs-waitforexit | A Windows VBScript launcher used by scheduled tasks calls sh... | real_defect | real_defect | 1/3 | real_defect | REAL file-brain + code (repo code) |
| dryrun-blocked | An installer script validates that bash.exe and a helper fil... | real_defect | real_defect | 1/3 | real_defect | REAL file-brain + code |
| uninstall-exit0 | The installer's -Uninstall mode catches unregister exception... | real_defect | real_defect | 1/3 | real_defect | REAL file-brain + code |
| quote-validation | Task commands are interpolated into a double-quoted argument... | real_defect | real_defect | 1/3 | real_defect | REAL file-brain + code (repo code) |
| apostrophe-path | A derived POSIX path is wrapped in single quotes without esc... | real_defect | real_defect | 1/3 | real_defect | REAL file-brain + code |
| unc-paths | A Windows-to-POSIX path converter silently mangles UNC paths... | undetermined | false_positive | 1/3 | real_defect | REAL file-brain + code |
| hardcoded-username | Documentation examples shipped in a public npm package embed... | real_defect | false_positive | 1/3 | real_defect | REAL file-brain + code |
| audit-log-observability | Task registrations are only logged to console stdout; an ope... | undetermined | enhancement_opportunity | 1/3 | enhancement_opportunity | REAL file-brain + code |
| whitelist-gate-weakening | Adding directory names 'daemon' and 'jobs' to a health-check... | undetermined | false_positive | 1/3 | false_positive | REAL file-brain + code (repo code) |
| ps1-syntax-gate | A new PowerShell file class shipped in the package has zero ... | real_defect | enhancement_opportunity | 1/3 | enhancement_opportunity | REAL file-brain + code |
| test-hardcoded-path | A newly added test hardcodes an absolute machine-specific wo... | real_defect | real_defect | 1/3 | real_defect | REAL file-brain + code |
| fixreview-parents1 | Re-attack claim: Path(__file__).resolve().parents[1] used to... | false_positive | false_positive | 1/3 | false_positive | REAL file-brain + code |
| fixreview-backtick-test | Tautology-check claim: a regression test asserting the absen... | undetermined | false_positive | 1/3 | false_positive | REAL file-brain + code |
| regression-ui-suite | In a fresh review worktree, the UI test harness fails becaus... | undetermined | false_positive | 1/3 | false_positive | REAL file-brain + code |
| cimergewait-exit0 | A CI-wait-and-merge helper printed 'CI FAILED: <check>' and ... | real_defect | real_defect | 1/3 | real_defect | REAL file-brain + code |
| vbs-syntax-validity | Re-attack claim: 'rc = shell.Run(cmd, 0, True)' function-cal... | false_positive | false_positive | 1/3 | false_positive | REAL file-brain + code |

## Key Finding: Item 9 (whitelist-gate-weakening)

**Primary model**: gpt-5.6-sol

Baseline (decontextualized): undetermined
Seated (real file-brain + secret_scan.py): false_positive (stability: 1/1)

✓ FLIPPED: Item 9 reversed from undetermined to false_positive with real context.
✓ Real secret_scan.py in context pack enabled the challenger to see the refutation.

### Real Sources Included in Pack (Item 9)

- **tools/secret_scan.py** (full header, 1-100): Shows recursive file scanning patterns
- **tools/power_selftest.py** (lines 80-150): Shows known_ok whitelist section
- **STATE.md** (real, full): Orchestrator context + decisions
- **state/tracker.json** (real, if present): Open work items
- **Finding text** (blind): Presented without labels


## Honest Framing

This run tests **file-brain context isolation** — whether real code and state can be safely included in OrchestratorDriver context packs. It does NOT test:
- Long-loop coherence (iterative refinement over decisions)
- Orchestrator seat-swap readiness (full loop + running backlog)
- Cost/latency of different backends

**Early-abort gate**: Frontier-first model (gpt-5.6-sol) run first. If item 9 doesn't flip with real context, cheaper models skipped (cost-rational). If it does flip, gpt-5.5 tested for portability.
