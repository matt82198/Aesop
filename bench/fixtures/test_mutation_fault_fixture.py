#!/usr/bin/env python3
"""
Unit tests for mutation_fault_fixture.py — intentionally incomplete for validation.

This test suite deliberately covers SOME but not ALL functions in the fixture module.
This allows us to verify mutation_test.py's accuracy:

Expected results:
  - normalize_score: mutations KILLED (well tested)
  - check_threshold: mutations KILLED (well tested)
  - is_positive: mutations SURVIVE (not tested)
  - count_items: mutations SURVIVE (not tested)
  - validate_key: mutations SURVIVE (not tested)

Typical outcome: ~6-8 killed, ~12-16 survived
"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import mutation_fault_fixture as target


class TestNormalizeScore(unittest.TestCase):
    """Tests for normalize_score — well covered."""

    def test_normalize_zero(self):
        """normalize_score(0) should return 0."""
        self.assertEqual(target.normalize_score(0), 0)

    def test_normalize_five(self):
        """normalize_score(5) should return 50."""
        self.assertEqual(target.normalize_score(5), 50)

    def test_normalize_ten(self):
        """normalize_score(10) should return 100."""
        self.assertEqual(target.normalize_score(10), 100)

    def test_normalize_one(self):
        """normalize_score(1) should return 10."""
        self.assertEqual(target.normalize_score(1), 10)


class TestCheckThreshold(unittest.TestCase):
    """Tests for check_threshold — well covered."""

    def test_check_threshold_below(self):
        """check_threshold(5, 10) should return True (5 < 10)."""
        self.assertTrue(target.check_threshold(5, 10))

    def test_check_threshold_above(self):
        """check_threshold(15, 10) should return False (15 >= 10)."""
        self.assertFalse(target.check_threshold(15, 10))

    def test_check_threshold_equal(self):
        """check_threshold(10, 10) should return False (10 >= 10)."""
        self.assertFalse(target.check_threshold(10, 10))

    def test_check_threshold_zero(self):
        """check_threshold(0, 5) should return True (0 < 5)."""
        self.assertTrue(target.check_threshold(0, 5))


# NOTE: is_positive, count_items, and validate_key are NOT tested.
# This allows mutations in those functions to survive, demonstrating
# that the mutation tool correctly identifies gaps in test coverage.


if __name__ == "__main__":
    unittest.main()
