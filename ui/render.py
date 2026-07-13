#!/usr/bin/env python3
"""
Aesop UI template rendering — stdlib-only.

The dashboard HTML/CSS/JS lives in templates/dashboard.html (extracted from
serve.py in the wave-9 split). The only server-side substitution is the
per-session CSRF token, injected via a unique sentinel so the template stays a
plain static file (no .format()/% — the CSS/JS is full of { } and % literals).
"""
import json
import os

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
_DASHBOARD_HTML = os.path.join(_TEMPLATE_DIR, "dashboard.html")

# Sentinel the template carries in place of the CSRF token literal.
_CSRF_SENTINEL = "__AESOP_CSRF_SENTINEL__"


def render_dashboard(session_token):
    """Return the dashboard HTML with the CSRF token substituted in.

    Reads the template fresh each call (cheap; keeps edits live in dev). The
    token is inserted as a JS string literal via json.dumps so it is always a
    valid, properly-quoted value.
    """
    with open(_DASHBOARD_HTML, encoding="utf-8") as f:
        html = f.read()
    return html.replace(_CSRF_SENTINEL, json.dumps(session_token))
