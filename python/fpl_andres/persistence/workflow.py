"""Durable execution log for scheduled jobs.

Every ingest or model run opens a ``workflow_runs`` row before doing work and
closes it with a terminal status. The ``(workflow_name, idempotency_key)``
unique constraint is what makes a re-dispatch safe.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

from fpl_andres.persistence.supabase import SupabaseRestClient, SupabaseWriteError


class WorkflowAlreadyRunningError(RuntimeError):
    """Raised when an identical run is already in flight."""


@dataclass
class WorkflowRun:
    """A single job execution."""

    workflow_name: str
    idempotency_key: str
    event_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    row_counts: dict[str, int] = field(default_factory=dict)

    def record_rows(self, table: str, count: int) -> None:
        self.row_counts[table] = self.row_counts.get(table, 0) + count


class WorkflowRunRecorder:
    """Context manager that opens and closes a ``workflow_runs`` row."""

    def __init__(self, client: SupabaseRestClient, run: WorkflowRun) -> None:
        self._client = client
        self._run = run
        self._started_at: datetime | None = None

    def __enter__(self) -> WorkflowRun:
        self._started_at = datetime.now(UTC)
        try:
            self._client.insert(
                "workflow_runs",
                [
                    {
                        "workflow_name": self._run.workflow_name,
                        "idempotency_key": self._run.idempotency_key,
                        "status": "running",
                        "event_id": self._run.event_id,
                        "started_at": self._started_at.isoformat(),
                        "metadata": self._run.metadata,
                    }
                ],
            )
        except SupabaseWriteError as error:
            if "duplicate key" in str(error).lower() or "23505" in str(error):
                raise WorkflowAlreadyRunningError(
                    f"{self._run.workflow_name} already recorded for {self._run.idempotency_key}"
                ) from error
            raise
        return self._run

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        finished_at = datetime.now(UTC).isoformat()
        filters = {
            "workflow_name": f"eq.{self._run.workflow_name}",
            "idempotency_key": f"eq.{self._run.idempotency_key}",
        }
        metadata: dict[str, Any] = dict(self._run.metadata)
        metadata["row_counts"] = self._run.row_counts

        values: dict[str, Any] = {
            "finished_at": finished_at,
            "metadata": metadata,
        }
        if exc is None:
            values["status"] = "succeeded"
        else:
            values["status"] = "failed"
            values["failure_reason"] = _redacted_reason(exc)
        self._client.update("workflow_runs", values, filters=filters)


def _redacted_reason(exc: BaseException) -> str:
    """Summarise a failure without echoing a payload that may embed a secret."""
    return f"{type(exc).__name__}: {str(exc)[:400]}"


# Substrings that mark a value as never safe to persist. Deliberately specific:
# a broad match on "key" would redact "gameweek" and every legitimate id.
_SECRET_NAME_MARKERS = (
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "api_key",
    "apikey",
    "access_key",
    "auth",
    "bearer",
    "cookie",
    "session",
    "signature",
)
# A JSON Web Token always starts this way; a caller pasting one is the most
# likely accident.
_JWT_PREFIX = "eyJ"
_MAX_METADATA_VALUE = 200
REDACTED = "[redacted]"


def redact_metadata(parts: Mapping[str, Any]) -> dict[str, Any]:
    """Strip anything that looks like a credential before it reaches the row.

    `workflow_runs.metadata` is written from caller-supplied parameters, and
    nothing stopped a token arriving in one. Redaction is by name and by shape,
    because a secret can arrive under an innocent key.
    """
    redacted: dict[str, Any] = {}
    for name, value in parts.items():
        lowered = str(name).lower()
        if any(marker in lowered for marker in _SECRET_NAME_MARKERS):
            redacted[name] = REDACTED
            continue
        if isinstance(value, str) and (
            value.startswith(_JWT_PREFIX) or len(value) > _MAX_METADATA_VALUE
        ):
            redacted[name] = REDACTED
            continue
        redacted[name] = value
    return redacted


def build_idempotency_key(parts: Mapping[str, Any]) -> str:
    """Deterministic key from the parameters that define a unique run.

    Hashed rather than concatenated for two reasons: a value containing the
    separator could otherwise collide with a different set of parts, and the
    key is stored in cleartext, so a caller-supplied secret would have been
    persisted verbatim.
    """
    canonical = json.dumps(
        {str(key): parts[key] for key in sorted(parts, key=str)},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def open_run(
    client: SupabaseRestClient,
    *,
    workflow_name: str,
    parts: Mapping[str, Any],
    event_id: int | None = None,
) -> WorkflowRunRecorder:
    run = WorkflowRun(
        workflow_name=workflow_name,
        idempotency_key=build_idempotency_key(parts),
        event_id=event_id,
        metadata=redact_metadata(parts),
    )
    return WorkflowRunRecorder(client, run)


__all__ = [
    "REDACTED",
    "WorkflowAlreadyRunningError",
    "WorkflowRun",
    "WorkflowRunRecorder",
    "build_idempotency_key",
    "open_run",
    "redact_metadata",
]
