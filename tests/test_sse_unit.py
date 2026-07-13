"""Unit tests for ui/sse.py — SSE client registry, broadcast, and hash-gated emit.

Contracts under test (wave-10 P1 seam coverage, wave-9 split follow-up):
  - broadcast_sse() must never raise NameError when a client queue's put_nowait
    or get_nowait raises inside the queue.Full retry path (the except branch
    must bind `e` before referencing it, and must not shadow the module-level
    `sys` import with a redundant local `import sys`).
  - reset_state() clears _latest_snapshots (in place, keeping the same dict
    object), empties _sse_clients, and installs a fresh _collector_stop_event.
  - _maybe_emit() is hash-gated: broadcasting the same snapshot twice under the
    same name only broadcasts once.

Run: python -m unittest tests.test_sse_unit
"""
import importlib.util
import io
import os
import queue
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

UI_DIR = Path(__file__).parent.parent / "ui"


def load_sse(fixture_root):
    """Import a fresh ui/sse.py module instance, with its sibling deps resolvable.

    sse.py does plain (non-relative) imports of `config`, `collectors`, `agents`,
    which only resolve if ui/ is on sys.path — mirrors the shim serve.py installs.
    """
    ui_dir = str(UI_DIR)
    if ui_dir not in sys.path:
        sys.path.insert(0, ui_dir)

    os.environ["AESOP_ROOT"] = str(fixture_root)
    os.environ["AESOP_TRANSCRIPTS_ROOT"] = str(fixture_root / "transcripts")

    import config
    config.reload()

    spec = importlib.util.spec_from_file_location(f"sse_unit_{id(fixture_root)}", UI_DIR / "sse.py")
    sse = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sse)
    return sse


class SSEFixtureCase(unittest.TestCase):
    def setUp(self):
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-sse-unit-"))
        (self.fixture_root / "state").mkdir()
        (self.fixture_root / "transcripts").mkdir()
        self._saved_env = {k: os.environ.get(k) for k in ("AESOP_ROOT", "AESOP_TRANSCRIPTS_ROOT")}
        self.sse = load_sse(self.fixture_root)

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.fixture_root, ignore_errors=True)


class ExplodingQueue:
    """Stand-in for queue.Queue that always looks full, then blows up on retry.

    put_nowait() always raises queue.Full (as a real full queue would), driving
    broadcast_sse() into its retry branch; get_nowait() then raises a different
    exception (simulating e.g. a concurrent unregister) to exercise the inner
    `except Exception as e:` path.
    """

    def put_nowait(self, item):
        raise queue.Full()

    def get_nowait(self):
        raise RuntimeError("boom: queue drained concurrently")


class TestBroadcastSseExceptionPath(SSEFixtureCase):
    """wave-10 P1: the retry-on-full except branch must not NameError on `e`."""

    def test_full_then_exploding_retry_does_not_raise(self):
        sse = self.sse
        with sse._sse_lock:
            sse._sse_clients.append(ExplodingQueue())

        buf = io.StringIO()
        try:
            with redirect_stderr(buf):
                sse.broadcast_sse("data", '{"ok": true}')
        except NameError as e:
            self.fail(f"broadcast_sse raised NameError (undefined `e`): {e}")

        # It should have logged the real failure, not silently swallowed it.
        logged = buf.getvalue()
        self.assertIn("collector_loop", logged)
        self.assertIn("RuntimeError", logged)
        self.assertIn("boom: queue drained concurrently", logged)

    def test_healthy_client_still_receives_broadcast(self):
        sse = self.sse
        q = queue.Queue(maxsize=4)
        with sse._sse_lock:
            sse._sse_clients.append(q)

        sse.broadcast_sse("data", '{"n": 1}')

        self.assertEqual(q.get_nowait(), ("data", '{"n": 1}'))


class TestResetState(SSEFixtureCase):
    def test_reset_state_clears_snapshots_and_clients_and_rearms_stop_event(self):
        sse = self.sse

        with sse._latest_lock:
            sse._latest_snapshots["data"] = '{"stale": true}'
        snapshots_obj = sse._latest_snapshots  # same object identity, mutated in place

        with sse._sse_lock:
            sse._sse_clients.append(queue.Queue())

        old_stop_event = sse._collector_stop_event
        sse._collector_started = True

        sse.reset_state()

        self.assertIs(sse._latest_snapshots, snapshots_obj)
        self.assertTrue(all(v is None for v in sse._latest_snapshots.values()),
                         f"snapshots not cleared: {sse._latest_snapshots}")
        self.assertEqual(sse._sse_clients, [])
        self.assertFalse(sse._collector_started)
        self.assertIsNot(sse._collector_stop_event, old_stop_event)
        self.assertTrue(old_stop_event.is_set(), "stale collector thread must be signalled to stop")
        self.assertFalse(sse._collector_stop_event.is_set(), "fresh stop event must start unset")


class TestMaybeEmitHashGate(SSEFixtureCase):
    def test_same_snapshot_twice_broadcasts_once(self):
        sse = self.sse
        q = queue.Queue(maxsize=8)
        with sse._sse_lock:
            sse._sse_clients.append(q)

        last_hashes = {}
        snapshot = {"tiers": ["a", "b"]}

        sse._maybe_emit("backlog", snapshot, last_hashes)
        sse._maybe_emit("backlog", snapshot, last_hashes)  # unchanged -> gated, no 2nd broadcast

        self.assertEqual(q.qsize(), 1, "identical snapshot must only broadcast once")
        event_name, payload = q.get_nowait()
        self.assertEqual(event_name, "backlog")
        self.assertIn('"a"', payload)

    def test_changed_snapshot_broadcasts_again(self):
        sse = self.sse
        q = queue.Queue(maxsize=8)
        with sse._sse_lock:
            sse._sse_clients.append(q)

        last_hashes = {}
        sse._maybe_emit("backlog", {"tiers": ["a"]}, last_hashes)
        sse._maybe_emit("backlog", {"tiers": ["a", "b"]}, last_hashes)

        self.assertEqual(q.qsize(), 2, "changed snapshot must broadcast again")


if __name__ == "__main__":
    unittest.main()
