# Reproducing Aesop

This document explains how to reproduce the project's claims from a clean checkout.

## Overview

The Aesop project includes:
1. **Full test suites** (Node.js + Python) that verify core functionality
2. **An offline benchmark scorer** that proves the benchmark scoring logic works correctly

Both can be reproduced entirely offline, without API keys or external dependencies, from any clean clone of the repository.

## Reproducing from a Clean Clone

### Prerequisites

- **Node.js**: 18 or later
- **Python**: 3.12 or later
- **Git**: any recent version

### Steps

1. Clone the repository (no special flags needed):
   ```bash
   git clone https://github.com/matt82198/aesop.git
   cd aesop
   ```

2. Verify Node.js and Python are installed:
   ```bash
   node --version
   python --version
   ```

3. Install Node.js dependencies:
   ```bash
   npm ci
   ```

4. Run the full test suite (Python + Node.js):
   ```bash
   # Run Node.js tests
   npm run test:node
   
   # Run Python tests
   python -m unittest discover -s tests
   ```

5. Run the benchmark scorer offline:
   ```bash
   # Run the benchmark unit tests (syntax, ground truth format, etc.)
   python -m unittest tests.test_bench_runner -v
   
   # Run the offline mock benchmark
   python tools/bench_runner.py --runner mock
   ```

## What the `.github/workflows/reproduce.yml` Job Does

The `reproduce` workflow in GitHub Actions automates the above steps:

1. **Fresh checkout**: Uses a clean clone (no state reuse from other CI jobs)
2. **Syntax checks**: Validates all Node.js (.mjs) and shell scripts (.sh)
3. **Node.js tests**: Runs the full test suite with `npm run test:node`
4. **Python tests**: Runs the full test suite with `python -m unittest discover`
5. **Benchmark scorer**: Proves the offline mock benchmark reproduces (no external API calls)

The workflow is triggered:
- **Manually**: Via GitHub Actions "Run workflow" button (workflow_dispatch)
- **Weekly**: Every Sunday at 2:00 AM UTC (schedule)

## What Is and Isn't Reproduced

### Reproduced (offline, no API keys needed)

- ✓ All committed test suites (correctness, integration, governance)
- ✓ The benchmark **scorer logic** (matching, scoring, reporting)
- ✓ The benchmark **mock runner** (deterministic offline accuracy score)
- ✓ The committed benchmark files (`bench/tasks.jsonl`, `bench/ground_truth.jsonl`)

### Not Reproduced (requires external APIs)

- ✗ A real multi-model benchmark (calling Claude API, OpenAI, etc.)
- ✗ The dashboard browser tests (Playwright, requires UI setup)
- ✗ Performance/timing benchmarks
- ✗ The full CI job's additional linting and drift checks

The benchmark mock runner always returns the same accuracy score because it uses a hardcoded heuristic (plain string/regex matching), not a real model. This is intentional — the tests prove the *scorer* works correctly, not that any model achieves a specific accuracy.

## Interpreting Results

### Success

```
YAML is valid
All Node.js tests pass
All Python tests pass
Benchmark reproduction successful
```

### Failure

If any step fails, the workflow exits with a non-zero exit code and prints the failure details. Common issues:

1. **Node.js test failure**: Check `tests/*.test.mjs` for the specific failing test.
2. **Python test failure**: Check the error message; most often a missing test fixture or a test isolation bug.
3. **Benchmark reproduction failure**: Run `python tools/bench_runner.py --runner mock` manually to see the exact error.

## For Project Maintainers

When you add new features or tests:

1. Ensure all tests pass locally: `npm run test:all` (or individually per suite)
2. The `reproduce` workflow will catch any regressions automatically
3. If reproduction fails, it indicates the committed test fixtures or scorer are inconsistent

## References

- Test discovery: `python -m unittest discover --help`
- Benchmark scorer: `python tools/bench_runner.py --help`
- GitHub Actions workflow syntax: https://docs.github.com/en/actions
