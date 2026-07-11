"""Durable tool-call checkpoints for safe runtime recovery."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


class CheckpointConflictError(RuntimeError):
    """Raised when a call identifier is reused for different input."""


class IncompleteCheckpointError(RuntimeError):
    """Raised when replay could duplicate an operation with an unknown outcome."""


@dataclass(frozen=True)
class CheckpointRecord:
    """One tool-call checkpoint."""

    session_id: str
    call_id: str
    tool_name: str
    principal_id: str
    fingerprint: str
    status: str
    result: dict[str, Any] | None = None
    lease_hash: str | None = None


@dataclass(frozen=True)
class CheckpointClaim:
    """Atomic claim result; only the owner receives the completion lease."""

    record: CheckpointRecord
    lease_id: str | None = None

    @property
    def owned(self) -> bool:
        """Whether this caller created the started checkpoint."""
        return self.lease_id is not None


class CheckpointStore(Protocol):
    """Storage boundary used by the application runtime."""

    async def get(self, session_id: str, call_id: str) -> CheckpointRecord | None:
        """Load an existing checkpoint."""

    async def claim(
        self,
        session_id: str,
        call_id: str,
        tool_name: str,
        principal_id: str,
        fingerprint: str,
    ) -> CheckpointClaim:
        """Atomically create a started checkpoint or return the existing record."""

    async def complete(
        self,
        session_id: str,
        call_id: str,
        principal_id: str,
        fingerprint: str,
        lease_id: str,
        result: dict[str, Any],
    ) -> CheckpointRecord:
        """Persist the completed result used for replay."""


def _record_key(session_id: str, call_id: str) -> str:
    return json.dumps([session_id, call_id], separators=(",", ":"))


def _validate_fingerprint(record: CheckpointRecord, fingerprint: str) -> None:
    if record.fingerprint != fingerprint:
        raise CheckpointConflictError(
            f"Checkpoint {record.session_id}/{record.call_id} was reused with different input"
        )


def _validate_principal(record: CheckpointRecord, principal_id: str) -> None:
    if record.principal_id != principal_id:
        raise CheckpointConflictError(
            f"Checkpoint {record.session_id}/{record.call_id} belongs to a different principal"
        )


def _lease_hash(lease_id: str) -> str:
    return hashlib.sha256(lease_id.encode("utf-8")).hexdigest()


def _new_claim(
    session_id: str,
    call_id: str,
    tool_name: str,
    principal_id: str,
    fingerprint: str,
) -> CheckpointClaim:
    lease_id = secrets.token_urlsafe(32)
    record = CheckpointRecord(
        session_id=session_id,
        call_id=call_id,
        tool_name=tool_name,
        principal_id=principal_id,
        fingerprint=fingerprint,
        status="started",
        lease_hash=_lease_hash(lease_id),
    )
    return CheckpointClaim(record=record, lease_id=lease_id)


def _existing_claim(
    record: CheckpointRecord,
    principal_id: str,
    fingerprint: str,
) -> CheckpointClaim:
    _validate_principal(record, principal_id)
    _validate_fingerprint(record, fingerprint)
    return CheckpointClaim(record=record)


def _completed_record(
    existing: CheckpointRecord,
    lease_id: str,
    result: dict[str, Any],
) -> CheckpointRecord:
    if existing.status != "started" or existing.lease_hash != _lease_hash(lease_id):
        raise CheckpointConflictError(
            f"Checkpoint {existing.session_id}/{existing.call_id} has an invalid owner lease"
        )
    return CheckpointRecord(
        session_id=existing.session_id,
        call_id=existing.call_id,
        tool_name=existing.tool_name,
        principal_id=existing.principal_id,
        fingerprint=existing.fingerprint,
        status="completed",
        result=result,
    )


class InMemoryCheckpointStore:
    """Process-local checkpoint store used when no durable path is configured."""

    def __init__(self):
        self._records: dict[str, CheckpointRecord] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str, call_id: str) -> CheckpointRecord | None:
        async with self._lock:
            return self._records.get(_record_key(session_id, call_id))

    async def claim(
        self,
        session_id: str,
        call_id: str,
        tool_name: str,
        principal_id: str,
        fingerprint: str,
    ) -> CheckpointClaim:
        async with self._lock:
            key = _record_key(session_id, call_id)
            existing = self._records.get(key)
            if existing is not None:
                return _existing_claim(existing, principal_id, fingerprint)
            claim = _new_claim(
                session_id,
                call_id,
                tool_name,
                principal_id,
                fingerprint,
            )
            self._records[key] = claim.record
            return claim

    async def complete(
        self,
        session_id: str,
        call_id: str,
        principal_id: str,
        fingerprint: str,
        lease_id: str,
        result: dict[str, Any],
    ) -> CheckpointRecord:
        async with self._lock:
            key = _record_key(session_id, call_id)
            existing = self._records[key]
            _validate_principal(existing, principal_id)
            _validate_fingerprint(existing, fingerprint)
            record = _completed_record(existing, lease_id, result)
            self._records[key] = record
            return record


class JSONCheckpointStore:
    """Atomic JSON checkpoint store suitable for restart recovery."""

    _locks_guard = threading.Lock()
    _path_locks: dict[str, threading.RLock] = {}

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser().resolve()
        path_key = os.fspath(self.path)
        with self._locks_guard:
            self._lock = self._path_locks.setdefault(path_key, threading.RLock())

    async def get(self, session_id: str, call_id: str) -> CheckpointRecord | None:
        with self._lock:
            records = self._read_records()
            return records.get(_record_key(session_id, call_id))

    async def claim(
        self,
        session_id: str,
        call_id: str,
        tool_name: str,
        principal_id: str,
        fingerprint: str,
    ) -> CheckpointClaim:
        with self._lock:
            records = self._read_records()
            key = _record_key(session_id, call_id)
            existing = records.get(key)
            if existing is not None:
                return _existing_claim(existing, principal_id, fingerprint)
            claim = _new_claim(
                session_id,
                call_id,
                tool_name,
                principal_id,
                fingerprint,
            )
            records[key] = claim.record
            self._write_records(records)
            return claim

    async def complete(
        self,
        session_id: str,
        call_id: str,
        principal_id: str,
        fingerprint: str,
        lease_id: str,
        result: dict[str, Any],
    ) -> CheckpointRecord:
        with self._lock:
            records = self._read_records()
            key = _record_key(session_id, call_id)
            existing = records[key]
            _validate_principal(existing, principal_id)
            _validate_fingerprint(existing, fingerprint)
            record = _completed_record(existing, lease_id, result)
            records[key] = record
            self._write_records(records)
            return record

    def _read_records(self) -> dict[str, CheckpointRecord]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as checkpoint_file:
            payload = json.load(checkpoint_file)
        if payload.get("version") not in {2, 3} or not isinstance(payload.get("records"), dict):
            raise ValueError(f"Unsupported checkpoint format in {self.path}")
        return {
            key: CheckpointRecord(**{**record, "lease_hash": record.get("lease_hash")})
            for key, record in payload["records"].items()
        }

    def _write_records(self, records: dict[str, CheckpointRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            dir=self.path.parent,
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as checkpoint_file:
                json.dump(
                    {
                        "version": 3,
                        "records": {key: asdict(record) for key, record in records.items()},
                    },
                    checkpoint_file,
                    indent=2,
                    sort_keys=True,
                    default=str,
                )
                checkpoint_file.flush()
                os.fsync(checkpoint_file.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
