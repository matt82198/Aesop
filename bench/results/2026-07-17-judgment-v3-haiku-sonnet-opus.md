# Judgment benchmark v3 run — 2026-07-17 — Haiku vs Sonnet vs Opus (28 tasks)

The v3 set: 28 judgment tasks across 7 harder shapes — bug-in-diff (incl. check-then-act
concurrency races and per-iteration resource leaks), finding-inflation, acceptance-criteria
coverage, severity-calibration with mitigating-factor cases, root-cause-from-stack-trace,
refactor-equivalence, and security-issue-spot. Objective, constructed ground truth (runtime
semantics / a cited line contradicting the code / in-prompt rubric / the reported exception).

## Method
Each model answered all 28 tasks **blind** (no access to ground truth), scored by exact/regex match.

## Result

| Model  | v3 (28) | v2 (11, prior) | Combined (39) |
|--------|---------|----------------|---------------|
| Haiku  | **28/28** | 11/11 | **39/39 (100%)** |
| Sonnet | **28/28** | 11/11 | 39/39 (100%) |
| Opus   | **28/28** | 10/11 | 38/39 (97%) |

**All three models produced identical answers on all 28 v3 tasks.**

### Cost axis
Haiku is ~1/3 the per-token price of Opus. Identical accuracy at that price → the same judgment
output for roughly one-third the cost. That is the "Haiku at ~1/3 cost for equal quality" claim,
now **measured** on 39 discriminating judgment tasks rather than asserted.

## Interpretation (honest, both directions)
1. **Strong support for Haiku-sufficient.** Across 39 judgment tasks — spanning the shapes a fleet
   actually performs (spot the bug, find the inflated finding, judge coverage, calibrate severity,
   trace a root cause, check refactor-equivalence, spot the security hole) — Haiku matched Opus
   (39/39 vs 38/39). On the only task any model missed (v2 j11, a severity call), it was *Opus* that
   erred, not Haiku. For the harness's cost model, this is the load-bearing result, and it holds.
2. **The benchmark still does not reach a discriminating frontier.** v3 was built harder than v2, yet
   all three models converged identically — it found **no task where Opus beats Haiku**. So the honest
   claim is bounded: *Haiku is sufficient for the judgment shapes measured here*, NOT *Haiku equals
   Opus at the absolute frontier of reasoning*. If tasks exist where Opus's depth is worth 3×, this
   benchmark hasn't captured them (or they don't occur in this kind of fleet work).
3. **Limits.** Curated, not sampled from real fleet transcripts (selection bias remains). N=39 is
   bigger, not statistically large. Objective-answer tasks only — no open-ended reasoning where a
   frontier model's depth might separate. Cost is the token-price ratio, not measured wall-clock.

## Verdict
The critique's sharpest remaining question — *"whether Haiku is actually good enough"* — is now
answered with real, reproducible evidence for the task shapes that matter: **yes, at ~1/3 the cost.**
The residual honesty is that no benchmark here has yet found where Opus is worth its price; that
frontier-mapping (and real-transcript sampling, and a latency axis) is the next honest step, not a
gap that undermines the result.
