# Data Contracts

FPL Andres separates raw evidence, normalized domain contracts and controlling rules.
A source payload may be stored even when its contract fails, but failed evidence cannot
produce or promote a recommendation.

## Provenance

Every fetched artifact carries:

- `source`: `fpl`, `vaastav` or `derived`;
- `fetchedAt`: when FPL Andres received the bytes;
- `dataAvailableAt`: the earliest time those bytes could legitimately inform a decision;
- `contentHash`: lowercase SHA-256 of the exact response bytes;
- `upstreamReference`: the exact endpoint or pinned revision URL.

`dataAvailableAt` cannot follow `fetchedAt`. Historical rows whose availability follows
the prediction cutoff are rejected before feature construction.

The canonical Zod schemas are exported to
`packages/contracts/generated/contracts.schema.json`. The Python Pydantic mirrors and
TypeScript schemas run the same valid/invalid corpora from
`packages/contracts/fixtures`. CI regenerates the JSON Schema in memory and fails on
drift.

## Public FPL endpoints

Only GET requests matching these families leave the same-origin proxy:

- `bootstrap-static/`;
- `fixtures/`, with optional `event=1..38`;
- `entry/{id}/`;
- `entry/{id}/history/`;
- `entry/{id}/event/{gw}/picks/`;
- `element-summary/{id}/`;
- `leagues-classic/{id}/standings/`, with bounded pagination and phase parameters.

The upstream host is fixed to `fantasy.premierleague.com`; incoming cookies,
authorization and forwarding headers are never copied. Alternate hosts, traversal,
encoded separators, unexpected query keys, duplicate query keys and out-of-range IDs
fail before a network request.

Responses must be JSON and remain below 8 MiB for bootstrap or 5 MiB otherwise.
Transient 408/425/429/5xx responses and transport failures retry at most 3 times with
bounded exponential jitter. Vercel proxy attempts share an 8.5-second total budget
inside the 10-second function lifetime. Ordinary 4xx responses do not retry. Picks 404s become a
typed `FplPicksUnavailable` fact without guessing whether the cause is future data or an
invalid entry.

## Published rules

`game_config.rules` is authoritative for the 9 squad, budget, transfer and currency
fields exposed by bootstrap. Each must exactly match its `game_settings` mirror.

`game_config.scoring` must expose the complete 35-field set captured for 2026/27.
Missing or newly added fields are contract failures until reviewed. Point-bearing
fields are parsed into `ScoringRules`; the full field-name set remains attached for
drift detection.

Every chip preserves its separate window, ID, type and explicit nullable
`overrides.pick_multiplier`. All override containers must exist. Repeated chip names
are never deduplicated.

### Rules not published in bootstrap

Bootstrap currently does not publish:

- the weekly base free-transfer award;
- DefCon action thresholds by position/role;
- the effective multiplier or bench behavior represented by each chip (the current
  `overrides.pick_multiplier` values are explicitly null, including Triple Captain);
- a complete textual definition for all assist and bonus edge cases.

These values must come from a season-specific authoritative addendum carrying its own
source reference, retrieval timestamp and content hash. They are arguments to rules
construction, not defaults in an adapter. Until that addendum is verified, affected
optimizer and scoring behavior remains unavailable.

## Public entry state

Raw entry payloads are normalized into `FplEntry`. Manager first/last name and region
fields are deliberately dropped. Pre-season `current_event`, bank and value may be
explicitly null; a missing key is different and fails the source contract.

Public state still reflects the last processed deadline. Private current transfers and
bank are corrected through a separate `TeamStateOverrides` contract in a later
milestone.

## Historical archive

Every vaastav path includes a 40-character commit SHA and season. CSV parsing removes
same-gameweek `xP` case-insensitively and records it in `excluded_fields`. The raw bytes
remain content-addressed for audit. Direct Understat crawling is prohibited by the
project capability boundary.

## Persistence

Raw bytes are intended for a private, content-addressed storage path. Postgres
`source_snapshots` and `rules_snapshots` hold immutable metadata and normalized rules.
Both tables use forced RLS with no anonymous/authenticated policy. Update/delete
triggers prevent provenance from being rewritten after use.

`projection_runs`, `team_goal_projections` and `model_promotion_decisions` apply the
same forced-RLS and immutability policy to derived artifacts. Predictions retain their
run cutoff, evidence level, latest evidence timestamp, source hashes and reason codes.
Promotion decisions retain paired interval values and every controlling bootstrap
parameter. Postgres rejects prediction evidence newer than its run cutoff and rejects
a promoted decision unless its sample floor is met and its paired lower confidence
bound is strictly positive.
