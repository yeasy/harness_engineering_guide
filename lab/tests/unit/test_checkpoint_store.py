"""Atomic ownership tests for runtime checkpoints."""

from __future__ import annotations

import asyncio

import pytest

from mini_harness.runtime.checkpoint import (
    CheckpointConflictError,
    InMemoryCheckpointStore,
    JSONCheckpointStore,
)


CLAIM_ARGS = ("session", "call", "write", "alice", "fingerprint")


@pytest.mark.asyncio
@pytest.mark.parametrize("store_factory", [InMemoryCheckpointStore])
async def test_claim_returns_exactly_one_lease_for_concurrent_callers(store_factory):
    store = store_factory()

    claims = await asyncio.gather(*(store.claim(*CLAIM_ARGS) for _ in range(8)))

    owners = [claim for claim in claims if claim.owned]
    assert len(owners) == 1
    assert owners[0].lease_id
    assert all(claim.record.status == "started" for claim in claims)


@pytest.mark.asyncio
async def test_json_store_instances_share_one_atomic_claim(tmp_path):
    path = tmp_path / "checkpoints.json"
    stores = [JSONCheckpointStore(path) for _ in range(8)]

    claims = await asyncio.gather(*(store.claim(*CLAIM_ARGS) for store in stores))

    assert sum(claim.owned for claim in claims) == 1


@pytest.mark.asyncio
async def test_only_the_claim_lease_can_complete_a_checkpoint():
    store = InMemoryCheckpointStore()
    claim = await store.claim(*CLAIM_ARGS)

    with pytest.raises(CheckpointConflictError, match="lease"):
        await store.complete(
            "session",
            "call",
            "alice",
            "fingerprint",
            "wrong-lease",
            {"success": True},
        )

    completed = await store.complete(
        "session",
        "call",
        "alice",
        "fingerprint",
        claim.lease_id,
        {"success": True},
    )
    assert completed.status == "completed"
    assert completed.lease_hash is None
