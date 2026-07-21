"""state_store.coordination — lease-by-append claim for exclusive resource access.

Implements DB-native CLAIM (lease-via-append) on top of the existing event log:
to claim resource R, append a claim_requested event to the 'claims' stream;
the winner is the lowest-version append for that resource key; readers fold
the stream to see who holds it.

Fail-CLOSED by construction: if you cannot append or read, you do NOT hold
the claim and must not dispatch. TTL + claim_released events handle crashed
holders (analogous to lock.mjs PID-liveness staleness, but expressed as events).

No risky changes to store.py or api.py — uses only existing append/read primitives.

Stdlib only: time.
"""
from __future__ import annotations

import time


def fold_claims(events: list) -> dict[str, str]:
    """Fold a claims stream into the current state of who holds each resource.

    Processes claim_requested and claim_released events to determine the winner
    for each resource. The winner is the lowest-version claim_requested for
    that resource (first serialized append wins; ties impossible because versions
    are unique). A claim is valid only if it has NOT been released (or was re-claimed
    after release, in which case the re-claim is the new low-version claim).

    Args:
        events: list of event dicts from the claims stream
                (as returned by EventStore.read('claims'))

    Returns:
        dict mapping resource_id -> holding_instance_id for all currently
        held resources. Empty dict if no claims exist or all have been released.
    """
    # Track all claims by resource and instance
    claims_by_resource = {}  # resource -> {instance_id: version}
    # Track all releases by resource and instance
    releases_by_resource = {}  # resource -> {instance_id: [release_versions]}

    # First pass: collect all claims and releases
    for ev in events:
        etype = ev.get("type")
        payload = ev.get("payload") or {}
        version = ev.get("version", 0)

        if etype == "claim_requested":
            resource = payload.get("resource")
            instance_id = payload.get("instance_id")
            if resource is not None and instance_id is not None:
                if resource not in claims_by_resource:
                    claims_by_resource[resource] = {}
                claims_by_resource[resource][instance_id] = version

        elif etype == "claim_released":
            resource = payload.get("resource")
            instance_id = payload.get("instance_id")
            if resource is not None and instance_id is not None:
                if resource not in releases_by_resource:
                    releases_by_resource[resource] = {}
                if instance_id not in releases_by_resource[resource]:
                    releases_by_resource[resource][instance_id] = []
                releases_by_resource[resource][instance_id].append(version)

    # Second pass: determine current holders
    holders = {}
    for resource, claims in claims_by_resource.items():
        # For each instance claiming this resource, check if it was released
        active_claims = {}
        for instance_id, claim_version in claims.items():
            releases = releases_by_resource.get(resource, {}).get(instance_id, [])
            # Check if there's a release AFTER this claim (that invalidates it)
            if any(rel_version > claim_version for rel_version in releases):
                # This claim was released and not re-claimed; skip it
                continue
            active_claims[instance_id] = claim_version

        # Find the minimum version among active claims (the winner)
        if active_claims:
            winner_instance = min(active_claims.keys(), key=lambda x: active_claims[x])
            holders[resource] = winner_instance

    return holders


def try_claim(store, resource: str, instance_id: str, ttl: float = 300.0) -> bool:
    """Attempt to claim exclusive access to a resource.

    Appends a claim_requested event to the 'claims' stream, then re-reads
    and folds to check if this instance won the claim. Fail-CLOSED: if ANY
    exception occurs (append fails, read fails, or exception during fold),
    return False (claim not held, do not proceed).

    Args:
        store: StateAPI or EventStore instance (must have append() and get() methods)
        resource: the resource identifier to claim (e.g., "wave_123", "lane_0", ...)
        instance_id: the instance identifier requesting the claim
        ttl: time-to-live in seconds (default 300s = 5min); embedded in the payload
             for later TTL-based expiry checks (not enforced here, but available
             for reconciliation)

    Returns:
        bool: True if this instance holds the claim after the append,
              False otherwise (including on any error).
    """
    try:
        # Append claim request to the claims stream
        store.append(
            "claims",
            "claim_requested",
            {"resource": resource, "instance_id": instance_id, "ttl": ttl},
            actor=instance_id,
        )

        # Re-read claims stream and fold to see current state
        events = store.get("claims")
        claims = fold_claims(events)

        # Return True if we hold this resource
        return claims.get(resource) == instance_id
    except Exception:
        # Fail-closed: any exception means we don't hold the claim
        return False


def release(store, resource: str, instance_id: str) -> None:
    """Release a claimed resource.

    Appends a claim_released event to the 'claims' stream, marking that
    this instance no longer holds the resource. Idempotent: releasing
    a resource that was not held is a no-op (the fold will see the
    release but no matching claim, so it has no effect).

    Args:
        store: StateAPI or EventStore instance (must have append() method)
        resource: the resource identifier being released
        instance_id: the instance identifier releasing the claim
    """
    store.append(
        "claims",
        "claim_released",
        {"resource": resource, "instance_id": instance_id},
        actor=instance_id,
    )


def current_holder(store, resource: str) -> str | None:
    """Return the instance_id currently holding a resource, or None if unclaimed.

    Reads and folds the claims stream to find the winner for the resource.
    Returns None if the resource is not claimed or has been released.

    Args:
        store: StateAPI or EventStore instance (must have get() method)
        resource: the resource identifier to query

    Returns:
        The instance_id of the current holder, or None if unclaimed.
    """
    try:
        events = store.get("claims")
        claims = fold_claims(events)
        return claims.get(resource)
    except Exception:
        # Fail-closed: on any error, we cannot determine the holder
        return None
