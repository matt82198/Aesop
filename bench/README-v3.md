# bench/*_v3_judgment — bigger, harder, cost-aware judgment benchmark

## Why this exists

The external critique of the fleet's "Haiku is good enough" claim landed on one point above
all: the claim is a **cost** claim ("equal quality at ~1/3 the cost"), and the benchmark so
far measured only accuracy. v2 (`tasks_v2_judgment.jsonl`, 11 tasks) proved the harness and
task *design* can discriminate — but its first real-model run was Haiku 11/11, Sonnet 11/11,
Opus 10/11 (see `bench/results/2026-07-17-judgment-haiku-sonnet-opus.md`): suggestive, and
N far too small to assert anything. Two gaps remained, both called out in that result's own
"Limits" section:

1. **N too small, coverage too narrow.** 11 tasks over 4 judgment shapes can't separate
   models statistically, and a single divergence (Opus on j11) drove the whole delta.
2. **No cost axis.** "Haiku at ~1/3 cost for equal quality" was still *asserted*, because the
   apparatus recorded accuracy and nothing else.

v3 closes both: **28 tasks over 7 judgment shapes**, made harder and more discriminating, plus
a **cost axis** in `tools/bench_runner.py` so accuracy and cost are reported *together*.

## What's new vs v2

| | v2 (`tasks_v2_judgment.jsonl`) | v3 (`tasks_v3_judgment.jsonl`) |
|---|---|---|
| Task count | 11 | **28** |
| Judgment shapes | 4 | **7** |
| Shapes | bug-in-diff, finding-inflation, criteria-coverage, severity | + root-cause-from-stack-trace, refactor-equivalence, security-issue-spot |
| Difficulty | judgment, one edge per task | subtle concurrency/ordering/off-by-one/resource-leak; plausible distractors; mitigating-factor severity; behavior-preserving traps |
| Cost axis | none | **token + latency recorded per model, reported next to accuracy** |
| Ground truth | runtime semantics / quoted-line facts / in-prompt rubric | same objective routes, extended to the 3 new shapes |

The seven shapes (task ids):

- **bug_judgment_diff** (k01–k07, 4 yes / 3 no): does a diff introduce a bug on some valid
  input? Includes an off-by-one slice (k01), a check-then-act **concurrency race** where the
  guard moves outside the lock (k03), a per-iteration **resource leak** (k04), an
  **ordering**/cleanup change from dropping try/finally (k05, a *non*-bug — `with` still
  closes), and a **mutate-during-iteration** RuntimeError (k06). Two "no" tasks (k02 reindex,
  k07 `sum()` refactor) are behaviorally identical refactors that *look* risky.
- **finding_inflation** (k08–k11): three findings on one function, exactly one factually wrong
  (a fabricated SQL-injection on parameterized code, a "no upper-bound check" where one
  exists, a "file never closed" where `finally` closes it, a "last element dropped" that isn't).
  The two accurate findings are the plausible distractors.
- **acceptance_criteria_coverage** (k12–k15): does the plan cover every criterion? Three
  partial-coverage traps (missing strength check / permission gate / duplicate-email check)
  and one fully-covered plan (answer `yes`) whose criteria are reworded to tempt a false gap.
- **severity_calibration** (k16–k19): apply the in-prompt rubric. Includes mitigating-factor
  cases where both over- and under-escalation tempt — an authenticated IDOR that reads as
  `high` not `critical` (k16), a token leak gated on non-default config → `medium` (k17), an
  impractical timing side-channel → `low` (k18), and an unauthenticated RCE → `critical` (k19).
- **root_cause_stack_trace** (k20–k22): pick the correct root cause from a traceback — the
  right stack frame for a `KeyError` (k20), the crash-in-the-except-handler vs the original
  timeout in a chained traceback (k21), an off-by-one column bound behind an `IndexError`
  (k22). Correct answers sit at A / C / B, not a fixed position.
- **refactor_equivalence** (k23–k25): is the refactor behavior-preserving? A subtle `or`-default
  that mis-maps a valid empty string (k23, changed), an equivalent `sum()` (k24), and a
  short-circuit-vs-full-scan change observable through a stated side effect (k25, changed).
- **security_issue_spot** (k26–k28): a real path traversal (k26), a *non*-issue where a
  reviewer's XSS claim is wrong because `html.escape` neutralizes it (k27), and pick the one
  SQL-injectable variant of three (k28, an f-string amid parameterized queries).

## Why the ground truth is objective (not author opinion)

Same bar as v2: **objectively defensible to a skeptic from the input alone**, reproducible by
re-reading the ~10–25 lines in each prompt. A judgment benchmark graded by the same kind of
judgment it measures would just reintroduce the "agents grading agents" problem the whole
`bench/` scaffold exists to avoid. Every v3 answer follows by one of these routes:

- **Provable runtime behavior.** `readings[-1]`/off-by-one slices, `del` during dict iteration
  raising `RuntimeError`, `finally` running on `return`, a lock moved off a check-then-act,
  `sum(gen)` equalling an accumulate loop — each verifiable in a REPL, not a matter of taste.
  The concurrency and ordering claims (k03, k05, k06) are stated in terms of what the
  interpreter/thread scheduler admits, not a vibe: k03's membership test is textually outside
  the `with lock:` block, so two callers can both pass it.
- **A cited line that contradicts the code (finding_inflation).** Each false finding quotes or
  describes behavior the code's own text refutes (e.g. claims "no upper-bound check" against
  `1 <= port <= 65535`). Checkable by reading the one line.
- **A rubric supplied in-prompt, applied mechanically (severity).** The four-bucket rubric is
  in the same prompt; the answer is derived by matching the finding's stated facts to the
  rubric's own wording. k18 is `low` because the finding *itself* states the attack is
  impractical and undemonstrated against a hash compare — the objectivity claim is "the answer
  follows from the stated rubric," not "this rubric is the one true standard."
- **Text-presence for coverage; the reported exception for root-cause.** Coverage answers are a
  re-read of whether the plan mentions each criterion. Root-cause answers are pinned to the
  actually-reported exception type/value/frame in the traceback, plus the stated context.

The v3 test (`tests/test_bench_v3.py`) additionally guards *discrimination*, not just
well-formedness: a hand-written correct-answer stub scores 100%, and a hand-written
**plausible-wrong** stub — the specific mistake a careless judgment makes on each task (missing
a reachable edge, rubber-stamping an inflated finding, positional bias, over/under-escalation,
blaming the wrong frame) — scores near zero. A set where the plausible-wrong key scores as well
as the right one would not discriminate between models, however the tasks read.

## The cost axis (what changed in bench_runner.py)

`run_bench()` still returns `(results, accuracy)` and every existing runner and test is
untouched — a runner returning a bare string is the original contract and stays fully
supported. **Additionally**, a runner may now return a `(text, usage)` pair, where `usage` is
`{"tokens": N, "latency_ms": M}` (or a bare int taken as a token count). Then:

- `run_bench` records per-task `tokens` / `latency_ms` on each result row (`None` when the
  runner returned a bare string).
- `summarize_cost(results)` aggregates total/average tokens and latency.
- `build_summary(model, results, accuracy)` produces one row combining **accuracy and cost**.
- `print_table` prints a cost line under the accuracy line; `print_comparison(rows)` prints
  models as rows with accuracy and cost as columns — the table in which "same accuracy, a
  fraction of the tokens" can be **shown**, not asserted.

This module still **never calls a real model or spends a token**. Usage comes from whatever
runner the caller wires in; the mock runner remains cost-free. Run v3 exactly like v1/v2:

```bash
python tools/bench_runner.py --tasks bench/tasks_v3_judgment.jsonl \
    --ground-truth bench/ground_truth_v3_judgment.jsonl
```

(This prints the mock runner's meaningless score against v3 — the mock is a regex heuristic
with no branch for judgment prompts. Expected, not a result.)

## Honest limits

- **Still curated, not transcript-sampled.** These 28 scenarios are *shaped like* real fleet
  decisions and grounded in provable code/rubric facts, but they were constructed by this
  wave's author, not pulled verbatim from an actual fleet transcript. A true sample from real
  fleet history (with provenance/anonymization) remains future work. Selection bias remains.
- **N=28 is bigger, not big.** Enough to cover 7 shapes 3–7 times each and to separate a
  careful model from a careless one on this rubric; still not a population from which to read a
  precise model-vs-model percentage. Treat small per-shape deltas as noise.
- **Binary / small-alphabet answers only.** Every task collapses to yes/no, a single letter, a
  criterion id, or one of four severity words — chosen so exact/regex matching (no LLM grader
  in the loop) can score judgment without reintroducing "agent grades agent." The harness still
  can't credit a correct judgment phrased differently or give partial credit.
- **Cost axis measures what the runner reports.** bench_runner records and aggregates tokens
  and latency; it does not itself define a price. The dollar figure for "1/3 the cost" comes
  from the caller's per-model token pricing applied to `total_tokens`, and latency is
  wall-clock-dependent. The axis makes the comparison *recordable and reportable*; it does not
  make it free of the caller's measurement conditions.
- **Severity/refactor answers are rubric- and domain-relative.** k16–k19 follow the *stated*
  rubric (a reasonable but not externally-canonical one, e.g. not CVSS); k02/k05/k07/k24/k25
  are "behavior-preserving *for the stated input domain*." Both are objective given the
  prompt's stated frame, which is the bar — not a claim that the frame is the only valid one.
- **No real model has been run against v3 here.** Per the same boundary v1/v2 drew, the actual
  Haiku-vs-Sonnet-vs-Opus comparison (now with cost) costs real tokens and belongs to the
  orchestrator as its own dated result in `bench/results/`. `tests/test_bench_v3.py` proves the
  set *can* discriminate and the cost axis *records and reports*, using synthetic stubs only.
