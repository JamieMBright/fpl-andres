-- Audit item #197: a promotion decision must be reproducible.
--
-- The table recorded the seed, the resample count and the sample size, which is
-- enough to re-run the bootstrap and not enough to reproduce the answer. Three
-- things were missing: which code ran, over which corpus, and with which
-- numerical libraries. scipy's spearmanr and HiGHS' simplex are the parts doing
-- the arithmetic, and neither promises bit-identical results across versions.
--
-- Also records the seed replication added alongside: a decision that promotes on
-- some seeds and not others is not a decision about the model, and the count
-- that agreed is the evidence for that.
--
-- All nullable. Rows written before these columns existed genuinely do not know
-- their lineage, and backfilling a guess would be worse than an honest gap.

alter table public.model_promotion_decisions
  add column if not exists code_revision text,
  add column if not exists corpus_fingerprint text,
  add column if not exists dependency_fingerprint text,
  add column if not exists dependency_versions text[],
  add column if not exists seed_replicates integer,
  add column if not exists seeds_promoting integer;

alter table public.model_promotion_decisions
  drop constraint if exists model_promotion_decisions_lineage_shape;

alter table public.model_promotion_decisions
  add constraint model_promotion_decisions_lineage_shape check (
    (code_revision is null or code_revision ~ '^[0-9a-f]{7,40}$')
    and (corpus_fingerprint is null or corpus_fingerprint ~ '^sha256:[0-9a-f]{64}$')
    and (dependency_fingerprint is null or dependency_fingerprint ~ '^sha256:[0-9a-f]{64}$')
  );

-- A split vote is refused, so promoting fewer times than it replicated and still
-- being promoted would mean the unanimity rule had been bypassed.
alter table public.model_promotion_decisions
  drop constraint if exists model_promotion_decisions_seed_agreement;

alter table public.model_promotion_decisions
  add constraint model_promotion_decisions_seed_agreement check (
    seed_replicates is null
    or seeds_promoting is null
    or (
      seeds_promoting between 0 and seed_replicates
      and (not promoted or seeds_promoting = seed_replicates)
    )
  );

-- The question this lineage exists to answer: same code, same corpus, did the
-- decision change?
create index if not exists model_promotion_decisions_lineage_idx
  on public.model_promotion_decisions (season, candidate_model, code_revision, corpus_fingerprint);

comment on column public.model_promotion_decisions.dependency_versions is
  'Pinned versions of the libraries that do the arithmetic. Kept alongside the '
  'hash because a hash says two runs differed and the list says how.';
