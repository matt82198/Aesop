# Benchmark run — 2026-07-16 — Haiku vs Sonnet vs Opus

First REAL run of the held-out benchmark (wave-26 shipped only the scaffold + offline mock;
the wave-26 critique correctly called that "measurement theater"). This is the actual measurement.

## Method
- Each model answered all 12 held-out tasks in `bench/tasks.jsonl` **blind** — given only the task
  inputs, explicitly forbidden from reading `bench/ground_truth.jsonl`.
- Answers scored against the committed ground truth with the repo's own scorer semantics
  (`tools/bench_runner.py` exact-match / `expected_regex`).
- Models: `haiku`, `sonnet`, `opus` (one agent per model, pinned).

## Result

| Model  | Score | Accuracy |
|--------|-------|----------|
| Haiku  | 12/12 | **100%** |
| Sonnet | 12/12 | **100%** |
| Opus   | 12/12 | **100%** |

Answers were **identical across all three models** on 11/12 tasks; on `t06` Opus returned `#482`
and Haiku/Sonnet returned `482` — both satisfy the ground-truth regex `^#?482$`, so all three pass.

## Honest interpretation (this cuts both ways)

1. **For "Haiku is sufficient":** on these tasks, the cheapest model matched the most expensive one
   exactly. That is real, if narrow, evidence that Haiku is adequate for this *task shape* —
   deterministic extraction and single-label classification, which is a large fraction of real
   subagent work (log parsing, file classification, field extraction).
2. **Against the benchmark itself:** a 100%-across-the-board result means the benchmark **does not
   discriminate** between the models — so it cannot, on its own, distinguish "Haiku suffices" from
   "these tasks are too easy to matter." The single judgment-shaped task (`t09`, is-this-a-real-bug)
   had all three converge on the same (correct) answer, so the dimension where cheap and expensive
   models plausibly diverge was never actually exercised.

So the wave-26 critic was right on both counts: the apparatus needed a real run (now done), and the
run reveals the apparatus is inadequate to settle the broader claim. This measures a floor, not the
frontier.

## Limits
- N=12 — below any real noise floor; differences smaller than ~1 task are meaningless.
- Task selection skews to programmatically-checkable extraction/classification (11/12), which is
  exactly where a cheap model or even a regex does fine. Real subagent work has proportionally more
  judgment (bug adjudication, plan-vs-spec coverage, severity calibration) that this set omits.
- No latency/cost dimension recorded here; the claim "Haiku at 1/3 cost for equal quality" needs the
  cost axis alongside accuracy.

## Next (wave-28 seed)
Add **discriminating, judgment-shaped tasks sampled from real fleet transcripts** — e.g. "is this
audit finding real or inflated?" (the exact failure mode of the wave-24 all-Haiku audit), "does this
plan cover every acceptance criterion?", "rank these three fixes by blast radius." Only tasks where
Haiku and Opus *actually diverge* can measure the frontier. Until then, treat "Haiku sufficient" as
established for extraction/classification only, and unproven for judgment.
