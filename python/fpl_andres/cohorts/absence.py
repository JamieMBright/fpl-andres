"""Which catalogued managers have stopped answering, and when to give up on them.

A cohort read once and never re-read is a cohort that decays. Accounts are
deleted, renamed and abandoned, and FPL answers a request for a gone entry with
a 404 rather than with anything that says so. The capture job hits every
catalogued manager after every deadline, which makes it the one place that
learns this -- so it is the place that records it.

One miss is a network. Two is a coincidence. The threshold is a choice and it
is the caller's, because it trades how long a dead account keeps a place in the
five hundred against how easily a live one loses it to a bad afternoon.

Nothing here decides who is good. It decides who is still there.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

__all__ = ["DEFAULT_TOLERANCE", "departed", "record_attempt"]

#: Consecutive deadlines a manager may miss before the ranking replaces him.
#: Three is about three weeks, which is long enough that a run of upstream
#: failures cannot empty the cohort and short enough that a deleted account does
#: not hold a place for a month. Assumed, not measured.
DEFAULT_TOLERANCE = 3


def record_attempt(
    previous: Mapping[int, int],
    attempted: Iterable[int],
    answered: Iterable[int],
) -> dict[int, int]:
    """Consecutive misses per entry, after one capture.

    An entry that answered is cleared rather than decremented: the question is
    "is he still there", and one answer settles it however many times he has
    been missed before. An entry nobody asked about keeps whatever it had --
    a run cut short by its budget must not look like a run that found nobody.
    """
    live = set(answered)
    ledger = dict(previous)
    for entry_id in attempted:
        if entry_id in live:
            ledger.pop(entry_id, None)
        else:
            ledger[entry_id] = ledger.get(entry_id, 0) + 1
    return ledger


def departed(ledger: Mapping[int, int], tolerance: int = DEFAULT_TOLERANCE) -> frozenset[int]:
    """Entries that have missed enough deadlines to be treated as gone."""
    if tolerance < 1:
        raise ValueError(f"tolerance must be at least one deadline, got {tolerance}")
    return frozenset(entry for entry, misses in ledger.items() if misses >= tolerance)
