"""
Test suite for ci_workflow_lint.py

Tests verify that the linter correctly detects:
  1. npm ci steps without package-lock.json (the exact bug from wave-rc5)
  2. Test scripts defined in package.json but not invoked by workflows
  3. YAML parse errors
  4. File reference issues (best-effort)

Fixture-root isolated tests using tempfile to avoid pollution.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ci_workflow_lint


class CIWorkflowLintTest(unittest.TestCase):
    """Test ci_workflow_lint functionality."""

    def setUp(self):
        """Create isolated fixture root with .github/workflows directory."""
        self.fixture_root = Path(tempfile.mkdtemp(prefix="ci-lint-test-"))
        self.workflows_dir = self.fixture_root / ".github" / "workflows"
        self.workflows_dir.mkdir(parents=True)

    def tearDown(self):
        """Clean up fixture root."""
        if self.fixture_root.exists():
            shutil.rmtree(self.fixture_root)

    def _write_workflow(self, filename, content):
        """Write a workflow file to the fixtures directory."""
        workflow_path = self.workflows_dir / filename
        workflow_path.write_text(content, encoding='utf-8')
        return workflow_path

    def _write_package_json(self, subdir, data):
        """Write a package.json file to a subdirectory."""
        pkg_dir = self.fixture_root / subdir
        pkg_dir.mkdir(parents=True, exist_ok=True)
        pkg_file = pkg_dir / "package.json"
        pkg_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
        return pkg_file

    def _write_package_lock(self, subdir):
        """Write an empty package-lock.json file."""
        pkg_dir = self.fixture_root / subdir
        pkg_dir.mkdir(parents=True, exist_ok=True)
        lock_file = pkg_dir / "package-lock.json"
        lock_file.write_text("{}\n", encoding='utf-8')
        return lock_file

    def test_npm_ci_without_lockfile_bug(self):
        """
        Reproduce the exact bug from wave-rc5: npm ci without package-lock.json.

        A workflow step runs "npm ci" at the repo root, but there's no
        package-lock.json at the root. This should be caught as a finding.
        """
        # Write the root package.json
        self._write_package_json(".", {"name": "test", "scripts": {}})

        # Write a workflow with npm ci but no package-lock.json at root
        workflow_content = """
name: CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Install dependencies
        run: npm ci
"""
        self._write_workflow("ci.yml", workflow_content)

        # Run linter
        exit_code, findings = ci_workflow_lint.lint_workflows(str(self.fixture_root))

        # Should find the issue
        self.assertEqual(exit_code, 1)
        self.assertTrue(any("npm ci" in f for f in findings),
                       f"Expected npm ci finding, got: {findings}")
        self.assertTrue(any("package-lock.json" in f for f in findings),
                       f"Expected package-lock.json finding, got: {findings}")

    def test_npm_ci_with_lockfile_passes(self):
        """
        npm ci with package-lock.json present should pass.
        """
        # Write root package.json and package-lock.json
        self._write_package_json(".", {"name": "test", "scripts": {}})
        self._write_package_lock(".")

        # Write workflow with npm ci
        workflow_content = """
name: CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Install
        run: npm ci
"""
        self._write_workflow("ci.yml", workflow_content)

        # Run linter
        exit_code, findings = ci_workflow_lint.lint_workflows(str(self.fixture_root))

        # Should pass (no npm ci findings)
        npm_ci_findings = [f for f in findings if "npm ci" in f and "package-lock" in f]
        self.assertFalse(npm_ci_findings, f"Should not find npm ci issues, got: {npm_ci_findings}")

    def test_npm_ci_with_working_directory(self):
        """
        npm ci with working-directory should check lockfile in that directory.
        """
        # Write root package.json (no lockfile)
        self._write_package_json(".", {"name": "root", "scripts": {}})

        # Write ui/web package.json and lockfile
        self._write_package_json("ui/web", {"name": "ui", "scripts": {}})
        self._write_package_lock("ui/web")

        # Write workflow with working-directory
        workflow_content = """
name: CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Build UI
        working-directory: ui/web
        run: npm ci
"""
        self._write_workflow("ci.yml", workflow_content)

        # Run linter
        exit_code, findings = ci_workflow_lint.lint_workflows(str(self.fixture_root))

        # Should pass because package-lock.json exists in ui/web
        npm_ci_findings = [f for f in findings if "npm ci" in f and "package-lock" in f]
        self.assertFalse(npm_ci_findings, f"Should not find npm ci issues, got: {npm_ci_findings}")

    def test_npm_ci_with_cd_in_run(self):
        """
        npm ci after cd should check lockfile in the cd directory.
        """
        # Write root and ui/web
        self._write_package_json(".", {"name": "root", "scripts": {}})
        self._write_package_json("ui/web", {"name": "ui", "scripts": {}})
        self._write_package_lock("ui/web")

        # Write workflow with cd in run
        workflow_content = """
name: CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Build UI
        run: |
          cd ui/web
          npm ci
"""
        self._write_workflow("ci.yml", workflow_content)

        # Run linter
        exit_code, findings = ci_workflow_lint.lint_workflows(str(self.fixture_root))

        # Should pass because package-lock.json exists in ui/web
        npm_ci_findings = [f for f in findings if "npm ci" in f and "package-lock" in f]
        self.assertFalse(npm_ci_findings, f"Should not find npm ci issues, got: {npm_ci_findings}")

    def test_test_script_not_invoked(self):
        """
        Test scripts in package.json but not run by workflows should be flagged.
        """
        # Write package.json with test:py
        self._write_package_json(".", {
            "name": "test",
            "scripts": {
                "test:py": "python -m unittest",
                "test:node": "node --test"
            }
        })

        # Write workflow that only runs test:node
        workflow_content = """
name: CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Run Node tests
        run: npm run test:node
"""
        self._write_workflow("ci.yml", workflow_content)

        # Run linter
        exit_code, findings = ci_workflow_lint.lint_workflows(str(self.fixture_root))

        # Should find that test:py is not invoked
        self.assertEqual(exit_code, 1)
        self.assertTrue(any("test:py" in f and "not invoked" in f for f in findings),
                       f"Expected test:py not invoked, got: {findings}")

    def test_all_test_scripts_invoked(self):
        """
        When all test scripts are invoked, linter should pass (for that check).
        """
        # Write package.json with test scripts
        self._write_package_json(".", {
            "name": "test",
            "scripts": {
                "test:py": "python -m unittest",
                "test:node": "node --test",
                "test:sh": "bash tests/test.sh"
            }
        })

        # Write workflow that runs all three
        workflow_content = """
name: CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Run Python tests
        run: python -m unittest discover

      - name: Run Node tests
        run: npm run test:node

      - name: Run Shell tests
        run: bash tests/test.sh
"""
        self._write_workflow("ci.yml", workflow_content)

        # Run linter
        exit_code, findings = ci_workflow_lint.lint_workflows(str(self.fixture_root))

        # No test coverage findings expected
        test_coverage_findings = [f for f in findings if "not invoked" in f]
        self.assertFalse(test_coverage_findings,
                        f"Should not find test coverage issues, got: {test_coverage_findings}")

    def test_yaml_parse_error(self):
        """
        Invalid YAML should be caught.
        """
        # Write invalid YAML (unmatched bracket in mapping)
        workflow_content = """
name: CI
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Invalid YAML
        run: echo "hello"
        invalid: [unclosed bracket
"""
        self._write_workflow("ci.yml", workflow_content)

        # Run linter
        exit_code, findings = ci_workflow_lint.lint_workflows(str(self.fixture_root))

        # Should find parse error
        self.assertEqual(exit_code, 1)
        self.assertTrue(any("parse" in f.lower() or "YAML" in f for f in findings),
                       f"Expected YAML parse error, got: {findings}")

    def test_json_output(self):
        """
        JSON output format should include exit_code and findings.
        """
        # Write a simple workflow with an issue
        self._write_package_json(".", {
            "name": "test",
            "scripts": {"test:py": "python -m unittest"}
        })

        workflow_content = """
name: CI
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: No tests run
        run: echo "hello"
"""
        self._write_workflow("ci.yml", workflow_content)

        # Run linter with JSON output
        exit_code, findings = ci_workflow_lint.lint_workflows(str(self.fixture_root), json_output=True)

        # Check that findings are returned as strings (they're already formatted)
        self.assertEqual(exit_code, 1)
        self.assertTrue(len(findings) > 0)
        self.assertTrue(all(isinstance(f, str) for f in findings))

    def test_no_workflows_found(self):
        """
        If no workflows exist, should report this.
        """
        # Remove the workflows directory we created
        shutil.rmtree(self.workflows_dir.parent)

        # Run linter
        exit_code, findings = ci_workflow_lint.lint_workflows(str(self.fixture_root))

        # Should report no workflows
        self.assertEqual(exit_code, 1)
        self.assertTrue(any("No workflow files found" in f for f in findings))

    def test_no_package_json_no_error(self):
        """
        If no package.json exists, linter should still work (just check YAML).
        """
        # Write a valid workflow with no package.json
        workflow_content = """
name: CI
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v7
"""
        self._write_workflow("ci.yml", workflow_content)

        # Run linter
        exit_code, findings = ci_workflow_lint.lint_workflows(str(self.fixture_root))

        # Should not crash, might have other findings but not about package.json
        # The only finding might be about test coverage
        self.assertIsInstance(exit_code, int)
        self.assertIsInstance(findings, list)


class TestToolsImportable(unittest.TestCase):
    """Verify ci_workflow_lint is importable and callable."""

    def test_import_ci_workflow_lint(self):
        """ci_workflow_lint module should import without error."""
        # Already imported at module level above
        self.assertTrue(hasattr(ci_workflow_lint, 'lint_workflows'))
        self.assertTrue(callable(ci_workflow_lint.lint_workflows))

    def test_main_function_exists(self):
        """main function should exist."""
        self.assertTrue(hasattr(ci_workflow_lint, 'main'))
        self.assertTrue(callable(ci_workflow_lint.main))


if __name__ == "__main__":
    unittest.main()
