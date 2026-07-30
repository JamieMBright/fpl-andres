# Optimizer Contract

FPL Andres has two squad solvers behind explicit capability boundaries. Neither solver
is a live recommendation until its player forecasts are promoted and the product API
connects a validated team state to it.

## Exact input state

`PublicTeamState` is assembled from the public entry and picks endpoints for the last
processed deadline. It preserves the 15 picks, captaincy, bank, value, transfer cost,
source timestamps and exact content hashes. It does not contain current private free
transfers, purchase/selling prices, queued moves or available chips.

`TeamStateOverrides` is a separate manager-supplied object. A planning state exists only
when the priced 15-player squad, bank, free transfers, queued transfer delta and chips
are explicit and reconcile with the public snapshot. Browser storage is local, strict,
and namespaced by team ID plus public deadline. A canonical SHA-256 identifies the
validated override object; persisted plans store this hash and timestamps, not the raw
override JSON or priced squad.

## Pre-GW1 initial squad

FPL Andres must support an initial-squad recommendation before FPL has processed the
first deadline. This mode does not accept or require a Team ID because no public picks
snapshot exists yet. It is a squad-construction problem, not a transfer problem.

An initial-squad request must supply:

- the official FPL player list, prices, listed positions, clubs and availability fields;
- the published fixture schedule and an explicit prediction cutoff;
- promoted, timestamped player forecasts for every event in the requested opening
  horizon;
- a season-specific rules snapshot containing the initial budget, squad/formation
  counts and club limit; and
- explicit event weights and horizon rather than a hidden default.

The solver chooses the 15-player squad, GW1 starting XI, captain and vice-captain while
enforcing those sourced rules. It must attach forecast evidence levels, source hashes
and timestamps to the result. Missing role or heatmap evidence only disables the OOP
signal; it does not block initial-squad construction. A recommendation remains
unavailable until its player forecasts pass the promotion contract.

## Single-event HiGHS

The SciPy/HiGHS MILP chooses the final squad, starting XI and captain while enforcing:

- exact squad and lineup sizes;
- exact position counts and formation bounds;
- maximum players per club;
- current selling-value budget and candidate purchase prices;
- transfer cap, available free transfers and sourced hit cost;
- one captain in the XI and a deterministic vice-captain.

The primary objective is net expected points after transfer cost. Secondary solves
minimize transfers and then prefer stronger retained squads with deterministic ID
tie-breaking. An output is accepted only when HiGHS proves optimality.

## Rolling HiGHS

The rolling solver optimizes all supplied events jointly. Bank and free-transfer state
flow between events; unused free transfers receive the sourced weekly award and remain
under the sourced season cap. Each event has an explicit cutoff, objective weight,
forecast panel and transaction-price scenario.

The current price scenario is `provided_event_prices`. To avoid inventing the effective
selling price of a player bought during the plan, only players held at the initial
deadline may be sold, and each can be sold at most once. A player acquired inside the
horizon cannot be resold. More complete churn requires acquisition-cohort price
accounting and is unavailable rather than approximated.

## Bounded quick solver

The TypeScript quick solver uses same-position replacement beam search. It evaluates
lineup formation and captaincy exactly inside each retained squad, ranks truncated
candidates by feasible one-transfer squad gain under club and budget constraints, and
reports hard diagnostics for candidate limits, beam width, transfer depth, evaluated
states and truncation.

The shared regret corpus is independently solved by Python HiGHS. With beam width 16,
eight candidates per position and two transfers, the current three-case corpus has
zero regret. A local 600-solve Windows baseline on 2026-07-29, including a 15-player
FPL-shaped case, measured p50 0.17 ms, p95 8.23 ms and max 10.00 ms. These are local
engineering measurements, not a production latency SLO or a population-wide regret
claim.

## Explicitly unsupported modes

All current requests must declare:

- objective `expected_value`;
- chip scenario `none`;
- `current_prices` for one-event plans or `provided_event_prices` for rolling plans.

Protect-rank and chase-rank objectives need calibrated outcome distributions and an
explicit utility contract. Chip scenarios need authoritative multiplier, bench and
transfer behavior that bootstrap currently does not publish. Other values fail schema
validation instead of silently falling back to expected value or no-chip behavior.

## Audit persistence

`optimization_runs` and `optimization_event_plans` are immutable, forced-RLS tables
with no browser policy. They retain solver identity, configuration, objective, price
and chip scenarios, cutoff chronology, public hashes, manager override hash, structured
event decisions and evidence hashes. Postgres validates hash formats, array uniqueness,
squad/lineup partitioning, captaincy membership and transfer accounting independently
of the application models.
