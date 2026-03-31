"""
/api/season/projections — all 30 teams with CI, pace, and narrative
/api/season/standings — projected division standings
"""

from fastapi import APIRouter, Request, HTTPException
from app.config import PROJECTION_YEAR

router = APIRouter(prefix="/api")

# Division → list of team names for sorting
DIVISIONS = [
    "American League East",
    "American League Central",
    "American League West",
    "National League East",
    "National League Central",
    "National League West",
]


LG_AVG_OPS = 0.720
LG_AVG_SP_ERA = 4.20
LG_AVG_BP_ERA = 4.30
LG_AVG_WAR = 18.0   # average detectable roster WAR in our model


def _generate_narrative(team_proj: dict) -> str:
    """
    Generate a specific, data-grounded one-line narrative.
    Identifies the single biggest driver — offense, rotation, bullpen, run differential
    luck/regression, WAR concentration, or depth — from actual projected numbers.
    No hardcoded team names.
    """
    wins = team_proj.get("projected_wins", 81)
    pyth = float(team_proj.get("pythagorean_wins") or wins)
    last_actual = int(team_proj.get("last_season_wins") or wins)
    # luck_delta = prior-year Pythagorean minus prior-year actual wins
    # Positive = team underperformed their RS/RA (should improve — regression toward Pythagorean)
    # Negative = team overperformed their RS/RA (regression risk)
    luck_delta = float(team_proj.get("luck_delta") or 0)
    war = float(team_proj.get("total_war") or 0)
    rs = int(team_proj.get("projected_rs") or 700)
    ra = int(team_proj.get("projected_ra") or 700)

    batters = [b for b in team_proj.get("batters", []) if b.get("ops")]
    pitchers = team_proj.get("pitchers", [])

    # --- Offensive metrics ---
    ops_vals = sorted([b["ops"] for b in batters], reverse=True)
    avg_ops = sum(ops_vals) / len(ops_vals) if ops_vals else LG_AVG_OPS
    # WAR from top batter
    top_batter = max(batters, key=lambda b: b.get("war") or 0) if batters else None
    top_bat_war = top_batter.get("war", 0) if top_batter else 0
    top_bat_name = top_batter["name"] if top_batter else None
    # Lineup depth: count batters projected above 2.0 WAR
    impact_bats = sum(1 for b in batters if (b.get("war") or 0) >= 2.0)

    # --- Rotation metrics ---
    starters = [p for p in pitchers if p.get("position") == "SP" and p.get("era")]
    relievers = [p for p in pitchers if p.get("position") == "RP" and p.get("era")]
    sp_eras = [p["era"] for p in starters]
    bp_eras = [p["era"] for p in relievers]
    avg_sp_era = sum(sp_eras) / len(sp_eras) if sp_eras else LG_AVG_SP_ERA
    avg_bp_era = sum(bp_eras) / len(bp_eras) if bp_eras else LG_AVG_BP_ERA
    qualified_starters = sum(1 for p in starters if (p.get("ip") or 0) >= 150)
    top_sp = max(starters, key=lambda p: p.get("war") or 0) if starters else None
    top_sp_war = top_sp.get("war", 0) if top_sp else 0

    # --- Run differential signal ---
    run_diff = rs - ra
    # luck_delta: prior-year Pythagorean - prior-year actual wins
    # Large positive = won fewer than RS/RA expected → likely to improve (Tango regression)
    # Large negative = won more than RS/RA expected → regression risk
    luck_divergence = abs(luck_delta) > 5
    underperformed_luck = luck_delta > 5    # should win more (improvement candidate)
    overperformed_luck  = luck_delta < -5   # lucky, regression risk

    # --- Categorize team (calibrated to realistic Marcel projection ranges) ---
    ops_delta = avg_ops - LG_AVG_OPS          # positive = better than league
    sp_delta = LG_AVG_SP_ERA - avg_sp_era      # positive = better than league
    bp_delta = LG_AVG_BP_ERA - avg_bp_era      # positive = better than league

    # Thresholds calibrated to actual Marcel output distributions (OPS range ~.695-.740, ERA range 3.80-4.65)
    offense_elite   = ops_delta >  0.015   # OPS > .735
    offense_good    = ops_delta >  0.005   # OPS > .725
    offense_below   = ops_delta < -0.010   # OPS < .710
    offense_poor    = ops_delta < -0.020   # OPS < .700
    rotation_elite  = sp_delta  >  0.25   # ERA < 3.95
    rotation_good   = sp_delta  >  0.10   # ERA < 4.10
    rotation_below  = sp_delta  < -0.15   # ERA > 4.35
    rotation_poor   = sp_delta  < -0.35   # ERA > 4.55
    bullpen_poor    = bp_delta  < -0.20   # BP ERA > 4.50
    depth_thin      = war < 12
    # SP WAR from Marcel is unreliable (undercounts IP); use ERA + batter depth instead
    lineup_one_dim  = top_bat_war > 4.0 and impact_bats <= 1
    lineup_thin     = impact_bats <= 1 and top_bat_war <= 4.0

    # --- Build narrative from most distinctive characteristic ---

    # 1. Luck / Pythagorean divergence — if large, this is THE story
    if underperformed_luck:
        return (
            f"Prior-year Pythagorean ({int(pyth)}W) exceeded actual wins by {luck_delta:.0f}W — "
            f"unlucky in one-run games/sequencing; OLS model projects regression improvement to {wins}W"
        )
    if overperformed_luck:
        return (
            f"Won {abs(luck_delta):.0f}W more than run differential implied (Pythagorean: {int(pyth)}W) — "
            f"bullpen sequencing/one-run game luck embeds regression risk into the {wins}W projection"
        )

    # 2. Elite / balanced teams (rotation_elite threshold: avg ERA < 3.95)
    if rotation_elite and offense_elite:
        return (
            f"Complete team: {avg_ops:.3f} OPS offense ({ops_delta:+.3f} vs league) + {avg_sp_era:.2f} ERA rotation — "
            f"{run_diff:+d} run differential with {impact_bats} batters ≥2 WAR supports {wins}W"
        )
    if rotation_elite and offense_good:
        return (
            f"Rotation-led with above-average offense: {avg_sp_era:.2f} ERA staff ({sp_delta:+.2f} vs league) + "
            f"{avg_ops:.3f} OPS lineup; {run_diff:+d} run differential projects {wins}W"
        )
    if rotation_elite and offense_below:
        return (
            f"Pitching-first identity: {avg_sp_era:.2f} ERA rotation ({sp_delta:+.2f} vs league) is the engine, "
            f"but {avg_ops:.3f} OPS lineup ({ops_delta:.3f} below league) caps the offensive ceiling"
        )
    if rotation_elite:
        return (
            f"Rotation is the differentiator at {avg_sp_era:.2f} ERA ({sp_delta:+.2f} vs league) — "
            f"average offense ({avg_ops:.3f} OPS) means run prevention, not run-scoring, drives {wins}W"
        )

    # 3. Single-star dependency (one elite bat carrying a thin lineup)
    if lineup_one_dim and top_bat_name:
        return (
            f"{top_bat_name} ({top_bat_war:.1f} WAR) is the offensive engine with only {impact_bats} "
            f"other bat(s) ≥2 WAR — {avg_sp_era:.2f} ERA rotation; projection vulnerable to injury"
        )

    # 4. Offense-first teams
    if offense_elite and rotation_below:
        return (
            f"Offense-first: {avg_ops:.3f} OPS lineup ({ops_delta:+.3f} above league) is carrying a "
            f"{avg_sp_era:.2f} ERA rotation — bullpen leverage losses are the primary risk"
        )
    if offense_elite and rotation_good:
        return (
            f"Deep, above-average offense ({avg_ops:.3f} OPS, {impact_bats} bats ≥2 WAR) paired with "
            f"solid {avg_sp_era:.2f} ERA rotation; {run_diff:+d} run differential supports {wins}W"
        )
    if offense_elite:
        return (
            f"Offense-driven: {avg_ops:.3f} OPS lineup ({ops_delta:+.3f} above league) with {impact_bats} "
            f"impact bats; rotation ERA {avg_sp_era:.2f} is acceptable but not a strength"
        )

    # 5. Rotation weakness with a capable lineup
    if rotation_poor and offense_good:
        return (
            f"Rotation is the primary drag ({avg_sp_era:.2f} ERA, {sp_delta:.2f} below league) — "
            f"{avg_ops:.3f} OPS lineup generates enough offense to stay competitive but ceiling is capped"
        )
    if rotation_below and offense_good:
        return (
            f"Below-average rotation ({avg_sp_era:.2f} ERA, {sp_delta:.2f} below league) is the key drag — "
            f"{avg_ops:.3f} OPS lineup provides enough offense to contend; health of staff is the variable"
        )
    if rotation_below and offense_below and wins >= 75:
        return (
            f"Below-average on both sides: {avg_sp_era:.2f} ERA rotation and {avg_ops:.3f} OPS lineup both "
            f"trail league norms — {run_diff:+d} run differential and {war:.1f} WAR carry the {wins}W projection"
        )
    if rotation_poor:
        return (
            f"Rotation is a significant liability ({avg_sp_era:.2f} ERA, {sp_delta:.2f} vs league) — "
            f"average offense ({avg_ops:.3f} OPS) offers limited margin for error; wins come in low-scoring games"
        )

    # 6. Offense weakness with solid pitching
    if offense_poor and rotation_good:
        return (
            f"Run production is the ceiling: {avg_ops:.3f} OPS lineup ({ops_delta:.3f} below league) — "
            f"{avg_sp_era:.2f} ERA rotation keeps games close but lineup needs improvement to contend"
        )
    if offense_below and rotation_good:
        return (
            f"Pitching-reliant profile: {avg_sp_era:.2f} ERA rotation ({sp_delta:+.2f} above league) compensates "
            f"for a below-average {avg_ops:.3f} OPS lineup; {run_diff:+d} run differential anchors {wins}W"
        )

    # 7. Bullpen liability when rotation is sound
    if bullpen_poor and not rotation_below:
        return (
            f"Rotation ({avg_sp_era:.2f} ERA) solid but bullpen ({avg_bp_era:.2f} ERA) is a liability — "
            f"blown saves and leverage losses threaten the {run_diff:+d} run differential advantage"
        )

    # 8. Thin lineup depth (no stars, no depth)
    if lineup_thin:
        depth_str = "no batters" if impact_bats == 0 else f"only {impact_bats} batter"
        return (
            f"Limited lineup depth — {depth_str} projecting ≥2.0 WAR; {avg_ops:.3f} OPS average, "
            f"{avg_sp_era:.2f} ERA rotation must shoulder the burden to reach {wins}W"
        )

    # 9. High run differential contender (not caught by earlier branches)
    if run_diff >= 100 and wins >= 95:
        return (
            f"Run differential powerhouse at {run_diff:+d} ({rs} RS / {ra} RA) — {avg_ops:.3f} OPS offense "
            f"and {avg_sp_era:.2f} ERA rotation both above-average; {war:.1f} WAR roster depth"
        )

    # 10. Balanced contender / fringe
    if wins >= 92:
        return (
            f"Well-rounded contender: {avg_ops:.3f} OPS / {avg_sp_era:.2f} ERA rotation, {run_diff:+d} "
            f"run differential — {impact_bats} impact bats and {war:.1f} WAR support a playoff push"
        )
    if wins >= 85:
        return (
            f"Fringe contender: {avg_ops:.3f} OPS / {avg_sp_era:.2f} ERA — competitive across both sides; "
            f"{run_diff:+d} run differential and {impact_bats} impact bat(s) define the ceiling"
        )
    if wins >= 80:
        return (
            f"Middle-of-the-pack profile: {avg_ops:.3f} OPS / {avg_sp_era:.2f} ERA rotation — "
            f"no dominant dimension; {run_diff:+d} run differential and {war:.1f} WAR anchor {wins}W"
        )

    # 11. Rebuilding
    if wins < 75:
        return (
            f"Active rebuild: {rs}-{ra} run differential ({run_diff:+d}) and {war:.1f} WAR depth anchor "
            f"the projection at {wins}W — player development outcomes set the 2027 ceiling"
        )

    return (
        f"Projected at {wins}W on {run_diff:+d} run differential ({rs} RS / {ra} RA); "
        f"{avg_ops:.3f} OPS offense, {avg_sp_era:.2f} rotation ERA, {war:.1f} total WAR"
    )


def _current_pace(team_proj: dict, current_season_data: dict | None) -> dict:
    """Compute how the team is pacing vs projection if season has started."""
    if not current_season_data:
        return {"status": "season_not_started", "current_wins": None, "pace": None}

    wins = current_season_data.get("wins", 0)
    losses = current_season_data.get("losses", 0)
    games_played = wins + losses

    if games_played < 5:
        return {"status": "too_early", "current_wins": wins, "pace": None}

    win_pct = wins / games_played
    pace_wins = round(win_pct * 162)
    projected = team_proj.get("projected_wins", 81)
    diff = pace_wins - projected

    return {
        "status": "active",
        "current_wins": wins,
        "current_losses": losses,
        "games_played": games_played,
        "current_win_pct": round(win_pct, 3),
        "pace_wins": pace_wins,
        "vs_projection": diff,
        "trend": "ahead" if diff > 3 else ("behind" if diff < -3 else "on_track"),
    }


@router.get("/season/projections")
async def season_projections(request: Request):
    """Full season projections for all 30 teams with CI, pace, and narrative."""
    cache = request.app.state.projection_cache
    standings_cache = request.app.state.standings_cache
    team_model = getattr(request.app.state, "team_model", None)

    if not standings_cache:
        raise HTTPException(status_code=503, detail="Projections not yet computed")

    # Get current season standings for pace calculation
    try:
        current_standings_raw = await request.app.state.api_client.get_standings(PROJECTION_YEAR)
        current_by_team = {t["team_id"]: t for t in current_standings_raw}
    except Exception:
        current_by_team = {}

    result = []
    for entry in standings_cache:
        team_id = entry["team_id"]
        full_proj = cache.get_team(team_id)
        if not full_proj:
            continue

        pace = _current_pace(full_proj, current_by_team.get(team_id))
        narrative = _generate_narrative(full_proj)

        rmse = team_model.avg_rmse if team_model else 8.0
        ci_half = round(1.645 * rmse, 1)

        result.append({
            "team_id": team_id,
            "name": entry["name"],
            "abbreviation": entry["abbreviation"],
            "league": entry["league"],
            "division": entry["division"],
            "projected_wins": full_proj["projected_wins"],
            "projected_losses": full_proj["projected_losses"],
            "win_pct": full_proj["win_pct"],
            "ci_low": max(40, full_proj["projected_wins"] - int(ci_half)),
            "ci_high": min(120, full_proj["projected_wins"] + int(ci_half)),
            "pythagorean_wins": full_proj.get("pythagorean_wins"),
            "roster_war_wins": full_proj.get("roster_war_wins"),
            "regressed_wins": full_proj.get("regressed_wins"),
            "total_war": full_proj.get("total_war"),
            "projected_rs": full_proj.get("projected_rs"),
            "projected_ra": full_proj.get("projected_ra"),
            "pace": pace,
            "narrative": narrative,
        })

    # Sort by division then projected wins
    result.sort(key=lambda t: (t["division"], -t["projected_wins"]))

    return {
        "season": PROJECTION_YEAR,
        "teams": result,
        "model_rmse": round(team_model.avg_rmse, 2) if team_model else None,
        "last_updated": _now_ts(),
    }


@router.get("/season/standings")
async def season_standings_by_division(request: Request):
    """Division standings with projected playoff picture."""
    resp = await season_projections(request)
    teams = resp["teams"]

    grouped: dict[str, list] = {}
    for t in teams:
        div = t["division"]
        if div not in grouped:
            grouped[div] = []
        grouped[div].append(t)

    # Within each division rank by projected wins
    divisions_out = {}
    for div, div_teams in grouped.items():
        sorted_teams = sorted(div_teams, key=lambda t: -t["projected_wins"])
        for rank, t in enumerate(sorted_teams, 1):
            t["division_rank"] = rank
        divisions_out[div] = sorted_teams

    # Wild card picture: top 3 non-division-winners per league
    al_teams = [t for t in teams if "American" in t["league"]]
    nl_teams = [t for t in teams if "National" in t["league"]]

    def _wc_picture(league_teams):
        div_winners = {}
        for t in league_teams:
            div = t["division"]
            if div not in div_winners or t["projected_wins"] > div_winners[div]["projected_wins"]:
                div_winners[div] = t
        winner_ids = {t["team_id"] for t in div_winners.values()}
        non_winners = sorted(
            [t for t in league_teams if t["team_id"] not in winner_ids],
            key=lambda t: -t["projected_wins"]
        )
        return [{"team_id": t["team_id"], "name": t["name"], "projected_wins": t["projected_wins"], "wc_seed": i + 1}
                for i, t in enumerate(non_winners[:3])]

    return {
        "season": PROJECTION_YEAR,
        "divisions": divisions_out,
        "al_wildcard": _wc_picture(al_teams),
        "nl_wildcard": _wc_picture(nl_teams),
        "last_updated": _now_ts(),
    }


def _now_ts() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
