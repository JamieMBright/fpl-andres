-- It was asked for referential integrity or a reconciliation job for
-- `source_snapshots.storage_path`, so that deleted objects do not leave orphan
-- rows.
--
-- Investigating found something else. Nothing in this repository uploads to
-- Supabase Storage: the only object-storage reference anywhere is this column.
-- There are no objects to delete and therefore no orphans of the kind the item
-- describes. Every row already points at a location nothing has ever written.
--
-- The column is still doing real work, but not the work its name suggests. The
-- value is `<source>/<sha256 without its prefix>` -- a content address derived
-- entirely from `content_hash`. It identifies which archive bytes the row came
-- from, deterministically, and that is worth keeping.
--
-- The integrity that actually applies here is therefore internal rather than
-- referential: the path must agree with the hash beside it. A row where they
-- disagree means the provenance chain is broken, and until now nothing said so.
--
-- Enforced with a check rather than a reconciliation job, because the property
-- is a function of the row itself. A job would run periodically and report; a
-- check makes the bad write impossible.

alter table public.source_snapshots
  drop constraint if exists source_snapshots_path_matches_hash;

alter table public.source_snapshots
  add constraint source_snapshots_path_matches_hash check (
    storage_path = source || '/' || substring(content_hash from 8)
  );

comment on column public.source_snapshots.storage_path is
  'Content address, not a filesystem path: <source>/<sha256 hex>. Nothing '
  'uploads to object storage; this identifies which bytes the row came from. '
  'source_snapshots_path_matches_hash keeps it consistent with content_hash.';
