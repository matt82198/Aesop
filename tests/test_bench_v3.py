#!/usr/bin/env python3
"""Unit tests for bench/tasks_v3_judgment.jsonl + bench/ground_truth_v3_judgment.jsonl
-- the wave-32 "bigger, harder, cost-aware" judgment set -- and for the cost axis
added to tools/bench_runner.py.

Like v2, these tests do NOT call a real model (that comparison is separate,
orchestrator-run work -- see bench/README-v3.md). They reuse bench_runner's
existing loader/scorer (no new scoring logic here) to prove:

1. The task file and ground-truth file are well-formed and mutually consistent
   (same id set, every regex compiles, every scorer field present), the set is
   the intended size (24-30), and all seven judgment shapes are present.
2. A hand-written CORRECT stub runner scores 100% (the ground truth is
   internally satisfiable).
3. A hand-written PLAUSIBLE-WRONG stub runner -- the specific mistake a
   cheap/careless judgment would make on each task -- scores LOW and strictly
   below the correct stub. That gap is the discrimination proof.
4. The new cost axis in bench_runner records per-task token/latency usage,
   aggregates it, reports it alongside accuracy, and stays fully
   backward-compatible with bare-string runners.
"""
import io
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import bench_runner  # noqa: E402

TASKS_PATH = REPO_ROOT / "bench" / "tasks_v3_judgment.jsonl"
GROUND_TRUTH_PATH = REPO_ROOT / "bench" / "ground_truth_v3_judgment.jsonl"

# The objectively-correct answer for every task, written independently of the
# ground-truth file's field names so this table is a second, human-readable
# source of truth to eyeball against bench/README-v3.md and the jsonl, not a
# blind echo of the ground-truth file.
CANONICAL_ANSWERS = {
    # bug_judgment_diff (4 yes / 3 no)
    "k01": "yes",       # off-by-one slice returns n+1 items
    "k02": "no",        # range reindex is an equivalent iteration
    "k03": "yes",       # membership check moved outside the lock -> race/double-compute
    "k04": "yes",       # open() with no close(), thousands of files, long-lived process
    "k05": "no",        # `with` context manager still guarantees close() -> equivalent
    "k06": "yes",       # deleting during iteration over d.keys() raises RuntimeError
    "k07": "no",        # sum(gen) refactor is behaviorally identical to the loop
    # finding_inflation (false finding at C, A, B, C)
    "k08": "C",         # there IS an upper-bound check; 70000 raises, not accepted
    "k09": "A",         # query is parameterized (?), not string-concatenated -> no injection
    "k10": "B",         # `finally` runs even when the try block returns -> file IS closed
    "k11": "C",         # range(0,len,size) covers the last element; nothing dropped
    # acceptance_criteria_coverage
    "k12": "AC3",       # plan never mentions password-strength validation
    "k13": "AC3",       # plan never mentions the export permission/403 check
    "k14": "yes",       # all four criteria covered
    "k15": "AC4",       # plan never checks for an already-registered/duplicate email
    # severity_calibration (rubric in prompt)
    "k16": "high",      # authenticated IDOR, sensitive data, no further conditions
    "k17": "medium",    # gated on a non-default DEBUG=true configuration
    "k18": "low",       # impractical hash-compare timing side-channel, none demonstrated
    "k19": "critical",  # unauthenticated remote arbitrary code execution (yaml.load)
    # root_cause_stack_trace (correct at A, C, B)
    "k20": "A",         # KeyError 'u_9931' at line 18 (DB[uid]); line 42 succeeded
    "k21": "C",         # the except handler's err.respons typo raises the reported error
    "k22": "B",         # range(C+1) indexes column C -> off-by-one column bound
    # refactor_equivalence (no / yes / no)
    "k23": "no",        # `or` maps a valid empty-string name to 'anonymous'
    "k24": "yes",       # sum() over the same terms from 0 -> equivalent
    "k25": "no",        # comprehension calls pred on every element; side effect differs
    # security_issue_spot
    "k26": "yes",       # unvalidated filename + os.path.join/open -> path traversal
    "k27": "no",        # html.escape neutralizes XSS in element text; reviewer is wrong
    "k28": "B",         # f-string interpolates untrusted email into SQL -> injectable
}

# A plausible WRONG answer per task: not random noise, but the specific mistake a
# cheap or careless judgment plausibly makes (missing a reachable edge case,
# rubber-stamping an inflated finding, positional bias, over/under-escalating
# severity, blaming the wrong stack frame).
PLAUSIBLE_WRONG_ANSWERS = {
    "k01": "no",         # misses the off-by-one
    "k02": "yes",        # false-alarms on an equivalent reindex
    "k03": "no",         # misses that the check is no longer lock-protected
    "k04": "no",         # assumes "returns the right data" means no leak
    "k05": "yes",        # thinks removing try/finally dropped the cleanup
    "k06": "no",         # misses the mutate-during-iteration RuntimeError
    "k07": "yes",        # false-alarms on an equivalent refactor
    "k08": "A",          # picks a real finding instead of the fabricated one
    "k09": "B",          # picks a real finding instead of the inflated injection claim
    "k10": "A",          # picks a real finding instead of the false "not closed" claim
    "k11": "A",          # picks a real finding instead of the false "element dropped" claim
    "k12": "yes",        # misses the uncovered strength-check criterion
    "k13": "yes",        # misses the uncovered permission criterion
    "k14": "AC1",        # false-alarms a gap on a fully-covered plan
    "k15": "yes",        # misses the uncovered duplicate-email criterion
    "k16": "critical",   # over-escalates an authenticated (not unauth) finding
    "k17": "high",       # ignores the non-default-config gating
    "k18": "medium",     # over-escalates an impractical theoretical issue
    "k19": "high",       # under-escalates an unauthenticated RCE
    "k20": "B",          # blames the wrong frame (line 42 instead of line 18)
    "k21": "A",          # blames the original timeout, not the handler crash
    "k22": "A",          # blames an empty board despite the stated R rows
    "k23": "yes",        # misses the empty-string behavior change
    "k24": "no",         # false-alarms on an equivalent refactor
    "k25": "yes",        # misses the side-effect call-count change
    "k26": "no",         # misses the path traversal
    "k27": "yes",        # rubber-stamps the incorrect XSS finding
    "k28": "A",          # picks a safe parameterized variant as the vulnerable one
}

EXPECTED_CATEGORIES = {
    "bug_judgment_diff",
    "finding_inflation",
    "acceptance_criteria_coverage",
    "severity_calibration",
    "root_cause_stack_trace",
    "refactor_equivalence",
    "security_issue_spot",
}


def _prompt_to_id_map(tasks):
    return {t["prompt"]: t["id"] for t in tasks}


def _make_stub_runner(tasks, answers_by_id):
    """Build a ModelRunner that maps each prompt back to its id (exact prompt-text
    lookup, not index/ground-truth peeking) and returns answers_by_id[id]."""
    prompt_to_id = _prompt_to_id_map(tasks)

    def runner(prompt: str) -> str:
        return answers_by_id[prompt_to_id[prompt]]

    return runner


class TestV3TaskFilesWellFormed(unittest.TestCase):
    """Structural checks reusing bench_runner's own loader/validator."""

    @classmethod
    def setUpClass(cls):
        cls.tasks = bench_runner.load_tasks(TASKS_PATH)
        cls.ground_truth = bench_runner.load_ground_truth(GROUND_TRUTH_PATH)

    def test_task_count_is_in_the_24_to_30_range(self):
        # v3's headline change vs v2 (11 tasks): a bigger N.
        self.assertGreaterEqual(len(self.tasks), 24)
        self.assertLessEqual(len(self.tasks), 30)

    def test_task_ids_are_unique(self):
        ids = [t["id"] for t in self.tasks]
        self.assertEqual(len(ids), len(set(ids)))

    def test_ground_truth_id_set_exactly_matches_task_id_set(self):
        task_ids = {t["id"] for t in self.tasks}
        gt_ids = set(self.ground_truth.keys())
        self.assertEqual(task_ids, gt_ids)

    def test_answer_tables_cover_exactly_the_task_id_set(self):
        # Guards this test file: adding/removing a task without updating the
        # answer tables fails loudly instead of silently under-testing.
        task_ids = {t["id"] for t in self.tasks}
        self.assertEqual(task_ids, set(CANONICAL_ANSWERS.keys()))
        self.assertEqual(task_ids, set(PLAUSIBLE_WRONG_ANSWERS.keys()))

    def test_every_task_has_a_nonempty_prompt(self):
        for task in self.tasks:
            self.assertTrue(task["prompt"].strip(), msg=f"task {task['id']} has empty prompt")

    def test_task_prompts_are_unique(self):
        # The stub runners key off exact prompt text; a duplicate prompt would
        # make the lookup ambiguous and silently mis-score a task.
        prompts = [t["prompt"] for t in self.tasks]
        self.assertEqual(len(prompts), len(set(prompts)))

    def test_every_exact_task_ground_truth_has_expected_field(self):
        for task in self.tasks:
            if task["match"] == "exact":
                gt = self.ground_truth[task["id"]]
                self.assertIn("expected", gt, msg=f"task {task['id']} (exact) missing 'expected'")

    def test_every_regex_task_ground_truth_has_expected_regex_field_and_it_compiles(self):
        for task in self.tasks:
            if task["match"] == "regex":
                gt = self.ground_truth[task["id"]]
                self.assertIn(
                    "expected_regex", gt, msg=f"task {task['id']} (regex) missing 'expected_regex'"
                )
                re.compile(gt["expected_regex"])  # raises if malformed

    def test_both_match_types_are_represented(self):
        match_types = {t["match"] for t in self.tasks}
        self.assertEqual(match_types, {"exact", "regex"})

    def test_all_seven_judgment_shapes_present(self):
        categories = {t["category"] for t in self.tasks}
        self.assertEqual(categories, EXPECTED_CATEGORIES)

    def test_each_category_has_at_least_three_tasks(self):
        from collections import Counter

        counts = Counter(t["category"] for t in self.tasks)
        for cat in EXPECTED_CATEGORIES:
            self.assertGreaterEqual(
                counts[cat], 3, msg=f"category {cat} has only {counts[cat]} task(s)"
            )

    def test_binary_answers_are_not_all_the_same_word(self):
        # A yes/no set that is secretly all-"yes" would be gamed by a constant
        # answer. Assert both yes and no appear among the exact-match answers.
        exact_answers = {
            self.ground_truth[t["id"]]["expected"].lower()
            for t in self.tasks
            if t["match"] == "exact"
        }
        self.assertIn("yes", exact_answers)
        self.assertIn("no", exact_answers)


class TestV3CorrectStubScoresPerfectly(unittest.TestCase):
    """A runner giving the objectively-correct answer to every task must score
    100% -- proves the ground truth is internally satisfiable before we look at
    a wrong answer key."""

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


class TestV3WrongStubScoresLow(unittest.TestCase):
    """A runner giving a plausible-but-wrong answer to every task must score low
    and strictly below the correct stub. This is the discrimination proof: the
    specific, plausible mistake pattern for each task must be distinguishable
    from the correct answer by the exact/regex rubric."""

    @classmethod
    def setUpClass(cls):
        cls.tasks = bench_runner.load_tasks(TASKS_PATH)
        cls.ground_truth = bench_runner.load_ground_truth(GROUND_TRUTH_PATH)
        runner = _make_stub_runner(cls.tasks, PLAUSIBLE_WRONG_ANSWERS)
        cls.results, cls.accuracy = bench_runner.run_bench(cls.tasks, cls.ground_truth, runner)

    def test_accuracy_is_low(self):
        # Every canned wrong answer differs from the canonical one, so this
        # should be 0.0; a generous < 0.2 ceiling documents intent without
        # being brittle.
        self.assertLess(self.accuracy, 0.2)

    def test_wrong_stub_scores_strictly_below_correct_stub(self):
        correct_runner = _make_stub_runner(self.tasks, CANONICAL_ANSWERS)
        _, correct_accuracy = bench_runner.run_bench(
            self.tasks, self.ground_truth, correct_runner
        )
        self.assertLess(self.accuracy, correct_accuracy)

    def test_plausible_wrong_answers_never_accidentally_equal_canonical(self):
        # Sanity-check the fixture: a "wrong" answer typo'd to match the real
        # answer would weaken the low-score assertion. Verify at the data level.
        for tid, wrong in PLAUSIBLE_WRONG_ANSWERS.items():
            self.assertNotEqual(
                wrong.strip().lower(),
                CANONICAL_ANSWERS[tid].strip().lower(),
                msg=f"task {tid}: wrong-answer stub coincides with the canonical answer",
            )


class TestV3AnswerDistributionDefendsAgainstGaming(unittest.TestCase):
    """A discriminating set must not be beatable by a single constant answer or a
    fixed positional pick. Assert no single answer dominates within a shape."""

    @classmethod
    def setUpClass(cls):
        cls.tasks = bench_runner.load_tasks(TASKS_PATH)

    def test_no_single_letter_wins_multiple_choice_shapes(self):
        # Across the letter-answer shapes, a constant "always answer C" must not
        # score a majority. Check each such category individually.
        from collections import Counter

        letter_categories = {
            "finding_inflation",
            "root_cause_stack_trace",
        }
        for cat in letter_categories:
            cat_ids = [t["id"] for t in self.tasks if t["category"] == cat]
            answers = [CANONICAL_ANSWERS[i] for i in cat_ids]
            most_common_count = Counter(answers).most_common(1)[0][1]
            self.assertLessEqual(
                most_common_count,
                len(cat_ids) - 1,
                msg=f"{cat}: a single constant letter answers {most_common_count}/{len(cat_ids)}",
            )


class TestCostAxis(unittest.TestCase):
    """Prove the wave-32 cost axis in bench_runner: per-task usage is recorded,
    aggregated, reported alongside accuracy, and backward-compatible with
    bare-string runners. No real model is called; usage is supplied by stubs."""

    def _mini(self):
        tasks = [
            {"id": "c1", "category": "x", "match": "exact", "prompt": "p1"},
            {"id": "c2", "category": "x", "match": "exact", "prompt": "p2"},
        ]
        ground_truth = {
            "c1": {"id": "c1", "expected": "yes"},
            "c2": {"id": "c2", "expected": "no"},
        }
        return tasks, ground_truth

    def test_runner_returning_text_and_usage_dict_records_per_task_cost(self):
        tasks, gt = self._mini()
        usage_by_prompt = {
            "p1": ("yes", {"tokens": 120, "latency_ms": 40.0}),
            "p2": ("no", {"tokens": 80, "latency_ms": 20.0}),
        }
        results, accuracy = bench_runner.run_bench(tasks, gt, lambda p: usage_by_prompt[p])
        self.assertEqual(accuracy, 1.0)  # scoring still works on the (text, usage) form
        by_id = {r["id"]: r for r in results}
        self.assertEqual(by_id["c1"]["tokens"], 120)
        self.assertEqual(by_id["c1"]["latency_ms"], 40.0)
        self.assertEqual(by_id["c2"]["tokens"], 80)

    def test_summarize_cost_aggregates_tokens_and_latency(self):
        tasks, gt = self._mini()
        usage_by_prompt = {
            "p1": ("yes", {"tokens": 120, "latency_ms": 40.0}),
            "p2": ("no", {"tokens": 80, "latency_ms": 20.0}),
        }
        results, _ = bench_runner.run_bench(tasks, gt, lambda p: usage_by_prompt[p])
        cost = bench_runner.summarize_cost(results)
        self.assertTrue(cost["has_cost"])
        self.assertEqual(cost["total_tokens"], 200)
        self.assertEqual(cost["avg_tokens"], 100.0)
        self.assertEqual(cost["total_latency_ms"], 60.0)
        self.assertEqual(cost["avg_latency_ms"], 30.0)

    def test_build_summary_carries_accuracy_and_cost_together(self):
        tasks, gt = self._mini()
        usage_by_prompt = {
            "p1": ("yes", {"tokens": 120, "latency_ms": 40.0}),
            "p2": ("WRONG", {"tokens": 80, "latency_ms": 20.0}),
        }
        results, accuracy = bench_runner.run_bench(tasks, gt, lambda p: usage_by_prompt[p])
        row = bench_runner.build_summary("stub", results, accuracy)
        self.assertEqual(row["model"], "stub")
        self.assertEqual(row["n_correct"], 1)
        self.assertEqual(row["accuracy"], 0.5)
        self.assertEqual(row["total_tokens"], 200)  # cost recorded even for a wrong answer

    def test_bare_string_runner_is_backward_compatible_and_cost_free(self):
        tasks, gt = self._mini()
        results, accuracy = bench_runner.run_bench(tasks, gt, lambda p: "yes" if p == "p1" else "no")
        self.assertEqual(accuracy, 1.0)
        for r in results:
            self.assertIsNone(r["usage"])
            self.assertIsNone(r["tokens"])
            self.assertIsNone(r["latency_ms"])
        cost = bench_runner.summarize_cost(results)
        self.assertFalse(cost["has_cost"])
        self.assertIsNone(cost["total_tokens"])

    def test_runner_may_return_bare_int_token_count(self):
        text, usage = bench_runner.normalize_runner_output(("answer", 512))
        self.assertEqual(text, "answer")
        self.assertEqual(usage, {"tokens": 512, "latency_ms": None})

    def test_malformed_runner_output_raises(self):
        with self.assertRaises(ValueError):
            bench_runner.normalize_runner_output(("a", "b", "c"))  # 3-tuple
        with self.assertRaises(ValueError):
            bench_runner.normalize_runner_output(123)  # bare non-str/tuple
        with self.assertRaises(ValueError):
            bench_runner.normalize_runner_output(("text", True))  # bool token count

    def test_print_table_includes_cost_columns_when_usage_present(self):
        tasks, gt = self._mini()
        usage_by_prompt = {
            "p1": ("yes", {"tokens": 120, "latency_ms": 40.0}),
            "p2": ("no", {"tokens": 80, "latency_ms": 20.0}),
        }
        results, accuracy = bench_runner.run_bench(tasks, gt, lambda p: usage_by_prompt[p])
        buf = io.StringIO()
        bench_runner.print_table("stub", results, accuracy, stream=buf)
        out = buf.getvalue()
        self.assertIn("tokens", out)
        self.assertIn("latency_ms", out)
        self.assertIn("Accuracy:", out)
        self.assertIn("Cost:", out)
        self.assertIn("total_tokens=200", out)

    def test_print_table_omits_cost_line_for_bare_string_runner(self):
        tasks, gt = self._mini()
        results, accuracy = bench_runner.run_bench(tasks, gt, lambda p: "yes")
        buf = io.StringIO()
        bench_runner.print_table("stub", results, accuracy, stream=buf)
        out = buf.getvalue()
        self.assertIn("Accuracy:", out)
        self.assertNotIn("Cost:", out)

    def test_print_comparison_shows_accuracy_and_cost_side_by_side(self):
        tasks, gt = self._mini()
        haiku = {"p1": ("yes", {"tokens": 100, "latency_ms": 30.0}),
                 "p2": ("no", {"tokens": 90, "latency_ms": 25.0})}
        opus = {"p1": ("yes", {"tokens": 300, "latency_ms": 120.0}),
                "p2": ("no", {"tokens": 280, "latency_ms": 110.0})}
        h_res, h_acc = bench_runner.run_bench(tasks, gt, lambda p: haiku[p])
        o_res, o_acc = bench_runner.run_bench(tasks, gt, lambda p: opus[p])
        rows = [
            bench_runner.build_summary("haiku", h_res, h_acc),
            bench_runner.build_summary("opus", o_res, o_acc),
        ]
        buf = io.StringIO()
        bench_runner.print_comparison(rows, stream=buf)
        out = buf.getvalue()
        self.assertIn("haiku", out)
        self.assertIn("opus", out)
        self.assertIn("accuracy", out)
        # Same accuracy, very different cost -- the whole point of the axis.
        self.assertEqual(rows[0]["accuracy"], rows[1]["accuracy"])
        self.assertLess(rows[0]["avg_tokens"], rows[1]["avg_tokens"])


if __name__ == "__main__":
    unittest.main()
