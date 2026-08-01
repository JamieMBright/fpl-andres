# Corpus provenance

Audit item #189. A backtest claim is only reproducible if someone can rebuild the
data it was measured over. This records what was loaded, from where, and when.

## What is loaded

Loaded **2026-07-30**, verified against the hosted project **2026-07-31**.

| Season  | Rows   | Gameweeks | Elements | xG coverage |
| ------- | ------ | --------- | -------- | ----------- |
| 2019-20 | —      | 47        | —        | none        |
| 2020-21 | —      | 38        | —        | none        |
| 2021-22 | —      | 38        | —        | none        |
| 2022-23 | 26,505 | 37        | 778      | 1.0         |
| 2023-24 | 29,725 | 38        | 865      | 1.0         |
| 2024-25 | 27,605 | 38        | 804      | 1.0         |
| 2025-26 | 29,747 | 38        | 841      | 1.0         |

**185,954 player-gameweek rows** in total, 380 fixtures and 20 clubs per season.

Per-season counts exist only for the four seasons in
`apps/web/src/data/validation.json`, which is the artifact the calibration page
serves and covers the window where `expected_goals` exists. The three earlier
seasons account for the remaining 72,372 rows as an aggregate; they are ingested
and usable, but nothing published breaks them out.

**2022-23 has 37 gameweeks, not 38.** Gameweek 7 was postponed following the
death of Queen Elizabeth II and never replayed as a numbered round. Every
2022-23 aggregate is therefore over 37 weeks. `missingGameweeks` in the artifact
names it; nothing did before audit item #56.

## Where it came from

[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League),
read at a pinned commit:

```
https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/{commit_sha}/data/{season}/
    teams.csv
    players_raw.csv
    fixtures.csv
    gws/gw{1..47}.csv
```

Seasons before 2019-20 are refused rather than partially ingested: the archive
only publishes `teams.csv` and `fixtures.csv` from 2019-20 onward, and without
them the schema's foreign keys cannot be satisfied.

## The commit SHA

**Not recorded in this repository.** It was supplied as a workflow dispatch
input on 2026-07-30 and never written back to a committed file. That is the gap
#189 identified, and it is real: the archive is a live repository, so "the
vaastav archive" without a SHA does not name a specific dataset.

It is recoverable, and not from run-log archaeology. Every ingested row cites a
`source_snapshots` row, and that row's `upstream_reference` is the full archive
URL — which contains the SHA:

```sql
select distinct
  split_part(upstream_reference, '/', 7) as commit_sha,
  split_part(upstream_reference, '/', 9) as season,
  min(fetched_at) as first_fetched
from public.source_snapshots
where source = 'vaastav'
group by 1, 2
order by 2;
```

Run that against the hosted project and record the result in the table below.
More than one SHA per season would mean the season was ingested twice from
different archive states, which is worth knowing on its own.

| Season  | Commit SHA        |
| ------- | ----------------- |
| 2019-20 | _to be recovered_ |
| 2020-21 | _to be recovered_ |
| 2021-22 | _to be recovered_ |
| 2022-23 | _to be recovered_ |
| 2023-24 | _to be recovered_ |
| 2024-25 | _to be recovered_ |
| 2025-26 | _to be recovered_ |

Leaving these as placeholders rather than guessing is deliberate. A wrong SHA in
a provenance document is worse than a missing one: the missing one prompts the
query above, and the wrong one prompts a reproduction that quietly uses different
data.

## Reproducing a load

```powershell
python -m fpl_andres.cli.ingest_historical `
  --seasons 2024-25 `
  --commit <sha from the table above> `
  --data-available-at 2026-07-30T00:00:00Z
```

Writes are upserts keyed on `(season, gameweek, element_id, fixture_id)`, so
re-running replaces rows in place rather than duplicating them. Every fetch
happens before every write, so a dropped connection writes nothing — see audit
item #59.

## What a backtest needs beyond this

The corpus is mutable by design: FPL revises in-season data after a gameweek
closes, and a corpus that refused the correction would be permanently wrong. So
knowing the SHA is necessary and not sufficient — a backtest also needs to know
which corpus _state_ it ran against.

That is `corpus_fingerprint`, a sha256 over the observation rows and fixture
results, recorded on every `backtest_runs` and `model_promotion_decisions` row.
See audit items #153 and #197. Two runs with the same code revision and different
fingerprints were measured over different data, and the difference between their
metrics says nothing about the model.
