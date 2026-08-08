-- A backtest score is only meaningful next to the data that
-- produced it.
--
-- `code_revision` already answered "which code ran". Nothing answered "over
-- which corpus", and the corpus is a mutable table: a re-ingest correcting one
-- fixture changes every metric derived from it. Without this, a moved number is
-- indistinguishable from a moved model.
--
-- Nullable, because rows written before this column existed genuinely do not
-- know their corpus and backfilling a guess would be worse than the gap. New
-- writes supply it; `backtest_runs_fingerprint_shape` refuses a malformed one
-- rather than letting a truncated hash pass as provenance.

alter table public.backtest_runs
  add column if not exists corpus_fingerprint text;

alter table public.backtest_runs
  drop constraint if exists backtest_runs_fingerprint_shape;

alter table public.backtest_runs
  add constraint backtest_runs_fingerprint_shape check (
    corpus_fingerprint is null
    or corpus_fingerprint ~ '^sha256:[0-9a-f]{64}$'
  );

-- The comparison this column exists to enable: same corpus, same code, did the
-- metric move? Ordered so the planner can answer it without a sequential scan
-- once the table holds more than one season's worth of runs.
create index if not exists backtest_runs_corpus_method_idx
  on public.backtest_runs (season, method, corpus_fingerprint);

comment on column public.backtest_runs.corpus_fingerprint is
  'sha256 of the observation rows and fixture results the run scored over. '
  'Null only for runs written before the column existed.';
