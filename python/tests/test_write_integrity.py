"""Writes that look like they worked are worse than writes that fail.

Three failure modes, all silent before: an upsert whose payload omits a conflict
column inserts a duplicate instead of updating; a single upstream 5xx kills a
whole unattended run; and a crash mid-checkpoint leaves the sweep unable to
resume.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from fpl_andres.persistence.supabase import (
    SupabaseCredentials,
    SupabaseRestClient,
    SupabaseWriteError,
)

URL = "https://example.supabase.co"


def _client(handler) -> SupabaseRestClient:
    return SupabaseRestClient(
        SupabaseCredentials(url=URL, secret_key="k"),
        transport=httpx.MockTransport(handler),
    )


class ConflictColumnTest(unittest.TestCase):
    def test_a_row_missing_a_conflict_column_is_refused(self) -> None:
        with (
            _client(lambda r: httpx.Response(201, json=[])) as client,
            self.assertRaises(SupabaseWriteError) as caught,
        ):
            client.upsert("elements", [{"season": "2025-26"}], on_conflict="season,element_id")

        self.assertIn("element_id", str(caught.exception))
        self.assertIn("duplicate", str(caught.exception))

    def test_the_offending_row_is_identified(self) -> None:
        rows = [
            {"season": "2025-26", "element_id": 1},
            {"season": "2025-26"},
        ]

        with (
            _client(lambda r: httpx.Response(201, json=[])) as client,
            self.assertRaises(SupabaseWriteError) as caught,
        ):
            client.upsert("elements", rows, on_conflict="season,element_id")

        self.assertIn("row 1", str(caught.exception))

    def test_a_complete_payload_is_written(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.params.get("on_conflict", ""))
            return httpx.Response(201, json=[])

        with _client(handler) as client:
            client.upsert(
                "elements",
                [{"season": "2025-26", "element_id": 1}],
                on_conflict="season,element_id",
            )

        self.assertEqual(seen, ["season,element_id"])

    def test_an_insert_without_a_conflict_target_is_unaffected(self) -> None:
        with _client(lambda r: httpx.Response(201, json=[])) as client:
            client.insert("elements", [{"anything": 1}])


class RetryTest(unittest.TestCase):
    def test_a_transient_5xx_is_retried_and_then_succeeds(self) -> None:
        attempts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            if len(attempts) < 3:
                return httpx.Response(503, json={"message": "upstream busy"})
            return httpx.Response(201, json=[])

        with patch("fpl_andres.persistence.supabase.time.sleep"), _client(handler) as client:
            client.insert("workflow_runs", [{"workflow_name": "x"}])

        self.assertEqual(len(attempts), 3)

    def test_a_4xx_is_not_retried_because_it_will_not_change(self) -> None:
        attempts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            return httpx.Response(400, json={"message": "bad column"})

        with (
            patch("fpl_andres.persistence.supabase.time.sleep"),
            _client(handler) as client,
            self.assertRaises(SupabaseWriteError),
        ):
            client.insert("workflow_runs", [{"workflow_name": "x"}])

        self.assertEqual(len(attempts), 1)

    def test_a_persistent_5xx_eventually_surfaces_the_status(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "still broken"})

        with (
            patch("fpl_andres.persistence.supabase.time.sleep"),
            _client(handler) as client,
            self.assertRaises(SupabaseWriteError) as caught,
        ):
            client.insert("workflow_runs", [{"workflow_name": "x"}])

        self.assertIn("500", str(caught.exception))

    def test_a_transport_error_is_retried(self) -> None:
        attempts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            if len(attempts) < 2:
                raise httpx.ConnectError("connection reset")
            return httpx.Response(201, json=[])

        with patch("fpl_andres.persistence.supabase.time.sleep"), _client(handler) as client:
            client.insert("workflow_runs", [{"workflow_name": "x"}])

        self.assertEqual(len(attempts), 2)

    def test_backoff_grows_between_attempts(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"message": "busy"})

        with (
            patch("fpl_andres.persistence.supabase.time.sleep") as slept,
            _client(handler) as client,
            self.assertRaises(SupabaseWriteError),
        ):
            client.insert("workflow_runs", [{"workflow_name": "x"}])

        waits = [call.args[0] for call in slept.call_args_list]
        self.assertEqual(waits, sorted(waits))
        self.assertGreater(waits[-1], waits[0])


class CheckpointTest(unittest.TestCase):
    def test_the_checkpoint_is_replaced_atomically(self) -> None:
        from fpl_andres.cli import sweep_managers

        with TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "sweep-checkpoint.json"
            with patch.object(sweep_managers, "CHECKPOINT", checkpoint):
                sweep_managers._save_progress(sweep_managers.Progress(next_id=17, with_history=5))
                saved = json.loads(checkpoint.read_text(encoding="utf-8"))

                self.assertEqual(saved["next_id"], 17)
                # No temp file survives a successful write.
                self.assertEqual(
                    sorted(p.name for p in Path(directory).iterdir()),
                    ["sweep-checkpoint.json"],
                )


if __name__ == "__main__":
    unittest.main()
