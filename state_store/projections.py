"""state_store.projections — fold tracker events into current state.

``project_tracker`` reconstructs the tracker.json shape
(``{"version": 1, "items": [...]}``) from the ``tracker`` event stream:

  - ``item_created``  : payload is the full item dict; establishes the item
                        (kept in first-seen order).
  - ``item_updated``  : payload is ``{"id": <id>, ...partial fields}``; merges
                        the given fields onto the existing item.
  - ``item_archived`` : payload is ``{"id": <id>}`` (+ optional
                        ``completed_at``); sets ``status`` to ``"archived"``.

Unknown ids on update/archive and unknown event types are ignored, keeping the
fold tolerant of partial/legacy streams.
"""
from __future__ import annotations

TRACKER_VERSION = 1


def project_tracker(events: list) -> dict:
    """Return the current tracker state projected from ``events``."""
    order = []      # item ids in first-seen order (stable output ordering)
    items = {}      # id -> item dict
    for ev in events:
        etype = ev.get("type")
        payload = ev.get("payload") or {}
        if etype == "item_created":
            iid = payload.get("id")
            if iid is None:
                continue
            if iid not in items:
                order.append(iid)
            items[iid] = dict(payload)
        elif etype == "item_updated":
            iid = payload.get("id")
            if iid in items:
                merged = dict(items[iid])
                for key, value in payload.items():
                    if key != "id":
                        merged[key] = value
                items[iid] = merged
        elif etype == "item_archived":
            iid = payload.get("id")
            if iid in items:
                merged = dict(items[iid])
                merged["status"] = "archived"
                if "completed_at" in payload:
                    merged["completed_at"] = payload["completed_at"]
                items[iid] = merged
        # any other event type is ignored
    return {"version": TRACKER_VERSION, "items": [items[i] for i in order]}
