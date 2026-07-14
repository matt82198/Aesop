"""state_store.export — render a projection back into git-tracked JSON.

In the DB-source-of-truth design git stops being *read* for state; this job
renders human-readable, diffable snapshots (e.g. tracker.json) FROM the
projections for durability and review. The JSON style (indent=2, ascii-escaped)
matches the existing state/tracker.json so a future cutover produces
minimal-diff snapshots.
"""
from __future__ import annotations

import json


def export_tracker(api, out_path: str) -> None:
    """Write the tracker projection to ``out_path`` as pretty JSON."""
    projection = api.project("tracker")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(projection, fh, indent=2)
        fh.write("\n")
