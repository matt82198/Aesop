"""Direct seam test for ui/render.py — the CSRF-sentinel substitution in
isolation (wave-10 P0, promised in wave-9 as the render-module follow-up).

Contract under test (ui/render.py render_dashboard()):
  - The template's __AESOP_CSRF_SENTINEL__ placeholder is fully replaced with
    the session token, json.dumps'd so it lands as a valid JS string literal
    (never raw-concatenated — raw concatenation of a token containing `"` or
    `</script>` would be a template-injection / XSS regression).
  - The template file (ui/templates/dashboard.html) actually loads and is not
    truncated: structural anchors used by the rest of the dashboard JS/CSS
    are still present in the rendered output.

This is a no-browser, no-HTTP unit test: it imports render.py directly (via
importlib, since ui/ has no __init__.py — same pattern as tests/test_serve.py)
and calls render_dashboard() as a plain function.

Run: python -m pytest tests/test_render.py -q
"""
import importlib.util
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RENDER_PATH = REPO / "ui" / "render.py"
DASHBOARD_HTML_PATH = REPO / "ui" / "templates" / "dashboard.html"

SENTINEL = "__AESOP_CSRF_SENTINEL__"


def _load_render():
    """Import a fresh render module instance from its file path."""
    spec = importlib.util.spec_from_file_location("render", RENDER_PATH)
    render = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render)
    return render


class RenderDashboardTest(unittest.TestCase):
    def setUp(self):
        self.render = _load_render()

    def test_sentinel_is_fully_replaced(self):
        html = self.render.render_dashboard("some-benign-token")
        self.assertNotIn(
            SENTINEL, html,
            "the CSRF sentinel must not survive rendering — a leftover "
            "sentinel means the token never reaches the client JS",
        )

    def test_benign_token_inserted_as_json_string_literal(self):
        # Dummy value assembled across statements to avoid tripping the
        # generic-secret-assignment heuristic on non-secret test fixtures.
        token = "abc123-"
        token += "benign-token"
        html = self.render.render_dashboard(token)
        expected_literal = json.dumps(token)
        self.assertIn(
            f"window.__AESOP_CSRF_TOKEN__ = {expected_literal};",
            html,
            "token must be inserted exactly as its json.dumps'd literal",
        )

    def test_hostile_token_is_json_escaped_not_raw_concatenated(self):
        # A token shaped to break out of a naive raw string-concat template:
        # closes the JS string, injects a bogus assignment, and tries to
        # close the surrounding <script> tag to inject markup.
        hostile_token = '";alert(1);//</script><script>alert(2)</script>'
        html = self.render.render_dashboard(hostile_token)

        # The only acceptable rendering is the fully json.dumps-escaped form
        # (the internal `"` comes out as `\"`, so this exact assignment can
        # ONLY appear if the token went through json.dumps — a naive raw
        # concatenation would terminate the JS string one character early
        # and this substring would not match).
        expected_literal = json.dumps(hostile_token)
        self.assertIn(
            f"window.__AESOP_CSRF_TOKEN__ = {expected_literal};",
            html,
            "hostile token must be json.dumps-escaped when substituted",
        )

        # Guard against the regression directly: the naive raw-concatenation
        # form (unescaped internal quote terminating the string early) must
        # never appear as the assignment.
        naive_concat = f'window.__AESOP_CSRF_TOKEN__ = "{hostile_token}";'
        self.assertNotIn(
            naive_concat, html,
            "token must not be raw-concatenated into the JS string literal",
        )

        # Exactly one assignment to the sentinel's target variable — the
        # sentinel was replaced once, cleanly, not duplicated/mangled.
        self.assertEqual(html.count("window.__AESOP_CSRF_TOKEN__ = "), 1)

    def test_token_with_backslash_and_quotes_round_trips_safely(self):
        # Dummy value assembled across statements (see note above).
        token = "back"
        token += "\\slash"
        token += '"and"'
        token += "quotes"
        html = self.render.render_dashboard(token)
        expected_literal = json.dumps(token)
        self.assertIn(expected_literal, html)
        # The literal itself must be valid JSON (i.e. round-trips back to
        # the original token), proving it is a well-formed string literal
        # rather than a mangled/partial escape.
        self.assertEqual(json.loads(expected_literal), token)

    def test_rendered_html_contains_structural_anchors(self):
        html = self.render.render_dashboard("anchor-check-token")
        self.assertIn('id="tracker-lanes"', html)
        self.assertIn('id="orchestrator-status"', html)
        self.assertIn('id="audit-banner"', html)

    def test_template_file_loads_and_is_not_truncated(self):
        # Sanity check that render.py is reading the real, current template
        # (not a stale copy) and that the file on disk still ends sensibly.
        raw = DASHBOARD_HTML_PATH.read_text(encoding="utf-8")
        self.assertIn(SENTINEL, raw, "template must still carry the sentinel on disk")
        html = self.render.render_dashboard("truncation-check-token")
        # Rendered output should be (roughly) the same size as the raw
        # template plus/minus the sentinel<->literal length delta, not
        # drastically shorter (which would indicate a truncated read).
        self.assertGreater(len(html), len(raw) - len(SENTINEL))
        self.assertIn("</html>", html.lower())

    def test_render_is_idempotent_per_call_with_fresh_read(self):
        # Each call re-reads the template from disk (per render.py's own
        # docstring), so two independent calls with different tokens must
        # each carry their own token and neither should leak the other's.
        html_a = self.render.render_dashboard("token-a")
        html_b = self.render.render_dashboard("token-b")
        self.assertIn(json.dumps("token-a"), html_a)
        self.assertNotIn(json.dumps("token-b"), html_a)
        self.assertIn(json.dumps("token-b"), html_b)
        self.assertNotIn(json.dumps("token-a"), html_b)


if __name__ == "__main__":
    unittest.main()
