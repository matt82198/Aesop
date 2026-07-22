#!/usr/bin/env python3
"""Doc-contract test for backend configuration schema.

Extracts JSON config snippets from docs/INSTALL.md and validates each
against load_backend_config to prevent doc/code schema drift.
"""

import json
import re
import tempfile
from pathlib import Path

import pytest

# Add driver to path for imports
import sys
driver_path = Path(__file__).parent.parent / "driver"
sys.path.insert(0, str(driver_path))

from backend_config import load_backend_config


def extract_json_blocks_from_markdown(md_content: str) -> list[dict]:
    """Extract all JSON code blocks from markdown content.

    Returns list of dicts with 'line_num' and 'json_obj' keys.
    """
    blocks = []
    lines = md_content.split('\n')
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith('```json'):
            # Found a JSON block
            start_line = i
            i += 1
            json_lines = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                json_lines.append(lines[i])
                i += 1
            if i < len(lines):  # Found closing ```
                json_text = '\n'.join(json_lines)
                try:
                    json_obj = json.loads(json_text)
                    blocks.append({
                        'line_num': start_line + 1,
                        'json_obj': json_obj,
                        'raw': json_text
                    })
                except json.JSONDecodeError as e:
                    raise AssertionError(
                        f"Invalid JSON in INSTALL.md at line {start_line + 1}: {e}"
                    )
        i += 1
    return blocks


def test_extract_json_from_install_md():
    """Verify that we can extract JSON blocks from INSTALL.md."""
    install_path = Path(__file__).parent.parent / "docs" / "INSTALL.md"
    assert install_path.exists(), f"INSTALL.md not found at {install_path}"

    md_content = install_path.read_text(encoding='utf-8')
    blocks = extract_json_blocks_from_markdown(md_content)

    # Should find at least 2 JSON blocks in INSTALL.md
    # (the general aesop.config.json example and backend examples)
    assert len(blocks) >= 2, f"Expected at least 2 JSON blocks, found {len(blocks)}"


def test_backend_config_snippets_from_install_md():
    """Load and validate every JSON config snippet from INSTALL.md.

    This test ensures documentation schema matches the actual implementation,
    preventing doc/code drift.
    """
    install_path = Path(__file__).parent.parent / "docs" / "INSTALL.md"
    md_content = install_path.read_text(encoding='utf-8')
    blocks = extract_json_blocks_from_markdown(md_content)

    # Filter to blocks that have a 'backend' key (backend configuration examples)
    backend_blocks = [b for b in blocks if isinstance(b['json_obj'], dict)
                      and 'backend' in b['json_obj']]

    assert len(backend_blocks) > 0, "No backend configuration examples found in INSTALL.md"

    # For each backend config block, verify it can be loaded without error
    for i, block in enumerate(backend_blocks):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "aesop.config.json"
            config_path.write_text(json.dumps(block['json_obj']), encoding='utf-8')

            # This should not raise an exception
            try:
                config = load_backend_config(str(config_path))
                # Verify the backend field is present and valid
                assert 'backend' in config, f"Loaded config missing 'backend' field: {config}"
                assert isinstance(config['backend'], str), \
                    f"'backend' field must be string, got {type(config['backend'])}: {config}"
                assert config['backend'] in ('claude', 'codex', 'openai-compatible'), \
                    f"Unknown backend: {config['backend']}"
            except Exception as e:
                raise AssertionError(
                    f"Backend config snippet at line {block['line_num']} failed validation:\n"
                    f"Config: {json.dumps(block['json_obj'], indent=2)}\n"
                    f"Error: {e}"
                ) from e


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
