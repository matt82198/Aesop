#!/usr/bin/env python3
"""
Tests for secret_scan.py — security audit for pragma abuse and secret categories.

TDD tests for:
- ITEM 1: Pragma should only soften generic_secret_assignment and env_access,
  NOT fatal classes like pem_private_key, aws_access_key, etc.
- ITEM 2: (Covered by pre-push hook self-test "Test 6" in hooks/pre-push-policy.sh)

FIXTURE SAFETY: All dummy secrets below are assembled at runtime via _j() string
concatenation so that NO scanner pattern ever appears contiguously in this source
file. This keeps the repo's own push gate clean WITHOUT using the pragma escape
hatch (which is exactly the bypass these tests lock down). Every value is a
well-known dummy/documentation form — nothing here is a live credential.
"""

import subprocess
import unittest
from pathlib import Path
import sys
import tempfile
import os

# Add parent directory to path so we can import secret_scan
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from secret_scan import has_pragma, scan_file

SCANNER_PATH = Path(__file__).parent.parent / "tools" / "secret_scan.py"


def _j(*parts):
    """Join fragments at runtime so secret-shaped strings never appear
    contiguously in this source file (the scanned artifact)."""
    return "".join(parts)


def _write_fixture(suffix, lines):
    """Write lines to a temp file, return its path (caller unlinks)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    ) as f:
        for line in lines:
            f.write(line + "\n")
        return f.name


PRAGMA_LINE = "# secretscan: allow-pattern-docs"
JS_PRAGMA_LINE = "// secretscan: allow-pattern-docs"


class TestPragmaNotSoftensFatalSecrets(unittest.TestCase):
    """ITEM 1: Pragma should NOT soften fatal secret categories."""

    def test_pem_key_with_pragma_is_fatal(self):
        """PEM private key with pragma should still be FATAL (exit 1)."""
        # Dummy PEM block; header assembled from fragments at runtime
        pem_begin = _j("-----BEGIN RSA ", "PRIVATE", " KEY-----")
        pem_end = _j("-----END RSA ", "PRIVATE", " KEY-----")
        temp_path = _write_fixture(
            ".pem",
            [
                PRAGMA_LINE,
                pem_begin,
                "MIIEpAIBAAKCAQEA1234567890abcdef1234567890abcdef1234567890ab",
                pem_end,
            ],
        )

        try:
            findings = scan_file(Path(temp_path))

            self.assertTrue(len(findings) > 0, "Should find PEM key")

            fatal_findings = [f for f in findings if f[3] is True]
            self.assertTrue(
                len(fatal_findings) > 0,
                f"PEM key should be fatal even with pragma. Findings: {findings}",
            )

            pem_findings = [f for f in findings if f[1] == "pem_private_key"]
            self.assertTrue(len(pem_findings) > 0, "Should detect pem_private_key rule")
            self.assertTrue(
                pem_findings[0][3] is True, "pem_private_key should be fatal"
            )
        finally:
            os.unlink(temp_path)

    def test_aws_access_key_with_pragma_is_fatal(self):
        """AWS access key with pragma should still be FATAL (exit 1)."""
        # AWS's canonical documentation dummy key, assembled at runtime
        dummy_aws = _j("AKIA", "IOSFODNN7EXAMPLE")
        temp_path = _write_fixture(
            ".py",
            [PRAGMA_LINE, "k = '" + dummy_aws + "'"],
        )

        try:
            findings = scan_file(Path(temp_path))

            aws_findings = [f for f in findings if f[1] == "aws_access_key"]
            self.assertTrue(len(aws_findings) > 0, "Should detect aws_access_key rule")
            self.assertTrue(
                aws_findings[0][3] is True, "aws_access_key should be fatal"
            )
        finally:
            os.unlink(temp_path)

    def test_github_token_with_pragma_is_fatal(self):
        """GitHub token with pragma should still be FATAL (exit 1)."""
        # Dummy GitHub-style token (prefix + filler), assembled at runtime
        dummy_gh = _j("ghp_", "1234567890abcdefghij1234567890")
        temp_path = _write_fixture(
            ".js",
            [JS_PRAGMA_LINE, "const v = '" + dummy_gh + "'"],
        )

        try:
            findings = scan_file(Path(temp_path))

            github_findings = [f for f in findings if f[1] == "github_token"]
            self.assertTrue(len(github_findings) > 0, "Should detect github_token rule")
            self.assertTrue(
                github_findings[0][3] is True, "github_token should be fatal"
            )
        finally:
            os.unlink(temp_path)

    def test_pragma_softens_generic_secret_only(self):
        """Pragma SHOULD soften generic_secret_assignment (non-fatal)."""
        # Keyword split so the assignment shape never appears in this source file
        kw = _j("pass", "word")
        temp_path = _write_fixture(
            ".py",
            [PRAGMA_LINE, kw + ' = "this_is_a_test_example_password_12345"'],
        )

        try:
            findings = scan_file(Path(temp_path))

            generic_findings = [
                f for f in findings if f[1] == "generic_secret_assignment"
            ]
            self.assertTrue(
                len(generic_findings) > 0,
                "Should detect generic_secret_assignment",
            )
            # With pragma, this should be non-fatal
            self.assertTrue(
                generic_findings[0][3] is False,
                "generic_secret_assignment should be non-fatal with pragma",
            )
        finally:
            os.unlink(temp_path)

    def test_pragma_softens_env_access_only(self):
        """Pragma SHOULD soften env_access (non-fatal)."""
        # env accessor assembled at runtime so the access shape is not in source
        env_call = _j("os.envi", "ron['API_", "TOKEN']")
        temp_path = _write_fixture(
            ".py",
            [PRAGMA_LINE, "v = " + env_call],
        )

        try:
            findings = scan_file(Path(temp_path))

            env_findings = [f for f in findings if f[1] == "env_access"]
            self.assertTrue(len(env_findings) > 0, "Should detect env_access")
            # With pragma, this should be non-fatal
            self.assertTrue(
                env_findings[0][3] is False,
                "env_access should be non-fatal with pragma",
            )
        finally:
            os.unlink(temp_path)

    def test_slack_token_with_pragma_is_fatal(self):
        """Slack token with pragma should still be FATAL (exit 1)."""
        # Dummy Slack-style token, assembled at runtime
        dummy_slack = _j("xox", "b-1234567890-abcdefghijklmnop")
        temp_path = _write_fixture(
            ".py",
            [PRAGMA_LINE, "v = '" + dummy_slack + "'"],
        )

        try:
            findings = scan_file(Path(temp_path))

            slack_findings = [f for f in findings if f[1] == "slack_token"]
            self.assertTrue(len(slack_findings) > 0, "Should detect slack_token")
            self.assertTrue(
                slack_findings[0][3] is True, "slack_token should be fatal"
            )
        finally:
            os.unlink(temp_path)

    def test_connection_string_with_pragma_is_fatal(self):
        """Connection string with pragma should still be FATAL (exit 1)."""
        # Dummy connection URL assembled at runtime (scheme/creds/host split)
        dummy_url = _j(
            "postgresql:", "//user:dummypass", "@prod.example.com:5432/db"
        )
        temp_path = _write_fixture(
            ".py",
            [PRAGMA_LINE, "url = '" + dummy_url + "'"],
        )

        try:
            findings = scan_file(Path(temp_path))

            conn_findings = [f for f in findings if f[1] == "connection_string"]
            self.assertTrue(len(conn_findings) > 0, "Should detect connection_string")
            self.assertTrue(
                conn_findings[0][3] is True, "connection_string should be fatal"
            )
        finally:
            os.unlink(temp_path)

    def test_openai_anthropic_key_with_pragma_is_fatal(self):
        """OpenAI/Anthropic key with pragma should still be FATAL (exit 1)."""
        # Dummy sk-style key, assembled at runtime
        dummy_sk = _j("sk", "-1234567890abcdefghij1234567890")
        temp_path = _write_fixture(
            ".js",
            [JS_PRAGMA_LINE, "const v = '" + dummy_sk + "'"],
        )

        try:
            findings = scan_file(Path(temp_path))

            openai_findings = [f for f in findings if f[1] == "openai_anthropic_key"]
            self.assertTrue(
                len(openai_findings) > 0, "Should detect openai_anthropic_key"
            )
            self.assertTrue(
                openai_findings[0][3] is True, "openai_anthropic_key should be fatal"
            )
        finally:
            os.unlink(temp_path)


class TestScannerSelfScanClean(unittest.TestCase):
    """The scanner must scan its OWN source clean with ZERO pragma reliance.

    Rationale: the pragma can no longer soften fatal classes (pem_private_key
    etc.), so any contiguous self-matching pattern literal in the scanner's
    source would fatally flag the scanner itself. Pattern literals that
    self-match must be runtime-assembled from fragments instead.
    """

    def test_scanner_has_no_pragma(self):
        """tools/secret_scan.py must NOT rely on the in-file pragma."""
        self.assertFalse(
            has_pragma(SCANNER_PATH),
            "Scanner source must not carry the pragma; it must scan itself "
            "clean by construction (fragment-assembled pattern literals).",
        )

    def test_scanner_scans_itself_clean(self):
        """python tools/secret_scan.py tools/secret_scan.py -> CLEAN, exit 0."""
        result = subprocess.run(
            [sys.executable, str(SCANNER_PATH), str(SCANNER_PATH)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Self-scan must exit 0. stdout: {result.stdout!r} "
            f"stderr: {result.stderr!r}",
        )
        self.assertIn("CLEAN", result.stdout, "Self-scan must report CLEAN")
        self.assertNotIn(
            "ALLOWED-DOC",
            result.stdout,
            "Self-scan must be clean WITHOUT pragma-softened findings",
        )


if __name__ == "__main__":
    unittest.main()
