import re
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPOSITORY_ROOT / "supabase" / "migrations"
FOUNDATION_MIGRATION = MIGRATIONS_DIR / "20260729180000_foundation.sql"
EVIDENCE_MIGRATION = MIGRATIONS_DIR / "20260729183000_evidence_snapshots.sql"
PROJECTION_MIGRATION = MIGRATIONS_DIR / "20260730120000_projection_artifacts.sql"
PLAN_MIGRATION = MIGRATIONS_DIR / "20260731120000_optimization_artifacts.sql"
FOREIGN_KEY_INDEX_MIGRATION = MIGRATIONS_DIR / "20260731130000_foreign_key_indexes.sql"
HISTORY_MIGRATION = MIGRATIONS_DIR / "20260801120000_history_corpus.sql"
DEFENSIVE_COMPONENTS_MIGRATION = MIGRATIONS_DIR / "20260801130000_defensive_components.sql"
FIXTURE_GRAIN_MIGRATION = MIGRATIONS_DIR / "20260801140000_fixture_grain_and_event_range.sql"
BACKTEST_MIGRATION = MIGRATIONS_DIR / "20260801150000_backtest_artifacts.sql"
CROWD_MIGRATION = MIGRATIONS_DIR / "20260801160000_crowd_snapshots.sql"

_CREATE_TABLE = re.compile(r"create table (?:if not exists )?public\.(\w+)")
_INDEX_TARGET = re.compile(
    r"create index (?:concurrently )?(?:if not exists )?\w+\s+on public\.(\w+)"
)
_ALTER_TARGET = re.compile(r"alter table (?:only )?public\.(\w+)")
_REFERENCES_TARGET = re.compile(r"references public\.(\w+)")

HISTORY_TABLES = (
    "seasons",
    "teams",
    "elements",
    "fixtures",
    "element_gameweek_stats",
    "element_price_observations",
)


def test_every_migration_only_touches_tables_that_already_exist() -> None:
    """Migrations apply in filename order, so a table must precede its use.

    Regression guard: the foreign-key index migration once sorted before the
    migration creating `optimization_runs`, so every clean `supabase db reset`
    failed with 42P01 while already-migrated environments stayed green.
    """
    created: set[str] = set()
    problems: list[str] = []

    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = " ".join(path.read_text(encoding="utf-8").lower().split())
        # A migration may reference anything it creates itself.
        created.update(_CREATE_TABLE.findall(sql))

        for pattern, kind in (
            (_INDEX_TARGET, "indexes"),
            (_ALTER_TARGET, "alters"),
            (_REFERENCES_TARGET, "references"),
        ):
            for table in pattern.findall(sql):
                if table not in created:
                    problems.append(f"{path.name} {kind} public.{table} before it is created")

    assert problems == []


def test_foundation_table_is_explicitly_protected_by_rls() -> None:
    sql = FOUNDATION_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table public.workflow_runs" in sql
    assert "alter table public.workflow_runs enable row level security" in sql
    assert "grant " not in sql
    assert "create policy" not in sql


def test_evidence_snapshots_are_immutable_and_default_deny() -> None:
    sql = EVIDENCE_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table public.source_snapshots" in sql
    assert "create table public.rules_snapshots" in sql
    assert "unique (source, content_hash)" in sql
    assert "data_available_at <= fetched_at" in sql
    for table in ("source_snapshots", "rules_snapshots"):
        assert f"alter table public.{table} enable row level security" in sql
        assert f"alter table public.{table} force row level security" in sql
    assert "create policy" not in sql
    assert "grant " not in sql


def test_projection_artifacts_are_immutable_and_default_deny() -> None:
    sql = PROJECTION_MIGRATION.read_text(encoding="utf-8").lower()

    for table in ("projection_runs", "team_goal_projections", "model_promotion_decisions"):
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql
        assert f"alter table public.{table} force row level security" in sql
        assert f"create trigger {table}_are_immutable" in sql
    assert "data_available_at <= prediction_cutoff" in sql
    assert "cardinality(source_hashes) > 0" in sql
    assert "paired_improvement_lower > 0" in sql
    assert "sample_size >= minimum_sample_size" in sql
    assert "resamples >= 0" in sql
    assert "resamples > 0 or sample_size < minimum_sample_size" in sql
    assert "create policy" not in sql
    assert "grant " not in sql


def test_optimization_artifacts_hash_private_state_and_remain_default_deny() -> None:
    sql = PLAN_MIGRATION.read_text(encoding="utf-8").lower()

    for table in ("optimization_runs", "optimization_event_plans"):
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql
        assert f"alter table public.{table} force row level security" in sql
        assert f"create trigger {table}_are_immutable" in sql
    assert "manager_overrides_hash" in sql
    assert "public_source_hashes" in sql
    assert "data_available_at <= prediction_cutoff" in sql
    assert "public_data_available_at <= prediction_cutoff" in sql
    assert "overrides_updated_at <= prediction_cutoff" in sql
    assert "cardinality(source_hashes) > 0" in sql
    assert "cardinality(squad_element_ids)" in sql
    assert "price_scenario = 'current_prices'" in sql
    assert "price_scenario = 'provided_event_prices'" in sql
    assert "chip_scenario = 'none'" in sql
    assert "private.positive_unique_bigint_array" in sql
    assert "private.unique_sha256_array" in sql
    assert "private.bigint_array_is_subset" in sql
    assert "private.bigint_arrays_are_disjoint" in sql
    for forbidden in (
        "override_json",
        "available_free_transfers",
        "purchase_price_tenths",
        "selling_price_tenths",
    ):
        assert forbidden not in sql
    assert "create policy" not in sql
    assert "grant " not in sql


def test_history_corpus_is_default_deny_and_traces_every_row_to_a_snapshot() -> None:
    sql = HISTORY_MIGRATION.read_text(encoding="utf-8").lower()

    for table in HISTORY_TABLES:
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql
        assert f"alter table public.{table} force row level security" in sql

    assert "create policy" not in sql
    assert "grant " not in sql


def test_history_rows_carry_provenance_and_stable_cross_season_identity() -> None:
    sql = HISTORY_MIGRATION.read_text(encoding="utf-8").lower()

    # Every observation table must point at the immutable snapshot it came from.
    for table in ("teams", "elements", "fixtures", "element_gameweek_stats"):
        assert table in sql
    assert sql.count("source_snapshot_id uuid not null references public.source_snapshots(id)") == 5

    # element_id is season-scoped; code is the cross-season join key.
    assert "element_code integer not null" in sql
    assert "element_gameweek_stats_code_idx" in sql

    # DefCon labels only exist from 2025/26, so the column must stay nullable.
    assert "defensive_contribution integer check" in sql
    assert "defensive_contribution is null or defensive_contribution >= 0" in sql


def test_history_corpus_is_upsertable_rather_than_immutable() -> None:
    sql = HISTORY_MIGRATION.read_text(encoding="utf-8").lower()

    # FPL revises in-season data, so these tables intentionally carry no
    # immutability trigger. Provenance lives in source_snapshots instead.
    for table in HISTORY_TABLES:
        assert f"create trigger {table}_are_immutable" not in sql


def test_defensive_components_are_additive_idempotent_and_nullable() -> None:
    raw = DEFENSIVE_COMPONENTS_MIGRATION.read_text(encoding="utf-8").lower()
    sql = " ".join(raw.split())

    # The corpus migration is already applied to the hosted project, so this
    # one must alter rather than create, and must be safe to re-run.
    assert "create table" not in sql
    for column in ("clearances_blocks_interceptions", "tackles", "recoveries"):
        assert f"add column if not exists {column} integer" in sql
        assert f"{column} is null or {column} >= 0" in sql
        # A NOT NULL default would be indistinguishable from an observed zero.
        assert f"{column} integer not null" not in sql
    assert "create policy" not in sql
    assert "grant " not in sql


def test_gameweek_stats_are_keyed_per_fixture_not_per_gameweek() -> None:
    raw = FIXTURE_GRAIN_MIGRATION.read_text(encoding="utf-8").lower()
    sql = " ".join(raw.split())

    # Double and triple gameweeks put a player in more than one fixture per
    # gameweek, so the fixture belongs in the key.
    assert "primary key (season, gameweek, element_id, fixture_id)" in sql
    assert "alter column fixture_id set not null" in sql
    assert "create table" not in sql
    assert "create policy" not in sql
    assert "grant " not in sql


def test_the_gameweek_range_covers_a_disrupted_season() -> None:
    raw = FIXTURE_GRAIN_MIGRATION.read_text(encoding="utf-8").lower()
    sql = " ".join(raw.split())

    # 2019/20 was suspended and resumed; its fixtures run to event 47.
    assert "event between 1 and 47" in sql
    assert "gameweek between 1 and 47" in sql


def test_backtest_artifacts_are_immutable_and_default_deny() -> None:
    raw = BACKTEST_MIGRATION.read_text(encoding="utf-8").lower()
    sql = " ".join(raw.split())

    for table in ("backtest_runs", "backtest_predictions"):
        assert f"create table public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql
        assert f"alter table public.{table} force row level security" in sql
        assert f"create trigger {table}_are_immutable" in sql
    assert "create policy" not in sql
    assert "grant " not in sql


def test_a_backtest_metric_is_attributable_to_the_code_that_produced_it() -> None:
    raw = BACKTEST_MIGRATION.read_text(encoding="utf-8").lower()
    sql = " ".join(raw.split())

    # Without a revision, two runs of the same season cannot be compared.
    assert "code_revision text not null" in sql
    assert "unique ( season, method, code_revision, first_scored_gameweek )" in sql
    assert "scored_observations = 0 or spearman is not null" in sql
    assert "spearman is null or spearman between -1 and 1" in sql


def test_backtest_predictions_survive_only_alongside_their_run() -> None:
    raw = BACKTEST_MIGRATION.read_text(encoding="utf-8").lower()
    sql = " ".join(raw.split())

    assert "references public.backtest_runs(id) on delete cascade" in sql
    assert "primary key (run_id, gameweek, element_id)" in sql


def test_crowd_snapshots_are_immutable_and_default_deny() -> None:
    raw = CROWD_MIGRATION.read_text(encoding="utf-8").lower()
    sql = " ".join(raw.split())

    assert "create table public.crowd_snapshots" in sql
    assert "alter table public.crowd_snapshots enable row level security" in sql
    assert "alter table public.crowd_snapshots force row level security" in sql
    assert "create trigger crowd_snapshots_are_immutable" in sql
    assert "create policy" not in sql
    assert "grant " not in sql


def test_a_crowd_snapshot_keeps_every_capture_rather_than_overwriting() -> None:
    raw = CROWD_MIGRATION.read_text(encoding="utf-8").lower()
    sql = " ".join(raw.split())

    # captured_at is part of the key: movement is the entire point of the table.
    assert "primary key (season, event, element_id, captured_at)" in sql
    assert "captained_by is null or total_managers is not null" in sql
