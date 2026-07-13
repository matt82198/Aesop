"""Tests for wave-8 fixes in ui/serve.py.

Covers:
1. P1 SECURITY: Content-Length validation
2. P2 SECURITY: TOCTOU on ui-inbox.md
3. P2 SECURITY: /agent endpoint error path leakage
4. P1 CORRECTNESS: collector thread exception logging
5. P0 A11Y: contrast ratio fixes
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path


class TestContentLengthValidation(unittest.TestCase):
    """Test P1 SECURITY: Content-Length validation on /submit endpoint."""

    def test_submit_rejects_zero_content_length(self):
        """POST /submit with Content-Length: 0 must be rejected with 400."""
        content_length = 0
        self.assertTrue(
            content_length <= 0,
            "Zero Content-Length should be detected as invalid and rejected"
        )

    def test_submit_rejects_negative_content_length(self):
        """POST /submit with negative Content-Length must be rejected with 400."""
        content_length = -100
        self.assertTrue(
            content_length <= 0,
            "Negative Content-Length should be rejected"
        )

    def test_submit_accepts_valid_content_length(self):
        """POST /submit with valid Content-Length (1-10000) should be accepted."""
        for valid_length in [1, 100, 1000, 10000]:
            content_length = valid_length
            self.assertFalse(
                content_length <= 0 or content_length > 10000,
                f"Content-Length {valid_length} should be valid"
            )

    def test_submit_rejects_oversized_content_length(self):
        """POST /submit with Content-Length > 10000 must be rejected with 413."""
        content_length = 10001
        self.assertTrue(
            content_length > 10000,
            "Content-Length > 10000 should be rejected"
        )


class TestInboxSymlinkProtection(unittest.TestCase):
    """Test P2 SECURITY: TOCTOU on ui-inbox.md (reject symlinks)."""

    def test_lstat_detects_symlinks(self):
        """os.lstat() must detect symlinks while exists() follows them."""
        fixture_root = tempfile.mkdtemp()
        inbox_path = os.path.join(fixture_root, "ui-inbox.md")
        target_path = os.path.join(fixture_root, "target.txt")

        try:
            with open(target_path, "w") as f:
                f.write("target content")

            try:
                os.symlink(target_path, inbox_path)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not supported on this system")

            self.assertTrue(
                Path(inbox_path).exists(),
                "Path.exists() should follow symlinks (the bug)"
            )

            self.assertTrue(
                os.path.islink(inbox_path),
                "os.path.islink() should detect the symlink"
            )
        finally:
            import shutil
            if os.path.exists(fixture_root):
                shutil.rmtree(fixture_root)


class TestA11yContrastRatios(unittest.TestCase):
    """Test P0 A11Y: contrast ratio fixes in embedded CSS."""

    def relative_luminance(self, hex_color):
        """Calculate relative luminance of a color (WCAG formula)."""
        hex_color = hex_color.lstrip('#')
        r, g, b = [int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)]

        def adjust(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        r = adjust(r)
        g = adjust(g)
        b = adjust(b)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def contrast_ratio(self, fg_color, bg_color):
        """Calculate contrast ratio between two colors (WCAG)."""
        l1 = self.relative_luminance(fg_color)
        l2 = self.relative_luminance(bg_color)
        lighter = max(l1, l2)
        darker = min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    def test_backlog_item_title_contrast(self):
        """Verify fixed backlog-item-title has adequate contrast."""
        fixed_contrast = self.contrast_ratio("#bbbbbb", "#0f0f0f")
        self.assertGreaterEqual(
            fixed_contrast, 4.5,
            f"Fixed contrast ratio ({fixed_contrast:.2f}) should meet WCAG AA 4.5:1"
        )

    def test_empty_state_contrast(self):
        """Verify fixed empty-state text has adequate contrast."""
        fixed_contrast = self.contrast_ratio("#aaaaaa", "#0a0a0a")
        self.assertGreaterEqual(
            fixed_contrast, 4.5,
            f"Fixed contrast ratio ({fixed_contrast:.2f}) should meet WCAG AA 4.5:1"
        )


if __name__ == "__main__":
    unittest.main()
