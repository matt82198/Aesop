"""
Guard test: Verify that all test_*.py files define test functions within unittest.TestCase classes.

This test scans all test files and fails if any module-level `def test_` functions
exist outside of a TestCase subclass — preventing the silent-skip bug where pytest-style
tests aren't collected by `python -m unittest discover`.
"""

import ast
import unittest
from pathlib import Path


class BareTestFunctionScanner(ast.NodeVisitor):
    """AST visitor to detect bare test functions (not in TestCase classes)."""

    def __init__(self, filename):
        self.filename = filename
        self.bare_tests = []
        self.in_test_class = False
        self.class_stack = []

    def visit_ClassDef(self, node):
        """Track when entering/exiting TestCase classes."""
        # Check if this class inherits from unittest.TestCase or similar
        # Handle both "TestCase" (Name) and "unittest.TestCase" (Attribute)
        is_test_class = any(
            (isinstance(base, ast.Name) and "TestCase" in base.id) or
            (isinstance(base, ast.Attribute) and base.attr == "TestCase")
            for base in node.bases
        )
        if is_test_class:
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()
        else:
            self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """Detect test functions."""
        if node.name.startswith("test_"):
            # Test function found — check if we're inside a TestCase
            if not self.class_stack:
                self.bare_tests.append((node.name, node.lineno))
        self.generic_visit(node)


class TestNoBareTestFunctions(unittest.TestCase):
    """Verify all test_*.py files follow unittest.TestCase structure."""

    def test_no_bare_test_functions_in_test_suite(self):
        """Scan all test files and fail if any have bare test functions."""
        test_dir = Path(__file__).parent
        test_files = sorted(test_dir.glob("test_*.py"))

        bare_function_reports = []

        for test_file in test_files:
            try:
                source = test_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(test_file))
                scanner = BareTestFunctionScanner(str(test_file))
                scanner.visit(tree)

                if scanner.bare_tests:
                    bare_function_reports.append((test_file.name, scanner.bare_tests))
            except SyntaxError as e:
                self.fail(f"Syntax error in {test_file}: {e}")

        # Report findings
        if bare_function_reports:
            error_msg = "Found bare test functions (not in TestCase):\n"
            for filename, functions in bare_function_reports:
                error_msg += f"\n  {filename}:\n"
                for func_name, lineno in functions:
                    error_msg += f"    line {lineno}: {func_name}\n"
            error_msg += "\nAll test functions must be defined as methods inside a unittest.TestCase subclass.\n"
            self.fail(error_msg)


if __name__ == "__main__":
    unittest.main()
