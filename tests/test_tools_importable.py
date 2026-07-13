"""Import/compile/UTF-8 smoke gate for every tools/*.py (wave-10 P1).

Regression: orchestrator_status.py once shipped with a stray cp1252 byte that
made it a SyntaxError on EVERY run. Nothing in CI imported it, so it slipped
through untested for a full wave. This suite is the cheap, generic floor that
would have caught it: every file under tools/ must (1) decode as UTF-8,
(2) py_compile cleanly, and (3) import without error in a subprocess (so a
broken tool can't poison the test process itself, and so any __main__ guard
is never triggered — we only import the module, we never run it).

stdlib-only, no network, no fixtures. Test methods are generated dynamically
per tool file so a failure names the exact tool in the test ID/CI log.
"""
import py_compile
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO / "tools"

_IMPORT_SNIPPET = (
    "import importlib.util, sys\n"
    "path = sys.argv[1]\n"
    "spec = importlib.util.spec_from_file_location('tool_under_test', path)\n"
    "mod = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(mod)\n"
)


def _tool_files():
    return sorted(TOOLS_DIR.glob("*.py"))


def _safe_name(path):
    return path.stem.replace("-", "_")


class TestToolsImportable(unittest.TestCase):
    """Base class; per-tool test methods are attached below."""

    def test_tools_dir_has_python_files(self):
        # Guards against silent no-op coverage if tools/ is ever emptied
        # or renamed — an empty discovery would make every generated
        # test vanish and this suite would pass while checking nothing.
        files = _tool_files()
        self.assertGreater(
            len(files), 0,
            "no tools/*.py files discovered — check TOOLS_DIR / glob pattern"
        )


def _make_utf8_test(path):
    def test(self):
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            self.fail(
                f"{path.relative_to(REPO)} is not valid UTF-8 "
                f"(byte {exc.start}: {exc.reason}) — this is the exact "
                f"class of bug (cp1252 byte) that shipped a broken tool"
            )
    return test


def _make_compile_test(path):
    def test(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfile = str(Path(tmp) / (path.stem + ".pyc"))
            try:
                py_compile.compile(str(path), cfile=cfile, doraise=True)
            except py_compile.PyCompileError as exc:
                self.fail(f"{path.relative_to(REPO)} failed py_compile: {exc}")
    return test


def _make_import_test(path):
    def test(self):
        # Run in a subprocess: a bad tool (crash, sys.exit, infinite loop
        # guarded incorrectly) must not take down the test process. The
        # module is loaded under a synthetic name so any `if __name__ ==
        # "__main__":` block is never executed — this only exercises import.
        result = subprocess.run(
            [sys.executable, "-c", _IMPORT_SNIPPET, str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode, 0,
            f"{path.relative_to(REPO)} failed to import cleanly "
            f"(exit {result.returncode}):\n{result.stderr}"
        )
    return test


for _path in _tool_files():
    _name = _safe_name(_path)
    setattr(TestToolsImportable, f"test_utf8_{_name}", _make_utf8_test(_path))
    setattr(TestToolsImportable, f"test_compiles_{_name}", _make_compile_test(_path))
    setattr(TestToolsImportable, f"test_imports_{_name}", _make_import_test(_path))


if __name__ == "__main__":
    unittest.main()
