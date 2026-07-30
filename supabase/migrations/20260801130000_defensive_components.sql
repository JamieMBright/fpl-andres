-- Defensive-contribution component columns.
--
-- The 2025/26 archive publishes the components behind the defensive_contribution
-- label: clearances_blocks_interceptions, tackles and recoveries. The DefCon
-- model needs them because the qualifying threshold differs by position
-- (defenders count CBIT, midfielders and forwards count CBIRT), so the label
-- alone cannot be re-derived or modelled per position.
--
-- Additive and idempotent: the history corpus migration has already been applied
-- to the hosted project. Nullable throughout, because these columns do not exist
-- in archives before 2025/26 and a zero would be indistinguishable from an
-- observed zero.

alter table public.element_gameweek_stats
    add column if not exists clearances_blocks_interceptions integer
        check (
            clearances_blocks_interceptions is null
            or clearances_blocks_interceptions >= 0
        );

alter table public.element_gameweek_stats
    add column if not exists tackles integer
        check (tackles is null or tackles >= 0);

alter table public.element_gameweek_stats
    add column if not exists recoveries integer
        check (recoveries is null or recoveries >= 0);

comment on column public.element_gameweek_stats.clearances_blocks_interceptions is
    'CBI count. Null before 2025/26, where the archive does not publish it.';
comment on column public.element_gameweek_stats.tackles is
    'Tackle count. Null before 2025/26, where the archive does not publish it.';
comment on column public.element_gameweek_stats.recoveries is
    'Recovery count, counted toward the midfield and forward DefCon threshold only.';
