#!/usr/bin/env python3
"""Test suite for wave templates: preset manifest validation and generation.

Validates that wave-manifest presets (SaaS, data, library) conform to the
required schema and can be loaded and instantiated correctly.

Tests:
  - Template file existence and valid JSON/YAML format
  - Manifest schema compliance (required fields, structure)
  - Placeholder substitution (ownsFiles, testCmd)
  - No overlap in file ownership across items
  - Linux parity (paths, newlines, encoding)
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add tools/ to path for imports.
REPO = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    from wave_templates import (
        load_preset,
        instantiate_template,
        validate_manifest,
        PRESETS_DIR,
    )
except ImportError as e:
    print(f"Failed to import wave_templates: {e}")
    sys.exit(1)


class TestWaveTemplatesSchemaCompliance(unittest.TestCase):
    """Validate manifest schema compliance for all presets."""

    def test_preset_files_exist(self):
        """Each preset file should exist."""
        presets_to_test = ["saas", "data", "library"]
        for preset_name in presets_to_test:
            preset_file = PRESETS_DIR / f"{preset_name}.json"
            self.assertTrue(
                preset_file.exists(),
                f"Preset file missing: {preset_file}"
            )

    def test_preset_json_valid(self):
        """Each preset file should contain valid JSON."""
        presets_to_test = ["saas", "data", "library"]
        for preset_name in presets_to_test:
            try:
                preset = load_preset(preset_name)
                self.assertIsNotNone(preset)
                self.assertIsInstance(preset, dict)
            except Exception as e:
                self.fail(f"Failed to load preset {preset_name}: {e}")

    def test_manifest_schema_compliance_saas(self):
        """SaaS preset should generate valid manifests."""
        preset = load_preset("saas")
        manifest = instantiate_template(preset, project_name="my-saas", base_dir="/tmp/test")
        self._validate_manifest_structure(manifest)

    def test_manifest_schema_compliance_data(self):
        """Data preset should generate valid manifests."""
        preset = load_preset("data")
        manifest = instantiate_template(preset, project_name="my-data", base_dir="/tmp/test")
        self._validate_manifest_structure(manifest)

    def test_manifest_schema_compliance_library(self):
        """Library preset should generate valid manifests."""
        preset = load_preset("library")
        manifest = instantiate_template(preset, project_name="my-lib", base_dir="/tmp/test")
        self._validate_manifest_structure(manifest)

    def _validate_manifest_structure(self, manifest):
        """Helper to validate core manifest structure."""
        # Must have items array
        self.assertIn("items", manifest, "Manifest missing 'items' array")
        items = manifest["items"]
        self.assertIsInstance(items, list, "'items' must be a list")
        self.assertGreater(len(items), 0, "'items' must not be empty")

        # Each item must have required fields
        required_item_fields = {"slug", "prompt", "ownsFiles"}
        for item in items:
            for field in required_item_fields:
                self.assertIn(
                    field, item,
                    f"Item {item.get('slug', 'unknown')} missing required field '{field}'"
                )

            # slug must be non-empty string
            self.assertIsInstance(item["slug"], str)
            self.assertGreater(len(item["slug"]), 0)

            # ownsFiles must be a non-empty list
            self.assertIsInstance(item["ownsFiles"], list)
            self.assertGreater(len(item["ownsFiles"]), 0)

            # prompt must be non-empty string
            self.assertIsInstance(item["prompt"], str)
            self.assertGreater(len(item["prompt"]), 0)

    def test_no_file_ownership_overlap(self):
        """No two items should own the same file."""
        presets_to_test = ["saas", "data", "library"]
        for preset_name in presets_to_test:
            preset = load_preset(preset_name)
            manifest = instantiate_template(preset, project_name="test", base_dir="/tmp")

            owner_map = {}
            conflicts = []
            for item in manifest.get("items", []):
                for f in item.get("ownsFiles", []):
                    if f in owner_map:
                        conflicts.append((f, owner_map[f], item["slug"]))
                    else:
                        owner_map[f] = item["slug"]

            self.assertEqual(
                len(conflicts), 0,
                f"File ownership overlap in {preset_name}: {conflicts}"
            )

    def test_placeholder_substitution(self):
        """Placeholders like {project_name} should be substituted."""
        preset = load_preset("saas")
        project_name = "my-awesome-project"
        manifest = instantiate_template(
            preset,
            project_name=project_name,
            base_dir="/workspace"
        )

        manifest_str = json.dumps(manifest)
        # Should NOT contain placeholder strings after substitution
        self.assertNotIn("{project_name}", manifest_str)
        self.assertNotIn("{base_dir}", manifest_str)

    def test_manifest_validation_passes(self):
        """validate_manifest() should pass for all generated manifests."""
        presets_to_test = ["saas", "data", "library"]
        for preset_name in presets_to_test:
            preset = load_preset(preset_name)
            manifest = instantiate_template(preset, project_name="test", base_dir="/tmp")
            # Should not raise an exception
            try:
                validate_manifest(manifest)
            except Exception as e:
                self.fail(f"Validation failed for {preset_name}: {e}")

    def test_linux_parity_paths(self):
        """Paths should use forward slashes (POSIX) for portability."""
        presets_to_test = ["saas", "data", "library"]
        for preset_name in presets_to_test:
            preset = load_preset(preset_name)
            manifest = instantiate_template(preset, project_name="test", base_dir="/workspace")

            for item in manifest.get("items", []):
                for file_path in item.get("ownsFiles", []):
                    # On Windows, os.sep is '\', but we want '/' for portability
                    self.assertNotIn("\\", file_path,
                        f"Path should use forward slashes, got: {file_path}")

    def test_linux_parity_encoding(self):
        """Files should be UTF-8 with LF line endings."""
        presets_to_test = ["saas", "data", "library"]
        for preset_name in presets_to_test:
            preset_file = PRESETS_DIR / f"{preset_name}.json"
            content = preset_file.read_text(encoding="utf-8")
            # Should not contain CRLF
            self.assertNotIn("\r\n", content,
                f"{preset_name}.json should use LF, not CRLF")


class TestWaveTemplatesIntegration(unittest.TestCase):
    """Integration tests for template instantiation."""

    def test_instantiate_saas_template(self):
        """Can instantiate a SaaS manifest with parameters."""
        preset = load_preset("saas")
        manifest = instantiate_template(
            preset,
            project_name="payment-api",
            base_dir="/home/dev/projects"
        )
        self.assertGreater(len(manifest["items"]), 0)

    def test_instantiate_data_template(self):
        """Can instantiate a data-project manifest with parameters."""
        preset = load_preset("data")
        manifest = instantiate_template(
            preset,
            project_name="analytics-pipeline",
            base_dir="/opt/data"
        )
        self.assertGreater(len(manifest["items"]), 0)

    def test_instantiate_library_template(self):
        """Can instantiate a library manifest with parameters."""
        preset = load_preset("library")
        manifest = instantiate_template(
            preset,
            project_name="crypto-utils",
            base_dir="/src"
        )
        self.assertGreater(len(manifest["items"]), 0)

    def test_different_parameters_yield_different_manifests(self):
        """Different project names should yield different manifests."""
        preset = load_preset("saas")
        m1 = instantiate_template(preset, project_name="app1", base_dir="/tmp")
        m2 = instantiate_template(preset, project_name="app2", base_dir="/tmp")

        # The manifests should differ (e.g., in slugs, file paths)
        self.assertNotEqual(
            json.dumps(m1, sort_keys=True),
            json.dumps(m2, sort_keys=True)
        )


if __name__ == "__main__":
    unittest.main()
