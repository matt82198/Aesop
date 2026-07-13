"""Lightweight, no-browser unit test for sanitizeURL(), the URL-scheme allowlist
used by buildTrackerItem() in ui/templates/dashboard.html to neutralize
javascript:/data:/vbscript: URIs supplied via a tracker item's pr_link before
they are ever placed into an <a href="..."> (wave-10 P0 stored-XSS fix).

This test extracts the sanitizeURL() function VERBATIM out of the template
(regex) and executes it under Node, so it can never drift from the logic that
actually ships — there is no reimplementation to fall out of sync.

This is a fast sanity check, not the authoritative proof. The authoritative,
end-to-end proof is tools/verify_dash.py assertion (m), which drives a real
headless browser, calls the real buildTrackerItem() with a malicious pr_link,
and asserts the resulting DOM contains no executable href. Run that for the
real guarantee; run this for a quick, browser-free regression signal.

Run: python tests/test_pr_link_xss.py
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DASHBOARD = REPO / "ui" / "templates" / "dashboard.html"


def _extract_sanitize_url() -> str:
    html = DASHBOARD.read_text(encoding="utf-8")
    m = re.search(r"        function sanitizeURL\(url\) \{.*?\n        \}", html, re.DOTALL)
    if not m:
        raise AssertionError(
            "sanitizeURL() not found in ui/templates/dashboard.html at the "
            "expected indentation — has it been renamed, moved, or removed?"
        )
    return m.group(0)


def _run_cases(cases):
    """Runs sanitizeURL(url) under Node for each case, returns the list of results."""
    fn_src = _extract_sanitize_url()
    script = (
        "const location = { href: 'http://localhost:8000/' };\n"
        + fn_src
        + "\nconst cases = " + json.dumps(cases) + ";\n"
        "process.stdout.write(JSON.stringify(cases.map(c => sanitizeURL(c))));\n"
    )
    proc = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    if proc.returncode != 0:
        raise AssertionError(f"node execution of extracted sanitizeURL() failed: {proc.stderr}")
    return json.loads(proc.stdout)


@unittest.skipUnless(shutil.which("node"), "node not available on PATH")
class SanitizeURLTest(unittest.TestCase):
    def test_blocks_javascript_scheme(self):
        self.assertEqual(_run_cases(["javascript:alert(1)"]), [""])

    def test_blocks_data_scheme(self):
        self.assertEqual(
            _run_cases(["data:text/html,<script>alert(1)</script>"]), [""]
        )

    def test_blocks_vbscript_scheme(self):
        self.assertEqual(_run_cases(["vbscript:msgbox(1)"]), [""])

    def test_blocks_empty_and_falsy(self):
        self.assertEqual(_run_cases(["", None]), ["", ""])

    def test_allows_https(self):
        url = "https://github.com/org/repo/pull/1"
        self.assertEqual(_run_cases([url]), [url])

    def test_allows_http(self):
        url = "http://example.com/pr/2"
        self.assertEqual(_run_cases([url]), [url])

    def test_allows_relative_path_against_http_base(self):
        # Resolves to http: against the mocked location.href, so it passes
        # through unchanged (sanitizeURL returns the original string, not the
        # resolved absolute URL).
        url = "/org/repo/pull/3"
        self.assertEqual(_run_cases([url]), [url])


if __name__ == "__main__":
    unittest.main()
