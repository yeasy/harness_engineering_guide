"""Durable tool-call checkpoints for safe runtime recovery."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
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
    fingerprint: str
    status: str
    result: dict[str, Any] | None = None


class CheckpointStore(Protocol):
    """Storage boundary used by the application runtime."""

    async def get(self, session_id: str, call_id: str) -> CheckpointRecord | None:
        """Load an existing checkpoint."""

    async def begin(
        self,
        session_id: str,
        call_id: str,
        tool_name: str,
        fingerprint: str,
    ) -> CheckpointRecord:
        """Record that an operation is about to execute."""

    async def complete(
        self,
        session_id: str,
        call_id: str,
        fingerprint: str,
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


class InMemoryCheckpointStore:
    """Process-local checkpoint store used when no durable path is configured."""

    def __init__(self):
        self._records: dict[str, CheckpointRecord] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str, call_id: str) -> CheckpointRecord | None:
        async with self._lock:
            return self._records.get(_record_key(session_id, call_id))

    async def begin(
        self,
        session_id: str,
        call_id: str,
        tool_name: str,
        fingerprint: str,
    ) -> CheckpointRecord:
        async with self._lock:
            key = _record_key(session_id, call_id)
            existing = self._records.get(key)
            if existing is not None:
                _validate_fingerprint(existing, fingerprint)
                return existing
            record = CheckpointRecord(
                session_id=session_id,
                call_id=call_id,
                tool_name=tool_name,
                fingerprint=fingerprint,
                status="started",
            )
            self._records[key] = record
            return record

    async def complete(
        self,
        session_id: str,
        call_id: str,
        fingerprint: str,
        result: dict[str, Any],
    ) -> CheckpointRecord:
        async with self._lock:
            key = _record_key(session_id, call_id)
            existing = self._records[key]
            _validate_fingerprint(existing, fingerprint)
            record = CheckpointRecord(
                session_id=existing.session_id,
                call_id=existing.call_id,
                tool_name=existing.tool_name,
                fingerprint=existing.fingerprint,
                status="completed",
                result=result,
            )
            self._records[key] = record
            return record


class JSONCheckpointStore:
    """Atomic JSON checkpoint store suitable for restart recovery."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._lock = asyncio.Lock()

    async def get(self, session_id: str, call_id: str) -> CheckpointRecord | None:
        async with self._lock:
            records = self._read_records()
            return records.get(_record_key(session_id, call_id))

    async def begin(
        self,
        session_id: str,
        call_id: str,
        tool_name: str,
        fingerprint: str,
    ) -> CheckpointRecord:
        async with self._lock:
            records = self._read_records()
            key = _record_key(session_id, call_id)
            existing = records.get(key)
            if existing is not None:
                _validate_fingerprint(existing, fingerprint)
                return existing
            record = CheckpointRecord(
                session_id=session_id,
                call_id=call_id,
                tool_name=tool_name,
                fingerprint=fingerprint,
                status="started",
            )
            records[key] = record
            self._write_records(records)
            return record

    async def complete(
        self,
        session_id: str,
        call_id: str,
        fingerprint: str,
        result: dict[str, Any],
    ) -> CheckpointRecord:
        async with self._lock:
            records = self._read_records()
            key = _record_key(session_id, call_id)
            existing = records[key]
            _validate_fingerprint(existing, fingerprint)
            record = CheckpointRecord(
                session_id=existing.session_id,
                call_id=existing.call_id,
                tool_name=existing.tool_name,
                fingerprint=existing.fingerprint,
                status="completed",
                result=result,
            )
            records[key] = record
            self._write_records(records)
            return record

    def _read_records(self) -> dict[str, CheckpointRecord]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as checkpoint_file:
            payload = json.load(checkpoint_file)
        if payload.get("version") != 1 or not isinstance(payload.get("records"), dict):
            raise ValueError(f"Unsupported checkpoint format in {self.path}")
        return {
            key: CheckpointRecord(**record)
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
                        "version": 1,
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
