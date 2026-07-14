"""Tests for state_store — the event-sourced state layer (unittest).

Covers the append-only store (incl. concurrency), the tracker projection, and
the ingest -> project -> export round-trip against the REAL state/tracker.json.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from state_store import (  # noqa: E402
    EventStore,
    StateAPI,
    export_tracker,
    ingest_tracker_json,
    project_tracker,
)


class EventStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "events.db")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_returns_monotonic_per_stream_version(self):
        s = EventStore(self.db)
        self.assertEqual(s.append("a", "e", {"n": 1}, "t"), 1)
        self.assertEqual(s.append("a", "e", {"n": 2}, "t"), 2)
        self.assertEqual(s.append("a", "e", {"n": 3}, "t"), 3)
        versions = [e["version"] for e in s.read("a")]
        self.assertEqual(versions, [1, 2, 3])

    def test_per_stream_versions_are_independent(self):
        s = EventStore(self.db)
        self.assertEqual(s.append("a", "e", {}, "t"), 1)
        self.assertEqual(s.append("b", "e", {}, "t"), 1)
        self.assertEqual(s.append("a", "e", {}, "t"), 2)
        self.assertEqual(s.append("b", "e", {}, "t"), 2)

    def test_payload_dict_round_trips(self):
        s = EventStore(self.db)
        payload = {"title": "x", "tags": ["a", "b"], "nested": {"k": 1}, "pr_link": None}
        s.append("a", "item_created", payload, "t")
        got = s.read("a")[0]["payload"]
        self.assertEqual(got, payload)

    def test_read_all_spans_streams_ascending_by_id(self):
        s = EventStore(self.db)
        s.append("a", "e", {}, "t")
        s.append("b", "e", {}, "t")
        s.append("a", "e", {}, "t")
        streams = [e["stream"] for e in s.read_all()]
        self.assertEqual(streams, ["a", "b", "a"])

    def test_empty_stream_reads_empty(self):
        self.assertEqual(EventStore(self.db).read("nope"), [])

    def test_concurrent_appends_have_no_dupes_or_gaps(self):
        # Two threads, each its OWN EventStore on the SAME db, released together.
        n = 50
        barrier = threading.Barrier(2)

        def worker():
            store = EventStore(self.db)
            barrier.wait()
            for _ in range(n):
                store.append("s", "e", {}, "t")

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        versions = sorted(e["version"] for e in EventStore(self.db).read("s"))
        self.assertEqual(versions, list(range(1, 2 * n + 1)))


class ProjectionTest(unittest.TestCase):
    def test_created_updated_archived_fold(self):
        events = [
            {"type": "item_created", "payload": {"id": "x", "title": "T", "lane": "proposed", "status": "todo"}},
            {"type": "item_created", "payload": {"id": "y", "title": "U", "lane": "proposed", "status": "todo"}},
            {"type": "item_updated", "payload": {"id": "x", "lane": "in-progress", "status": "in-progress"}},
            {"type": "item_archived", "payload": {"id": "y", "completed_at": "2026-07-14T00:00:00Z"}},
            {"type": "unknown_type", "payload": {"id": "z"}},
        ]
        proj = project_tracker(events)
        self.assertEqual(proj["version"], 1)
        by_id = {it["id"]: it for it in proj["items"]}
        self.assertEqual([it["id"] for it in proj["items"]], ["x", "y"])  # first-seen order
        self.assertEqual(by_id["x"]["lane"], "in-progress")
        self.assertEqual(by_id["x"]["status"], "in-progress")
        self.assertEqual(by_id["x"]["title"], "T")  # untouched field preserved
        self.assertEqual(by_id["y"]["status"], "archived")
        self.assertEqual(by_id["y"]["completed_at"], "2026-07-14T00:00:00Z")

    def test_update_or_archive_unknown_id_is_noop(self):
        proj = project_tracker([
            {"type": "item_updated", "payload": {"id": "ghost", "lane": "done"}},
            {"type": "item_archived", "payload": {"id": "ghost"}},
        ])
        self.assertEqual(proj["items"], [])


class ApiAndExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "events.db")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_project_unknown_view_raises(self):
        api = StateAPI(self.db)
        with self.assertRaises(ValueError):
            api.project("does-not-exist")

    def test_append_project_export_end_to_end(self):
        api = StateAPI(self.db)
        api.append("tracker", "item_created", {"id": "a", "title": "A", "lane": "proposed"}, "u")
        api.append("tracker", "item_updated", {"id": "a", "lane": "done"}, "u")
        proj = api.project("tracker")
        self.assertEqual(proj["items"][0]["lane"], "done")
        out = os.path.join(self.tmp, "tracker_out.json")
        export_tracker(api, out)
        reloaded = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(reloaded, proj)

    def test_ingest_project_export_round_trips_real_tracker(self):
        tracker_path = ROOT / "state" / "tracker.json"
        if not tracker_path.exists():
            self.skipTest("no state/tracker.json checked out")
        original = json.loads(tracker_path.read_text(encoding="utf-8"))
        api = StateAPI(self.db)
        n = ingest_tracker_json(api, str(tracker_path))
        self.assertEqual(n, len(original["items"]))
        projected = api.project("tracker")
        # Round-trip must reproduce the exact item list (semantic equality).
        self.assertEqual(projected["items"], original["items"])
        out = os.path.join(self.tmp, "roundtrip.json")
        export_tracker(api, out)
        reloaded = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(reloaded["items"], original["items"])


if __name__ == "__main__":
    unittest.main()
