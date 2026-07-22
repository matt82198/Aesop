#!/usr/bin/env python3
"""
verify_ui_trio.py — Browser proof covering three UI trio panels:
1. Gantt Timeline (agent phase visualization)
2. Audit Tail Stream (latest audit/verification outcomes)
3. Live Reasoning Transparency (per-agent reasoning activity)

Uses AESOP_PROOF_FIXTURES pattern with self-hosted UI server.
Tests that endpoints return valid data and components are renderable.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any

REPO = Path(__file__).resolve().parent.parent


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def wait_for_server(port: int, timeout_s: float = 30.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2):
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False

# Test fixtures path
FIXTURES_PATH = Path(__file__).parent / 'verify_ui_trio_fixtures.json'

def load_fixtures() -> Dict[str, Any]:
    """Load or create test fixtures."""
    if FIXTURES_PATH.exists():
        with open(FIXTURES_PATH) as f:
            return json.load(f)

    # Create default fixtures for testing
    fixtures = {
        'gantt_endpoint': '/api/wave/gantt',
        'audit_endpoint': '/api/wave/audit-tail',
        'reasoning_endpoint': '/api/wave/reasoning-tail',
        'expected_keys': {
            'gantt': ['available', 'agents', 'at'],
            'audit': ['available', 'audit_items', 'at'],
            'reasoning': ['available', 'agents', 'at'],
        }
    }

    with open(FIXTURES_PATH, 'w') as f:
        json.dump(fixtures, f, indent=2)

    return fixtures


def test_gantt_endpoint(base_url: str) -> bool:
    """Test GET /api/wave/gantt returns valid Gantt data."""
    try:
        url = f"{base_url}/api/wave/gantt"
        with urllib.request.urlopen(url, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))

            # Validate structure
            assert isinstance(data, dict), "Gantt response must be dict"
            assert 'available' in data, "Missing 'available' field"
            assert 'agents' in data, "Missing 'agents' field"
            assert 'at' in data, "Missing 'at' timestamp"

            # Validate agents list (even if empty when no active workflow)
            assert isinstance(data['agents'], list), "agents must be list"

            if data['available'] and data['agents']:
                # If available, check agent structure
                for agent in data['agents']:
                    assert 'id' in agent, "Agent missing 'id'"
                    assert 'phases' in agent, "Agent missing 'phases'"
                    assert 'total_duration_sec' in agent, "Agent missing 'total_duration_sec'"
                    assert 'status' in agent, "Agent missing 'status'"

            print("[PASS] Gantt endpoint valid")
            return True
    except Exception as e:
        print(f"[FAIL] Gantt endpoint failed: {e}")
        return False


def test_audit_endpoint(base_url: str) -> bool:
    """Test GET /api/wave/audit-tail returns valid audit data."""
    try:
        url = f"{base_url}/api/wave/audit-tail"
        with urllib.request.urlopen(url, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))

            # Validate structure
            assert isinstance(data, dict), "Audit response must be dict"
            assert 'available' in data, "Missing 'available' field"
            assert 'audit_items' in data, "Missing 'audit_items' field"
            assert 'at' in data, "Missing 'at' timestamp"

            # Validate items list
            assert isinstance(data['audit_items'], list), "audit_items must be list"

            if data['available'] and data['audit_items']:
                # Check item structure
                for item in data['audit_items']:
                    assert 'type' in item, "Item missing 'type' field"
                    assert item['type'] in ['audit_backlog', 'verdict'], "Invalid item type"

            print("[PASS] Audit endpoint valid")
            return True
    except Exception as e:
        print(f"[FAIL] Audit endpoint failed: {e}")
        return False


def test_reasoning_endpoint(base_url: str) -> bool:
    """Test GET /api/wave/reasoning-tail returns valid reasoning data with proper redaction."""
    import re

    try:
        url = f"{base_url}/api/wave/reasoning-tail"
        with urllib.request.urlopen(url, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))

            # Validate structure
            assert isinstance(data, dict), "Reasoning response must be dict"
            assert 'available' in data, "Missing 'available' field"
            assert 'agents' in data, "Missing 'agents' field"
            assert 'at' in data, "Missing 'at' timestamp"

            # Validate agents list
            assert isinstance(data['agents'], list), "agents must be list"

            if data['available'] and data['agents']:
                # Check agent structure
                for agent in data['agents']:
                    assert 'id' in agent, "Agent missing 'id'"
                    assert 'phase' in agent, "Agent missing 'phase'"
                    assert 'reasoning' in agent, "Agent missing 'reasoning'"
                    assert 'activity_age_sec' in agent, "Agent missing 'activity_age_sec'"
                    assert 'token_estimate' in agent, "Agent missing 'token_estimate'"

                    # Verify reasoning is redacted per transcript_digest contract:
                    # must not contain absolute paths, emails, or tokens; uses [PATH], [EMAIL], [USER], etc.
                    reasoning = agent['reasoning']

                    # Patterns that should NOT appear in redacted reasoning
                    unredacted_patterns = [
                        r'[A-Za-z]:\\',  # Windows path (C:\, D:\, etc.)
                        r'(?<![\[\w])/[a-z]',  # POSIX absolute path (/home, /c/, etc.)
                        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # Email
                        r'(?:sk-|ghp_|gho_|xox[baprs]-|AKIA)',  # Token patterns
                    ]

                    for pattern in unredacted_patterns:
                        matches = re.findall(pattern, reasoning)
                        assert not matches, \
                            f"Reasoning contains unredacted data matching {pattern}: {matches}"

            print("[PASS] Reasoning endpoint valid")
            return True
    except Exception as e:
        print(f"[FAIL] Reasoning endpoint failed: {e}")
        return False


def test_health_check(base_url: str) -> bool:
    """Test that the dashboard is accessible."""
    try:
        url = f"{base_url}/"
        with urllib.request.urlopen(url, timeout=5) as res:
            assert res.status == 200, f"Dashboard returned {res.status}"
            content = res.read().decode('utf-8')
            assert '<title>' in content, "HTML missing title"
            print("[PASS] Dashboard health check passed")
            return True
    except Exception as e:
        print(f"[FAIL] Dashboard health check failed: {e}")
        return False


def main():
    """Run verification suite for UI trio."""
    print("=" * 60)
    print("Verify UI Trio: Gantt Timeline + Audit Tail + Reasoning")
    print("=" * 60)

    # Fixtures for reference
    fixtures = load_fixtures()
    print(f"\nUsing fixtures from: {FIXTURES_PATH}")

    # Self-host the dashboard on a free port with isolated fixture state —
    # never depend on a live :8770 instance (it may run different code).
    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir) / 'state'
        state_dir.mkdir(parents=True)
        transcripts_dir = Path(tmpdir) / 'transcripts'
        transcripts_dir.mkdir(parents=True)

        # Create a fixture agent transcript with test content to enable redaction proof
        fixture_agent_data = {
            "agent_name": "verify-trio-fixture",
            "id": "verify-trio-fixture-001",
            "messages": [
                {
                    "type": "text",
                    "text": "Testing redaction of paths like C:\\Users\\matt8\\aesop and /c/Users/matt8/aesop"
                },
                {
                    "type": "text",
                    "text": "Testing email redaction: user@example.com and admin@test.org"
                },
                {
                    "type": "text",
                    "text": "Testing token patterns and sensitive data"
                }
            ]
        }
        (transcripts_dir / "agent-verify-trio-fixture-001.jsonl").write_text(
            json.dumps(fixture_agent_data) + '\n',
            encoding='utf-8'
        )

        env = os.environ.copy()
        env['PORT'] = str(port)
        env['AESOP_STATE_ROOT'] = str(state_dir)
        env['AESOP_ROOT'] = str(REPO)
        env['AESOP_WEB_DIST'] = str(REPO / 'ui' / 'web' / 'dist')
        env['AESOP_TRANSCRIPTS_ROOT'] = str(transcripts_dir)
        env['AESOP_PROOF_FIXTURES'] = '1'

        proc = subprocess.Popen(
            [sys.executable, str(REPO / 'ui' / 'serve.py')],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            print("\n--- Health Check ---")
            if not wait_for_server(port):
                print("\nERROR: self-hosted dashboard failed to start")
                return False
            if not test_health_check(base_url):
                print(f"\nERROR: Dashboard not accessible at {base_url}")
                return False

            print("\n--- API Endpoints ---")
            results = {
                'gantt': test_gantt_endpoint(base_url),
                'audit': test_audit_endpoint(base_url),
                'reasoning': test_reasoning_endpoint(base_url),
            }
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    print("\n" + "=" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("[PASS] All UI trio endpoints verified successfully")
        print("=" * 60)
        return True
    else:
        print("[FAIL] Some tests failed")
        print("=" * 60)
        return False


if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
