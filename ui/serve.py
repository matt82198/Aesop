#!/usr/bin/env python3
"""
Aesop Web Dashboard — stdlib-only local observability (thin entry point).

Serves a dark-theme HTML dashboard on a configurable port (default 8770) with
realtime updates via GET /events (Server-Sent Events). No external dependencies.

Wave-9 split: this module is now a thin composition layer. The implementation
lives in focused siblings, each of which reads config.* at call time so config
values stay live across reloads:
  - config.py      — path / env / aesop.config.json resolution (+ reload())
  - csrf.py        — session-token generation + request validation
  - collectors.py  — read-only data collectors, tracker CRUD, SSE snapshots
  - agents.py      — agent transcript reading + path-safe id handling
  - sse.py         — SSE client registry, broadcast, background collector loop
  - render.py      — dashboard template rendering (templates/dashboard.html)
  - handler.py     — DashboardHandler (HTTP routing/endpoints) + run_server

serve.py re-exports the sibling symbols so `serve.X` keeps resolving for the
existing test suite (which loads this file by path and pokes its module globals)
and for `python ui/serve.py` as the unchanged entry point.

Configuration, CSRF, and SSE details are documented in ui/CLAUDE.md.
"""
import os
import sys

# Sys.path shim: add ui/ so sibling imports resolve both when this file is run
# as `python ui/serve.py` and when it is loaded by path via importlib (tests).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
config.reload()

import csrf
csrf.init()

import render
import collectors
import agents
import sse

# Fresh collector/snapshot state per serve import (restores the per-import
# isolation the monolith had; the sse module object is cached across re-imports).
sse.reset_state()

# Re-export sibling symbols so serve.X keeps resolving for tests + the handler.
from config import *
from csrf import *
from render import render_dashboard
from collectors import *
from agents import *
from sse import *
from collectors import (_snapshot_data, _snapshot_tracker,
                        _snapshot_orchestrator_status, drain_tracker_inbox)
from agents import _AGENT_ID_FORBIDDEN, _transcripts_fingerprint
from sse import (_sse_lock, _sse_clients, _latest_lock, _latest_snapshots,
                 _collector_lock, _collector_stop_event, _maybe_emit)

# HTTP handler + server entry.
import handler
from handler import DashboardHandler, run_server

if __name__ == "__main__":
    run_server()
