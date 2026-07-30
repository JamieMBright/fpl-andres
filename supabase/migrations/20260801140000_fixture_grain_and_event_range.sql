-- Corrections found by the first real ingest run.
--
-- 1. Gameweek range. 2019/20 was suspended and resumed, and its fixtures run to
--    event 47. A 1..38 bound is simply wrong for a disrupted season.
--
-- 2. Row grain. Double and triple gameweeks mean a player can appear more than
--    once in the same gameweek: 2,217 such players in 2021/22 alone, and one
--    player with three fixtures in 2020/21 GW35. Keying on
--    (season, gameweek, element_id) collapsed those into a single row and made
--    the upsert fail with 21000. The true grain is per player per fixture.
--
--    fixture_id is populated on every archive row checked, so it can carry a
--    NOT NULL and join the key.

alter table public.fixtures
    drop constraint if exists fixtures_event_check;
alter table public.fixtures
    add constraint fixtures_event_check
    check (event is null or event between 1 and 47);

alter table public.element_gameweek_stats
    drop constraint if exists element_gameweek_stats_gameweek_check;
alter table public.element_gameweek_stats
    add constraint element_gameweek_stats_gameweek_check
    check (gameweek between 1 and 47);

alter table public.element_gameweek_stats
    drop constraint if exists element_gameweek_stats_fixture_id_check;
alter table public.element_gameweek_stats
    alter column fixture_id set not null;
alter table public.element_gameweek_stats
    add constraint element_gameweek_stats_fixture_id_check
    check (fixture_id > 0);

alter table public.element_gameweek_stats
    drop constraint if exists element_gameweek_stats_pkey;
alter table public.element_gameweek_stats
    add constraint element_gameweek_stats_pkey
    primary key (season, gameweek, element_id, fixture_id);

comment on table public.element_gameweek_stats is
    'Per-player per-fixture observed match statistics. Keyed by fixture because double and triple gameweeks put a player in more than one match per gameweek.';
