"""Minimal PostgREST client for the service-role write path.

Deliberately not the ``supabase`` SDK: the repository already depends on httpx,
the write surface is small, and a thin client keeps the secret handling explicit
and auditable.
"""

from __future__ import annotations

import functools
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Literal, Self

import httpx

from fpl_andres import timeouts

Resolution = Literal["merge-duplicates", "ignore-duplicates"]

_SECRET_ENV = "SUPABASE_SECRET_KEY"
_URL_ENV = "SUPABASE_URL"
_MAX_ROWS_PER_REQUEST = 500
# PostgREST sits behind a proxy with a request body limit. Rows here range from
# a few hundred bytes to several kilobytes, so a row count alone does not bound
# the payload: 500 wide rows can be an order of magnitude larger than 500 narrow
# ones, and the failure arrives as a 413 in the middle of a run rather than at
# the start of one. Six megabytes leaves headroom under the common 10 MB limit.
_MAX_BYTES_PER_REQUEST = 6 * 1024 * 1024
_MAX_DETAIL = 500
# A scheduled run is unattended, so a blip should cost seconds, not the job.
_MAX_ATTEMPTS = 3
_RETRY_BASE_SECONDS = 0.5
# Postgres unique_violation. PostgREST passes the SQLSTATE through unchanged.
UNIQUE_VIOLATION = "23505"


class MissingCredentialsError(RuntimeError):
    """Raised when the service-role credentials are absent or malformed."""


class SupabaseWriteError(RuntimeError):
    """Raised when PostgREST rejects a write.

    Carries the SQLSTATE where PostgREST supplied one. Callers that need to tell
    one rejection from another should read ``code`` rather than match on the
    message: the message is prose that changes with a Postgres version or a
    server locale, and the code is a five-character identifier that does not.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BatchLimits:
    """How much of a write may travel in one request.

    Configurable because the right answer differs per table and per deployment:
    a narrow append-only observation table and a wide stats table have nothing
    in common but a name. Both bounds apply; whichever is reached first ends the
    batch.
    """

    max_rows: int = _MAX_ROWS_PER_REQUEST
    max_bytes: int = _MAX_BYTES_PER_REQUEST

    def __post_init__(self) -> None:
        if self.max_rows < 1:
            raise ValueError("max_rows must be at least 1")
        if self.max_bytes < 1:
            raise ValueError("max_bytes must be at least 1")


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
        """Read credentials, failing closed when either is absent or wrong.

        A missing secret is an error rather than a silent no-op so a misconfigured
        job fails visibly instead of appearing to succeed while writing nothing.

        Every failure here names the variable at fault. A configuration error
        that says only "invalid" sends someone to read the code, and the two
        values involved are the ones nobody can safely print while debugging.
        """
        url = _required_env_string(env, _URL_ENV)
        secret_key = _required_env_string(env, _SECRET_ENV)
        missing = [
            name for name, value in ((_URL_ENV, url), (_SECRET_ENV, secret_key)) if not value
        ]
        if missing:
            raise MissingCredentialsError(
                "missing required environment variables: " + ", ".join(sorted(missing))
            )
        # Transposed values are the likeliest way to get two non-empty strings
        # that are both wrong. Without this the error is "SUPABASE_URL must be
        # an https URL", which is true and unhelpful: the URL is fine, it is
        # just in the other variable.
        if secret_key.startswith("https://"):
            raise MissingCredentialsError(
                f"{_SECRET_ENV} looks like a URL; {_URL_ENV} and {_SECRET_ENV} may be transposed"
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
        timeout: float = timeouts.SUPABASE_REST,
        batch_limits: BatchLimits | None = None,
    ) -> None:
        self._credentials = credentials
        self._batch_limits = batch_limits or BatchLimits()
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

    def __repr__(self) -> str:
        """The default repr would be safe today; this keeps it safe on purpose."""
        return f"SupabaseRestClient(url={self._credentials.url!r})"

    def _send(self, call: Callable[[], httpx.Response]) -> httpx.Response:
        """Retry a transient upstream failure before giving up on the run.

        A single 5xx or dropped connection used to fail a whole scheduled job.
        Only server-side and transport failures are retried: a 4xx is our fault
        and will fail identically however many times it is sent.
        """
        delay = _RETRY_BASE_SECONDS
        last_error: httpx.HTTPError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = call()
            except httpx.HTTPError as error:
                last_error = error
            else:
                if response.status_code < 500 or attempt == _MAX_ATTEMPTS - 1:
                    return response
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(delay)
                delay *= 2
        raise SupabaseWriteError(
            f"gave up after {_MAX_ATTEMPTS} attempts: {type(last_error).__name__}"
        ) from last_error

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
        batch_limits: BatchLimits | None = None,
    ) -> list[dict[str, Any]]:
        """Write rows, optionally resolving conflicts.

        ``resolution="ignore-duplicates"`` makes a re-run a no-op.
        ``resolution="merge-duplicates"`` upserts.

        ``batch_limits`` overrides the client's default for this call, so a
        table with unusually wide rows can be tuned without changing every
        other write.
        """
        if not rows:
            return []

        if on_conflict:
            _require_conflict_columns(table, rows, on_conflict)

        prefer = [f"return={'representation' if returning else 'minimal'}"]
        if resolution is not None:
            prefer.append(f"resolution={resolution}")

        params = {"on_conflict": on_conflict} if on_conflict else None

        written: list[dict[str, Any]] = []
        for chunk in _chunked(rows, batch_limits or self._batch_limits):
            body = json.dumps(list(chunk), separators=(",", ":"), default=str)
            response = self._send(
                functools.partial(
                    self._client.post,
                    f"/{table}",
                    params=params,
                    headers={"Prefer": ",".join(prefer)},
                    content=body,
                )
            )
            if response.status_code >= 400:
                raise SupabaseWriteError(
                    f"{table} write failed with {response.status_code}: "
                    f"{_safe_detail(response, self._credentials.secret_key)}",
                    code=_sqlstate(response),
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
        response = self._send(
            lambda: self._client.patch(
                f"/{table}",
                params=dict(filters),
                headers={"Prefer": "return=minimal"},
                content=json.dumps(dict(values), separators=(",", ":"), default=str),
            )
        )
        if response.status_code >= 400:
            raise SupabaseWriteError(
                f"{table} update failed with {response.status_code}: "
                f"{_safe_detail(response, self._credentials.secret_key)}",
                code=_sqlstate(response),
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
        response = self._send(lambda: self._client.get(f"/{table}", params=params))
        if response.status_code >= 400:
            raise SupabaseWriteError(
                f"{table} read failed with {response.status_code}: "
                f"{_safe_detail(response, self._credentials.secret_key)}",
                code=_sqlstate(response),
            )
        rows: list[dict[str, Any]] = response.json()
        return rows


def _required_env_string(env: Mapping[str, str], name: str) -> str:
    """Read one variable, refusing anything that is not a string.

    A ``Mapping[str, str]`` is the declared type, but the caller is usually
    ``os.environ`` or a dict assembled somewhere else, and a non-string here
    would otherwise surface as ``AttributeError: 'NoneType' object has no
    attribute 'strip'`` from inside a credentials constructor -- which names
    neither the variable nor the problem.
    """
    raw: object = env.get(name, "")
    if not isinstance(raw, str):
        raise MissingCredentialsError(f"{name} must be a string, not {type(raw).__name__}")
    return raw.strip()


def _chunked(
    rows: Sequence[Mapping[str, Any]], limits: BatchLimits
) -> list[Sequence[Mapping[str, Any]]]:
    """Split rows so that no request exceeds either bound.

    Serialised size is measured per row and accumulated, rather than by encoding
    a candidate batch and backing off, because the second is quadratic in the
    number of rows and this runs over a hundred thousand of them.

    A single row larger than ``max_bytes`` still travels alone. Splitting it is
    not possible and refusing it here would turn a server-side limit into a
    client-side one, hiding which row is at fault behind our own error.
    """
    batches: list[Sequence[Mapping[str, Any]]] = []
    start = 0
    size = 0
    for index, row in enumerate(rows):
        row_bytes = len(json.dumps(row, separators=(",", ":"), default=str).encode())
        rows_in_batch = index - start
        if rows_in_batch > 0 and (
            rows_in_batch >= limits.max_rows or size + row_bytes > limits.max_bytes
        ):
            batches.append(rows[start:index])
            start = index
            size = 0
        size += row_bytes
    if start < len(rows):
        batches.append(rows[start:])
    return batches


def _sqlstate(response: httpx.Response) -> str | None:
    """The Postgres SQLSTATE PostgREST reported, when it reported one.

    PostgREST passes the code through in its error body. Reading it lets a
    caller distinguish a unique violation from a foreign key violation without
    matching on English, which changes between Postgres versions and server
    locales and would silently stop matching after an upgrade.
    """
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    code = body.get("code")
    return code if isinstance(code, str) and code else None


def _safe_detail(response: httpx.Response, secret: str) -> str:
    """Return the upstream error without echoing the payload or our own key.

    A gateway that rejects a request sometimes quotes the offending header back.
    That would put the service-role key into an exception message and from there
    into a log, which is why the mask on the credentials repr was not enough.
    """
    try:
        body = response.json()
    except ValueError:
        return _clip(_scrub(response.text, secret))
    if isinstance(body, dict):
        parts = [str(body[key]) for key in ("message", "details", "hint", "code") if body.get(key)]
        if parts:
            return _clip(_scrub(" | ".join(parts), secret))
    return _clip(_scrub(str(body), secret))


def _scrub(detail: str, secret: str) -> str:
    return detail.replace(secret, "<redacted>") if secret else detail


def _require_conflict_columns(
    table: str, rows: Sequence[Mapping[str, Any]], on_conflict: str
) -> None:
    """Every conflict column must be present in every row.

    PostgREST cannot match a conflict target it was not given, so a payload
    missing one of these columns silently inserts a duplicate instead of
    updating the existing row. The failure is invisible until the table has two
    of something that should be unique.
    """
    required = {column.strip() for column in on_conflict.split(",") if column.strip()}
    if not required:
        return
    for index, row in enumerate(rows):
        missing = sorted(required - set(row))
        if missing:
            raise SupabaseWriteError(
                f"{table} upsert row {index} is missing on_conflict column(s) "
                f"{missing}; this would insert a duplicate rather than update"
            )


def _clip(detail: str) -> str:
    """Say when a message was cut, so a clip is not read as the whole message."""
    if len(detail) <= _MAX_DETAIL:
        return detail
    return detail[:_MAX_DETAIL] + f"... [truncated, {len(detail)} chars]"


__all__ = [
    "UNIQUE_VIOLATION",
    "BatchLimits",
    "MissingCredentialsError",
    "Resolution",
    "SupabaseCredentials",
    "SupabaseRestClient",
    "SupabaseWriteError",
]
