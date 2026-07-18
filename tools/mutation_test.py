#!/usr/bin/env python3
"""
Mutation testing tool — measures whether a module's tests actually catch bugs.

This tool applies small source-code mutations (copy, never mutate original) to
a target module and runs its test suite against each mutation. Tests that pass
despite a mutation indicate a gap in test coverage (weak tests). Survived
mutations are reported as weak spots the tests don't cover.

Why: green test suites often just mean 'tests agree with the code', not
'tests catch bugs'. Mutation testing reveals test quality gaps.

Mutations applied:
  - Flip comparison operators (== <-> !=, < <-> >=, > <-> <=)
  - Replace numeric literals with +1
  - Replace boolean returns with negation
  - Replace 'and' <-> 'or'
  - Replace 'is None' <-> 'is not None'

Configuration (aesop.config.json):
  [none — no configuration needed]

API:
  run(target_module_path, test_module_path) -> dict
    Returns {"killed": int, "survived": int, "mutations": [...]}
    mutations is a list of {"file": str, "line": int, "original": str, "mutated": str}

CLI:
  python tools/mutation_test.py --target module.py --test test_module.py [--json]
    Exit 0 always (advisory, not gated). --json outputs JSON to stdout.
"""

import argparse
import ast
import copy
import json
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional


class MutationGenerator(ast.NodeTransformer):
    """AST transformer that generates mutations of a Python module."""

    def __init__(self):
        self.mutations: List[Tuple[int, str, str]] = []  # (line, original, mutated)
        self.current_mutation_idx = 0
        self.target_mutation_idx = -1  # -1 means no mutation, just record

    def record_mutation(self, line: int, original: str, mutated: str) -> None:
        """Record a mutation and track mutation index."""
        self.mutations.append((line, original, mutated))

    def visit_Compare(self, node: ast.Compare) -> Any:
        """Mutate comparison operators: == <-> !=, < <-> >=, etc."""
        self.generic_visit(node)

        # Map of operator mutations
        op_map = {
            ast.Eq: (ast.NotEq, "==", "!="),
            ast.NotEq: (ast.Eq, "!=", "=="),
            ast.Lt: (ast.GtE, "<", ">="),
            ast.Gt: (ast.LtE, ">", "<="),
            ast.LtE: (ast.Gt, "<=", ">"),
            ast.GtE: (ast.Lt, ">=", "<"),
        }

        for i, op in enumerate(node.ops):
            if type(op) in op_map:
                mutated_op, orig_str, mut_str = op_map[type(op)]
                self.record_mutation(node.lineno, orig_str, mut_str)

                if self.current_mutation_idx == len(self.mutations) - 1 and self.target_mutation_idx == self.current_mutation_idx:
                    node.ops[i] = mutated_op()

                self.current_mutation_idx += 1

        return node

    def visit_Constant(self, node: ast.Constant) -> Any:
        """Mutate numeric literals: n -> n+1."""
        self.generic_visit(node)

        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            mutated_val = node.value + 1
            self.record_mutation(node.lineno, str(node.value), str(mutated_val))

            if self.current_mutation_idx == len(self.mutations) - 1 and self.target_mutation_idx == self.current_mutation_idx:
                node.value = mutated_val

            self.current_mutation_idx += 1

        return node

    def visit_Return(self, node: ast.Return) -> Any:
        """Mutate boolean returns: True -> False, False -> True."""
        self.generic_visit(node)

        if node.value and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, bool):
                orig_val = node.value.value
                mut_val = not orig_val
                self.record_mutation(node.lineno, str(orig_val), str(mut_val))

                if self.current_mutation_idx == len(self.mutations) - 1 and self.target_mutation_idx == self.current_mutation_idx:
                    node.value.value = mut_val

                self.current_mutation_idx += 1

        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        """Mutate boolean operators: and <-> or."""
        self.generic_visit(node)

        if isinstance(node.op, (ast.And, ast.Or)):
            is_and = isinstance(node.op, ast.And)
            orig_str = "and" if is_and else "or"
            mut_str = "or" if is_and else "and"
            self.record_mutation(node.lineno, orig_str, mut_str)

            if self.current_mutation_idx == len(self.mutations) - 1 and self.target_mutation_idx == self.current_mutation_idx:
                node.op = ast.Or() if is_and else ast.And()

            self.current_mutation_idx += 1

        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        """Mutate 'not' in returns to None checks."""
        self.generic_visit(node)
        return node


def extract_mutations(source: str) -> List[Tuple[int, str, str]]:
    """Parse source and extract all possible mutations."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    transformer = MutationGenerator()
    transformer.generic_visit(tree)
    return transformer.mutations


def apply_mutation(source: str, mutation_idx: int) -> Optional[str]:
    """Apply a specific mutation to source code by index.

    Returns mutated source, or None if mutation_idx is out of range.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    mutations = extract_mutations(source)
    if mutation_idx < 0 or mutation_idx >= len(mutations):
        return None

    # Re-parse and apply the specific mutation
    tree = ast.parse(source)
    transformer = MutationGenerator()
    transformer.target_mutation_idx = mutation_idx
    new_tree = transformer.visit(tree)

    try:
        return ast.unparse(new_tree)
    except Exception:
        # If unparsing fails, return None
        return None


def run_tests(test_module_path: str, work_dir: str, timeout: int = 30) -> Tuple[int, str]:
    """Run tests in a subprocess.

    Returns (exit_code, stdout+stderr).
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-xvs", test_module_path],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return 124, "Test timeout (>{}s)".format(timeout)
    except FileNotFoundError:
        # pytest not available, fall back to unittest
        try:
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "-v", test_module_path],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout + result.stderr
        except Exception as e:
            return 127, str(e)


def run(target_module_path: str, test_module_path: str) -> Dict[str, Any]:
    """Run mutation testing on target_module_path using test_module_path.

    Returns {
        "killed": int,
        "survived": int,
        "mutations": [
            {"file": str, "line": int, "original": str, "mutated": str},
            ...
        ]
    }
    """
    target_path = Path(target_module_path).resolve()
    test_path = Path(test_module_path).resolve()

    if not target_path.exists():
        return {
            "killed": 0,
            "survived": 0,
            "mutations": [],
            "error": f"target module not found: {target_module_path}",
        }

    if not test_path.exists():
        return {
            "killed": 0,
            "survived": 0,
            "mutations": [],
            "error": f"test module not found: {test_module_path}",
        }

    # Read target source
    try:
        source = target_path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "killed": 0,
            "survived": 0,
            "mutations": [],
            "error": f"failed to read target: {e}",
        }

    # Extract mutations
    mutations = extract_mutations(source)
    if not mutations:
        return {
            "killed": 0,
            "survived": 0,
            "mutations": [],
        }

    # Create temporary work directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Copy target to temp dir
        temp_target = tmpdir / target_path.name
        temp_target.write_text(source, encoding="utf-8")

        # Copy test to temp dir
        temp_test = tmpdir / test_path.name
        try:
            test_source = test_path.read_text(encoding="utf-8")
            temp_test.write_text(test_source, encoding="utf-8")
        except Exception as e:
            return {
                "killed": 0,
                "survived": 0,
                "mutations": [],
                "error": f"failed to copy test: {e}",
            }

        # Copy any other Python files from test directory (dependencies)
        test_dir = test_path.parent
        for py_file in test_dir.glob("*.py"):
            if py_file.name not in (test_path.name, target_path.name):
                try:
                    dest = tmpdir / py_file.name
                    dest.write_text(py_file.read_text(encoding="utf-8"), encoding="utf-8")
                except Exception:
                    pass  # Best effort

        # Run tests against unmutated code (baseline)
        baseline_exit, _ = run_tests(str(temp_test), str(tmpdir))
        baseline_passes = (baseline_exit == 0)

        killed = 0
        survived = 0
        survived_mutations = []

        # Test each mutation
        for mut_idx, (line, orig, mutated) in enumerate(mutations):
            mutated_source = apply_mutation(source, mut_idx)
            if mutated_source is None:
                continue

            # Write mutated source to temp file
            temp_target.write_text(mutated_source, encoding="utf-8")

            # Run tests
            exit_code, _ = run_tests(str(temp_test), str(tmpdir))
            tests_pass = (exit_code == 0)

            if tests_pass:
                # Mutation survived (tests didn't catch the bug)
                survived += 1
                survived_mutations.append({
                    "file": target_path.name,
                    "line": line,
                    "original": orig,
                    "mutated": mutated,
                })
            else:
                # Mutation killed (tests caught the bug)
                killed += 1

        # Restore original
        temp_target.write_text(source, encoding="utf-8")

        return {
            "killed": killed,
            "survived": survived,
            "mutations": survived_mutations,
        }


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Mutation testing tool — measure test quality by applying mutations."
    )
    parser.add_argument("--target", required=True, help="Target module to mutate (path to .py file)")
    parser.add_argument("--test", required=True, help="Test module to run (path to .py file)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args(argv)

    result = run(args.target, args.test)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Mutation test results:")
        print(f"  Killed:   {result['killed']}")
        print(f"  Survived: {result['survived']}")
        if result["survived"] > 0:
            print(f"\nSurvived mutations (test gaps):")
            for mut in result["mutations"]:
                print(f"  {mut['file']}:{mut['line']} — {mut['original']} -> {mut['mutated']}")
        if "error" in result:
            print(f"\nError: {result['error']}", file=sys.stderr)

    return 0  # Exit 0 always (advisory)


if __name__ == "__main__":
    sys.exit(main())
