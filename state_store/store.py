"""state_store.store — SQLite-backed, append-only, concurrency-safe event log.

Durable substrate for aesop's event-sourced state layer (the DB-source-of-truth
design; git becomes a rendered export, not the coordination layer). Backend is
SQLite in WAL mode so many readers and serialized writers share one file; the
same interface is meant to swap to Postgres behind ``state_store.api.StateAPI``
for team scale without touching call sites.

Stdlib only (sqlite3, json, time) per aesop's no-external-deps invariant.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time


class EventStore:
    """Append-only event log stored at ``db_path``.

    Safe under concurrent appends from multiple threads AND multiple EventStore
    instances on the same file: every call opens its own connection with
    ``PRAGMA busy_timeout`` and assigns the per-stream version inside a
    ``BEGIN IMMEDIATE`` transaction, so the read-max-version-then-insert is
    atomic and two writers can never collide or duplicate a version.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts      REAL    NOT NULL,
                    actor   TEXT    NOT NULL,
                    stream  TEXT    NOT NULL,
                    type    TEXT    NOT NULL,
                    payload TEXT    NOT NULL,
                    version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_stream_version "
                "ON events(stream, version)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts           REAL    NOT NULL,
                    stream       TEXT    NOT NULL,
                    event_version INTEGER NOT NULL,
                    projection   TEXT    NOT NULL,
                    checksum     TEXT    NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_stream_version "
                "ON snapshots(stream, event_version)"
            )
            conn.commit()
        finally:
            conn.close()

    def append(self, stream: str, event_type: str, payload: dict, actor: str = "system") -> int:
        """Append one event to ``stream``; return its new per-stream version (1-based)."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            # BEGIN IMMEDIATE takes the write lock up front so the
            # read-max-then-insert below is atomic under contention.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM events WHERE stream = ?",
                (stream,),
            ).fetchone()
            version = row[0] + 1
            conn.execute(
                "INSERT INTO events (ts, actor, stream, type, payload, version) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), actor, stream, event_type, json.dumps(payload), version),
            )
            conn.commit()
            return version
        finally:
            conn.close()

    def read(self, stream: str) -> list:
        """Return all events for ``stream`` ascending by version (empty if none)."""
        return self._rows("WHERE stream = ? ORDER BY version ASC", (stream,))

    def read_all(self) -> list:
        """Return all events across all streams ascending by id."""
        return self._rows("ORDER BY id ASC", ())

    def _rows(self, clause: str, params) -> list:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            cur = conn.execute(
                "SELECT id, ts, actor, stream, type, payload, version FROM events " + clause,
                params,
            )
            rows = []
            for r in cur.fetchall():
                try:
                    payload = json.loads(r[5])
                    rows.append({
                        "id": r[0], "ts": r[1], "actor": r[2], "stream": r[3],
                        "type": r[4], "payload": payload, "version": r[6],
                    })
                except json.JSONDecodeError as e:
                    # Log corrupt event (stream id + sequence) to stderr and skip
                    print(
                        f"WARNING: corrupt JSON payload in stream={r[3]} id={r[0]}: {e}",
                        file=sys.stderr,
                    )
            return rows
        finally:
            conn.close()

    def save_snapshot(self, stream: str, event_version: int, projection: dict) -> None:
        """Save a materialized projection snapshot at a specific event version.

        The snapshot enables tail-replay: instead of replaying from event 1,
        project() can resume from this snapshot's version and fold only newer events.

        Args:
            stream: the stream name (e.g. "tracker")
            event_version: the per-stream event version this snapshot was computed through
            projection: the materialized state dict (e.g. the full tracker projection)
        """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            projection_json = json.dumps(projection, separators=(",", ":"), sort_keys=True)
            checksum = hashlib.sha256(projection_json.encode()).hexdigest()
            conn.execute(
                "INSERT INTO snapshots (ts, stream, event_version, projection, checksum) "
                "VALUES (?, ?, ?, ?, ?)",
                (time.time(), stream, event_version, projection_json, checksum),
            )
            conn.commit()
        finally:
            conn.close()

    def read_snapshot(self, stream: str) -> tuple | None:
        """Read the most recent snapshot for a stream.

        Returns:
            A tuple (event_version, projection_dict, checksum) if a valid snapshot exists,
            or None if no snapshot found.

        On corrupt/unreadable snapshot, logs a warning and returns None (falls back to
        full replay).
        """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            cur = conn.execute(
                "SELECT event_version, projection, checksum FROM snapshots "
                "WHERE stream = ? ORDER BY event_version DESC LIMIT 1",
                (stream,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            event_version, projection_json, checksum = row
            try:
                projection = json.loads(projection_json)
                # Verify checksum
                computed_checksum = hashlib.sha256(projection_json.encode()).hexdigest()
                if computed_checksum != checksum:
                    print(
                        f"WARNING: snapshot checksum mismatch for stream={stream} "
                        f"version={event_version}; falling back to full replay",
                        file=sys.stderr,
                    )
                    return None
                return (event_version, projection, checksum)
            except json.JSONDecodeError as e:
                print(
                    f"WARNING: corrupt JSON in snapshot for stream={stream} "
                    f"version={event_version}: {e}; falling back to full replay",
                    file=sys.stderr,
                )
                return None
        finally:
            conn.close()
