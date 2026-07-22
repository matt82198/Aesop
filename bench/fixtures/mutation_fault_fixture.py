#!/usr/bin/env python3
"""
Mutation testing validation fixture — correct code with weak test coverage.

This module contains correct implementations. Tests are deliberately incomplete
to measure mutation tool accuracy: covered code should kill mutations, uncovered
code allows mutations to survive.

Functions:
  - normalize_score: multiply by 10 (WELL TESTED)
  - check_threshold: compare with < (MODERATELY TESTED)
  - is_positive: check x > 0 (NOT TESTED)
  - count_items: return len() (NOT TESTED)
  - validate_key: check key in dict (NOT TESTED)

Expected: ~6-8 mutations killed (in tested code),
          ~12-16 survived (in untested code)
"""


def normalize_score(score):
    """Normalize a score from 0-10 to 0-100."""
    return score * 10


def check_threshold(value, threshold):
    """Check if value is strictly less than threshold."""
    return value < threshold


def is_positive(x):
    """Check if x is positive (> 0).

    NOT TESTED — mutations will survive.
    """
    return x > 0


def count_items(items):
    """Count the number of items in a list.

    NOT TESTED — mutations will survive.
    """
    return len(items)


def validate_key(data_dict, key):
    """Check if required key exists in dictionary.

    NOT TESTED — mutations will survive.
    """
    return key in data_dict
