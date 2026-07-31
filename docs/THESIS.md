# Core thesis

Stated by the owner, 31 July 2026. This is the specification the recommendation
engine is measured against. Everything in `docs/BUILD_PLAN.md` serves it, and
anything that does not serve it is not worth building.

## The claim

Given an accurate projection of expected points from now until the end of the
season, there exists an optimal path of free transfers, substitutions and
captaincies that converts the current team into the highest probability of
scoring the most points.

The thesis is not that we predict football better than anyone else. It is that
**we use probability to maximise the likelihood of outperforming a baseline**.

## How it is proved

Take any random opening team. Run the planning algorithm, which decides which
transfers, substitutions and captaincies happen and when. Execute that plan,
re-planning at every gameweek as new information arrives. Compare the points
against baselines.

## Baselines, weakest to strongest

1. **Zombie.** Do nothing. Establishes what skill is worth at all.
2. **Form chaser.** The conventional non-naive way people actually play:
   transfer in the highest-form player not already owned. This is the honest
   comparison, because it is what a competent human does.
3. **The crowd.** The most-transferred-in player each gameweek, from the
   published transfer counts. Beating the aggregate decision of eleven million
   managers is the real bar.

## xPts becomes ExPts

Expected points are not the objective. **Effective points** are: the points that
actually move you up a ranking, measured against either overall rank or a
specific mini-league. A haul everyone else also owns moves nobody. The
conversion from xPts to ExPts is what separates scoring well from finishing
well.

## The model must update

Priors are updated by each gameweek's result as it arrives, and the posterior
becomes the prior for the next. All available information is used to project
from the current gameweek to the end of the season, maximising both total points
and rank climb.

## Chips are part of the plan, not an afterthought

- **Wildcard**, one per half-season. Play it when unlimited transfers would
  dramatically raise ExPts. Every gameweek is a candidate and the optimum is
  found by analysis, not feel.
- **Free Hit**, once per season. Best when at most one free transfer is
  available and a completely different team is wanted for a single gameweek.
  It raises ExPts for the next gameweek only, then the squad reverts, so its
  value is a one-week spike rather than a lasting improvement.
- **Triple Captain**, once per season. Play it on the single highest ExPts
  player-gameweek of the season.
- **Bench Boost**, once per season. Not yet specified by the owner.

## Consequence

A plan that ignores chips, or that optimises raw points rather than rank
movement, or that cannot re-plan as results arrive, is not an implementation of
this thesis. It is a weaker thing that happens to share some of its vocabulary.
