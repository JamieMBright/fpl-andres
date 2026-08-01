"""The service-role secret must never reach a log, a repr or an exception.

`SupabaseCredentials.__repr__` masks it, but a masked literal is a promise, not
a guarantee: a dataclass helper, a traceback frame or an httpx error can carry
the same value by another route. These tests assert the property rather than the
implementation, so a future refactor that reintroduces the leak fails here.
"""

from __future__ import annotations

import dataclasses
import json
import traceback
import unittest

import httpx

from fpl_andres.persistence.supabase import (
    SupabaseCredentials,
    SupabaseRestClient,
    SupabaseWriteError,
)
from fpl_andres.persistence.workflow import (
    REDACTED,
    build_idempotency_key,
    redact_metadata,
)

SECRET = "sb_secret_9f4c1e77c0a24b6e8d3a5f21b7c94e08"
URL = "https://qpmlfbuouporvwebjxhk.supabase.co"


def _credentials() -> SupabaseCredentials:
    return SupabaseCredentials(url=URL, secret_key=SECRET)


def _client(handler) -> SupabaseRestClient:
    return SupabaseRestClient(_credentials(), transport=httpx.MockTransport(handler))


class CredentialsTest(unittest.TestCase):
    def test_repr_does_not_carry_the_secret(self) -> None:
        self.assertNotIn(SECRET, repr(_credentials()))

    def test_str_does_not_carry_the_secret(self) -> None:
        self.assertNotIn(SECRET, str(_credentials()))

    def test_format_does_not_carry_the_secret(self) -> None:
        self.assertNotIn(SECRET, f"{_credentials()}")

    def test_the_repr_still_names_the_project(self) -> None:
        """Redaction must not make an operator unable to tell which project."""
        self.assertIn(URL, repr(_credentials()))


class ClientTest(unittest.TestCase):
    def test_client_repr_does_not_carry_the_secret(self) -> None:
        with _client(lambda request: httpx.Response(200, json=[])) as client:
            self.assertNotIn(SECRET, repr(client))

    def test_a_write_failure_message_does_not_carry_the_secret(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            # An upstream that echoes the auth header back at us.
            return httpx.Response(
                401,
                json={"message": f"bad key {request.headers.get('apikey')}"},
            )

        with _client(handler) as client, self.assertRaises(SupabaseWriteError) as caught:
            client.insert("workflow_runs", [{"workflow_name": "x"}])

        self.assertNotIn(SECRET, str(caught.exception))

    def test_a_traceback_does_not_carry_the_secret(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "boom"})

        try:
            with _client(handler) as client:
                client.insert("workflow_runs", [{"workflow_name": "x"}])
        except SupabaseWriteError as error:
            rendered = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            self.assertNotIn(SECRET, rendered)
        else:  # pragma: no cover - the handler always fails
            self.fail("expected a write error")

    def test_a_truncated_upstream_message_says_it_was_truncated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"message": "x" * 900})

        with _client(handler) as client, self.assertRaises(SupabaseWriteError) as caught:
            client.insert("workflow_runs", [{"workflow_name": "x"}])

        self.assertIn("truncated", str(caught.exception))


class WorkflowMetadataTest(unittest.TestCase):
    def test_a_secret_named_field_is_redacted(self) -> None:
        redacted = redact_metadata({"season": "2025-26", "supabase_secret": SECRET})

        self.assertEqual(redacted["supabase_secret"], REDACTED)
        self.assertEqual(redacted["season"], "2025-26")

    def test_a_token_under_an_innocent_name_is_still_redacted(self) -> None:
        """A JWT is recognisable by shape, whatever it is called."""
        redacted = redact_metadata({"note": "eyJhbGciOiJIUzI1NiJ9.payload.sig"})

        self.assertEqual(redacted["note"], REDACTED)

    def test_an_overlong_value_is_redacted_rather_than_stored(self) -> None:
        redacted = redact_metadata({"note": "z" * 400})

        self.assertEqual(redacted["note"], REDACTED)

    def test_ordinary_parameters_survive_untouched(self) -> None:
        parts = {"season": "2025-26", "gameweek": 7, "entry_id": 212279}

        self.assertEqual(redact_metadata(parts), parts)

    def test_the_idempotency_key_does_not_embed_the_secret(self) -> None:
        key = build_idempotency_key({"season": "2025-26", "token": SECRET})

        self.assertNotIn(SECRET, key)

    def test_the_key_is_order_independent(self) -> None:
        self.assertEqual(
            build_idempotency_key({"season": "2024-25", "gameweek": 3}),
            build_idempotency_key({"gameweek": 3, "season": "2024-25"}),
        )

    def test_a_separator_in_a_value_cannot_collide_with_other_parts(self) -> None:
        """The old concatenated key made these two indistinguishable."""
        first = build_idempotency_key({"a": "1|b=2"})
        second = build_idempotency_key({"a": "1", "b": "2"})

        self.assertNotEqual(first, second)

    def test_the_key_fits_the_column_constraint(self) -> None:
        key = build_idempotency_key({"season": "2025-26", "gameweek": 3})

        self.assertTrue(1 <= len(key) <= 200)


class DataclassLeakTest(unittest.TestCase):
    def test_asdict_is_the_one_route_that_still_exposes_it(self) -> None:
        """Recorded deliberately: dataclasses.asdict bypasses __repr__.

        Nothing in the package calls it on credentials, and this test exists so
        that if someone starts to, they meet an explicit statement rather than a
        surprise.
        """
        exposed = json.dumps(dataclasses.asdict(_credentials()))

        self.assertIn(SECRET, exposed)


if __name__ == "__main__":
    unittest.main()
