"""state_store.identity — stable per-instance orchestrator identity.

Derives a stable instance_id for each orchestrator process: hostname:pid:nonce.
The nonce is a short random string (for entropy) so two orchestrators on the
same box with different pids still get different identities.

Identity is deterministic within a process lifetime (cached) but varies
across process restarts (the nonce is not stable across restarts by design,
so instance_id changes on restart). Recommended: auto-derived for zero-config
solo mode, with optional aesop.config.json override for stable identities
across restarts.

Stdlib only: socket, os, random, string.
"""
from __future__ import annotations

import os
import random
import socket
import string


# Cached instance_id, computed once per process
_INSTANCE_ID_CACHE: str | None = None


def get_instance_id() -> str:
    """Return a stable per-instance orchestrator id.

    Computed once per process and cached. The id is the form:
        hostname:pid:nonce

    Where nonce is a random 6-character alphanumeric string, used to
    differentiate multiple orchestrators on the same box.

    Returns:
        A stable string identifier for this orchestrator instance.
    """
    global _INSTANCE_ID_CACHE
    if _INSTANCE_ID_CACHE is None:
        _INSTANCE_ID_CACHE = _derive_instance_id()
    return _INSTANCE_ID_CACHE


def _derive_instance_id() -> str:
    """Derive a new instance_id from hostname, pid, and random nonce."""
    hostname = socket.gethostname()
    pid = os.getpid()
    # Random 6-char alphanumeric nonce for entropy across processes
    nonce = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{hostname}:{pid}:{nonce}"
