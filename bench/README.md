# bench/ — Held-out benchmark scaffold

## Why this exists

Wave-25's autonomy expansion (self-merging portfolio PRs on green CI) rests on a
claim that has never been independently checked: **"Haiku is sufficient for fleet
subagent work, quality-equivalent to Sonnet/Opus."** The only evidence for that
claim to date has been the fleet grading its own output — agents judging agents —
with results recorded in a private `MEMORY.md`. That is not evidence a skeptical
outside reader can check. It is agents vouching for agents.

This directory, together with `tools/bench_runner.py`, is the **measurement
apparatus** for closing that gap: a small, fixed, held-out set of tasks with
answers checked by a plain Python string/regex comparison — no model, no agent,
no fleet member in the scoring loop.

**This wave does NOT run the comparison.** No Haiku-vs-Sonnet-vs-Opus numbers are
produced or claimed here. This PR ships the harness, the tasks, and the ground
truth, proven correct against a zero-cost mock runner. Producing an actual verdict
("Haiku scores X%, Opus scores Y%") is separate future work that spends real
tokens against real models and should be reported as its own dated result, not
folded into this scaffold.

## What's in here

- `tasks.jsonl` — 12 held-out tasks, one JSON object per line. Each task has:
  - `id` — stable identifier
  - `category` — what kind of subagent work it represents
  - `match` — `"exact"` or `"regex"`, tells the scorer how to check the answer
  - `prompt` — the full text sent to a model runner
- `ground_truth.jsonl` — one JSON object per line, keyed by `id`:
  - exact tasks: `{"id": ..., "expected": "<string>"}`
  - regex tasks: `{"id": ..., "expected_regex": "<pattern>"}`
- `tools/bench_runner.py` (repo root `tools/`, not under `bench/`) — the scorer
  and CLI. See below.

## Task selection

The 12 tasks are meant to be representative slices of what fleet subagents
actually do day to day, not a general-capability IQ test:

| category | represents |
|---|---|
| `classify_file_change` (t01-t04) | "what kind of file is this diff touching" triage, used to route review lenses |
| `extract_test_name` (t05) | pulling a failing test's name out of a CI log to file/re-dispatch a fix |
| `extract_issue_number` (t06) | linking a commit back to its tracked item |
| `classify_pr_title` (t07) | conventional-commit categorization for changelog/release tooling |
| `extract_exception_type` (t08) | triage-by-exception-class from a traceback |
| `is_real_bug_judgment` (t09) | the actually-hard case: does a reviewer's finding hold up — semantic judgment, not string matching |
| `extract_version` (t10) | parsing a CHANGELOG entry |
| `transform_snake_to_camel` (t11) | small deterministic text transform, the kind of thing a "just run sed" step gets delegated as |
| `extract_file_line` (t12) | pulling a `path:line` locator out of a log line |

Eleven of the twelve tasks have an objectively checkable, unambiguous answer.
One (`t09`) is a genuine judgment call included on purpose — most of what
"is this finding real" review work looks like — and it is the one task the
shipped mock runner gets wrong (see below), by design, to prove the scorer
actually discriminates between correct and incorrect answers rather than
rubber-stamping everything.

## How to run it

Offline, zero-cost, no API key, no network — runs the mock runner and prints
a table:

```bash
python tools/bench_runner.py
```

```
Benchmark results -- runner: mock
------------------------------------------------------------
id    category                    result
t01   classify_file_change        PASS
...
t09   is_real_bug_judgment        FAIL
...
------------------------------------------------------------
Accuracy: 11/12 = 91.7%
```

That 91.7% is a fixture of the mock heuristic's regex-parsing logic. **It is
not a claim about any real model.** The mock runner cannot perform semantic
judgment; it is a stand-in built only to prove the scoring pipeline works.

Override the task/ground-truth files (useful for local experimentation or
CI isolation):

```bash
python tools/bench_runner.py --tasks path/to/tasks.jsonl --ground-truth path/to/gt.jsonl
```

Programmatic use:

```python
from tools.bench_runner import load_tasks, load_ground_truth, run_bench

tasks = load_tasks()
ground_truth = load_ground_truth()
results, accuracy = run_bench(tasks, ground_truth, my_runner)
```

## Running against real models (wave-32+)

### Claude CLI runner

The benchmark ships with built-in runners for the local `claude` CLI (Anthropic's
official Claude Code command-line tool). If `claude` is installed and authenticated,
you can run the benchmark against real models without writing any custom runner code:

```bash
# Install claude if not already installed
npm install -g @anthropic-ai/claude-code

# Run the benchmark against Haiku, Sonnet, and Opus
python tools/bench_runner.py --runner haiku
python tools/bench_runner.py --runner sonnet
python tools/bench_runner.py --runner opus
```

The CLI runner:
- Shells `claude -p "<prompt>" --model <alias> --output-format json`
- Accepts model aliases: `haiku`, `sonnet`, `opus` (or full model ids)
- Captures wall-time latency (in milliseconds) alongside accuracy and tokens
- Gracefully fails with a clear error if `claude` is not on PATH

Example output (with cost data):

```
Benchmark results -- runner: haiku
------------------------------------------------------------------------
id    category                    result   tokens     latency_ms
t01   classify_file_change        PASS     42         125.3
t02   classify_file_change        PASS     38         118.2
...
------------------------------------------------------------------------
Accuracy: 11/12 = 91.7%
Cost:     total_tokens=512 avg_tokens/task=42.7 total_latency_ms=1450.5 avg_latency_ms=120.9
```

### Custom model runners

`run_bench()` takes any `Callable[[str], str]` or `Callable[[str], tuple]` — a
function that accepts a task `prompt` and returns either the model's raw text
response or a `(text, usage)` pair. To score a model beyond the built-in runners,
write a runner that calls it and register it, e.g.:

```python
# tools/bench_runner.py (or a separate script that imports it)
import anthropic
import time

_client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

def custom_runner(prompt: str) -> tuple:
    start = time.time()
    resp = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=64,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed_ms = (time.time() - start) * 1000
    text = resp.content[0].text
    usage = {
        "tokens": resp.usage.output_tokens,
        "latency_ms": elapsed_ms,
    }
    return (text, usage)

RUNNERS["custom"] = custom_runner
```

Then run `python tools/bench_runner.py --runner custom` and compare the printed
accuracy tables side by side.

## Honest limits

- **N=12 is small.** A handful of percentage points of difference between
  models on a 12-task set is noise, not signal. Do not report deltas smaller
  than a few tasks' worth of accuracy (roughly 8 percentage points here) as
  meaningful without a much larger task set or repeated sampling.
- **Task selection bias.** These 12 tasks were picked by one author (this
  wave's implementer) reasoning about "what fleet subagents do," not sampled
  from actual fleet transcripts. They may not represent the true task
  distribution, and they skew toward extraction/classification (regex- or
  string-checkable) because those are what a programmatic, agent-free scorer
  can grade. Only one task (`t09`) requires genuine semantic judgment — real
  subagent work almost certainly has a higher proportion of judgment calls
  than that, so this benchmark likely *overstates* how well a cheap
  extraction-shaped heuristic (or a cheap model) would do on the full mix of
  real fleet work.
- **No real model has been run against this yet.** Every accuracy number this
  README shows or that `bench_runner.py` prints today comes from the offline
  mock runner. "Haiku == Opus quality" remains an open, unmeasured question
  after this wave — this PR only makes it *measurable*.
- **Exact/regex match is a narrow rubric.** It can't credit a correct answer
  phrased differently (e.g., "Yes, it's real" vs. "yes"), and it can't detect
  a right-answer-for-the-wrong-reason. It is deliberately narrow because the
  point is removing agents from the grading loop, not building a lenient
  judge (a lenient judge reintroduces exactly the "agent grades agent"
  problem this scaffold exists to avoid).
- **Not a security/safety benchmark.** This says nothing about adversarial
  robustness, prompt injection resistance, or anything outside plain task
  accuracy.
- **Known repo-hygiene gap this PR leaves open (out of scope for this
  worktree):** adding `bench/` and `tools/bench_runner.py` trips
  `tests/domain-map-drift.test.mjs` (root `CLAUDE.md` domain map is missing a
  `bench/` entry; `tools/CLAUDE.md` FILES section is missing `bench_runner.py`).
  This worktree's write scope is limited to `bench/` and the two files it
  owns under `tools/`/`tests/`, so those two one-line doc additions are left
  for the integrating wave rather than made here.

## Sampling from real transcripts (wave-32+)

Beyond the curated 12-task benchmark, you can sample additional tasks from real
Claude Code session transcripts. This allows the benchmark to grow beyond
hand-written examples and measure real-world task distributions.

### The sampler

`bench/sample_transcripts.py` extracts decision-making moments from Claude Code
session JSONL files (transcripts of user interactions + agent tool calls + results).
It focuses on moments where decisions are made:
  - Classifying files, commits, or review findings
  - Extracting information from logs, diffs, or outputs
  - Judging whether a finding or fix is correct
  - Any reasoning about code or task outcomes

**Sanitization is critical.** The sampler aggressively removes PII and credentials
before outputting tasks, because the sampled task set lives in a public repository:
  - Absolute paths (→ `/path/to/<redacted>`)
  - Usernames, email addresses (→ `<email>`, `<username>`)
  - API tokens, secrets (→ `<api_key>`)
  - Repository names (→ `<name>`)
  - Any private context that could leak customer data

Usage (on your private transcript collection; results go to private outputs):

```bash
# Sample up to 100 tasks from your private transcripts directory
python bench/sample_transcripts.py \
  --transcripts-dir /path/to/your/transcripts \
  --output bench/tasks_sampled.jsonl \
  --max-tasks 100

# Create matching ground truth (this is the hard part — you provide the
# expected answers for the sampled tasks, based on a real model's output
# or your own judgment)
# See bench/fixtures/ground_truth_sampled.jsonl for the format.

# Score your sampled benchmark against a real model
python tools/bench_runner.py \
  --runner haiku \
  --tasks bench/tasks_sampled.jsonl \
  --ground-truth bench/ground_truth_sampled.jsonl
```

### Ground truth for sampled tasks

Sampled tasks are **not** automatically graded. You must provide ground truth:

- For `"match": "exact"` tasks: a single `"expected"` value (string)
- For `"match": "regex"` tasks: an `"expected_regex"` pattern

This ground truth can come from:
  1. Running a reference model (e.g., Opus) on each task and manually verifying
     the answer is correct
  2. Extracting the known-correct answer directly from the transcript context
  3. A domain expert reviewing the task and assigning the right answer

### Latency tracking (wave-32+)

The bench runner now records wall-time latency for each task, alongside accuracy
and token usage. This enables cost-quality analysis: "Haiku at X% accuracy, Y
tokens/task, Z ms/task — Sonnet at X'% accuracy, Y' tokens/task, Z' ms/task."

Runners can return latency in two ways:

```python
# Option 1: bare text response (backward-compatible, no cost data)
def my_runner(prompt):
    response = client.messages.create(...)
    return response.content[0].text

# Option 2: (text, usage) tuple with tokens and latency
def my_runner_with_metrics(prompt):
    import time
    start = time.time()
    response = client.messages.create(...)
    elapsed_ms = (time.time() - start) * 1000
    text = response.content[0].text
    usage = {
        "tokens": response.usage.output_tokens,
        "latency_ms": elapsed_ms
    }
    return (text, usage)
```

The scorer automatically extracts and reports:
  - Per-task latency (in the results table, if any task reports it)
  - Average latency and total latency across all tasks
  - Side-by-side comparison with other models

Example output:

```
Benchmark results -- runner: haiku
------------------------------------------------------------------------
id    category                    result   tokens     latency_ms
t01   classify_file_change        PASS     42         125.3
t02   classify_file_change        PASS     38         118.2
...
------------------------------------------------------------------------
Accuracy: 11/12 = 91.7%
Cost:     total_tokens=512 avg_tokens/task=42.7 total_latency_ms=1450.5 avg_latency_ms=120.9
```

This latency data is strictly observational — it describes *your* execution
environment (network, model load, time of day, etc.), not the model itself.
Do not interpret a single run's latency as a model property.
