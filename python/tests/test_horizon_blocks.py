"""Each rule of the game, tested on its own.

`solve` was around two hundred lines of nested indexing with no
names on any of it. A reader had to work out from
`variable(free_used_offset, event_index, index)` which of eleven rules was being
written, and there was no way to check one block without solving the whole
problem -- so no block had ever been checked on its own.

These do. Each test builds one block into an empty model and reads the
constraints back. What they mostly prove is arity and shape: that a rule touches
the variables it claims to and bounds them where it says. That is the part a
misplaced offset breaks, and the part a full solve hides -- a wrong index
usually still produces a feasible plan, and a feasible plan looks fine.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest
from test_horizon_optimizer import horizon_request

from fpl_andres.optimization.horizon_model import (
    HORIZON_BLOCKS,
    PER_EVENT_BLOCKS,
    HorizonModel,
    bank_flow,
    build_constraints,
    captaincy_eligibility,
    club_limit,
    free_transfer_ledger,
    negated,
    opening_position,
    position_quotas,
    selection_hierarchy,
    sell_each_player_once,
    squad_composition,
    squad_continuity,
    transfer_balance,
)


@pytest.fixture
def model() -> HorizonModel:
    request = horizon_request()
    player_ids = tuple(
        sorted(
            forecast.element_id
            for forecast in request.forecasts
            if forecast.event == request.events[0].event
        )
    )
    forecasts = {(forecast.event, forecast.element_id): forecast for forecast in request.forecasts}
    return HorizonModel(request=request, player_ids=player_ids, forecasts=forecasts)


def constraints(model: HorizonModel) -> list[tuple[dict[int, float], float, float]]:
    """Read back what was written, one entry per constraint."""
    built: list[dict[int, float]] = [{} for _ in range(model.constraint_count)]
    for row, column, value in zip(model.rows, model.columns, model.values, strict=True):
        built[row][column] = value
    return list(zip(built, model.lower_bounds, model.upper_bounds, strict=True))


class TestLayout:
    def test_every_block_gets_its_own_range_of_variables(self, model: HorizonModel) -> None:
        # Six per-player blocks then the per-event scalars. An overlap here
        # would make two rules write to the same variable, and the solver would
        # satisfy both by satisfying neither.
        offsets = [
            model.squad_offset,
            model.lineup_offset,
            model.captain_offset,
            model.transfer_in_offset,
            model.transfer_out_offset,
            model.paid_offset,
        ]
        assert offsets == sorted(offsets)
        assert len(set(offsets)) == len(offsets)
        for earlier, later in pairwise(offsets):
            assert later - earlier == model.block_size

    def test_no_variable_index_escapes_the_declared_count(self, model: HorizonModel) -> None:
        build_constraints(model)
        assert max(model.columns) < model.variable_count
        assert min(model.columns) >= 0

    def test_a_variable_is_addressed_by_arithmetic_not_by_lookup(self, model: HorizonModel) -> None:
        for event_index in range(model.event_count):
            for player in range(model.player_count):
                assert model.variable(model.squad_offset, event_index, player) == (
                    event_index * model.player_count + player
                )


class TestSquadComposition:
    def test_it_pins_the_squad_and_lineup_sizes_from_the_published_rules(
        self, model: HorizonModel
    ) -> None:
        # Not from a constant here: FPL has changed the squad size before, and
        # a number written into the solver would be a second source of truth.
        squad_composition(model, 0)
        rows = constraints(model)
        assert len(rows) == 3
        squad, lineup, captain = rows
        assert squad[1] == squad[2] == model.request.rules.squad_size
        assert lineup[1] == lineup[2] == model.request.rules.lineup_size
        assert captain[1] == captain[2] == 1.0

    def test_each_count_touches_every_player_exactly_once(self, model: HorizonModel) -> None:
        squad_composition(model, 0)
        for coefficients, _, _ in constraints(model):
            assert len(coefficients) == model.player_count
            assert set(coefficients.values()) == {1.0}


class TestSelectionHierarchy:
    def test_a_starter_must_be_owned_and_a_captain_must_start(self, model: HorizonModel) -> None:
        # Without these the solver starts a player it never bought, and the
        # plan is arithmetically perfect and completely unplayable.
        selection_hierarchy(model, 0)
        rows = constraints(model)
        assert len(rows) == 2 * model.player_count
        for coefficients, lower, upper in rows:
            assert sorted(coefficients.values()) == [-1.0, 1.0]
            assert upper == 0.0
            assert lower == -np.inf


class TestCaptaincyEligibility:
    def test_it_pins_ineligible_captains_and_requires_two_eligible_starters(
        self, model: HorizonModel
    ) -> None:
        event = model.events[0]
        element_id = next(iter(model.player_index))
        key = (event.event, element_id)
        model.forecasts[key] = model.forecasts[key].model_copy(update={"position_id": 1})

        captaincy_eligibility(model, 0)

        pinned, eligible = constraints(model)
        assert pinned[1] == pinned[2] == 0.0
        assert list(pinned[0].values()) == [1.0]
        assert eligible[1] == 2.0
        assert eligible[2] == np.inf
        assert len(eligible[0]) == model.player_count - 1


class TestSquadContinuity:
    def test_the_first_event_is_pinned_to_the_squad_actually_held(
        self, model: HorizonModel
    ) -> None:
        # This is what stops the horizon inventing a starting point it prefers.
        squad_continuity(model, 0)
        rows = constraints(model)
        flows = [row for row in rows if len(row[0]) == 3]
        held = sum(1 for _, lower, _ in flows if lower == 1.0)
        assert held == len(model.current)

    def test_a_later_event_carries_the_previous_squad_forward(self, model: HorizonModel) -> None:
        squad_continuity(model, 1)
        flows = [row for row in constraints(model) if len(row[0]) == 4]
        assert len(flows) == model.player_count
        for coefficients, lower, upper in flows:
            assert lower == 0.0
            assert upper == 0.0
            assert min(coefficients) < model.player_count  # the previous event

    def test_buying_and_selling_the_same_player_in_one_week_is_refused(
        self, model: HorizonModel
    ) -> None:
        # A way to spend a transfer on nothing, which the solver will take to
        # satisfy a count.
        squad_continuity(model, 0)
        pairs = [row for row in constraints(model) if len(row[0]) == 2]
        assert len(pairs) == model.player_count
        for coefficients, _, upper in pairs:
            assert set(coefficients.values()) == {1.0}
            assert upper == 1.0


class TestPositionQuotas:
    def test_every_position_gets_a_squad_count_and_a_formation_range(
        self, model: HorizonModel
    ) -> None:
        position_quotas(model, 0)
        rows = constraints(model)
        assert len(rows) == 2 * len(model.request.rules.positions)
        for position, (squad, lineup) in zip(
            model.request.rules.positions,
            [rows[index : index + 2] for index in range(0, len(rows), 2)],
            strict=True,
        ):
            assert squad[1] == squad[2] == position.squad_count
            assert lineup[1] == position.lineup_minimum
            assert lineup[2] == position.lineup_maximum


class TestClubLimit:
    def test_players_are_grouped_by_the_club_the_forecast_names(self, model: HorizonModel) -> None:
        # A wrong club id splits one club into two groups and
        # lets six players through as three plus three.
        club_limit(model, 0)
        rows = constraints(model)
        clubs = {
            model.forecast(model.events[0], element_id).team_id for element_id in model.player_index
        }
        assert len(rows) == len(clubs)
        assert sum(len(coefficients) for coefficients, _, _ in rows) == model.player_count

    def test_each_group_is_capped_at_the_published_limit(self, model: HorizonModel) -> None:
        club_limit(model, 0)
        for _, lower, upper in constraints(model):
            assert upper == model.request.rules.club_limit
            assert lower == -np.inf


class TestTransferBalance:
    def test_every_player_in_is_a_player_out(self, model: HorizonModel) -> None:
        transfer_balance(model, 0)
        rows = constraints(model)
        assert len(rows) == 2
        balance = rows[1]
        assert balance[1] == 0.0
        assert balance[2] == 0.0
        assert sorted(set(balance[0].values())) == [-1.0, 1.0]

    def test_the_cap_comes_from_the_rules(self, model: HorizonModel) -> None:
        transfer_balance(model, 0)
        assert constraints(model)[0][2] == model.request.rules.transfer_cap


class TestBankFlow:
    def test_selling_and_buying_prices_are_kept_apart(self, model: HorizonModel) -> None:
        # FPL's selling price is not the market price: a player bought before a
        # rise sells for less than he now costs. Treating them as one is the
        # classic way to produce a plan the manager cannot afford.
        bank_flow(model, 0)
        coefficients, lower, upper = constraints(model)[0]
        assert lower == 0.0
        assert upper == 0.0
        event = model.events[0]
        for element_id, index in model.player_index.items():
            forecast = model.forecast(event, element_id)
            out_column = model.variable(model.transfer_out_offset, 0, index)
            in_column = model.variable(model.transfer_in_offset, 0, index)
            assert coefficients[out_column] == -forecast.sell_price_tenths
            assert coefficients[in_column] == forecast.buy_price_tenths

    def test_the_bank_carries_between_events(self, model: HorizonModel) -> None:
        bank_flow(model, 0)
        coefficients = constraints(model)[0][0]
        assert coefficients[model.bank_offset + 1] == 1.0
        assert coefficients[model.bank_offset] == -1.0


class TestFreeTransferLedger:
    def test_a_minimum_is_written_as_two_inequalities_and_a_switch(
        self, model: HorizonModel
    ) -> None:
        # Free transfers used is min(transfers made, free transfers held), and
        # a minimum is not linear. Two inequalities plus a binary saying which
        # one is tight.
        free_transfer_ledger(model, 0)
        rows = constraints(model)
        assert len(rows) == 8
        free_compare = model.free_compare_offset
        switches = [row for row in rows if free_compare in row[0]]
        assert len(switches) == 2

    def test_big_m_is_derived_rather_than_picked(self, model: HorizonModel) -> None:
        # A constant large enough "to be safe" weakens the relaxation and slows
        # the solve; too small silently forbids legal plans. This is the
        # largest the two sides can differ by, and no larger.
        rules = model.request.rules
        expected = float(
            rules.transfer_cap
            + rules.transfer_rules.maximum_free_transfers
            + rules.transfer_rules.weekly_free_transfers
        )
        free_transfer_ledger(model, 0)
        magnitudes = {
            abs(value)
            for coefficients, _, _ in constraints(model)
            for value in coefficients.values()
        }
        assert expected in magnitudes
        assert max(magnitudes) == expected

    def test_everything_not_free_is_paid_for(self, model: HorizonModel) -> None:
        free_transfer_ledger(model, 0)
        paid = model.paid_offset
        rows = [row for row in constraints(model) if paid in row[0]]
        assert len(rows) == 1
        coefficients, lower, upper = rows[0]
        assert coefficients[paid] == 1.0
        assert lower == 0.0
        assert upper == 0.0

    def test_the_carry_is_capped_at_the_published_maximum(self, model: HorizonModel) -> None:
        free_transfer_ledger(model, 0)
        rows = constraints(model)
        weekly = model.request.rules.transfer_rules.weekly_free_transfers
        assert any(upper == weekly for _, _, upper in rows)


class TestHorizonWide:
    def test_a_player_can_be_sold_once_and_only_if_held(self, model: HorizonModel) -> None:
        # Without this the solver sells a player it does not own in a later
        # week to balance a count, and a free player becomes money.
        sell_each_player_once(model)
        rows = constraints(model)
        assert len(rows) == model.player_count
        sellable = sum(1 for _, _, upper in rows if upper == 1.0)
        assert sellable == len(model.current)
        assert all(upper in (0.0, 1.0) for _, _, upper in rows)

    def test_the_opening_bank_and_free_transfers_are_facts(self, model: HorizonModel) -> None:
        opening_position(model)
        rows = constraints(model)
        assert len(rows) == 2
        for _, lower, upper in rows:
            assert lower == upper


class TestAssembly:
    def test_every_block_is_wired_into_the_build(self, model: HorizonModel) -> None:
        # A block written and never called is the failure this file exists to
        # make impossible: the rule reads correctly and is not enforced.
        build_constraints(model)
        assert model.constraint_count > 0

        counted = HorizonModel(
            request=model.request,
            player_ids=model.player_ids,
            forecasts=model.forecasts,
        )
        expected = 0
        for event_index in range(counted.event_count):
            for block in PER_EVENT_BLOCKS:
                before = counted.constraint_count
                block(counted, event_index)
                assert counted.constraint_count > before, f"{block.__name__} wrote nothing"
                expected = counted.constraint_count
        for horizon_block in HORIZON_BLOCKS:
            before = counted.constraint_count
            horizon_block(counted)
            assert counted.constraint_count > before, f"{horizon_block.__name__} wrote nothing"
            expected = counted.constraint_count

        assert model.constraint_count == expected

    def test_every_constraint_has_a_bound(self, model: HorizonModel) -> None:
        # An unbounded row is a row that constrains nothing while looking like
        # it does.
        build_constraints(model)
        for coefficients, lower, upper in constraints(model):
            assert coefficients, "a constraint with no variables"
            assert lower != -np.inf or upper != np.inf

    def test_no_constraint_is_empty(self, model: HorizonModel) -> None:
        build_constraints(model)
        assert len(model.rows) == len(model.columns) == len(model.values)
        assert len(set(model.rows)) == model.constraint_count


class TestNegated:
    def test_it_flips_every_sign_and_keeps_every_key(self) -> None:
        assert negated({1: 2.0, 3: -4.0, 5: 0.0}) == {1: -2.0, 3: 4.0, 5: -0.0}
