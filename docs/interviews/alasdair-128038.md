# Interview — Alasdair, entry 128038

Conducted 31 July 2026. Recorded verbatim, then assessed against what the engine
actually does today. Where the engine does not do something, that is stated
rather than softened.

Profile: <https://fantasy.premierleague.com/en/entry/128038/history>

---

## Interview

When I'm making a transfer, the things that I'm looking at is the form of the
players available relative to the form of my current squad. So if one of my
current players is performing poorly over the last few weeks, obviously I'll
transfer in somebody else performing well.

I'm also examining the fixture difficulties, looking at who's playing well, who's
got an easy run of fixtures, because they're more desirable.

I also consider squad value, and I try to capitalise on price rises and falls in
order to maximise my squad value, because that has great benefits in the back end
of the season.

I'm also looking a lot at matchups. I think it's very important — for example, I
will transfer a right-sided forward in if they're playing against a team who are
very vulnerable on their left side, because I feel like that forward will be able
to hopefully score or assist. And you can extrapolate this to a defender against
a team with an impotent attack: that defender is likely to keep a clean sheet.

I'll also consider who rivals are likely to be transferring in, because I don't
really want to miss out. Although, having said that, I like to look at low
ownership punts based on ownership to maximise rank. And I care more about my
mini-league than I do my overall rank when I'm doing this, so I look at my
mini-leagues.

I try to notice trends — for example, if a player's making lots of chances even
if the chances aren't being converted.

And I'm definitely looking at defensive contribution points, and how likely a
player is to get DefCon points versus the opposition. For example, a defender
who's dominant aerially playing against a team who puts high crosses in is
a dead cert for DefCon points. So I've got eight points there potentially from
four defenders who I will start with — that's the same as two or three goals in
my squad.

I do look at expected goals and expected assists, to see if anybody is
underperforming or overperforming on their xG or xA. That's really important.

And if there is a double or blank gameweek, I would try to maximise the number of
players I've got playing in a double gameweek. Although, from personal
experience, the double gameweeks don't seem to be worth the planning.

---

## Commentary

Eleven distinct ideas. Six are built, three are partial, two are absent.

### Built

**Relative form, not absolute.** He compares candidates against the players he
already owns rather than against the league. That is exactly what
`plan_transfers` does: a move is scored on `incoming − outgoing` over the
horizon, so an ordinary replacement for a collapsing asset can beat a good
replacement for a good one.

**Fixture difficulty.** Built, and built the way he describes it rather than as a
single number. Team attack and defence strength are estimated from results to
date, split by venue. His "defender against an impotent attack" is the clean
sheet route; his "easy run" is the horizon ladder at +1, +3, +5 and +7.

**Chances created without conversion.** This is the xG/xA path, and it is already
the primary input to the rate model: goals and assists are blended with expected
goals and expected assists rather than read raw. A player generating chances he
is not converting keeps his projection.

**Defensive contribution.** Priced at two points, thresholds of ten actions for
defenders and twelve for midfielders and forwards, from each player's own
observed rate. It is also fixture-adjusted in the direction he implies: a side
under pressure makes more defensive actions, so DefCon rises against stronger
opponents while clean sheets fall. His arithmetic is right and it is why the
route was worth 7.5 percent of all points scored in 2025/26.

**Doubles and blanks.** A blank gameweek projects zero and a double pays twice.
The free hit and bench boost are both dated to the largest doubles of the season.

**Low-ownership punts for rank.** `PlayerSwing` computes expected points against
the gap between your ownership and the field's. Worth flagging honestly: the
maths says effective ownership cancels out of a transfer's _expected_ gain and
changes only variance, so this is a risk decision rather than a returns one.
Measured, the rank-aware tilt is worth about sixteen points a season across four
seasons and lost one of them. Weak.

### Partial

**Rival transfers, not wanting to miss out.** The crowd's net transfers are read
and used as a baseline policy, and rival mini-league squads can be fetched and
turned into effective ownership. None of it currently feeds the recommendation.

**Mini-league over overall rank.** `rivals.py` measures ownership inside a named
league, which is the right denominator for his stated goal. Not yet wired to any
surface, and the points-to-rank mapping it would need does not exist.

**xG over- and underperformance as a signal.** Expected goals feed the rates
model, but a player is never explicitly flagged as running hot or cold against
his underlying numbers. He treats that gap as the signal; the engine treats it as
an input and then hides it.

### Absent

**Squad value and price changes.** Not modelled at all. `_squad_value` returns
the fixed opening budget, so no manager in the simulation ever gains or loses a
penny of team value. He is explicit that this compounds into the back end of a
season, and he is right. This is the single largest gap the interview exposes.

**Positional matchups.** A right-sided forward against a defensively weak left
side is a real effect and the engine has no concept of it. Team strength is a
single attack and defence figure per side. Modelling this needs positional event
data — which flank attacks come down, aerial duel rates, cross volume — none of
which is in the corpus. His aerially dominant defender against a crossing side is
the same class of idea, applied to DefCon.

### Worth testing

He says double gameweeks "don't seem to be worth the planning" despite planning
for them. That is a falsifiable claim and the corpus can answer it: compare a
policy that targets doubles against one that ignores them. If he is right, the
free hit and bench boost timing should be reconsidered.
