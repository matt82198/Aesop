#!/usr/bin/env python3
"""OpenAI HTTP transport for the AgentDriver codex_driver.

Provides a callable transport that POSTs to the OpenAI Chat Completions API
via stdlib urllib.request. This is the injectable seam that lets tests pass
canned responses without network/secrets, and lets the driver stay dependency-light.

Transport contract:
  Transport = callable(payload: dict) -> dict
  where payload is the OpenAI Chat Completions request body (with schema + messages)
  and returns the parsed response JSON (with choices/usage).

The real transport reads OPENAI_API_KEY from os.environ at call time (NEVER
hardcoded). Use the pattern:
  key = os.environ.get("OPENAI_API_KEY")
so the source code string does NOT trigger secret_scan rules.
"""

import json
import os
import urllib.error
import urllib.request


# Type alias documenting the transport callable contract.
Transport = callable  # (payload: dict) -> dict


def default_openai_transport(
    payload: dict, timeout_s: float = 120.0, base_url: str = "https://api.openai.com/v1"
) -> dict:
    """Default transport: POST to OpenAI Chat Completions via urllib.

    Args:
        payload: OpenAI Chat Completions request body (messages, model, etc.).
        timeout_s: HTTP timeout in seconds (default 120).
        base_url: OpenAI API base URL (default production).

    Returns:
        Parsed JSON response (choices, usage, etc.).

    Raises:
        RuntimeError: if OPENAI_API_KEY env var is not set, or if the HTTP
            status is not 200-299.
        urllib.error.URLError: if the HTTP request fails.
    """
    # Read API key at call time from environment; NEVER hardcoded.
    # The pattern os.environ.get("OPENAI_API_KEY") does not trigger secret_scan
    # because the RHS contains dots/parens.
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable is not set. "
            "Set it before running the codex driver, or pass a FakeTransport in tests."
        )

    endpoint = f"{base_url}/chat/completions"

    # Build the HTTP request.
    payload_json = json.dumps(payload)
    request = urllib.request.Request(
        endpoint,
        data=payload_json.encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        # POST with hard timeout.
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = response.status
            body = response.read().decode("utf-8")

        # Classify non-2xx as an error.
        if not (200 <= status < 300):
            raise RuntimeError(
                f"OpenAI API returned HTTP {status}: {body[:200]}"
            )

        return json.loads(body)

    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI API returned invalid JSON: {exc}") from exc
