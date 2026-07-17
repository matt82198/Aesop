"""
Test hygiene enforcement: permanent isolation rules in code.

Scans tests/test_*.py files via AST and fails if:
1. A test uses bare os.chdir() not wrapped in try/finally and not paired
   with tearDown restoration (flags the pattern, recommends subprocess cwd= instead)
2. A test calls git config user.* without being scoped to a temp repo
   (git config user.* should only appear inside temp fixture setup, not in live tests)

These rules prevent wave-25 regressions:
- Bare os.chdir leak: if a temp dir is deleted and tests don't restore cwd,
  later tests inherit a poisoned cwd and Windows cleanup deadlocks.
  Accepted pattern: os.chdir in setUp with cwd restoration in tearDown.
  Preferred pattern: subprocess(..., cwd=...) instead.
- git config user mutation: tests should not mutate the global git identity;
  scope identity changes to temp repos only
"""

import ast
import os
import sys
import unittest
from pathlib import Path


class CallVisitor(ast.NodeVisitor):
    """Collect all function calls and class/function structure in the AST."""

    def __init__(self):
        self.calls = []
        self.current_function = None
        self.current_class = None
        self.in_try_block = False

    def visit_ClassDef(self, node):
        """Enter a class definition."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node):
        """Enter a function definition."""
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    def visit_AsyncFunctionDef(self, node):
        """Enter an async function definition."""
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    def visit_Try(self, node):
        """Track when we're inside a try block."""
        old_try = self.in_try_block
        self.in_try_block = True
        self.generic_visit(node)
        self.in_try_block = old_try

    def visit_Call(self, node):
        """Collect function calls."""
        self.calls.append({
            'node': node,
            'lineno': node.lineno,
            'function': self._call_name(node),
            'in_try': self.in_try_block,
            'in_function': self.current_function,
            'in_class': self.current_class,
        })
        self.generic_visit(node)

    @staticmethod
    def _call_name(node):
        """Extract function name from a Call node."""
        if isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return '.'.join(reversed(parts))
        elif isinstance(node.func, ast.Name):
            return node.func.id
        return None


def _class_has_teardown_restoring_cwd(tree, class_name):
    """Check if a class or its base classes have a tearDown method that calls os.chdir."""
    # First, find all classes in the tree
    all_classes = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            all_classes[node.name] = node

    # Now check the class and its bases
    def has_teardown_in_class_or_bases(name):
        if name not in all_classes:
            return False
        cls = all_classes[name]

        # Check this class's tearDown
        for item in cls.body:
            if isinstance(item, ast.FunctionDef) and item.name == 'tearDown':
                # Check if tearDown has os.chdir call
                visitor = CallVisitor()
                visitor.visit(item)
                for call in visitor.calls:
                    if call['function'] == 'os.chdir':
                        return True

        # Check base classes (inheritance)
        for base in cls.bases:
            if isinstance(base, ast.Name):
                if has_teardown_in_class_or_bases(base.id):
                    return True

        return False

    return has_teardown_in_class_or_bases(class_name)


class TestTestHygiene(unittest.TestCase):
    """Enforce permanent isolation rules in test code."""

    def test_no_bare_os_chdir_without_restoration(self):
        """Fail if any test uses os.chdir() in a try/finally restoration pattern.

        The wave-25 cwd-leak pattern: os.chdir into temp dir, then don't restore.
        This breaks all subsequent tests (cwd points to deleted temp dir).

        Allowed patterns:
        1. os.chdir in setUp, with class-level tearDown that restores os.chdir
        2. os.chdir in try/finally with restoration in finally
        3. Use subprocess(..., cwd=...) instead of os.chdir (preferred)

        Flag: os.chdir in test_* methods that:
        - Are NOT in try/finally blocks, AND
        - Are in a class WITHOUT a tearDown that calls os.chdir
        """
        tests_dir = Path(__file__).parent
        violations = []

        for test_file in sorted(tests_dir.glob("test_*.py")):
            if test_file.name == "test_test_hygiene.py":
                continue

            try:
                with open(test_file, "r", encoding="utf-8") as f:
                    source = f.read()
                    tree = ast.parse(source, filename=str(test_file))
            except SyntaxError as e:
                self.fail(f"Syntax error in {test_file}: {e}")

            visitor = CallVisitor()
            visitor.visit(tree)

            # Find os.chdir calls
            for call_info in visitor.calls:
                if call_info['function'] == 'os.chdir':
                    lineno = call_info['lineno']
                    func_name = call_info['in_function']
                    class_name = call_info['in_class']

                    # Allow os.chdir in setUp/tearDown (they manage restoration)
                    if func_name and (func_name.startswith('setUp') or func_name.startswith('tearDown')):
                        continue

                    # Allow os.chdir inside try/finally blocks (explicit restoration)
                    if call_info['in_try']:
                        continue

                    # Flag: bare os.chdir in test method without restoration
                    if func_name and func_name.startswith('test_'):
                        # Check if the class has a tearDown that calls os.chdir
                        if class_name and _class_has_teardown_restoring_cwd(tree, class_name):
                            # OK: class has tearDown restoration
                            continue

                        # Violation: test method calls os.chdir without restoration
                        violations.append(
                            f"{test_file.name}:{lineno} in {func_name}(): "
                            f"bare os.chdir() without restoration. "
                            f"Recommend using subprocess(..., cwd=...) instead, "
                            f"or wrap in try/finally with os.chdir(_saved_cwd) in finally."
                        )

        if violations:
            msg = "Found os.chdir() violations (wave-25 cwd-leak pattern):\n"
            msg += "\n".join(f"  {v}" for v in violations)
            self.fail(msg)

    def test_no_git_config_user_outside_temp_repos(self):
        """Fail if any test calls git config user.* on the live repo (not temp)."""
        tests_dir = Path(__file__).parent
        violations = []

        for test_file in sorted(tests_dir.glob("test_*.py")):
            if test_file.name == "test_test_hygiene.py":
                continue

            try:
                with open(test_file, "r", encoding="utf-8") as f:
                    source = f.read()
                    tree = ast.parse(source, filename=str(test_file))
            except SyntaxError as e:
                self.fail(f"Syntax error in {test_file}: {e}")

            # Look for subprocess.run(..., ["git", "config", "user.*, ...], cwd=...)
            # or subprocess.run(..., ["git", "config", "user.*", ...], cwd=...)
            # These should ONLY appear with cwd= pointing to a temp repo, not the live repo.
            # The test file should have a fixture setup that creates temp dirs.

            # Pattern: subprocess.run([..., "git", "config", "user.email"/"user.name", ...], cwd=str(repo))
            # where repo is a temp path (tempfile.TemporaryDirectory, Path(tempfile.mkdtemp()), etc.)

            # For now, we do a simple grep pattern: flag any line with git config user
            # that's NOT inside a temp fixture setup helper.
            # This is a heuristic: we look for _init_repo, make_commit, setUp patterns.

            lines = source.split('\n')
            for i, line in enumerate(lines, start=1):
                if 'git' in line and 'config' in line and ('user.email' in line or 'user.name' in line):
                    # Check if this line is inside a setup/fixture method
                    # Simple heuristic: grep backwards for def setUp, def _init_repo, etc.
                    is_in_fixture = False
                    for j in range(i - 1, max(0, i - 20), -1):
                        context_line = lines[j - 1]
                        if ('def setUp' in context_line or
                            'def _' in context_line or  # helper methods start with _
                            'def make_' in context_line or
                            'def fixture_' in context_line or
                            'tempfile' in context_line or
                            'mktemp' in context_line):
                            is_in_fixture = True
                            break

                    if not is_in_fixture:
                        violations.append(
                            f"{test_file.name}:{i} "
                            f"git config user.* call outside temp fixture scope. "
                            f"Git identity mutations must be scoped to temp repos only; "
                            f"define setup in _init_repo() or setUp() method with temp cwd."
                        )

        if violations:
            msg = "Found git config user.* violations (identity mutation outside temp repos):\n"
            msg += "\n".join(f"  {v}" for v in violations)
            self.fail(msg)


if __name__ == "__main__":
    unittest.main()
