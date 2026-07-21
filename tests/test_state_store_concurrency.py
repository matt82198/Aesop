"""Tests for state_store multi-process concurrency — the core proof.

Spawns 2+ concurrent PROCESSES (not threads — processes are the risk level)
against ONE shared SQLite DB to prove:
  (a) No lost update / no corruption: all appends land, versions are gapless,
      payloads round-trip
  (b) Exactly one claim winner per resource under contention
  (c) Fail-closed on error: append failure does not falsely grant a claim

Uses multiprocessing (not threads) to test cross-process safety, which is
where the CI flake and real team-scale concurrency issues live.

Follows Linux-parity rules:
  - sys.executable for subprocess spawning
  - stdlib unittest (no pytest assumption)
  - Enforced timeouts on any subprocess
  - ASCII-only output
  - No hardcoded absolute timestamps
  - Isolated temp DB per test
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from state_store import EventStore, StateAPI  # noqa: E402
from state_store.coordination import fold_claims, try_claim, release, current_holder  # noqa: E402
from state_store.identity import get_instance_id  # noqa: E402


def _worker_append_events(args):
    """Worker function for multiprocessing: append K events to a shared stream.

    Args:
        args: (db_path, stream, worker_id, num_events)

    Returns:
        dict with worker_id, appended versions, and any error message
    """
    db_path, stream, worker_id, num_events = args
    try:
        store = EventStore(db_path)
        versions = []
        for i in range(num_events):
            payload = {
                "worker_id": worker_id,
                "event_index": i,
                "timestamp": time.time(),
            }
            version = store.append(stream, "test_event", payload, actor=f"worker_{worker_id}")
            versions.append(version)
        return {"worker_id": worker_id, "versions": versions, "error": None}
    except Exception as e:
        return {"worker_id": worker_id, "versions": [], "error": str(e)}


def _worker_try_claim(args):
    """Worker function for multiprocessing: attempt to claim a resource.

    Args:
        args: (db_path, resource, instance_id)

    Returns:
        dict with instance_id, claim_success, and any error message
    """
    db_path, resource, instance_id = args
    try:
        store = StateAPI(db_path)
        success = try_claim(store, resource, instance_id)
        return {"instance_id": instance_id, "success": success, "error": None}
    except Exception as e:
        return {"instance_id": instance_id, "success": False, "error": str(e)}


class MultiProcessConcurrencyTest(unittest.TestCase):
    """Multi-process concurrency tests for state_store."""

    def setUp(self):
        """Create isolated temp DB for this test."""
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_concurrency.db")
        # Initialize DB
        EventStore(self.db_path)

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_no_lost_update_across_processes(self):
        """Spawn N processes appending to shared stream; assert all land gaplessly."""
        num_workers = 4
        events_per_worker = 50
        stream = "test_stream"

        results = []
        with Pool(processes=num_workers) as pool:
            # Spawn all workers
            async_results = [
                pool.apply_async(_worker_append_events, ((self.db_path, stream, worker_id, events_per_worker),))
                for worker_id in range(num_workers)
            ]
            # Collect results with timeout
            for async_result in async_results:
                try:
                    result = async_result.get(timeout=30)
                    results.append(result)
                except Exception as e:
                    self.fail(f"Worker failed or timed out: {e}")

        # Verify all workers succeeded
        for result in results:
            self.assertIsNone(result["error"], f"Worker {result['worker_id']} error: {result['error']}")

        # Verify all events landed
        store = EventStore(self.db_path)
        events = store.read(stream)
        total_appended = num_workers * events_per_worker
        self.assertEqual(len(events), total_appended, f"Expected {total_appended} events, got {len(events)}")

        # Verify versions are gapless (1..total_appended)
        versions = sorted([e["version"] for e in events])
        expected_versions = list(range(1, total_appended + 1))
        self.assertEqual(versions, expected_versions, "Versions are not gapless or have duplicates")

        # Verify payloads round-trip (spot check)
        for event in events[:10]:  # Check first 10
            payload = event["payload"]
            self.assertIn("worker_id", payload)
            self.assertIn("event_index", payload)
            self.assertIn("timestamp", payload)

    def test_exactly_one_claim_winner(self):
        """Spawn N processes claiming same resource; assert exactly one wins."""
        num_claimants = 4
        resource = "shared_resource_1"

        # Create instances with unique ids
        instance_ids = [f"orchestrator_{i}" for i in range(num_claimants)]

        results = []
        with Pool(processes=num_claimants) as pool:
            async_results = [
                pool.apply_async(
                    _worker_try_claim,
                    ((self.db_path, resource, instance_id),),
                )
                for instance_id in instance_ids
            ]
            for async_result in async_results:
                try:
                    result = async_result.get(timeout=30)
                    results.append(result)
                except Exception as e:
                    self.fail(f"Claimant failed or timed out: {e}")

        # Exactly one should have success=True
        winners = [r for r in results if r["success"]]
        self.assertEqual(len(winners), 1, f"Expected 1 winner, got {len(winners)}")

        # Verify the winner is deterministic via fold_claims
        store = StateAPI(self.db_path)
        events = store.get("claims")
        claims = fold_claims(events)
        holder = claims.get(resource)

        # The holder should be the single winner
        self.assertEqual(holder, winners[0]["instance_id"])

        # All other claimants should agree on who won
        for result in results:
            if result["success"]:
                self.assertEqual(result["instance_id"], holder)

    def test_fail_closed_on_claim_error(self):
        """Verify try_claim returns False when append fails, never True."""
        resource = "test_resource"
        instance_id = "orchestrator_test"

        # Create a mock store that fails on append
        class FailingStore:
            def append(self, *args, **kwargs):
                raise sqlite3.OperationalError("database is locked")

            def get(self, stream):
                return []

        store = FailingStore()
        result = try_claim(store, resource, instance_id)

        # Must return False on any error
        self.assertFalse(result, "try_claim should fail-closed (return False) on append error")

    def test_release_idempotent(self):
        """Verify release is idempotent (can release same resource multiple times)."""
        resource = "test_resource_release"
        instance_id = "orchestrator_release_test"

        store = StateAPI(self.db_path)

        # First, claim the resource
        try_claim(store, resource, instance_id)

        # Release once
        release(store, resource, instance_id)

        # Verify released
        holder_after_first = current_holder(store, resource)
        self.assertNotEqual(holder_after_first, instance_id)

        # Release again (should be idempotent)
        release(store, resource, instance_id)

        # Verify still released
        holder_after_second = current_holder(store, resource)
        self.assertNotEqual(holder_after_second, instance_id)

    def test_current_holder_query(self):
        """Verify current_holder returns the correct holder or None."""
        store = StateAPI(self.db_path)

        resource = "holder_query_test"
        instance_1 = "orchestrator_1"
        instance_2 = "orchestrator_2"

        # Initially unclaimed
        self.assertIsNone(current_holder(store, resource))

        # Try claim with instance_1 (will win since it's first)
        success_1 = try_claim(store, resource, instance_1)
        self.assertTrue(success_1)

        # Current holder should be instance_1
        self.assertEqual(current_holder(store, resource), instance_1)

        # Try claim with instance_2 (should fail, instance_1 already won)
        success_2 = try_claim(store, resource, instance_2)
        self.assertFalse(success_2)

        # Holder should still be instance_1
        self.assertEqual(current_holder(store, resource), instance_1)

        # Release from instance_1
        release(store, resource, instance_1)

        # Now instance_2's claim becomes active (it's the lowest un-released claim)
        self.assertEqual(current_holder(store, resource), instance_2)

        # Release from instance_2 as well
        release(store, resource, instance_2)

        # Now should be truly unclaimed
        self.assertIsNone(current_holder(store, resource))

    def test_multiple_disjoint_resources(self):
        """Verify each resource has independent claims."""
        store = StateAPI(self.db_path)

        resource_1 = "resource_1"
        resource_2 = "resource_2"
        instance_1 = "orchestrator_1"
        instance_2 = "orchestrator_2"

        # instance_1 claims resource_1
        success_1a = try_claim(store, resource_1, instance_1)
        self.assertTrue(success_1a)

        # instance_2 claims resource_2
        success_2b = try_claim(store, resource_2, instance_2)
        self.assertTrue(success_2b)

        # Verify each holds their resource
        self.assertEqual(current_holder(store, resource_1), instance_1)
        self.assertEqual(current_holder(store, resource_2), instance_2)

        # instance_1 tries to claim resource_2 (should fail)
        success_1b = try_claim(store, resource_2, instance_1)
        self.assertFalse(success_1b)

        # Claims should be unchanged
        self.assertEqual(current_holder(store, resource_1), instance_1)
        self.assertEqual(current_holder(store, resource_2), instance_2)


if __name__ == "__main__":
    unittest.main()
