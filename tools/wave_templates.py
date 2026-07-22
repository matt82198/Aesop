#!/usr/bin/env python3
"""Wave template manager: load and instantiate preset manifests for common project types.

Provides reusable wave-manifest scaffolds for bootstrapping first waves:
  - SaaS: API + frontend + ops (typical 3-tier)
  - Data: pipeline + analytics + infra (ETL/analytics pattern)
  - Library: core + tests + docs (reusable module pattern)

Each preset is a JSON file with template variables ({project_name}, {base_dir})
that are substituted during instantiation.

Usage (CLI):
  python tools/wave_templates.py <preset> --project-name my-app --base-dir /workspace

Usage (Python API):
  from wave_templates import load_preset, instantiate_template
  preset = load_preset("saas")
  manifest = instantiate_template(preset, project_name="my-app", base_dir="/workspace")

Invariants:
  - Presets live in templates/wave-presets/ (git-tracked, editable)
  - No file ownership overlap within a manifest (preflight guard)
  - All paths use forward slashes (POSIX) for cross-platform compatibility
  - UTF-8 encoding, LF line endings (Linux parity)
  - Manifests are fully resolved JSON (no further substitution by the wave engine)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Presets directory (relative to this file's location).
TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
PRESETS_DIR = REPO_ROOT / "templates" / "wave-presets"


def load_preset(preset_name: str) -> Dict[str, Any]:
    """Load a preset manifest template by name.

    Args:
        preset_name: preset identifier (e.g., "saas", "data", "library")

    Returns:
        dict with preset template (contains {project_name}, {base_dir} placeholders)

    Raises:
        FileNotFoundError: if preset file does not exist
        json.JSONDecodeError: if preset JSON is invalid
    """
    preset_file = PRESETS_DIR / f"{preset_name}.json"
    if not preset_file.exists():
        raise FileNotFoundError(f"Preset not found: {preset_file}")

    with open(preset_file, "r", encoding="utf-8") as f:
        return json.load(f)


def instantiate_template(
    preset: Dict[str, Any],
    project_name: str,
    base_dir: str,
) -> Dict[str, Any]:
    """Instantiate a preset template with project-specific values.

    Replaces placeholder strings {project_name} and {base_dir} throughout
    the preset. Also derives a wave_id and wave_description if not provided.

    Args:
        preset: template dict from load_preset()
        project_name: user's project/app name (e.g., "payment-api")
        base_dir: root working directory (e.g., "/workspace/my-app")

    Returns:
        dict with fully resolved manifest (ready to pass to wave engine)
    """
    # Deep copy to avoid mutating the original preset.
    manifest = json.loads(json.dumps(preset))

    # Utility to substitute placeholders recursively.
    def substitute(obj):
        if isinstance(obj, str):
            return obj.replace("{project_name}", project_name).replace("{base_dir}", base_dir)
        elif isinstance(obj, dict):
            return {k: substitute(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [substitute(item) for item in obj]
        else:
            return obj

    manifest = substitute(manifest)

    # Add wave metadata if not already present.
    if "wave_id" not in manifest:
        manifest["wave_id"] = f"wave-{project_name}".lower().replace(" ", "-")
    if "wave_description" not in manifest:
        manifest["wave_description"] = f"Bootstrap wave for {project_name}"

    return manifest


def validate_manifest(manifest: Dict[str, Any]) -> None:
    """Validate manifest schema and invariants.

    Checks:
      - items array exists and is non-empty
      - each item has required fields (slug, prompt, ownsFiles)
      - no file ownership overlap
      - no placeholder strings remain

    Args:
        manifest: the manifest dict to validate

    Raises:
        ValueError: if validation fails
    """
    if "items" not in manifest:
        raise ValueError("Manifest missing 'items' array")

    items = manifest["items"]
    if not isinstance(items, list) or len(items) == 0:
        raise ValueError("'items' must be a non-empty list")

    # Check required fields and validate structure.
    required_fields = {"slug", "prompt", "ownsFiles"}
    owner_map = {}
    conflicts = []

    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"Item must be a dict, got {type(item)}")

        # Check required fields.
        for field in required_fields:
            if field not in item:
                raise ValueError(f"Item {item.get('slug', 'unknown')} missing '{field}'")

        slug = item["slug"]
        if not isinstance(slug, str) or not slug:
            raise ValueError(f"Item slug must be non-empty string, got {slug}")

        # Check ownsFiles.
        owned_files = item.get("ownsFiles", [])
        if not isinstance(owned_files, list) or not owned_files:
            raise ValueError(f"Item {slug} must have non-empty ownsFiles list")

        # Track file ownership.
        for f in owned_files:
            if f in owner_map:
                conflicts.append((f, owner_map[f], slug))
            else:
                owner_map[f] = slug

    if conflicts:
        raise ValueError(f"File ownership overlap: {conflicts}")

    # Check no placeholders remain.
    manifest_str = json.dumps(manifest)
    if "{project_name}" in manifest_str or "{base_dir}" in manifest_str:
        raise ValueError("Manifest contains unsubstituted placeholders")


def main():
    """CLI entry point: load preset and output resolved manifest."""
    parser = argparse.ArgumentParser(
        description="Load and instantiate a wave manifest preset"
    )
    parser.add_argument(
        "preset",
        help="preset name: saas, data, or library"
    )
    parser.add_argument(
        "--project-name",
        required=True,
        help="project/app name (e.g., 'payment-api')"
    )
    parser.add_argument(
        "--base-dir",
        required=True,
        help="base working directory (e.g., '/workspace/my-app')"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="output file (default: stdout)"
    )

    args = parser.parse_args()

    try:
        # Load and instantiate.
        preset = load_preset(args.preset)
        manifest = instantiate_template(preset, args.project_name, args.base_dir)

        # Validate.
        validate_manifest(manifest)

        # Output.
        output_json = json.dumps(manifest, indent=2)
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(output_json, encoding="utf-8")
            print(f"Manifest written to {output_path}", file=sys.stderr)
        else:
            print(output_json)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
