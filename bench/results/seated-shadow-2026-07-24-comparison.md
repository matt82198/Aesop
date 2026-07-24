# Seated Shadow Adjudication — Real File-Brain A/B Results

## Per-Item Comparison: Baseline vs Seated Real Context

| Item ID | Finding | Baseline | Seated Modal | Stability | Ground Truth | Real Sources Included |
|---------|---------|----------|--------------|-----------|--------------|----------------------|
| vbs-waitforexit | A Windows VBScript launcher used by scheduled tasks calls sh... | enhancement_opportunity | ? | 0/3 | real_defect | REAL file-brain + code (repo code) |
| dryrun-blocked | An installer script validates that bash.exe and a helper fil... | real_defect | ? | 0/3 | real_defect | REAL file-brain + code |
| uninstall-exit0 | The installer's -Uninstall mode catches unregister exception... | real_defect | ? | 0/3 | real_defect | REAL file-brain + code |
| quote-validation | Task commands are interpolated into a double-quoted argument... | real_defect | ? | 0/3 | real_defect | REAL file-brain + code (repo code) |
| apostrophe-path | A derived POSIX path is wrapped in single quotes without esc... | real_defect | ? | 0/3 | real_defect | REAL file-brain + code |
| unc-paths | A Windows-to-POSIX path converter silently mangles UNC paths... | undetermined | ? | 0/3 | real_defect | REAL file-brain + code |
| hardcoded-username | Documentation examples shipped in a public npm package embed... | real_defect | ? | 0/3 | real_defect | REAL file-brain + code |
| audit-log-observability | Task registrations are only logged to console stdout; an ope... | real_defect | ? | 0/3 | enhancement_opportunity | REAL file-brain + code |
| whitelist-gate-weakening | Adding directory names 'daemon' and 'jobs' to a health-check... | undetermined | ? | 0/3 | false_positive | REAL file-brain + code (repo code) |
| ps1-syntax-gate | A new PowerShell file class shipped in the package has zero ... | real_defect | ? | 0/3 | enhancement_opportunity | REAL file-brain + code |
| test-hardcoded-path | A newly added test hardcodes an absolute machine-specific wo... | real_defect | ? | 0/3 | real_defect | REAL file-brain + code |
| fixreview-parents1 | Re-attack claim: Path(__file__).resolve().parents[1] used to... | false_positive | ? | 0/3 | false_positive | REAL file-brain + code |
| fixreview-backtick-test | Tautology-check claim: a regression test asserting the absen... | undetermined | ? | 0/3 | false_positive | REAL file-brain + code |
| regression-ui-suite | In a fresh review worktree, the UI test harness fails becaus... | undetermined | ? | 0/3 | false_positive | REAL file-brain + code |
| cimergewait-exit0 | A CI-wait-and-merge helper printed 'CI FAILED: <check>' and ... | real_defect | ? | 0/3 | real_defect | REAL file-brain + code |
| vbs-syntax-validity | Re-attack claim: 'rc = shell.Run(cmd, 0, True)' function-cal... | false_positive | ? | 0/3 | false_positive | REAL file-brain + code |

## Key Finding: Item 9 (whitelist-gate-weakening)

Item 9 flipped from FALSE_POSITIVE (baseline) to TRUE? NO (baseline: undetermined, seated: ?)

Seated context did not flip the verdict.
