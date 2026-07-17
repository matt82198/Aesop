# Judgment benchmark run — 2026-07-17 — Haiku vs Sonnet vs Opus

The v2 **judgment** set (`bench/tasks_v2_judgment.jsonl`), built after the v1 extraction set scored
100% across all three models and thus couldn't discriminate. v2 targets reasoning: spot the bug,
find the inflated finding, check acceptance-criteria coverage, calibrate severity per an in-prompt
rubric. Ground truth is objectively grounded (runtime semantics / quoted-line fact-checks /
mechanical rubric application), not opinion.

## Method
Each model answered all 11 tasks **blind** (no access to `ground_truth_v2_judgment.jsonl`), scored
by exact/regex match. Models: `haiku`, `sonnet`, `opus`, one pinned agent each.

## Result

| Model  | Score | Accuracy | Miss |
|--------|-------|----------|------|
| Haiku  | 11/11 | **100%** | — |
| Sonnet | 11/11 | **100%** | — |
| Opus   | 10/11 | **91%**  | j11 |

All three agreed on j01–j10. The **only divergence was j11** (severity calibration): Haiku and
Sonnet answered `medium` (the rubric-correct answer); **Opus answered `low`.**

## Interpretation (both directions, honestly)

1. **The v2 set discriminates** — the whole point. v1 was a 100% tie; v2 produced a real split.
   The task-design goal (cheap model plausibly errs, answer objectively checkable) is met, and here
   it was the *expensive* model that diverged.
2. **The divergence went against Opus**, not for it. That is a real, if tiny, data point *for* the
   "Haiku is sufficient" thesis the fleet's cost model depends on, and *against* any assumption that
   the frontier model is automatically safer for judgment work. Haiku did not merely tie Opus here —
   it out-scored it on rubric compliance.
3. **The honest caveat on j11:** "correct" means "follows from the task's stated rubric," and that
   rubric is the benchmark author's own summary, not an external standard. Opus's `low` may reflect
   genuine real-world severity nuance (the case had mitigating factors) that a mechanical rubric
   doesn't credit. So read this as **Opus being less rubric-compliant, NOT as Opus judging worse.**
   A model that "reasons past" a stated rubric is a different failure mode than one that can't reason.

## Limits
- **N=11, a single divergence.** This is one data point, not a verdict. Do not over-read a 9-point
  accuracy gap driven by one task.
- Tasks are curated by reasoning about fleet work, **not sampled from real transcripts** — selection
  bias remains.
- Binary/small-alphabet answers only (no partial credit); 4 judgment shapes; author-summarized rubric.
- No latency/cost axis recorded; the "Haiku at ~1/3 cost for equal quality" claim still needs cost
  measured alongside accuracy.

## Verdict
The harder benchmark works and discriminates, and on it **Haiku held its own with the frontier — in
fact edging it on rubric compliance.** This strengthens, without closing, the Haiku-sufficiency case:
the next step (wave-29 seed) is larger N and tasks sampled from real fleet transcripts, plus a
recorded cost axis, before "Haiku is sufficient for judgment" can be asserted rather than suggested.
