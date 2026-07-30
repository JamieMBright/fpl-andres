"""Minimal PostgREST client for the service-role write path.

Deliberately not the ``supabase`` SDK: the repository already depends on httpx,
the write surface is small, and a thin client keeps the secret handling explicit
and auditable.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Literal, Self

import httpx

Resolution = Literal["merge-duplicates", "ignore-duplicates"]

_SECRET_ENV = "SUPABASE_SECRET_KEY"
_URL_ENV = "SUPABASE_URL"
_MAX_ROWS_PER_REQUEST = 500


class MissingCredentialsError(RuntimeError):
    """Raised when the service-role credentials are absent or malformed."""


class SupabaseWriteError(RuntimeError):
    """Raised when PostgREST rejects a write."""


@dataclass(frozen=True)
class SupabaseCredentials:
    """Service-role credentials. Never logged, never serialised."""

    url: str
    secret_key: str

    def __post_init__(self) -> None:
        if not self.url.startswith("https://"):
            raise MissingCredentialsError(f"{_URL_ENV} must be an https URL")
        if not self.secret_key:
            raise MissingCredentialsError(f"{_SECRET_ENV} must not be empty")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        """Read credentials, failing closed when either is absent.

        A missing secret is an error rather than a silent no-op so a misconfigured
        job fails visibly instead of appearing to succeed while writing nothing.
        """
        url = env.get(_URL_ENV, "").strip()
        secret_key = env.get(_SECRET_ENV, "").strip()
        missing = [
            name for name, value in ((_URL_ENV, url), (_SECRET_ENV, secret_key)) if not value
        ]
        if missing:
            raise MissingCredentialsError(
                "missing required environment variables: " + ", ".join(sorted(missing))
            )
        return cls(url=url.rstrip("/"), secret_key=secret_key)

    def __repr__(self) -> str:
        return f"SupabaseCredentials(url={self.url!r}, secret_key=<redacted>)"


class SupabaseRestClient:
    """Write-only PostgREST client scoped to the service role."""

    def __init__(
        self,
        credentials: SupabaseCredentials,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._credentials = credentials
        self._client = httpx.Client(
            base_url=f"{credentials.url}/rest/v1",
            timeout=timeout,
            transport=transport,
            headers={
                "apikey": credentials.secret_key,
                "Authorization": f"Bearer {credentials.secret_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def insert(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        resolution: Resolution | None = None,
        on_conflict: str | None = None,
        returning: bool = False,
    ) -> list[dict[str, Any]]:
        """Write rows, optionally resolving conflicts.

        ``resolution="ignore-duplicates"`` makes a re-run a no-op.
        ``resolution="merge-duplicates"`` upserts.
        """
        if not rows:
            return []

        prefer = [f"return={'representation' if returning else 'minimal'}"]
        if resolution is not None:
            prefer.append(f"resolution={resolution}")

        params = {"on_conflict": on_conflict} if on_conflict else None

        written: list[dict[str, Any]] = []
        for chunk in _chunked(rows, _MAX_ROWS_PER_REQUEST):
            response = self._client.post(
                f"/{table}",
                params=params,
                headers={"Prefer": ",".join(prefer)},
                content=json.dumps(list(chunk), separators=(",", ":"), default=str),
            )
            if response.status_code >= 400:
                raise SupabaseWriteError(
                    f"{table} write failed with {response.status_code}: {_safe_detail(response)}"
                )
            if returning and response.content:
                written.extend(response.json())
        return written

    def upsert(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        on_conflict: str,
        returning: bool = False,
    ) -> list[dict[str, Any]]:
        return self.insert(
            table,
            rows,
            resolution="merge-duplicates",
            on_conflict=on_conflict,
            returning=returning,
        )

    def insert_ignoring_duplicates(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        on_conflict: str,
    ) -> None:
        self.insert(table, rows, resolution="ignore-duplicates", on_conflict=on_conflict)

    def update(
        self,
        table: str,
        values: Mapping[str, Any],
        *,
        filters: Mapping[str, str],
    ) -> None:
        response = self._client.patch(
            f"/{table}",
            params=dict(filters),
            headers={"Prefer": "return=minimal"},
            content=json.dumps(dict(values), separators=(",", ":"), default=str),
        )
        if response.status_code >= 400:
            raise SupabaseWriteError(
                f"{table} update failed with {response.status_code}: {_safe_detail(response)}"
            )

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: Mapping[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"select": columns}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(limit)
        response = self._client.get(f"/{table}", params=params)
        if response.status_code >= 400:
            raise SupabaseWriteError(
                f"{table} read failed with {response.status_code}: {_safe_detail(response)}"
            )
        rows: list[dict[str, Any]] = response.json()
        return rows


def _chunked(rows: Sequence[Mapping[str, Any]], size: int) -> list[Sequence[Mapping[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def _safe_detail(response: httpx.Response) -> str:
    """Return the upstream error without echoing any request payload."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(body, dict):
        parts = [str(body[key]) for key in ("message", "details", "hint", "code") if body.get(key)]
        if parts:
            return " | ".join(parts)[:500]
    return str(body)[:500]
