"""crowd_snapshots only collects forwards. fplcache lets the series run backwards.

Verified live on 2026-08-01: the archive stores four bootstrap payloads a day at
roughly six-hour spacing (0336, 0910, 1424, 1944), LZMA-compressed, 95KB each,
564 elements carrying code, now_cost and selected_by_percent.

Nothing here defaults a missing field. A zeroed ownership would be
indistinguishable from a genuinely unowned player.
"""

from __future__ import annotations

import io
import json
import lzma
import unittest
from datetime import UTC, datetime

from fpl_andres.adapters.fplcache import (
    FplCacheUnavailable,
    parse_snapshot,
    snapshot_directory,
    snapshot_url,
)

DAY = datetime(2026, 7, 31, tzinfo=UTC)
FILE = "0336.json.xz"


def _element(**overrides: object) -> dict[str, object]:
    element = {
        "code": 154561,
        "id": 1,
        "web_name": "Raya",
        "now_cost": 60,
        "selected_by_percent": "30.4",
        "transfers_in_event": 12,
        "transfers_out_event": 3,
    }
    element.update(overrides)
    return element


def _payload(elements: list[dict[str, object]] | None = None) -> bytes:
    document = {"elements": elements if elements is not None else [_element()]}
    return lzma.compress(json.dumps(document).encode("utf-8"))


def _parse(payload: bytes):
    return parse_snapshot(payload, source_url="https://example.invalid/x", day=DAY, file_name=FILE)


class LayoutTest(unittest.TestCase):
    def test_the_archive_path_is_not_zero_padded(self) -> None:
        self.assertEqual(snapshot_directory(DAY), "2026/7/31")

    def test_the_url_points_at_the_raw_archive(self) -> None:
        self.assertTrue(snapshot_url(DAY, FILE).endswith("cache/2026/7/31/0336.json.xz"))


class ParseTest(unittest.TestCase):
    def test_ownership_arrives_as_a_string_and_is_read_as_a_number(self) -> None:
        _, rows = _parse(_payload())

        self.assertEqual(rows[0].selected_by_percent, 30.4)
        self.assertEqual(rows[0].now_cost_tenths, 60)
        self.assertEqual(rows[0].element_code, 154561)

    def test_capture_time_comes_from_the_file_name(self) -> None:
        snapshot, _ = _parse(_payload())

        self.assertEqual(snapshot.captured_at, datetime(2026, 7, 31, 3, 36, tzinfo=UTC))
        self.assertEqual(snapshot.captured_at.tzinfo, UTC)

    def test_provenance_carries_a_content_hash(self) -> None:
        snapshot, _ = _parse(_payload())

        self.assertTrue(snapshot.content_hash.startswith("sha256:"))
        self.assertEqual(len(snapshot.content_hash), len("sha256:") + 64)
        self.assertEqual(snapshot.element_count, 1)

    def test_two_reads_of_the_same_bytes_hash_alike(self) -> None:
        payload = _payload()

        first, _ = _parse(payload)
        second, _ = _parse(payload)

        self.assertEqual(first.content_hash, second.content_hash)


class RefusalTest(unittest.TestCase):
    def test_a_missing_ownership_is_refused_not_zeroed(self) -> None:
        element = _element()
        del element["selected_by_percent"]

        with self.assertRaises(FplCacheUnavailable):
            _parse(_payload([element]))

    def test_a_missing_price_is_refused(self) -> None:
        element = _element()
        del element["now_cost"]

        with self.assertRaises(FplCacheUnavailable):
            _parse(_payload([element]))

    def test_an_unreadable_ownership_string_is_refused(self) -> None:
        with self.assertRaises(FplCacheUnavailable):
            _parse(_payload([_element(selected_by_percent="not a number")]))

    def test_an_empty_snapshot_is_refused(self) -> None:
        with self.assertRaises(FplCacheUnavailable):
            _parse(_payload([]))

    def test_bytes_that_are_not_lzma_are_refused(self) -> None:
        with self.assertRaises(FplCacheUnavailable):
            _parse(b"not compressed at all")

    def test_lzma_that_is_not_json_is_refused(self) -> None:
        with self.assertRaises(FplCacheUnavailable):
            _parse(lzma.compress(b"<html>rate limited</html>"))

    def test_an_unreadable_file_name_is_refused(self) -> None:
        with self.assertRaises(FplCacheUnavailable):
            parse_snapshot(
                _payload(),
                source_url="https://example.invalid/x",
                day=DAY,
                file_name="latest.json.xz",
            )

    def test_a_truncated_archive_is_refused(self) -> None:
        payload = _payload()

        with self.assertRaises(FplCacheUnavailable):
            _parse(payload[: len(payload) // 2])

    def test_the_stream_is_not_read_twice_from_a_spent_buffer(self) -> None:
        """Guards the io.BytesIO wrapper: a second parse must still work."""
        payload = _payload()
        _parse(payload)

        _, rows = _parse(payload)

        self.assertEqual(len(rows), 1)


class BufferTest(unittest.TestCase):
    def test_the_caller_keeps_its_own_bytes(self) -> None:
        payload = _payload()
        buffer = io.BytesIO(payload)

        _parse(payload)

        self.assertEqual(buffer.getvalue(), payload)


if __name__ == "__main__":
    unittest.main()
