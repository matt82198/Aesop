# bench/*_v2_judgment — a harder, judgment-shaped benchmark

## Why this exists

The original `bench/` scaffold (`tasks.jsonl` / `ground_truth.jsonl` / `tools/bench_runner.py`)
shipped a real, scored, agent-free measurement apparatus. But when it was actually run
against real models, the first result was: **Haiku = Sonnet = Opus = 12/12.** That is not
evidence the models are equivalent — it is evidence the *tasks* were too easy to
discriminate between them. Eleven of the twelve v1 tasks are extraction or classification
(pull a version number out of a changelog, classify a file path, convert snake_case to
camelCase) — mechanical, single-answer, low-ambiguity work that any competent model gets
right every time. Only one task (`t09`) asked for real judgment.

This directory adds a second task set, `tasks_v2_judgment.jsonl` /
`ground_truth_v2_judgment.jsonl`, made entirely of judgment-shaped tasks: the kind of call a
fleet subagent actually has to make day to day (is this diff hunk really a bug, is this
audit finding actually accurate, does this plan actually satisfy its acceptance criteria,
how severe is this finding) rather than a lookup a regex could do. These are exactly the
tasks where a cheap or careless model plausibly gets the wrong answer while a careful one
doesn't — which is the point: a benchmark that can't produce different scores for different
models isn't measuring anything.

## What makes these fair (not author opinion)

The brief for this task set was explicit that "objectively defensible to a skeptic from the
input alone" is the bar, not "the author's judgment call" — because a judgment benchmark
graded by the same kind of judgment it's trying to measure just reintroduces the
"agents grading agents" problem the whole `bench/` scaffold exists to avoid (see
`bench/README.md`). Every one of the 11 tasks here is constructed so the correct answer
follows mechanically from the input text, by one of three routes:

1. **Provable runtime behavior (`bug_judgment_diff`, 5 tasks: j01-j05).** Each task shows a
   diff to a small function plus a one-sentence context fact about how it's called. The
   "does this introduce a bug" answer is not a matter of taste — it is a claim about what
   the Python interpreter actually does with the stated reachable input:
   - `j01`: `readings[-1]` on `[]` is `IndexError`. You can verify this in a REPL in one
     line (`[][-1]`). The diff removes the empty-list guard, and the context states the
     empty case is reachable. Real bug.
   - `j02`: `sum(values)/len(values)` and the manual accumulate-loop it replaces produce
     identical results for every input, including `[]` (both return `0.0`). No bug — a
     model that flags this as risky is pattern-matching on "diff touches a check", not
     verifying behavior.
   - `j03`: `None.name` is `AttributeError`. Context states the caller passes `None` for a
     normal, expected case (anonymous visitors). Real bug.
   - `j04`: an `open()` with no `with`/`close()` anywhere in the function or its callers,
     invoked once per request in a long-running process, is a file-descriptor leak by
     definition — not a matter of opinion.
   - `j05`: the reviewer's finding is checked, not manufactured by us. A `with` block
     guarantees `__exit__`/`close()` runs even if `f.read()` raises; the *original* code's
     manual `f.close()` on its own line would actually be skipped on an exception. The
     reviewer has the leak claim backwards. No bug.
2. **A cited line that says the opposite of what the code does (`finding_inflation`,
   2 tasks: j06-j07).** Three findings are given about one short function; exactly one
   misstates the code's actual behavior, checkable by reading the code:
   - `j06`: Finding A claims an "unhandled `ZeroDivisionError`" occurs, but the function
     explicitly guards `b == 0` and raises `ValueError` first — the claimed crash cannot
     happen. Findings B and C are accurate (if minor) observations about the same code.
   - `j07`: Finding B claims the rotation check uses `>` (so an exactly-`max_lines` file
     "will NOT trigger rotation"), but the code reads `>=`, the opposite. Findings A and C
     are accurate.
   These mirror the exact "cites a line that does the opposite" shape called out in the
   task brief, and the wrongness is checkable purely by re-reading the one-line condition
   quoted in the code block.
3. **A rubric supplied in the prompt, applied mechanically (`severity_calibration`, 2
   tasks: j10-j11; `acceptance_criteria_coverage`, 2 tasks: j08-j09).** For severity, the
   full classification rubric (critical/high/medium/low, each with a concrete definition)
   is given *in the same prompt* as the finding — the correct bucket is derived by matching
   the finding's stated facts against the rubric's own wording, not by the grader's private
   sense of "how bad is this." `j10` (unauthenticated, remote, direct secret exposure) matches
   the `critical` definition on every clause. `j11` (requires an existing SSH session plus a
   non-default flag, and the actor already has DB access another way) fails both the
   `critical` and `high` definitions and matches `medium`'s "specific extra conditions"
   example almost verbatim. For acceptance-criteria coverage, the plan text and the numbered
   criteria are both given verbatim; whether the plan text mentions each criterion is a
   text-presence check a skeptic can do by re-reading the plan (`j08`'s plan never mentions
   audit logging at all — AC4 is simply absent; `j09`'s plan explicitly restates all four of
   its criteria).

None of these require trusting this wave's author's taste. Every answer is reproducible by
re-reading the ~10-20 lines of input given in that task's prompt.

## How this differs from v1

| | v1 (`tasks.jsonl`) | v2 (`tasks_v2_judgment.jsonl`) |
|---|---|---|
| Task shape | extraction / classification / transform | judgment: bug-or-not, finding-inflation, criteria-coverage, severity |
| Ground truth source | literal string present in the input | derived (runtime semantics, or a rubric applied to stated facts) |
| Where a cheap model plausibly errs | almost nowhere (11/12 mechanical) | by design, on most tasks — that's the point |
| Judgment-shaped tasks | 1 of 12 (`t09`) | 11 of 11 |
| First real-model result | Haiku = Sonnet = Opus = 12/12 (no discrimination) | not yet run (see Honest limits) |

v2 reuses v1's harness unchanged: `tools/bench_runner.py`'s `load_tasks()` /
`load_ground_truth()` / `score_output()` / `run_bench()` all work as-is against these files
via the `--tasks`/`--ground-truth` override flags or by passing explicit paths to the loader
functions. No new scoring logic was written for v2 — same schema (`id`, `category`, `match`,
`prompt` on the task side; `id` + `expected`/`expected_regex` on the ground-truth side), same
`exact`/`regex` match semantics. The "input" each task judges (a diff, three findings, a plan
plus criteria, a finding plus a rubric) is embedded directly in the `prompt` field, the same
convention v1's `t09` already used for its one judgment task — there is no separate `input`
field in the schema, by design, so the existing harness needed zero changes.

Run it exactly like v1:

```bash
python tools/bench_runner.py --tasks bench/tasks_v2_judgment.jsonl --ground-truth bench/ground_truth_v2_judgment.jsonl
```

(This prints the mock runner's score against v2, which will be low/meaningless — the mock is
a regex heuristic with no branches for judgment prompts. That is expected and is not a
result; see Honest limits.)

## Honest limits

- **Still small N.** 11 tasks is enough to prove the harness and the task *design* actually
  discriminate (see `tests/test_bench_v2.py`), not enough to produce a statistically
  meaningful model-vs-model percentage. Treat any single-digit-task delta between models as
  noise, same caveat as v1's README.
- **Still curated, not sampled.** The task brief asked for tasks "sampled from real fleet
  decisions"; what's here is *shaped like* real fleet decisions (bug-or-not calls on diffs,
  audit-finding review, acceptance-criteria coverage, severity calls) and grounded in
  provable code/rubric facts, but the specific 11 scenarios were constructed by this wave's
  author, not pulled verbatim from an actual fleet transcript. A true sample from real fleet
  history remains future work and would need its own provenance/anonymization pass.
- **Binary/small-alphabet answers only.** Every v2 task collapses to yes/no, a
  single-letter id, a criterion id, or one of four severity words — chosen deliberately so
  `exact`/`regex` matching (no LLM grader in the loop) can still score judgment tasks
  without reintroducing "agent grades agent." This means the *harness* still can't credit a
  correct judgment expressed in different words or partial credit for right-answer-wrong-id
  cases; it can only tell you pass/fail against the one canonical phrasing baked into ground
  truth, same limitation v1's README already documents.
- **Coverage of judgment types is narrow.** Four shapes (bug-or-not, finding-inflation,
  criteria-coverage, severity-from-rubric) are covered twice-to-five-times each; there are
  many other judgment shapes fleet subagents face (e.g. "is this refactor semantically
  equivalent," "does this test actually exercise the claimed bug," "is this the right file
  to fix") that aren't represented here at all.
- **No real model has been run against this yet.** Per this wave's brief, running the actual
  Haiku-vs-Sonnet-vs-Opus comparison on v2 is explicitly out of scope for this worktree — it
  costs real tokens and belongs to the orchestrator as its own dated result, same boundary
  v1 drew. `tests/test_bench_v2.py` only proves the task set *can* discriminate (a
  hand-written correct-answer stub scores 100%, a hand-written plausible-wrong-answer stub
  scores low) using synthetic stub runners, not any real model's output.
- **Severity rubric is still one rubric.** `j10`/`j11` derive their answer from a rubric
  given in-prompt, which makes those two tasks' ground truth mechanically checkable — but
  the rubric's four buckets are this author's summary of common severity-classification
  practice, not a citation to an external standard (e.g. CVSS). A different but reasonable
  rubric could shift where the medium/high boundary falls; the objectivity claim for those
  two tasks is "the answer follows from the stated rubric," not "the rubric itself is the
  unique correct one."
