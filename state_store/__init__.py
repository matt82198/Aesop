"""state_store — event-sourced state layer (DB source of truth, git as export).

Additive prototype landed 2026-07-14: the live ui/ tracker path is UNCHANGED.
This package provides the durable substrate to migrate aesop's coordination
state off git (which does not scale to concurrent writers) onto a real store
with transactions and per-stream versioning — SQLite (WAL) now, Postgres later
behind the same StateAPI. git is demoted to a rendered export (see export.py).

Design + rationale: conductor3 plans/aesop-scaling-rearchitecture.md; overview
in state_store/CLAUDE.md.
"""
from .api import StateAPI
from .export import export_tracker
from .ingest import ingest_tracker_json
from .projections import project_tracker
from .store import EventStore

__all__ = [
    "EventStore",
    "StateAPI",
    "project_tracker",
    "export_tracker",
    "ingest_tracker_json",
]
