# 5. No partitioning for the history corpus

- **Status**: accepted
- **Date**: 2026-08-01

## Context

It was asked for a partitioning or archival strategy for
`element_gameweek_stats`, on the grounds that the corpus grows by
seasons × gameweeks × players indefinitely.

The growth is real. The rate was never measured.

Row counts from the four ingested seasons, taken from the published validation
artifact rather than estimated:

| Season  | Rows   | Gameweeks | Elements |
| ------- | ------ | --------- | -------- |
| 2022-23 | 26,505 | 37        | 778      |
| 2023-24 | 29,725 | 38        | 865      |
| 2024-25 | 27,605 | 38        | 804      |
| 2025-26 | 29,747 | 38        | 841      |

That is **113,582 rows** in total and **28,396 per season**. At an estimated
244-byte row width — 24-byte tuple header, sixteen `int4`, four `int8`, eight
`numeric`, one `timestamptz`, one `boolean`, the season text and a uuid — the
table holds roughly **26 MB** and grows by **6.6 MB per season**.

Projected forward at that rate:

| Milestone       | Reached in  | Calendar year |
| --------------- | ----------- | ------------- |
| 100 MB          | 15 seasons  | 2041          |
| 500 MB          | 76 seasons  | 2101          |
| 1 million rows  | 35 seasons  | 2061          |
| 10 million rows | 352 seasons | 2378          |

The bound is not open-ended in any way that matters. A Premier League season is
fixed at 380 matches and roughly 800 registered players; the corpus grows by a
constant, not a compounding one.

## Decision

Do not partition. Do not archive. Revisit if
`element_gameweek_stats` exceeds **2 million rows** or the growth rate exceeds
**100,000 rows per season**, whichever comes first.

`python/tests/test_corpus_growth.py` checks both thresholds against the
published validation artifact on every run, so the decision re-examines itself
rather than depending on someone remembering this file.

## Consequences

**Queries stay simple.** The access paths the application actually uses —
`(season, gameweek, element_id)` and `(season, element_id, gameweek)` — are
served by the composite indexes added in `20260801170000_access_path_indexes.sql`.
A 113,000-row table with the right index does not need help from the planner.

**`supabase db reset` stays fast**, which matters because CI runs it on every
migration change. Declarative partitioning would add a parent table, a partition
per season, and a `create table` in every future ingest path.

**The unique constraint stays enforceable as written.** Postgres requires a
partition key to be part of every unique constraint. Partitioning by season
would work here because `season` already leads the key — but it is a constraint
on future schema changes bought for no present benefit.

**A season is still individually removable** without partitions:
`delete from element_gameweek_stats where season = '2022-23'` uses the leading
column of the primary key. The operation partitioning would make cheap is one
that is already cheap enough and has never been performed.

## Alternatives considered

**Partition by season now.** Rejected on the numbers above. Partitioning is
worth its complexity when a table is large enough that index maintenance,
vacuum, or bulk deletion hurt. At 26 MB none of those are measurable.

**Archive seasons older than N to cold storage.** Rejected: the backtest corpus
exists precisely to be read across all seasons at once. Walk-forward validation
over 2022-23 is not a historical curiosity, it is the point of the table.
Archiving the oldest data would be archiving the thing being tested.

**Compress or narrow the row.** Rejected as premature for the same reason. The
eight `numeric` columns are the widest part of the row and could be `real`, but
`numeric` is what preserves the exact values FPL publishes, and 6.6 MB a season
does not buy a change that loses precision.

**Do nothing and write nothing down.** Rejected: that is the state the audit
correctly flagged. The problem was never the absence of partitioning, it was the
absence of a measurement showing partitioning was unnecessary.
