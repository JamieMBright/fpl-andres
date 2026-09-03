from __future__ import annotations

from pathlib import Path

from fpl_andres.jsonio import read_json_file

ROOT = Path(__file__).resolve().parents[2]


def test_fpl_is_the_club_authority_for_every_solver_player() -> None:
    global_snapshot = read_json_file(ROOT / "apps" / "web" / "public" / "fpl-global.json")
    season_inputs = read_json_file(ROOT / "apps" / "web" / "src" / "data" / "season-inputs.json")
    bootstrap = global_snapshot["bootstrap"]
    teams = {int(team["id"]): str(team["short_name"]) for team in bootstrap["teams"]}
    current = {int(player["code"]): player for player in bootstrap["elements"]}
    mismatches: list[str] = []

    for player in season_inputs["players"]:
        source = current.get(int(player["code"]))
        if source is None:
            continue
        team_id = int(source["team"])
        if int(player["teamId"]) != team_id or player["club"] != teams[team_id]:
            mismatches.append(
                f"{player['name']}: solver {player['club']}/{player['teamId']}, "
                f"FPL {teams[team_id]}/{team_id}"
            )

    assert mismatches == [], "club assignments diverged from FPL: " + "; ".join(mismatches)
