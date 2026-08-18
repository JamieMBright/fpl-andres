"""Recovering a goals distribution from the markets a free odds feed publishes.

The clean sheet a manager is paid for is P(the opponent scores nothing). A
correct-score market gives that directly, but no free redistributor publishes
one. What is free is 1X2 and over/under 2.5 goals, and those two are enough,
because of one convenient fact:

**The sum of two independent Poisson variables is Poisson.** So if each side's
goals are Poisson, total goals is Poisson with mean `total = home + away`, and
the over/under 2.5 market pins `total` exactly with no reference to which side
scores them. One market, one unknown, one root.

That leaves the split. 1X2 pins it, but not through the draw: independent
Poisson is known to under-price draws, which is the whole reason Dixon-Coles
exists. So the split is fitted to the ratio of home wins to away wins, which
does not use the draw at all, and the leftover draw error is *reported* as
`draw_residual` rather than absorbed. A caller that finds a large residual has
found the low-score dependence this model deliberately does not fit.

With both means in hand every scoreline follows, so the correct-score market
that could not be bought is reconstructed instead: `score_probability(1, 0)`
is a real number here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.optimize import brentq

from fpl_andres.models.odds import OddsUnavailable, devig_shin

__all__ = [
    "GoalExpectation",
    "fit_goal_expectation",
    "fit_goal_expectation_from_probabilities",
    "score_probability",
    "total_goals_mean",
]

# Beyond this the Poisson tail contributes less than a thousandth of a goal of
# probability mass, and the win/draw/loss sums have converged to float noise.
_MAX_GOALS = 15

# A Premier League match has never averaged outside this, and a root outside it
# means the market was misread rather than unusual.
_MIN_TOTAL = 0.2
_MAX_TOTAL = 12.0

# Supremacy is a goal difference, bounded by the same reasoning.
_MAX_SUPREMACY = 8.0


@dataclass(frozen=True)
class GoalExpectation:
    """Both sides' expected goals, and how far the fit had to stretch."""

    home: float
    away: float
    #: Market probability of a draw minus the fitted model's. Positive means the
    #: market prices more draws than independent Poisson can produce, which is
    #: the usual direction and the size of the Dixon-Coles correction forgone.
    draw_residual: float

    @property
    def total(self) -> float:
        return self.home + self.away

    @property
    def home_clean_sheet(self) -> float:
        """The home side keeps it out, so the away mean is what matters."""
        return math.exp(-self.away)

    @property
    def away_clean_sheet(self) -> float:
        return math.exp(-self.home)


def _poisson(k: int, mean: float) -> float:
    return math.exp(-mean) * mean**k / math.factorial(k)


def score_probability(home_goals: int, away_goals: int, fit: GoalExpectation) -> float:
    """One scoreline, which is the market this feed does not sell."""
    if home_goals < 0 or away_goals < 0:
        raise OddsUnavailable("a scoreline cannot be negative")
    return _poisson(home_goals, fit.home) * _poisson(away_goals, fit.away)


def total_goals_mean(over_probability: float, line: float = 2.5) -> float:
    """Invert an over/under market for the mean of the total-goals Poisson.

    Only whole-goal lines matter here: 2.5 means "three or more", so the under
    side is P(0) + P(1) + P(2), which is monotone decreasing in the mean. One
    root, found rather than approximated.
    """
    if not 0.0 < over_probability < 1.0:
        raise OddsUnavailable(f"an over probability must sit inside (0, 1), got {over_probability}")
    if line <= 0 or line != int(line) + 0.5:
        raise OddsUnavailable(f"only half-goal lines are invertible here, got {line}")

    below = int(line)

    def excess(mean: float) -> float:
        under = sum(_poisson(goals, mean) for goals in range(below + 1))
        return (1.0 - under) - over_probability

    if excess(_MIN_TOTAL) > 0 or excess(_MAX_TOTAL) < 0:
        raise OddsUnavailable(
            f"an over-{line} probability of {over_probability:.4f} implies a total "
            "outside anything a football match produces"
        )
    return float(brentq(excess, _MIN_TOTAL, _MAX_TOTAL, xtol=1e-10))


def _outcome_probabilities(home: float, away: float) -> tuple[float, float, float]:
    """P(home win), P(draw), P(away win) for two independent Poissons."""
    home_pmf = [_poisson(goals, home) for goals in range(_MAX_GOALS + 1)]
    away_pmf = [_poisson(goals, away) for goals in range(_MAX_GOALS + 1)]

    home_win = 0.0
    draw = 0.0
    away_win = 0.0
    for scored, home_p in enumerate(home_pmf):
        for conceded, away_p in enumerate(away_pmf):
            joint = home_p * away_p
            if scored > conceded:
                home_win += joint
            elif scored == conceded:
                draw += joint
            else:
                away_win += joint
    return home_win, draw, away_win


def fit_goal_expectation_from_probabilities(
    match_probabilities: tuple[float, float, float],
    total: float,
) -> GoalExpectation:
    """Fit goal means from an already de-vigged 1X2 view and goal total."""
    if not all(
        math.isfinite(probability) and probability > 0.0 for probability in match_probabilities
    ):
        raise OddsUnavailable("match probabilities must be finite and positive")
    probability_sum = sum(match_probabilities)
    if not math.isclose(probability_sum, 1.0, abs_tol=1e-6):
        raise OddsUnavailable(f"match probabilities sum to {probability_sum:.4f}, not one")
    if not math.isfinite(total) or not _MIN_TOTAL <= total <= _MAX_TOTAL:
        raise OddsUnavailable(f"a total of {total} sits outside anything a football match produces")

    home_p, market_draw, away_p = (
        probability / probability_sum for probability in match_probabilities
    )
    decisive = home_p + away_p
    if decisive <= 0.0:
        raise OddsUnavailable("a market with no decisive outcome cannot set a supremacy")
    target = home_p / decisive

    def excess(supremacy: float) -> float:
        home_win, _, away_win = _outcome_probabilities(
            (total + supremacy) / 2.0, (total - supremacy) / 2.0
        )
        if home_win + away_win <= 0.0:
            return -target
        return home_win / (home_win + away_win) - target

    bound = min(_MAX_SUPREMACY, total - 1e-9)
    if excess(-bound) > 0 or excess(bound) < 0:
        raise OddsUnavailable(
            f"a home share of {target:.4f} at a total of {total:.3f} is not reachable"
        )
    supremacy = float(brentq(excess, -bound, bound, xtol=1e-10))

    home = (total + supremacy) / 2.0
    away = (total - supremacy) / 2.0
    _, model_draw, _ = _outcome_probabilities(home, away)
    return GoalExpectation(home=home, away=away, draw_residual=market_draw - model_draw)


def fit_goal_expectation(
    match_odds: tuple[float, float, float],
    over_under: tuple[float, float],
    line: float = 2.5,
) -> GoalExpectation:
    """Fit both expected-goal means from a 1X2 book and an over/under book.

    `match_odds` is decimal home, draw, away. `over_under` is decimal over then
    under. Both are de-vigged with Shin's method before anything is fitted,
    because a quoted price is not a probability and the margin is not spread
    evenly across the outcomes.
    """
    home_probability, draw_probability, away_probability = devig_shin(match_odds)
    match_probabilities = home_probability, draw_probability, away_probability
    over_p, _under_p = devig_shin(over_under)
    total = total_goals_mean(over_p, line)
    return fit_goal_expectation_from_probabilities(match_probabilities, total)
