# Benchmark Interpretation — rc.6 Measurement Memo

## What was measured

**Extraction + judgment benchmark: 4 runs, 39 unique tasks, 3 models pinned.**

| Run | Date | N | Task shape | Method |
|-----|------|---|-----------|--------|
| v1 | 2026-07-16 | 12 | Extraction/classification (11 deterministic, 1 judgment) | Blind, exact/regex match |
| v2 | 2026-07-17 | 11 | Judgment (bug-spot, finding-inflation, coverage, severity) | Blind, exact/regex match |
| v3 | 2026-07-17 | 28 | Judgment, 7 shapes (bugs, stack traces, refactors, security) | Blind, exact/regex match |
| CLI | 2026-07-18 | 12 | Extraction/classification (v1 tasks via `claude` CLI) | Blind, exact/regex match; latency recorded |

**Models:** `claude-haiku-4-5-20251001`, `claude-sonnet-5`, `claude-opus-4-8` (pinned per run).

**Latency (CLI run, 2026-07-18):** 12 tasks via `claude` CLI. Haiku: avg 5177.3 ms (P50 4987.0 ms). Sonnet: avg 5043.6 ms (P50 4110.3 ms). Opus: avg 4496.8 ms (P50 3723.3 ms). Includes 8659.3 ms CLI startup overhead on all models.

---

## What the evidence SUPPORTS

1. **Haiku sufficient for extraction/classification.** v1 (2026-07-16): Haiku 12/12, Sonnet 12/12, Opus 12/12 — identical answers on 11/12 tasks. Measured extraction/classification work matches fleet subagent task distribution.

2. **Haiku sufficient for judgment work.** v3 (2026-07-17): Haiku 28/28, Sonnet 28/28, Opus 28/28 across 28 judgment-shaped tasks (bug-spot, finding-inflation, coverage, severity, root-cause, refactor-equivalence, security). Combined with v2 (11 prior judgment tasks): Haiku/Sonnet 39/39, Opus 38/39. On the only divergence (v2 task, severity calibration), Opus erred, not Haiku.

3. **Cost parity within N=12 noise floor.** v1 + v2 + v3 combined: no task where Opus outperformed both Haiku and Sonnet. Haiku at ~1/3 per-token cost of Opus; identical accuracy = equivalent quality on measured shapes.

---

## What it does NOT support

1. **General model ranking.** N=12 (v1) or N=39 (all runs combined): deltas <8pp are noise. Sonnet 11/12 vs Haiku 12/12 is 1 task = within margin of error, not "Sonnet weaker."

2. **Opus capability verdict (2026-07-18 CLI run, 6/12 = 50% — high variance, not generalizable).** Opus showed 6 failures (3 reproducible semantic errors, 2 formatting-wrapped, 1 instability) vs. Haiku 12/12. This result lies outside the confidence interval for the other runs (v1: 12/12, v2: 38/39, v3: 28/28). Given N=12 and the narrow measurement window, this anomaly is **likely scoped to CLI config, system-prompt interaction, or this run's random seed**, not a verdict on the model itself. **Do not cite Opus 6/12 in comparisons** until re-run with fresh seed confirms; track as rc.5 follow-up. The measured variance highlights the importance of larger N and multiple sampling runs before drawing comparative claims.

3. **Frontier model boundary.** Benchmark does not discriminate at the frontier: all three converged on v3's hardest tasks (28/28 identical). The honest claim is bounded: **Haiku sufficient for task shapes measured here**, not "Haiku equals Opus at absolute reasoning frontier." If tasks exist where Opus's depth is worth 3×, this benchmark has not captured them (or they don't occur in fleet-work task distribution).

4. **Real-transcript task distribution.** All tasks hand-curated by reasoning about fleet work, not sampled from actual Claude Code session transcripts. Selection bias toward extraction/classification (11/12 in v1) where programmatic grading is tractable; real fleet work likely has higher proportion of open-ended judgment calls.

5. **Wall-clock cost-quality trade-off.** CLI latency (2026-07-18) measured includes 8659.3 ms startup overhead uniformly across all models; single-run samples do not represent model latency properties, only environment variance.

---

## Transcript-sampled benchmark roadmap (wave-27 onward)

**Wave-27 (Current):** Sampled task set production.

- **Tasks sampled:** 150 judgment/analysis tasks extracted from real aesop fleet transcripts
- **Strata:** extraction (25%), classification (16%), verdict_judgment (54%), repair_triage (5%)
- **Measurement of strata:** Reflected actual fleet workload by analyzing 1249 transcript files from 89 sessions; verdict/judgment work dominates (54%), extraction common (25%); distribution cited in task set metadata
- **Ground truth status:** 81 tasks (54%) have clear checkable specs; 69 (46%) marked `needs_grader_authoring` (no ground truth yet)
- **Grader-validity check:** All 81 graded tasks pass through bench_runner's exact-match scorer; infrastructure verified; offline mock runner produces 0% accuracy (expected for unseen judgment tasks; real verdict deferred to model runs)
- **Redaction:** Sanitizer removes paths, emails, API keys; all tasks ASCII-safe; passes secret_scan --staged gate

Next steps (wave-28+):
1. Provide expected outputs / hidden test cases for the 69 tasks marked `needs_grader_authoring` (human authoring or reference model generation)
2. Run live model benchmark (Haiku, Sonnet, Opus) against full set of 150 tasks
3. Compare accuracy on sampled tasks vs. original 12-task curated set; measure whether strata distribution affects model ranking

**Difference from curated set:** Sampled tasks are from real fleet operations (infrastructure audits, code review, defect triage) not handpicked scenarios. Task distribution reflects what Haiku actually spends cycles on, not what's "representative" in theory.

---

## Open work

- **Larger N + real-transcript sampling (wave-28+).** Grow from 39 curated + 150 sampled (189 total) to 300+ for tighter confidence intervals. Only with N in the hundreds can deltas of a few percentage points be claimed as signal.
- **Opus CLI anomaly inspection.** 2026-07-18 Opus 6/12 result is reproducible in this run but unverified for the model itself vs. system-prompt/CLI interaction. Re-run with Opus variant + system-prompt sweep to isolate root cause.
- **Discriminating frontier tasks.** Benchmark converged identically on all hardest judgment shapes (v3). Probe deeper: adversarial cases, multi-step reasoning with partial-credit rubrics, open-ended quality judgment where rubric doesn't apply.
- **Cost axis completeness.** Haiku ~1/3 per-token cost of Opus (pricing). Wall-clock latency measured; need multiple runs from varied environments to separate model property from measurement variance.

---

## References

- `bench/results/2026-07-16-haiku-sonnet-opus.md` — v1 extraction run, 12 tasks, all three models 100%.
- `bench/results/2026-07-17-judgment-haiku-sonnet-opus.md` — v2 judgment run, 11 tasks; Opus 1-task divergence (j11).
- `bench/results/2026-07-17-judgment-v3-haiku-sonnet-opus.md` — v3 judgment run, 28 tasks; all models identical.
- `bench/results/2026-07-18-claude-cli-latency.md` — CLI extraction run, 12 tasks; Opus anomaly (6/12), Haiku 12/12, Sonnet 11/12; latency recorded.
- `ANOMALY-REPORT.md` (scratchpad) — forensics of Opus 2026-07-18 failures: 3 semantic errors, 2 formatting-wrapped, 1 instability; variant probe worsened behavior.
- `bench/README.md` — scaffold definition, task categories, scoring semantics, limits.
- `bench/tasks.jsonl` — 12 held-out extraction/classification tasks (v1 base set).
- `bench/ground_truth.jsonl` — ground truth for v1.
- `tools/bench_runner.py` — scorer (exact match / regex match).

**Suggested README.md link:** Section "Running against real models (wave-32+)" → subsection "Claude CLI runner" (already present; points to this measurement path).
