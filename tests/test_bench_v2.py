#!/usr/bin/env python3
"""Unit tests for bench/tasks_v2_judgment.jsonl and bench/ground_truth_v2_judgment.jsonl
-- the wave-28 "harder discriminating benchmark" set.

These tests do NOT call a real model (that comparison is separate, post-merge work
run by the orchestrator -- see bench/README-v2.md). They prove three things about
the v2 task set itself, reusing tools/bench_runner.py's existing loader/scorer
(no new scoring logic is introduced here):

1. The task file and ground-truth file are well-formed and mutually consistent
   (same id set, every regex compiles, every field the scorer needs is present).
2. A hand-written CORRECT stub runner -- one canned right answer per task, wired
   by prompt text rather than by peeking at ground truth -- scores 100%.
3. A hand-written WRONG stub runner -- one canned, plausible-but-incorrect answer
   per task (the kind of mistake a cheap/careless judgment would make: missing a
   reachable edge case, agreeing with an inflated finding, picking the positional
   first/last option, over- or under-escalating severity) -- scores LOW.

(2) and (3) together are the "proves the set discriminates" check: a benchmark
where a wrong-but-plausible answer key scores as well as a right one would not be
a useful discriminator between models, no matter how the tasks read.
"""
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import bench_runner  # noqa: E402

TASKS_PATH = REPO_ROOT / "bench" / "tasks_v2_judgment.jsonl"
GROUND_TRUTH_PATH = REPO_ROOT / "bench" / "ground_truth_v2_judgment.jsonl"

# The objectively-correct answer for every task, written independently of the
# ground-truth file's field names (expected vs. expected_regex) so this table
# is a second, human-readable source of truth to eyeball against bench/README-v2.md
# and the ground-truth jsonl, not a blind echo of it.
CANONICAL_ANSWERS = {
    "j01": "yes",       # empty list reachable per context -> readings[-1] raises IndexError
    "j02": "no",        # sum()/len() refactor is behaviorally identical to the loop it replaces
    "j03": "yes",       # None reachable per context -> user.name raises AttributeError
    "j04": "yes",       # open() with no close()/with, called every request in a long-lived process
    "j05": "no",        # reviewer is wrong: `with` guarantees close(), old code could skip it on error
    "j06": "A",         # code explicitly raises ValueError before division; A's claim doesn't occur
    "j07": "B",         # code uses '>=' not '>'; B describes the opposite of the actual check
    "j08": "AC4",       # plan never mentions audit-logging rejected requests
    "j09": "yes",       # plan explicitly covers all four stated criteria
    "j10": "critical",  # unauthenticated + remote + direct secret exposure, per the given rubric
    "j11": "medium",    # requires SSH access + non-default flag -> "specific extra conditions" bucket
}

# A plausible WRONG answer per task -- not random noise, but the mistake a cheap
# or careless judgment plausibly makes on that specific task (missing a reachable
# edge case, rubber-stamping an equivalent-looking crash, agreeing with an
# inflated finding, positional bias, over/under-escalating severity).
PLAUSIBLE_WRONG_ANSWERS = {
    "j01": "no",        # misses that the empty-list path is actually reachable
    "j02": "yes",        # false-alarms on a refactor that is actually equivalent
    "j03": "no",         # misses that None is a normal, reachable case here
    "j04": "no",         # assumes "it still returns the right data" means no leak
    "j05": "yes",        # rubber-stamps the reviewer's incorrect finding
    "j06": "C",           # picks a real-but-minor finding instead of the fabricated one
    "j07": "A",           # positional/first-option bias instead of the actual off-by-one claim
    "j08": "yes",         # misses the uncovered criterion, assumes full coverage
    "j09": "AC1",         # false-alarms a gap on a plan that actually covers everything
    "j10": "high",        # under-escalates a critical, unauthenticated secret leak
    "j11": "critical",    # over-escalates a conditions-gated, already-authorized-access case
}


def _prompt_to_id_map(tasks):
    return {t["prompt"]: t["id"] for t in tasks}


def _make_stub_runner(tasks, answers_by_id):
    """Build a ModelRunner that maps each task's prompt back to its id (via an
    exact prompt-text lookup, not by peeking at the tasks list index or ground
    truth) and returns answers_by_id[id]. Mirrors how bench_runner.mock_runner
    is prompt-driven, not index-driven."""
    prompt_to_id = _prompt_to_id_map(tasks)

    def runner(prompt: str) -> str:
        tid = prompt_to_id[prompt]
        return answers_by_id[tid]

    return runner


class TestV2TaskFilesWellFormed(unittest.TestCase):
    """Structural checks reusing bench_runner's own loader/validator -- no new
    parsing logic is written here."""

    @classmethod
    def setUpClass(cls):
        cls.tasks = bench_runner.load_tasks(TASKS_PATH)
        cls.ground_truth = bench_runner.load_ground_truth(GROUND_TRUTH_PATH)

    def test_task_count_is_in_the_8_to_12_range(self):
        self.assertGreaterEqual(len(self.tasks), 8)
        self.assertLessEqual(len(self.tasks), 12)

    def test_task_ids_are_unique(self):
        ids = [t["id"] for t in self.tasks]
        self.assertEqual(len(ids), len(set(ids)))

    def test_ground_truth_id_set_exactly_matches_task_id_set(self):
        task_ids = {t["id"] for t in self.tasks}
        gt_ids = set(self.ground_truth.keys())
        self.assertEqual(task_ids, gt_ids)

    def test_canonical_answers_table_covers_exactly_the_task_id_set(self):
        # Guards this test file itself: if a task is added/removed without
        # updating CANONICAL_ANSWERS / PLAUSIBLE_WRONG_ANSWERS, fail loudly
        # instead of silently under-testing.
        task_ids = {t["id"] for t in self.tasks}
        self.assertEqual(task_ids, set(CANONICAL_ANSWERS.keys()))
        self.assertEqual(task_ids, set(PLAUSIBLE_WRONG_ANSWERS.keys()))

    def test_every_task_has_a_nonempty_prompt(self):
        for task in self.tasks:
            self.assertTrue(task["prompt"].strip(), msg=f"task {task['id']} has empty prompt")

    def test_task_prompts_are_unique(self):
        # The stub runners below key off exact prompt text; a duplicate prompt
        # would make the lookup ambiguous and silently mis-score a task.
        prompts = [t["prompt"] for t in self.tasks]
        self.assertEqual(len(prompts), len(set(prompts)))

    def test_every_exact_task_ground_truth_has_expected_field(self):
        for task in self.tasks:
            if task["match"] == "exact":
                gt = self.ground_truth[task["id"]]
                self.assertIn(
                    "expected", gt, msg=f"task {task['id']} (exact) missing 'expected' in ground truth"
                )

    def test_every_regex_task_ground_truth_has_expected_regex_field_and_it_compiles(self):
        for task in self.tasks:
            if task["match"] == "regex":
                gt = self.ground_truth[task["id"]]
                self.assertIn(
                    "expected_regex",
                    gt,
                    msg=f"task {task['id']} (regex) missing 'expected_regex' in ground truth",
                )
                re.compile(gt["expected_regex"])  # raises if malformed

    def test_both_match_types_are_represented(self):
        # Reused-loader compatibility check: v2 exercises both match modes v1
        # supports, not just one.
        match_types = {t["match"] for t in self.tasks}
        self.assertEqual(match_types, {"exact", "regex"})

    def test_categories_are_non_trivial_and_varied(self):
        categories = {t["category"] for t in self.tasks}
        self.assertGreaterEqual(len(categories), 4)

    def test_judgment_categories_present(self):
        # This set exists specifically to cover the four judgment-task shapes
        # called out in the wave-28 brief; assert none were quietly dropped.
        categories = {t["category"] for t in self.tasks}
        self.assertEqual(
            categories,
            {
                "bug_judgment_diff",
                "finding_inflation",
                "acceptance_criteria_coverage",
                "severity_calibration",
            },
        )


class TestV2CorrectStubScoresPerfectly(unittest.TestCase):
    """A hand-written runner that always gives the objectively-correct answer
    must score 100%. This proves the ground truth is internally satisfiable by
    at least one answer key (i.e. the scorer and the ground truth agree with
    each other), before we ever look at a wrong answer."""

    @classmethod
    def setUpClass(cls):
        cls.tasks = bench_runner.load_tasks(TASKS_PATH)
        cls.ground_truth = bench_runner.load_ground_truth(GROUND_TRUTH_PATH)
        runner = _make_stub_runner(cls.tasks, CANONICAL_ANSWERS)
        cls.results, cls.accuracy = bench_runner.run_bench(cls.tasks, cls.ground_truth, runner)

    def test_accuracy_is_exactly_one(self):
        self.assertEqual(self.accuracy, 1.0)

    def test_every_task_scored_correct(self):
        wrong = [r["id"] for r in self.results if not r["correct"]]
        self.assertEqual(wrong, [], msg=f"canonical-correct stub missed: {wrong}")


class TestV2WrongStubScoresLow(unittest.TestCase):
    """A hand-written runner that gives a plausible-but-wrong answer to every
    single task must score low. This is the actual discrimination proof: it is
    not enough for *some* wrong answer to fail (any random string would fail a
    strict exact/regex check) -- the specific, plausible mistake pattern for
    each task must be distinguishable from the correct one by this rubric."""

    @classmethod
    def setUpClass(cls):
        cls.tasks = bench_runner.load_tasks(TASKS_PATH)
        cls.ground_truth = bench_runner.load_ground_truth(GROUND_TRUTH_PATH)
        runner = _make_stub_runner(cls.tasks, PLAUSIBLE_WRONG_ANSWERS)
        cls.results, cls.accuracy = bench_runner.run_bench(cls.tasks, cls.ground_truth, runner)

    def test_accuracy_is_low(self):
        # Every canned wrong answer was constructed to differ from the
        # canonical answer, so this should be 0.0; assert a generous < 0.3
        # ceiling so the test documents intent (discriminates sharply) without
        # being brittle to a future task's wrong-answer choice happening to
        # coincide with its own correct answer under case-insensitive match.
        self.assertLess(self.accuracy, 0.3)

    def test_wrong_stub_scores_strictly_below_correct_stub(self):
        correct_runner = _make_stub_runner(self.tasks, CANONICAL_ANSWERS)
        _, correct_accuracy = bench_runner.run_bench(self.tasks, self.ground_truth, correct_runner)
        self.assertLess(self.accuracy, correct_accuracy)

    def test_plausible_wrong_answers_never_accidentally_equal_canonical(self):
        # Sanity-check the fixture itself: if any "wrong" answer were typo'd
        # to match the real answer, the low-score assertion above would be
        # weaker than it looks. Verify at the data level, independent of the
        # scorer, that every wrong answer differs from the canonical one.
        for tid, wrong in PLAUSIBLE_WRONG_ANSWERS.items():
            self.assertNotEqual(
                wrong.strip().lower(),
                CANONICAL_ANSWERS[tid].strip().lower(),
                msg=f"task {tid}: wrong-answer stub coincides with the canonical answer",
            )


if __name__ == "__main__":
    unittest.main()
