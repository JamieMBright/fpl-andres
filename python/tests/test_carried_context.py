"""A carried season is discounted when it was produced somewhere else.

The cross-season blend weighted the carried season by minutes
alone, so a striker's twenty goals for a relegated side counted exactly as
twenty goals for the side he still plays for. A move changes the service, the
set pieces and the penalty order; a move to a deeper role changes what the
position prior should even be.

Three answers, and the third matters as much as the others: same, changed, and
unknown. Unknown is not treated as same, because a source that cannot say is a
source that cannot rule out a move, and reading it as "unchanged" applies the
optimistic answer exactly where there is no evidence for it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fpl_andres.models.player_rates import (
    PlayerRateEvidence,
    RateObservation,
    RatePrior,
    project_player_rates,
)

CUTOFF = datetime(2026, 9, 12, 9, tzinfo=UTC)
HASH = "sha256:" + "a" * 64


def observation(
    *,
    season: str,
    event_id: int,
    minutes: int = 90,
    goals: int = 1,
    team_id: int | None = None,
    position_id: int | None = None,
    days_before: int = 400,
) -> RateObservation:
    return RateObservation(
        season=season,
        event_id=event_id,
        minutes=minutes,
        goals=goals,
        assists=0,
        kickoff_time=CUTOFF - timedelta(days=days_before),
        team_id=team_id,
        position_id=position_id,
    )


def evidence(
    *,
    current: tuple[RateObservation, ...],
    carried: tuple[RateObservation, ...],
    carried_context_weight: float,
) -> PlayerRateEvidence:
    return PlayerRateEvidence(
        element_code=154561,
        season="2026-27",
        prediction_event=5,
        current_season_observations=current,
        prior_season_observations=carried,
        prior=RatePrior(goals_per_90=0.28, assists_per_90=0.12, strength_minutes=450.0),
        minimum_minutes=180.0,
        blend_full_weight_minutes=900.0,
        carried_context_weight=carried_context_weight,
        decay_half_life_events=8.0,
        prediction_cutoff=CUTOFF,
        data_available_at=CUTOFF - timedelta(hours=1),
        source_hashes=(HASH,),
    )


def season(
    label: str,
    *,
    events: int,
    team_id: int | None,
    position_id: int | None,
    days_before: int,
    goals: int = 1,
) -> tuple[RateObservation, ...]:
    return tuple(
        observation(
            season=label,
            event_id=index + 1,
            goals=goals,
            team_id=team_id,
            position_id=position_id,
            days_before=days_before - index,
        )
        for index in range(events)
    )


def reason(projection: object, prefix: str) -> str:
    codes = projection.reason_codes  # type: ignore[attr-defined]
    return next(code for code in codes if code.startswith(prefix))


class TestContextDetection:
    def test_the_same_club_and_role_is_reported_as_same(self) -> None:
        result = project_player_rates(
            evidence(
                current=season("2026-27", events=3, team_id=1, position_id=4, days_before=20),
                carried=season("2025-26", events=10, team_id=1, position_id=4, days_before=400),
                carried_context_weight=0.6,
            )
        )
        assert reason(result, "carried_context=") == "carried_context=same"

    def test_a_different_club_is_reported_as_changed(self) -> None:
        result = project_player_rates(
            evidence(
                current=season("2026-27", events=3, team_id=2, position_id=4, days_before=20),
                carried=season("2025-26", events=10, team_id=1, position_id=4, days_before=400),
                carried_context_weight=0.6,
            )
        )
        assert reason(result, "carried_context=") == "carried_context=changed"

    def test_a_different_role_is_reported_as_changed(self) -> None:
        # A forward dropped into midfield keeps his club and loses his service.
        result = project_player_rates(
            evidence(
                current=season("2026-27", events=3, team_id=1, position_id=3, days_before=20),
                carried=season("2025-26", events=10, team_id=1, position_id=4, days_before=400),
                carried_context_weight=0.6,
            )
        )
        assert reason(result, "carried_context=") == "carried_context=changed"

    def test_a_source_that_records_neither_is_reported_as_unknown(self) -> None:
        result = project_player_rates(
            evidence(
                current=season("2026-27", events=3, team_id=None, position_id=None, days_before=20),
                carried=season(
                    "2025-26", events=10, team_id=None, position_id=None, days_before=400
                ),
                carried_context_weight=0.6,
            )
        )
        assert reason(result, "carried_context=") == "carried_context=unknown"

    def test_a_half_recorded_source_is_unknown_rather_than_same(self) -> None:
        # The trap. One side knows the club, the other does not, and the two
        # happen not to contradict each other -- which is not evidence that
        # they agree.
        result = project_player_rates(
            evidence(
                current=season("2026-27", events=3, team_id=1, position_id=4, days_before=20),
                carried=season("2025-26", events=10, team_id=None, position_id=4, days_before=400),
                carried_context_weight=0.6,
            )
        )
        assert reason(result, "carried_context=") == "carried_context=unknown"

    def test_the_most_recent_appearance_decides_it(self) -> None:
        # A player who moved in January is described by where he plays now.
        # Averaging the two halves of his season describes nowhere.
        first_half = tuple(
            observation(
                season="2025-26",
                event_id=index + 1,
                team_id=1,
                position_id=4,
                days_before=420 - index,
            )
            for index in range(5)
        )
        second_half = tuple(
            observation(
                season="2025-26",
                event_id=index + 6,
                team_id=2,
                position_id=4,
                days_before=380 - index,
            )
            for index in range(5)
        )
        result = project_player_rates(
            evidence(
                current=season("2026-27", events=3, team_id=2, position_id=4, days_before=20),
                carried=(*first_half, *second_half),
                carried_context_weight=0.6,
            )
        )
        assert reason(result, "carried_context=") == "carried_context=same"


class TestDiscount:
    def test_a_move_lowers_the_carried_weight(self) -> None:
        current = season("2026-27", events=3, team_id=2, position_id=4, days_before=20)
        carried = season("2025-26", events=10, team_id=1, position_id=4, days_before=400)
        stayed = season("2025-26", events=10, team_id=2, position_id=4, days_before=400)

        moved_result = project_player_rates(
            evidence(current=current, carried=carried, carried_context_weight=0.6)
        )
        stayed_result = project_player_rates(
            evidence(current=current, carried=stayed, carried_context_weight=0.6)
        )
        assert moved_result.carried_weight < stayed_result.carried_weight
        assert moved_result.carried_weight == pytest.approx(stayed_result.carried_weight * 0.6)

    def test_a_weight_of_one_leaves_the_previous_behaviour_exactly(self) -> None:
        # The escape hatch a caller uses to say "I have not decided this yet",
        # and the reason every existing call site could be updated mechanically.
        current = season("2026-27", events=3, team_id=2, position_id=4, days_before=20)
        carried = season("2025-26", events=10, team_id=1, position_id=4, days_before=400)
        stayed = season("2025-26", events=10, team_id=2, position_id=4, days_before=400)

        moved = project_player_rates(
            evidence(current=current, carried=carried, carried_context_weight=1.0)
        )
        unmoved = project_player_rates(
            evidence(current=current, carried=stayed, carried_context_weight=1.0)
        )
        assert moved.carried_weight == pytest.approx(unmoved.carried_weight)

    def test_a_weight_of_zero_discards_the_carried_season_entirely(self) -> None:
        result = project_player_rates(
            evidence(
                current=season("2026-27", events=3, team_id=2, position_id=4, days_before=20),
                carried=season("2025-26", events=10, team_id=1, position_id=4, days_before=400),
                carried_context_weight=0.0,
            )
        )
        assert result.carried_weight == pytest.approx(0.0)

    def test_an_unknown_context_is_not_discounted(self) -> None:
        # Discounting on a suspicion is as wrong as ignoring one. The reason
        # code is what carries the doubt forward.
        current = season("2026-27", events=3, team_id=None, position_id=None, days_before=20)
        carried = season("2025-26", events=10, team_id=None, position_id=None, days_before=400)
        discounted = project_player_rates(
            evidence(current=current, carried=carried, carried_context_weight=0.1)
        )
        undiscounted = project_player_rates(
            evidence(current=current, carried=carried, carried_context_weight=1.0)
        )
        assert discounted.carried_weight == pytest.approx(undiscounted.carried_weight)

    def test_the_weights_still_sum_to_one(self) -> None:
        # The discount moves weight onto the current season rather than losing
        # it. A blend that does not sum to one is not a blend.
        result = project_player_rates(
            evidence(
                current=season("2026-27", events=3, team_id=2, position_id=4, days_before=20),
                carried=season("2025-26", events=10, team_id=1, position_id=4, days_before=400),
                carried_context_weight=0.6,
            )
        )
        assert 0.0 <= result.carried_weight <= 1.0
        assert reason(result, "carried_weight=")

    def test_the_discount_cannot_produce_a_carried_weight_without_a_season(self) -> None:
        # The projection contract refuses a carried weight with nothing carried,
        # which is the failure This found the other way round.
        result = project_player_rates(
            evidence(
                current=season("2026-27", events=4, team_id=2, position_id=4, days_before=20),
                carried=(),
                carried_context_weight=0.6,
            )
        )
        assert result.carried_weight == 0.0
        assert result.carried_season is None


class TestContract:
    @pytest.mark.parametrize("weight", [-0.1, 1.1])
    def test_a_weight_outside_zero_to_one_is_refused(self, weight: float) -> None:
        with pytest.raises(ValueError, match="carried_context_weight"):
            evidence(
                current=season("2026-27", events=3, team_id=1, position_id=4, days_before=20),
                carried=season("2025-26", events=10, team_id=1, position_id=4, days_before=400),
                carried_context_weight=weight,
            )

    def test_the_weight_has_no_default(self) -> None:
        # A Caller parameter in docs/PARAMETERS.md: a contract field with no
        # default, so a caller that has not thought about it cannot proceed by
        # accident.
        with pytest.raises(ValueError, match="carried_context_weight"):
            PlayerRateEvidence(
                element_code=154561,
                season="2026-27",
                prediction_event=5,
                prior=RatePrior(goals_per_90=0.28, assists_per_90=0.12, strength_minutes=450.0),
                minimum_minutes=180.0,
                blend_full_weight_minutes=900.0,
                prediction_cutoff=CUTOFF,
                data_available_at=CUTOFF - timedelta(hours=1),
                source_hashes=(HASH,),
            )  # type: ignore[call-arg]

    @pytest.mark.parametrize(("team_id", "position_id"), [(0, 4), (21, 4), (1, 0), (1, 5)])
    def test_an_out_of_range_club_or_role_is_refused(self, team_id: int, position_id: int) -> None:
        # Twenty clubs, four positions. This is the reason the club
        # bound matters: a wrong id splits one club into two groups.
        with pytest.raises(ValueError):
            observation(season="2025-26", event_id=1, team_id=team_id, position_id=position_id)
