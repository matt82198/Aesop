"""state_store.api — StateAPI facade over the event store + projections.

The single seam callers use, so the backend (SQLite now, Postgres later) can be
swapped without touching call sites. ``project(view)`` reads the same-named
stream and folds it through the registered projector.
"""
from __future__ import annotations

from .projections import project_tracker
from .store import EventStore, ConcurrencyConflict

_PROJECTORS = {"tracker": project_tracker}


class StateAPI:
    """Facade: append events, read a stream, or project a view to current state."""

    def __init__(self, db_path: str):
        self._store = EventStore(db_path)

    def append(
        self,
        stream: str,
        event_type: str,
        payload: dict,
        actor: str = "system",
        expected_version: int | None = None,
    ) -> int:
        """Append one event; return its new per-stream version.

        Supports optimistic concurrency control via expected_version. See
        EventStore.append for full semantics.

        Raises:
            ConcurrencyConflict: If expected_version is provided and does not
                               match the stream's current max version.
        """
        return self._store.append(stream, event_type, payload, actor, expected_version)

    def get(self, stream: str) -> list:
        """Return all events in ``stream`` ascending by version."""
        return self._store.read(stream)

    def project(self, view: str) -> dict:
        """Fold the same-named stream through its projector into current state."""
        try:
            projector = _PROJECTORS[view]
        except KeyError:
            raise ValueError(f"unknown projection view: {view!r}")
        return projector(self.get(view))
