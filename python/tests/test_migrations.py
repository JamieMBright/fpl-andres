from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FOUNDATION_MIGRATION = REPOSITORY_ROOT / "supabase" / "migrations" / "20260729180000_foundation.sql"


def test_foundation_table_is_explicitly_protected_by_rls() -> None:
    sql = FOUNDATION_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table public.workflow_runs" in sql
    assert "alter table public.workflow_runs enable row level security" in sql
    assert "grant " not in sql
    assert "create policy" not in sql
