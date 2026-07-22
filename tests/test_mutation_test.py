#!/usr/bin/env python3
"""
Unit tests for tools/mutation_test.py — the mutation testing harness.

These tests prove the mutation testing tool correctly:
  (1) Detects when tests are too weak to catch bugs (survived mutations)
  (2) Detects when tests are strong and catch all bugs (killed mutations)

Uses synthetic fixture modules embedded below (not imported from disk,
to avoid pollution and circular dependencies).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import mutation_test  # noqa: E402


# Fixture 1: A simple weak target module (has bugs, but weak tests don't catch them)
WEAK_TARGET_SOURCE = '''
def is_positive(x):
    """Return True if x is positive."""
    return x >= 0  # BUG: should be x > 0

def add_one(x):
    """Add 1 to x."""
    return x + 1  # OK

def greet(name):
    """Greet someone."""
    return "Hello, " + name  # OK
'''

# Fixture 1: Weak test for the target (doesn't catch the >= bug)
WEAK_TEST_SOURCE = '''
import unittest
import sys
from pathlib import Path

# Add current directory to path (target is in same dir)
sys.path.insert(0, str(Path(__file__).parent))

import fixture_weak_target as target

class TestWeakTarget(unittest.TestCase):
    """Weak tests that don't catch all bugs."""

    def test_add_one(self):
        """Test add_one with only one case."""
        self.assertEqual(target.add_one(5), 6)

    def test_greet(self):
        """Test greet."""
        self.assertEqual(target.greet("Alice"), "Hello, Alice")

    # Missing: test_is_positive() — no tests for is_positive!
    # So the bug (>= instead of >) is never caught.

if __name__ == "__main__":
    unittest.main()
'''


# Fixture 2: A simple strong target module (no bugs)
STRONG_TARGET_SOURCE = '''
def is_positive(x):
    """Return True if x is positive."""
    return x > 0

def add_one(x):
    """Add 1 to x."""
    return x + 1

def is_even(x):
    """Return True if x is even."""
    return x % 2 == 0
'''

# Fixture 2: Strong test for the target (catches all bugs)
STRONG_TEST_SOURCE = '''
import unittest
import sys
from pathlib import Path

# Add current directory to path (target is in same dir)
sys.path.insert(0, str(Path(__file__).parent))

import fixture_strong_target as target

class TestStrongTarget(unittest.TestCase):
    """Strong tests that catch bugs."""

    def test_is_positive_true(self):
        """is_positive returns True for positive numbers."""
        self.assertTrue(target.is_positive(1))
        self.assertTrue(target.is_positive(100))

    def test_is_positive_false_for_zero(self):
        """is_positive returns False for zero."""
        self.assertFalse(target.is_positive(0))

    def test_is_positive_false_for_negative(self):
        """is_positive returns False for negative numbers."""
        self.assertFalse(target.is_positive(-5))

    def test_add_one_positive(self):
        """add_one works for positive numbers."""
        self.assertEqual(target.add_one(5), 6)
        self.assertEqual(target.add_one(0), 1)

    def test_add_one_negative(self):
        """add_one works for negative numbers."""
        self.assertEqual(target.add_one(-5), -4)

    def test_is_even_true(self):
        """is_even returns True for even numbers."""
        self.assertTrue(target.is_even(0))
        self.assertTrue(target.is_even(2))
        self.assertTrue(target.is_even(-4))

    def test_is_even_false(self):
        """is_even returns False for odd numbers."""
        self.assertFalse(target.is_even(1))
        self.assertFalse(target.is_even(-3))

if __name__ == "__main__":
    unittest.main()
'''


class TestMutationTestWeakTarget(unittest.TestCase):
    """Test mutation_test tool against weak target (should find survivors)."""

    def test_weak_target_has_survivors(self):
        """Weak tests should let some mutations survive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Write fixture files
            target_file = tmpdir / "fixture_weak_target.py"
            test_file = tmpdir / "test_fixture_weak.py"

            target_file.write_text(WEAK_TARGET_SOURCE, encoding="utf-8")
            test_file.write_text(WEAK_TEST_SOURCE, encoding="utf-8")

            # Run mutation test
            result = mutation_test.run(str(target_file), str(test_file))

            # Should have survivors (because tests don't check is_positive)
            self.assertGreater(
                result["survived"],
                0,
                "Expected weak tests to have survived mutations, but got none"
            )

            # Should have killed some mutations (add_one and greet are tested)
            self.assertGreater(
                result["killed"],
                0,
                "Expected weak tests to kill some mutations"
            )

    def test_weak_target_reports_survivors(self):
        """Weak tests should report which mutations survived."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            target_file = tmpdir / "fixture_weak_target.py"
            test_file = tmpdir / "test_fixture_weak.py"

            target_file.write_text(WEAK_TARGET_SOURCE, encoding="utf-8")
            test_file.write_text(WEAK_TEST_SOURCE, encoding="utf-8")

            result = mutation_test.run(str(target_file), str(test_file))

            # Mutations list should be populated
            self.assertIsInstance(result["mutations"], list)
            if result["survived"] > 0:
                self.assertGreater(
                    len(result["mutations"]),
                    0,
                    "Expected mutations list to be populated for survivors"
                )

            # Each mutation should have required keys
            for mut in result["mutations"]:
                self.assertIn("file", mut)
                self.assertIn("line", mut)
                self.assertIn("original", mut)
                self.assertIn("mutated", mut)


class TestMutationTestStrongTarget(unittest.TestCase):
    """Test mutation_test tool against strong target (should kill all mutations)."""

    def test_strong_target_kills_mutations(self):
        """Strong tests should kill all or nearly all mutations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            target_file = tmpdir / "fixture_strong_target.py"
            test_file = tmpdir / "test_fixture_strong.py"

            target_file.write_text(STRONG_TARGET_SOURCE, encoding="utf-8")
            test_file.write_text(STRONG_TEST_SOURCE, encoding="utf-8")

            # Run mutation test
            result = mutation_test.run(str(target_file), str(test_file))

            # Should have killed mutations
            self.assertGreater(
                result["killed"],
                0,
                "Expected strong tests to kill some mutations"
            )

            # Should have fewer or zero survivors (strong tests are comprehensive)
            # Note: we allow some survivors due to AST limitations or hard-to-kill
            # mutations, but the strong test should have far fewer than weak.
            self.assertLess(
                result["survived"],
                result["killed"],
                "Expected strong tests to kill more mutations than they miss"
            )


class TestMutationTestCLI(unittest.TestCase):
    """Test CLI interface."""

    def test_cli_with_json_output(self):
        """CLI --json should output valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            target_file = tmpdir / "fixture_strong_target.py"
            test_file = tmpdir / "test_fixture_strong.py"

            target_file.write_text(STRONG_TARGET_SOURCE, encoding="utf-8")
            test_file.write_text(STRONG_TEST_SOURCE, encoding="utf-8")

            # Run CLI with --json
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tools" / "mutation_test.py"),
                    "--target", str(target_file),
                    "--test", str(test_file),
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Should exit 0 (always advisory)
            self.assertEqual(result.returncode, 0)

            # Should output valid JSON
            output = json.loads(result.stdout)
            self.assertIn("killed", output)
            self.assertIn("survived", output)
            self.assertIn("mutations", output)

    def test_cli_exits_zero_always(self):
        """CLI should exit 0 always (even if mutations survive)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            target_file = tmpdir / "fixture_weak_target.py"
            test_file = tmpdir / "test_fixture_weak.py"

            target_file.write_text(WEAK_TARGET_SOURCE, encoding="utf-8")
            test_file.write_text(WEAK_TEST_SOURCE, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tools" / "mutation_test.py"),
                    "--target", str(target_file),
                    "--test", str(test_file),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Should exit 0 even with weak tests and survivors
            self.assertEqual(result.returncode, 0)


class TestMutationExtraction(unittest.TestCase):
    """Test mutation extraction logic."""

    def test_extract_mutations_from_comparisons(self):
        """extract_mutations should find comparison operator mutations."""
        source = "x == y"
        mutations = mutation_test.extract_mutations(source)
        self.assertGreater(len(mutations), 0)

    def test_extract_mutations_from_numeric_literals(self):
        """extract_mutations should find numeric literal mutations."""
        source = "x = 42"
        mutations = mutation_test.extract_mutations(source)
        self.assertGreater(len(mutations), 0)

    def test_extract_mutations_from_boolop(self):
        """extract_mutations should find boolean operator mutations."""
        source = "x and y"
        mutations = mutation_test.extract_mutations(source)
        self.assertGreater(len(mutations), 0)

    def test_apply_mutation_valid_index(self):
        """apply_mutation should apply mutation at valid index."""
        source = "x = 42"
        mutations = mutation_test.extract_mutations(source)
        if len(mutations) > 0:
            mutated = mutation_test.apply_mutation(source, 0)
            self.assertIsNotNone(mutated)
            self.assertNotEqual(mutated, source)

    def test_apply_mutation_invalid_index(self):
        """apply_mutation should return None for invalid index."""
        source = "x = 42"
        mutated = mutation_test.apply_mutation(source, 9999)
        self.assertIsNone(mutated)

    def test_extract_mutations_syntax_error(self):
        """extract_mutations should return empty list for invalid syntax."""
        source = "x = ("
        mutations = mutation_test.extract_mutations(source)
        self.assertEqual(len(mutations), 0)


# Fixture: A target with a function that always fails its test
BROKEN_BASELINE_TARGET_SOURCE = '''
def broken_function():
    """This function has logic that doesn't match its test."""
    return True
'''

# Fixture: A test that fails even on the original unmutated code (baseline fails)
BROKEN_BASELINE_TEST_SOURCE = '''
import unittest
import sys
from pathlib import Path

# Add current directory to path (target is in same dir)
sys.path.insert(0, str(Path(__file__).parent))

import fixture_broken_baseline as target

class TestBrokenBaseline(unittest.TestCase):
    """Tests that fail at baseline (test suite is broken)."""

    def test_broken_function_fails(self):
        """This test fails even on unmutated code."""
        # The function returns True but test expects False
        # This simulates a broken test suite that doesn't work in sandbox
        self.assertFalse(target.broken_function())

if __name__ == "__main__":
    unittest.main()
'''


class TestMutationTestBrokenBaseline(unittest.TestCase):
    """Test mutation_test handles broken baseline (test fails on unmutated code)."""

    def test_baseline_fails_returns_error_result(self):
        """When baseline test fails, tool should return error result with killed=0 and survived=0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            target_file = tmpdir / "fixture_broken_baseline.py"
            test_file = tmpdir / "test_fixture_broken_baseline.py"

            target_file.write_text(BROKEN_BASELINE_TARGET_SOURCE, encoding="utf-8")
            test_file.write_text(BROKEN_BASELINE_TEST_SOURCE, encoding="utf-8")

            # Run mutation test
            result = mutation_test.run(str(target_file), str(test_file))

            # Should have error field
            self.assertIn("error", result, "Expected error field in result when baseline fails")

            # Should report baseline failure
            self.assertIn("baseline", result.get("error", "").lower(),
                         "Expected error message to mention baseline")

            # killed and survived should be zeroed
            self.assertEqual(result["killed"], 0,
                           "Expected killed=0 when baseline fails")
            self.assertEqual(result["survived"], 0,
                           "Expected survived=0 when baseline fails")

            # mutations should be empty
            self.assertEqual(result["mutations"], [],
                           "Expected empty mutations when baseline fails")

    def test_baseline_fails_cli_returns_nonzero(self):
        """When baseline test fails, CLI should return nonzero exit code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            target_file = tmpdir / "fixture_broken_baseline.py"
            test_file = tmpdir / "test_fixture_broken_baseline.py"

            target_file.write_text(BROKEN_BASELINE_TARGET_SOURCE, encoding="utf-8")
            test_file.write_text(BROKEN_BASELINE_TEST_SOURCE, encoding="utf-8")

            # Run CLI
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tools" / "mutation_test.py"),
                    "--target", str(target_file),
                    "--test", str(test_file),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Should exit nonzero when baseline fails
            self.assertNotEqual(result.returncode, 0,
                              "Expected nonzero exit code when baseline fails")


class TestMutationTestWithSiblingImports(unittest.TestCase):
    """Test mutation_test handles modules with sibling imports (package dependencies)."""

    # A module that imports a REAL sibling module (not inline)
    SIBLING_TARGET_SOURCE = '''
import fixture_sibling_config as config_module

def validate_config(config_value):
    """Validate config using helper from config module."""
    result = config_module.is_valid_config(config_value)
    return result

def count_items(items):
    """Count items with a threshold."""
    count = len(items)
    return count >= 1

def process_item(item):
    """Process an item using config module."""
    if validate_config(item):
        return "valid: " + str(item)
    return "invalid"
'''

    # A sibling module that target imports
    SIBLING_CONFIG_SOURCE = '''
def is_valid_config(val):
    """Check if a config value is valid."""
    return val is not None and len(str(val)) > 0
'''

    # Test for the sibling target
    SIBLING_TARGET_TEST_SOURCE = '''
import unittest
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

import fixture_sibling_target as target

class TestSiblingTarget(unittest.TestCase):
    """Tests for module with sibling imports."""

    def test_validate_config_with_valid_value(self):
        """validate_config returns True for valid values."""
        self.assertTrue(target.validate_config("test"))
        self.assertTrue(target.validate_config(42))

    def test_validate_config_with_invalid_value(self):
        """validate_config returns False for None."""
        self.assertFalse(target.validate_config(None))
        self.assertFalse(target.validate_config(""))

    def test_process_item_valid(self):
        """process_item returns valid: prefix for valid items."""
        result = target.process_item("hello")
        self.assertTrue(result.startswith("valid:"))

    def test_process_item_invalid(self):
        """process_item returns invalid for None."""
        result = target.process_item(None)
        self.assertEqual(result, "invalid")

if __name__ == "__main__":
    unittest.main()
'''

    def test_sibling_imports_baseline_valid(self):
        """Baseline test should pass for module with sibling imports (real package layout)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create separate directories to simulate real layout: ui/ and tests/
            ui_dir = tmpdir / "ui"
            tests_dir = tmpdir / "tests"
            ui_dir.mkdir()
            tests_dir.mkdir()

            # Write fixture files in separate directories
            target_file = ui_dir / "fixture_sibling_target.py"
            sibling_file = ui_dir / "fixture_sibling_config.py"
            test_file = tests_dir / "test_fixture_sibling.py"

            target_file.write_text(self.SIBLING_TARGET_SOURCE, encoding="utf-8")
            sibling_file.write_text(self.SIBLING_CONFIG_SOURCE, encoding="utf-8")
            test_file.write_text(self.SIBLING_TARGET_TEST_SOURCE, encoding="utf-8")

            # Run mutation test — sandbox must provide sibling imports from ui/
            result = mutation_test.run(str(target_file), str(test_file))

            # Should NOT have an error (baseline should pass with siblings available)
            if "error" in result:
                # Debug output on failure
                self.fail(f"Sandbox failed: {result['error']}\n"
                         f"Target file: {target_file}\n"
                         f"Test file: {test_file}\n"
                         f"Sibling file exists: {sibling_file.exists()}")

            # Should have some mutations tested (at least baseline didn't fail)
            # Note: count_items() is not tested, so mutations in it survive
            total = result["killed"] + result["survived"]
            self.assertGreater(
                total,
                0,
                "Expected mutations to be tested with sibling imports available"
            )

    def test_sibling_imports_survives_uncovered_mutations(self):
        """With sibling imports available, uncovered mutations should survive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create separate directories to simulate real layout: ui/ and tests/
            ui_dir = tmpdir / "ui"
            tests_dir = tmpdir / "tests"
            ui_dir.mkdir()
            tests_dir.mkdir()

            target_file = ui_dir / "fixture_sibling_target.py"
            sibling_file = ui_dir / "fixture_sibling_config.py"
            test_file = tests_dir / "test_fixture_sibling.py"

            target_file.write_text(self.SIBLING_TARGET_SOURCE, encoding="utf-8")
            sibling_file.write_text(self.SIBLING_CONFIG_SOURCE, encoding="utf-8")
            test_file.write_text(self.SIBLING_TARGET_TEST_SOURCE, encoding="utf-8")

            result = mutation_test.run(str(target_file), str(test_file))

            # The count_items function has mutations but isn't tested, so they survive
            self.assertGreater(
                result["survived"],
                0,
                "Expected uncovered mutations to survive with sibling imports working"
            )


if __name__ == "__main__":
    unittest.main()
