"""Network timeout budgets, in one place.

Audit item #46. Six timeouts were spread across six modules — 20s, 60s, 60s,
20s, 10s and 30s — with no way to see them together and no stated reason for
any of them.

They are deliberately still different. A single number would be wrong for every
caller: a bootstrap fetch that has not answered in twenty seconds is not coming,
while a season archive is tens of megabytes and legitimately takes longer than
that to arrive. What was missing was one place to compare them and a reason
attached to each.

Connect timeouts are short everywhere. Failing to establish a socket is a
different failure from a slow response, and waiting a minute to discover DNS is
broken helps nobody.
"""

from __future__ import annotations

import httpx

__all__ = [
    "ARCHIVE_DOWNLOAD",
    "CONNECT",
    "FPL_API",
    "SUBPROCESS",
    "SUPABASE_REST",
    "client_timeout",
]

# Establishing the socket. Short: this is DNS and TCP, not the server thinking.
CONNECT = 8.0

# FPL's own API. It answers in well under a second when healthy; twenty seconds
# is already deep into "something is wrong" and the adapter's circuit breaker is
# the mechanism that should be reacting, not a longer wait.
FPL_API = 20.0

# PostgREST. Longer than FPL because a large upsert genuinely takes time to
# commit, and abandoning a write mid-flight leaves the caller unable to say
# whether it landed.
SUPABASE_REST = 30.0

# Season archives are tens of megabytes over GitHub's CDN. This is the one place
# a minute is a reasonable thing to wait.
ARCHIVE_DOWNLOAD = 60.0

# `git rev-parse`. Not network at all, but the same class of decision: if the
# local git binary has not answered in ten seconds it is not going to.
SUBPROCESS = 10.0


def client_timeout(total: float) -> httpx.Timeout:
    """An httpx timeout with the shared connect budget."""
    return httpx.Timeout(total, connect=CONNECT)
