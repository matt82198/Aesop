"""state_store.ingest — backfill events from an existing tracker.json.

Migration path for the DB-source-of-truth cutover: read the current
tracker.json and emit one ``item_created`` event per item (full payload) so the
event store reproduces the current state. History is not reconstructed (only
final state exists on disk), but the projection round-trips to the same items,
so an export re-renders the identical tracker.json.
"""
from __future__ import annotations

import json


def ingest_tracker_json(api, tracker_json_path: str, actor: str = "migration") -> int:
    """Append one ``item_created`` per item in ``tracker_json_path``.

    Returns the number of items ingested.
    """
    with open(tracker_json_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    items = data.get("items", [])
    for item in items:
        api.append("tracker", "item_created", item, actor)
    return len(items)
