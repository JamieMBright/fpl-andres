from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FOUNDATION_MIGRATION = REPOSITORY_ROOT / "supabase" / "migrations" / "20260729180000_foundation.sql"
EVIDENCE_MIGRATION = (
    REPOSITORY_ROOT / "supabase" / "migrations" / "20260729183000_evidence_snapshots.sql"
)
PROJECTION_MIGRATION = (
    REPOSITORY_ROOT / "supabase" / "migrations" / "20260730120000_projection_artifacts.sql"
)


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
