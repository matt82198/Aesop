"""Direct module-isolation unit tests for ui/collectors.py (wave-10 P0 seam tests,
promised follow-up to the wave-9 collectors/agents/sse split).

These tests `import collectors` directly — no HTTP server, no importlib-loading
of serve.py. Each fixture points AESOP_ROOT/AESOP_STATE_ROOT/AESOP_TRANSCRIPTS_ROOT
at an isolated tmp dir and calls config.reload() before exercising collectors.*.
collectors.py functions read config.* attributes at call time (not at import
time), so a fresh config.reload() per test is sufficient — no need to re-import
the collectors module itself between tests.

Covers: parse_audit_backlog tier parsing + glyph mapping, tracker CRUD
(create/get/update/delete + soft-delete), load_tracker corrupt-JSON quarantine,
_snapshot_orchestrator_status normalization, drain_tracker_inbox idempotency +
malformed-line rejection, get_alerts severity counting.

Run: python -m pytest tests/test_collectors.py -q
     python -m unittest tests.test_collectors
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

UI_DIR = Path(__file__).parent.parent / "ui"
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))

import config  # noqa: E402
import collectors  # noqa: E402

ENV_KEYS = ("AESOP_ROOT", "AESOP_STATE_ROOT", "AESOP_TRANSCRIPTS_ROOT",
            "AESOP_UI_COLLECT_INTERVAL", "PORT")


class CollectorsFixtureCase(unittest.TestCase):
    def setUp(self):
        self.fixture_root = Path(tempfile.mkdtemp(prefix="aesop-collectors-test-"))
        self.state_dir = self.fixture_root / "state"
        self.state_dir.mkdir(parents=True)
        (self.fixture_root / "transcripts").mkdir()
        self._saved_env = {k: os.environ.get(k) for k in ENV_KEYS}
        os.environ["AESOP_ROOT"] = str(self.fixture_root)
        os.environ["AESOP_STATE_ROOT"] = str(self.state_dir)
        os.environ["AESOP_TRANSCRIPTS_ROOT"] = str(self.fixture_root / "transcripts")
        os.environ["AESOP_UI_COLLECT_INTERVAL"] = "0.2"
        config.reload()

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.fixture_root, ignore_errors=True)


# ------------------------------------------------------------------------------
# parse_audit_backlog: tier parsing + glyph mapping
# ------------------------------------------------------------------------------

class TestParseAuditBacklog(CollectorsFixtureCase):
    def test_missing_file_returns_empty_tiers(self):
        self.assertFalse(config.AUDIT_BACKLOG_FILE.exists())
        result = collectors.parse_audit_backlog()
        self.assertEqual(result, {"tiers": []})

    def test_glyph_mapping_and_counts(self):
        content = (
            "## P0\n"
            "- ✅ **[sec] Fix XSS in dashboard**\n"
            "- \U0001f535 **[perf] Optimize query**\n"
            "- ⬜ **[ux] Improve button spacing**\n"
            "- ⏸ **[decision] Needs stakeholder input**\n"
            "\n"
            "## P1\n"
            "- ✅ **[test] Add coverage**\n"
        )
        config.AUDIT_BACKLOG_FILE.write_text(content, encoding="utf-8")

        result = collectors.parse_audit_backlog()
        self.assertEqual([t["tier"] for t in result["tiers"]], ["P0", "P1"])

        p0 = result["tiers"][0]
        self.assertEqual(p0["total"], 4)
        self.assertEqual(p0["done"], 1)
        self.assertEqual(p0["inflight"], 1)
        self.assertEqual(p0["todo"], 1)  # the pause glyph counts toward total only
        self.assertEqual(
            p0["items"],
            [
                {"status": "✅", "tag": "[sec]", "title": "Fix XSS in dashboard"},
                {"status": "\U0001f535", "tag": "[perf]", "title": "Optimize query"},
                {"status": "⬜", "tag": "[ux]", "title": "Improve button spacing"},
                {"status": "⏸", "tag": "[decision]", "title": "Needs stakeholder input"},
            ],
        )

        p1 = result["tiers"][1]
        self.assertEqual(p1["total"], 1)
        self.assertEqual(p1["done"], 1)

    def test_tier_header_matched_by_regex_prefix_survives_suffix_rename(self):
        # Header carries an evolving suffix ("(do first, wave 5)"); must still
        # match the P0 tier via prefix regex, not an exact-string comparison.
        content = (
            "## P0 (do first, wave 5, from five-lens re-audit)\n"
            "- ✅ **[sec] Item A**\n"
        )
        config.AUDIT_BACKLOG_FILE.write_text(content, encoding="utf-8")

        result = collectors.parse_audit_backlog()
        self.assertEqual(len(result["tiers"]), 1)
        self.assertEqual(result["tiers"][0]["tier"], "P0")
        self.assertEqual(result["tiers"][0]["total"], 1)

    def test_unknown_header_resets_current_tier_no_bleed_through(self):
        # A "## Features" header between two P0-lookalike blocks must NOT let its
        # item bleed through and get attributed to the previous tier.
        content = (
            "## P0\n"
            "- ✅ **[sec] Item A**\n"
            "\n"
            "## Features (user-requested)\n"
            "- ✅ **[feat] Should not be attributed to P0**\n"
            "\n"
            "## P1\n"
            "- \U0001f535 **[perf] Item B**\n"
        )
        config.AUDIT_BACKLOG_FILE.write_text(content, encoding="utf-8")

        result = collectors.parse_audit_backlog()
        tiers_by_name = {t["tier"]: t for t in result["tiers"]}
        self.assertEqual(set(tiers_by_name), {"P0", "P1"})
        self.assertEqual(tiers_by_name["P0"]["total"], 1)
        self.assertEqual(tiers_by_name["P0"]["items"][0]["title"], "Item A")
        self.assertEqual(tiers_by_name["P1"]["total"], 1)

    def test_stops_parsing_at_landing_log_section(self):
        content = (
            "## P0\n"
            "- ✅ **[sec] Item A**\n"
            "\n"
            "## Landing log\n"
            "- ✅ **[sec] Should not appear**\n"
        )
        config.AUDIT_BACKLOG_FILE.write_text(content, encoding="utf-8")

        result = collectors.parse_audit_backlog()
        self.assertEqual(len(result["tiers"]), 1)
        self.assertEqual(result["tiers"][0]["total"], 1)


# ------------------------------------------------------------------------------
# Tracker CRUD: create / get / update / delete (soft-delete)
# ------------------------------------------------------------------------------

class TestTrackerCrud(CollectorsFixtureCase):
    def test_create_tracker_item_applies_defaults_and_persists(self):
        item = collectors.create_tracker_item({"title": "New item"})

        self.assertEqual(item["title"], "New item")
        self.assertEqual(item["priority"], "P1")
        self.assertEqual(item["status"], "todo")
        self.assertEqual(item["lane"], "proposed")
        self.assertEqual(item["source"], "manual")
        self.assertEqual(item["tags"], [])
        self.assertIsNone(item["notes"])
        self.assertIsNone(item["pr_link"])
        self.assertIsNone(item["completed_at"])
        self.assertTrue(item["created_at"].endswith("Z"))
        self.assertEqual(len(item["id"]), 12)  # secrets.token_hex(6)

        reloaded = collectors.load_tracker()
        self.assertEqual(len(reloaded["items"]), 1)
        self.assertEqual(reloaded["items"][0]["id"], item["id"])

    def test_get_tracker_items_filters_by_status_and_priority(self):
        collectors.create_tracker_item({"title": "A", "status": "todo", "priority": "P0"})
        collectors.create_tracker_item({"title": "B", "status": "in-progress", "priority": "P0"})
        collectors.create_tracker_item({"title": "C", "status": "todo", "priority": "P1"})

        p0_todo = collectors.get_tracker_items(status="todo", priority="P0")
        self.assertEqual([i["title"] for i in p0_todo], ["A"])

        all_p0 = collectors.get_tracker_items(priority="P0")
        self.assertEqual({i["title"] for i in all_p0}, {"A", "B"})

        all_todo = collectors.get_tracker_items(status="todo")
        self.assertEqual({i["title"] for i in all_todo}, {"A", "C"})

    def test_update_tracker_item_sets_completed_at_only_on_done_transition(self):
        item = collectors.create_tracker_item({"title": "Task"})
        self.assertIsNone(item["completed_at"])

        updated = collectors.update_tracker_item(item["id"], {"status": "done"})
        self.assertEqual(updated["status"], "done")
        self.assertIsNotNone(updated["completed_at"])
        first_completed_at = updated["completed_at"]

        # A later edit that doesn't re-send status="done" must not clobber
        # the already-set completed_at timestamp.
        updated_again = collectors.update_tracker_item(item["id"], {"notes": "closed via PR"})
        self.assertEqual(updated_again["completed_at"], first_completed_at)
        self.assertEqual(updated_again["notes"], "closed via PR")

    def test_update_tracker_item_missing_id_raises(self):
        with self.assertRaises(Exception) as ctx:
            collectors.update_tracker_item("does-not-exist", {"status": "done"})
        self.assertIn("404", str(ctx.exception))

    def test_delete_tracker_item_soft_deletes_without_removing_row(self):
        item = collectors.create_tracker_item({"title": "To archive"})

        deleted = collectors.delete_tracker_item(item["id"])
        self.assertEqual(deleted["status"], "archived")

        reloaded = collectors.load_tracker()
        self.assertEqual(len(reloaded["items"]), 1)  # still present, not removed
        self.assertEqual(reloaded["items"][0]["status"], "archived")

    def test_delete_tracker_item_missing_id_raises(self):
        with self.assertRaises(Exception) as ctx:
            collectors.delete_tracker_item("does-not-exist")
        self.assertIn("404", str(ctx.exception))


# ------------------------------------------------------------------------------
# load_tracker: corrupt-JSON quarantine
# ------------------------------------------------------------------------------

class TestLoadTrackerCorruptQuarantine(CollectorsFixtureCase):
    def test_missing_tracker_file_returns_empty_without_creating_file(self):
        result = collectors.load_tracker()
        self.assertEqual(result, {"version": 1, "items": []})
        self.assertFalse(config.TRACKER_FILE.exists())

    def test_corrupt_json_is_quarantined_and_load_returns_empty(self):
        config.TRACKER_FILE.write_text("{not valid json!!", encoding="utf-8")

        result = collectors.load_tracker()

        self.assertEqual(result, {"version": 1, "items": []})
        self.assertFalse(config.TRACKER_FILE.exists())
        corrupt_path = config.TRACKER_FILE.with_suffix(".json.corrupt")
        self.assertTrue(corrupt_path.exists())
        self.assertEqual(corrupt_path.read_text(encoding="utf-8"), "{not valid json!!")

    def test_valid_json_missing_version_key_is_also_quarantined(self):
        config.TRACKER_FILE.write_text(json.dumps({"items": []}), encoding="utf-8")

        result = collectors.load_tracker()

        self.assertEqual(result, {"version": 1, "items": []})
        corrupt_path = config.TRACKER_FILE.with_suffix(".json.corrupt")
        self.assertTrue(corrupt_path.exists())


# ------------------------------------------------------------------------------
# _snapshot_orchestrator_status: normalization
# ------------------------------------------------------------------------------

class TestSnapshotOrchestratorStatus(CollectorsFixtureCase):
    def test_missing_file_returns_empty_orchestrators(self):
        result = collectors._snapshot_orchestrator_status()
        self.assertEqual(result, {"orchestrators": []})

    def test_bare_object_is_wrapped_with_age_and_stale(self):
        old_updated_at = (datetime.now(timezone.utc) - timedelta(seconds=3700)).isoformat().replace("+00:00", "Z")
        status_file = config.STATE_DIR / "orchestrator-status.json"
        status_file.write_text(
            json.dumps({"id": "orch-1", "role": "main", "updated_at": old_updated_at}),
            encoding="utf-8",
        )

        result = collectors._snapshot_orchestrator_status()

        self.assertEqual(len(result["orchestrators"]), 1)
        entry = result["orchestrators"][0]
        self.assertEqual(entry["id"], "orch-1")
        self.assertGreaterEqual(entry["age_seconds"], 3600)
        self.assertTrue(entry["stale"])

    def test_bare_object_recent_updated_at_is_not_stale(self):
        recent_updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        status_file = config.STATE_DIR / "orchestrator-status.json"
        status_file.write_text(
            json.dumps({"id": "orch-2", "role": "main", "updated_at": recent_updated_at}),
            encoding="utf-8",
        )

        result = collectors._snapshot_orchestrator_status()

        entry = result["orchestrators"][0]
        self.assertLess(entry["age_seconds"], 1800)
        self.assertFalse(entry["stale"])

    def test_already_normalized_list_shape_passes_through_unchanged(self):
        data = {"orchestrators": [{"id": "a"}, {"id": "b"}]}
        status_file = config.STATE_DIR / "orchestrator-status.json"
        status_file.write_text(json.dumps(data), encoding="utf-8")

        result = collectors._snapshot_orchestrator_status()
        self.assertEqual(result, data)  # exact passthrough, no age/stale injected

    def test_malformed_non_dict_json_returns_empty_orchestrators(self):
        status_file = config.STATE_DIR / "orchestrator-status.json"
        status_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        result = collectors._snapshot_orchestrator_status()
        self.assertEqual(result, {"orchestrators": []})


# ------------------------------------------------------------------------------
# drain_tracker_inbox: idempotency + malformed-line rejection
# ------------------------------------------------------------------------------

class TestDrainTrackerInbox(CollectorsFixtureCase):
    def _inbox_file(self):
        return config.STATE_DIR / ".tracker-inbox.jsonl"

    def test_same_source_and_title_is_not_duplicated_across_drains(self):
        entry = {"title": "Task X", "priority": "P1", "source": "audit-scan"}
        self._inbox_file().write_text(json.dumps(entry) + "\n", encoding="utf-8")

        first_created = collectors.drain_tracker_inbox()
        self.assertEqual(len(first_created), 1)
        self.assertFalse(self._inbox_file().exists())

        # Re-drop the inbox with the SAME source+title plus one genuinely new entry.
        entries = [
            entry,
            {"title": "Task Y", "priority": "P1", "source": "audit-scan"},
        ]
        self._inbox_file().write_text(
            "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8"
        )

        second_created = collectors.drain_tracker_inbox()
        self.assertEqual(len(second_created), 1)
        self.assertEqual(second_created[0]["title"], "Task Y")

        tracker = collectors.load_tracker()
        titles = [i["title"] for i in tracker["items"]]
        self.assertEqual(sorted(titles), ["Task X", "Task Y"])  # no duplicate Task X

    def test_malformed_lines_are_rejected_not_raised(self):
        lines = [
            json.dumps({"title": "Good entry", "source": "audit-scan"}),
            "{this is not valid json",
            json.dumps([1, 2, 3]),  # valid JSON, but not a dict
        ]
        self._inbox_file().write_text("\n".join(lines) + "\n", encoding="utf-8")

        created = collectors.drain_tracker_inbox()

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["title"], "Good entry")
        self.assertFalse(self._inbox_file().exists())

        rejects_file = config.STATE_DIR / ".tracker-inbox.rejects"
        self.assertTrue(rejects_file.exists())
        rejects_content = rejects_file.read_text(encoding="utf-8")
        self.assertIn("{this is not valid json", rejects_content)
        self.assertIn("[1, 2, 3]", rejects_content)

    def test_missing_inbox_file_returns_empty_list(self):
        self.assertFalse(self._inbox_file().exists())
        self.assertEqual(collectors.drain_tracker_inbox(), [])


# ------------------------------------------------------------------------------
# get_alerts: severity counting, skipping NOTE:/RESOLVED-FP
# ------------------------------------------------------------------------------

class TestGetAlerts(CollectorsFixtureCase):
    def test_missing_alerts_log_returns_zero_count(self):
        result = collectors.get_alerts()
        self.assertEqual(result, {"count": 0, "lines": []})

    def test_note_and_resolved_fp_lines_are_excluded_from_count(self):
        lines = [
            "ALERT: secret found in file1",
            "ALERT: secret found in file2",
            "NOTE: reviewed, ignore",
            "ALERT: secret found in file3",
            "RESOLVED-FP: false positive confirmed",
            "ALERT: secret found in file4",
            "ALERT: secret found in file5",
            "ALERT: secret found in file6",
        ]
        config.ALERTS_LOG.write_text("\n".join(lines), encoding="utf-8")

        result = collectors.get_alerts()

        self.assertEqual(result["count"], 6)
        self.assertEqual(len(result["lines"]), 5)  # only last 5 unreviewed shown
        for shown in result["lines"]:
            self.assertNotIn("NOTE:", shown)
            self.assertNotIn("RESOLVED-FP", shown)
        self.assertEqual(result["lines"][-1], "ALERT: secret found in file6")


if __name__ == "__main__":
    unittest.main()
