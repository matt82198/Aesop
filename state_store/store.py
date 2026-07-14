"""state_store.store — SQLite-backed, append-only, concurrency-safe event log.

Durable substrate for aesop's event-sourced state layer (the DB-source-of-truth
design; git becomes a rendered export, not the coordination layer). Backend is
SQLite in WAL mode so many readers and serialized writers share one file; the
same interface is meant to swap to Postgres behind ``state_store.api.StateAPI``
for team scale without touching call sites.

Stdlib only (sqlite3, json, time) per aesop's no-external-deps invariant.
"""
from __future__ import annotations

import json
import sqlite3
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
            return [
                {
                    "id": r[0], "ts": r[1], "actor": r[2], "stream": r[3],
                    "type": r[4], "payload": json.loads(r[5]), "version": r[6],
                }
                for r in cur.fetchall()
            ]
        finally:
            conn.close()
