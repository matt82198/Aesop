#!/usr/bin/env python3
"""
Aesop UI template rendering — stdlib-only.

The legacy dashboard HTML/CSS/JS lives in templates/dashboard.html (extracted
from serve.py in the wave-9 split). Wave-14 (dashboard rewrite, plan D3/D7)
retargets the same mechanism at the built React app: the handler passes
ui/web/dist/index.html as template_path when a committed dist is present, and
falls back to the legacy template otherwise. The only server-side substitution
is the per-session CSRF token, injected via a unique sentinel so the template
stays a plain static file (no .format()/% — the CSS/JS is full of { } and %
literals; the Vite build passes the sentinel-carrying inline script through
verbatim).
"""
import json
import os

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
_DASHBOARD_HTML = os.path.join(_TEMPLATE_DIR, "dashboard.html")

# Sentinel the template carries in place of the CSRF token literal.
_CSRF_SENTINEL = "__AESOP_CSRF_SENTINEL__"


def render_dashboard(session_token, template_path=None):
    """Return the dashboard HTML with the CSRF token substituted in.

    Args:
        session_token: the per-session CSRF token to inject.
        template_path: path to the template file carrying the CSRF sentinel
            (wave-14 U9 cutover: dist/index.html is always required; no
            fallback to templates/dashboard.html).

    Reads the template fresh each call (cheap; keeps edits live in dev). The
    token is inserted as a JS string literal via json.dumps so it is always a
    valid, properly-quoted value.

    Raises:
        TypeError: if template_path is None (legacy fallback removed at U9).
        FileNotFoundError: if the template file does not exist.
    """
    if template_path is None:
        raise TypeError(
            "render_dashboard() requires template_path after wave-14 U9 cutover; "
            "legacy fallback to templates/dashboard.html has been removed"
        )
    with open(template_path, encoding="utf-8") as f:
        html = f.read()
    return html.replace(_CSRF_SENTINEL, json.dumps(session_token))
