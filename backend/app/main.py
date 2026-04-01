"""MLB Predictor — FastAPI application.

On startup:
1. Load Lahman CSVs
2. Fit OLS team regression model (data-driven weights, walk-forward validated)
3. Build ID mapper (Lahman <-> MLBAM)
4. Initialize MLB API client
5. Compute Marcel projections for all known players
6. Compute team win projections for all 30 teams
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.data.lahman_loader import LahmanData
from app.data.id_mapper import IDMapper
from app.data.mlb_api_client import MLBApiClient
from app.data.cache import ProjectionCache
from app.data.statcast_client import StatcastClient
from app.models.marcel_batting import MarcelBatting
from app.models.marcel_pitching import MarcelPitching
from app.models.team_regression import fit_team_model, predict_wins
from app.models.statcast_adjustments import adjust_batting_projection, adjust_pitching_projection
from app.models.bayesian_updater import blend_projection
from app.data.vegas_lines import get_vegas_line
from app.config import LAHMAN_DIR, CHADWICK_DIR, PROJECTION_YEAR

from app.routers import search, teams, players
from app.routers import matchups, season, edge

# Rate limiter: 60 requests/minute per IP
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


def _run_sanity_checks(app):
    """Post-projection sanity checks — flag obvious errors before serving."""
    cache = app.state.projection_cache
    standings = app.state.standings_cache
    lahman = app.state.lahman

    print("\n--- SANITY CHECKS ---")
    violations = []

    # Check team win totals
    for team in standings:
        w = team["projected_wins"]
        name = team["name"]
        if w < 55:
            violations.append(f"  TEAM: {name} projects {w} wins (< 55)")
        elif w > 105:
            violations.append(f"  TEAM: {name} projects {w} wins (> 105)")

    # Check individual player projections
    for lahman_id, proj in cache.batting.items():
        name = proj.get("name", lahman_id)

        # Power hitter check: >25 HR in any of last 3 years must project >= 10
        hist = lahman.get_batting_history(lahman_id, PROJECTION_YEAR, n_years=3)
        if not hist.empty and "HR" in hist.columns:
            max_hr = int(hist["HR"].max())
            if max_hr >= 25 and proj.get("hr", 0) < 10:
                old_hr = proj["hr"]
                # Floor at 10 HR for known power hitters
                proj["hr"] = max(10, int(max_hr * 0.3))
                proj["hr_rate"] = round(proj["hr"] / max(proj["projected_pa"], 1), 4)
                violations.append(f"  BATTER FIX: {name} had {max_hr} HR max but projected {old_hr} → corrected to {proj['hr']}")
                cache.set_batting(lahman_id, proj)

        # Zero AVG check
        if proj.get("avg", 0) == 0 and proj.get("projected_pa", 0) > 100:
            violations.append(f"  BATTER: {name} has 0.000 AVG with {proj['projected_pa']} PA")

    for lahman_id, proj in cache.pitching.items():
        name = proj.get("name", lahman_id)

        # SP with >150 IP last year must project >100 IP
        hist = lahman.get_pitching_history(lahman_id, PROJECTION_YEAR, n_years=1)
        if not hist.empty and "IPouts" in hist.columns:
            last_ip = hist["IPouts"].sum() / 3
            if last_ip > 150 and proj.get("projected_ip", 0) < 100:
                old_ip = proj["projected_ip"]
                proj["projected_ip"] = round(max(100, last_ip * 0.7), 1)
                violations.append(f"  PITCHER FIX: {name} threw {last_ip:.0f} IP last year but projected {old_ip} → corrected to {proj['projected_ip']}")
                cache.set_pitching(lahman_id, proj)

    if violations:
        print(f"  {len(violations)} sanity violations found:")
        for v in violations:
            print(v)
    else:
        print("  All checks passed.")
    print()


async def _compute_team_projections(app):
    """Compute projections for all 30 teams using the fitted OLS model."""
    api_client = app.state.api_client
    cache = app.state.projection_cache
    batting_model = app.state.batting_model
    pitching_model = app.state.pitching_model
    id_mapper = app.state.id_mapper
    lahman = app.state.lahman
    team_model = app.state.team_model

    teams_list = await api_client.get_all_teams()
    app.state.teams_list = teams_list

    # Get last season standings for regression component
    standings = await api_client.get_standings(PROJECTION_YEAR - 1)
    last_season = {t["team_id"]: t for t in standings}

    # Current season standings (for teams > 30 games in)
    current_standings = await api_client.get_standings(PROJECTION_YEAR)
    current_season = {t["team_id"]: t for t in current_standings}

    standings_output = []

    for team in teams_list:
        team_id = team["id"]
        team_name = team["name"]
        print(f"  Processing {team_name}...")

        # Get roster
        try:
            roster = await api_client.get_roster(team_id)
        except Exception as e:
            print(f"    Failed to get roster for {team_name}: {e}")
            roster = []

        team_batters = []
        team_pitchers = []
        total_war = 0.0

        for player in roster:
            mlbam_id = player["id"]
            lahman_id = id_mapper.mlbam_to_lahman(mlbam_id)
            pos_type = player.get("position_type", "")
            pos = player.get("position", "")

            if pos_type == "Pitcher" or pos in ("P", "SP", "RP"):
                proj = None
                if lahman_id:
                    proj = cache.get_pitching(lahman_id)
                    if not proj:
                        proj = pitching_model.project(lahman_id)
                        if proj:
                            proj["team_id"] = team_id
                            cache.set_pitching(lahman_id, proj)
                if proj:
                    total_war += proj.get("war", 0)
                    team_pitchers.append({
                        "id": mlbam_id,
                        "name": proj.get("name", player["name"]),
                        "position": proj.get("position", pos),
                        "throws": player.get("throws", proj.get("throws", "")),
                        "era": proj.get("era"),
                        "whip": proj.get("whip"),
                        "k_per_9": proj.get("k_per_9"),
                        "hr_per_9": proj.get("hr_per_9"),
                        "ip": proj.get("projected_ip"),
                        "war": proj.get("war", 0),
                    })
                else:
                    team_pitchers.append({
                        "id": mlbam_id,
                        "name": player["name"],
                        "position": pos,
                        "throws": player.get("throws", ""),
                        "era": None, "whip": None, "k_per_9": None, "hr_per_9": None, "ip": None,
                        "war": 0.0,
                    })
            else:
                proj = None
                if lahman_id:
                    proj = cache.get_batting(lahman_id)
                    if not proj:
                        proj = batting_model.project(lahman_id)
                        if proj:
                            proj["team_id"] = team_id
                            cache.set_batting(lahman_id, proj)
                if proj:
                    total_war += proj.get("war", 0)
                    team_batters.append({
                        "id": mlbam_id,
                        "name": proj.get("name", player["name"]),
                        "position": proj.get("position", pos),
                        "bats": player.get("bats", "R"),
                        "avg": proj.get("avg"),
                        "ops": proj.get("ops"),
                        "hr": proj.get("hr"),
                        "war": proj.get("war", 0),
                    })
                else:
                    team_batters.append({
                        "id": mlbam_id,
                        "name": player["name"],
                        "position": pos,
                        "bats": player.get("bats", "R"),
                        "avg": None, "ops": None, "hr": None,
                        "war": 0.0,
                    })

        # RS/RA — require 30+ games for current season extrapolation
        rs, ra = 0, 0
        cs = current_season.get(team_id)
        ls = last_season.get(team_id)

        if cs and cs.get("runs_scored", 0) > 0:
            gp = cs.get("wins", 0) + cs.get("losses", 0)
            if gp >= 30:
                rs = int(cs["runs_scored"] / gp * 162)
                ra = int(cs["runs_allowed"] / gp * 162)

        if rs == 0 and ls:
            rs = ls.get("runs_scored", 0)
            ra = ls.get("runs_allowed", 0)

        if rs == 0:
            team_abbrev = team.get("abbreviation", "")
            lahman_teams = lahman.get_team_stats(PROJECTION_YEAR - 1)
            row = lahman_teams[lahman_teams["teamID"].str.upper() == team_abbrev.upper()] if not lahman_teams.empty else None
            if row is not None and not row.empty:
                rs = int(row.iloc[0].get("R", 700))
                ra = int(row.iloc[0].get("RA", 700))
            else:
                rs, ra = 700, 700

        last_wins = ls.get("wins", 81) if ls else 81
        last_games = ls.get("wins", 81) + ls.get("losses", 81) if ls else 162

        # Compute roster average age (weighted by WAR)
        total_age_war, total_war_for_age = 0.0, 0.0
        for b in team_batters:
            bw = max(b.get("war", 0), 0.1)
            # Look up age from cache
            total_war_for_age += bw
        for p in team_pitchers:
            pw = max(p.get("war", 0), 0.1)
            total_war_for_age += pw

        # Use OLS model for projection (data-driven weights)
        team_proj = predict_wins(
            model=team_model,
            runs_scored=rs,
            runs_allowed=ra,
            last_season_wins=last_wins,
            games_last_season=last_games,
            roster_war=total_war,
        )

        # Blend with Vegas consensus line (strongest public predictor)
        vegas_line = get_vegas_line(team_id)
        model_wins = team_proj["projected_wins"]
        if vegas_line:
            # Weight: 40% Vegas, 60% our model
            # Vegas captures info our model can't see (injuries, depth, market wisdom)
            blended_wins = int(round(model_wins * 0.6 + vegas_line * 0.4))
            team_proj["projected_wins"] = blended_wins
            team_proj["projected_losses"] = 162 - blended_wins
            team_proj["win_pct"] = round(blended_wins / 162, 3)
            team_proj["vegas_line"] = vegas_line
            team_proj["model_wins"] = model_wins
            team_proj["vegas_blend"] = True
        else:
            team_proj["vegas_blend"] = False

        # Bayesian in-season update if enough current-season games
        cs_data = current_season.get(team_id)
        if cs_data:
            cs_w = cs_data.get("wins", 0)
            cs_l = cs_data.get("losses", 0)
            cs_rs = cs_data.get("runs_scored", 0)
            cs_ra = cs_data.get("runs_allowed", 0)
            if cs_w + cs_l >= 10:
                bayesian = blend_projection(
                    preseason_wins=team_proj["projected_wins"],
                    current_wins=cs_w,
                    current_losses=cs_l,
                    current_rs=cs_rs,
                    current_ra=cs_ra,
                )
                team_proj["projected_wins"] = bayesian["projected_wins"]
                team_proj["projected_losses"] = bayesian["projected_losses"]
                team_proj["win_pct"] = bayesian["win_pct"]
                team_proj["bayesian_blend"] = bayesian
            else:
                team_proj["bayesian_blend"] = None
        else:
            team_proj["bayesian_blend"] = None

        team_proj.update({
            "team_id": team_id,
            "name": team_name,
            "abbreviation": team.get("abbreviation", ""),
            "league": team.get("league", ""),
            "division": team.get("division", ""),
            "batters": team_batters,
            "pitchers": team_pitchers,
            "_rs": rs,   # stored for WAR recomputation in step 11
            "_ra": ra,
            "_initial_war": total_war,
        })

        cache.set_team(team_id, team_proj)
        standings_output.append({
            "team_id": team_id,
            "name": team_name,
            "abbreviation": team.get("abbreviation", ""),
            "league": team.get("league", ""),
            "division": team.get("division", ""),
            "projected_wins": team_proj["projected_wins"],
            "projected_losses": team_proj["projected_losses"],
            "win_pct": team_proj["win_pct"],
            "vegas_line": vegas_line,
        })

    app.state.standings_cache = standings_output
    print(f"  Computed projections for {len(standings_output)} teams")


@asynccontextmanager
async def lifespan(app: FastAPI):
    start = datetime.now(timezone.utc)
    print("=" * 60)
    print("MLB Predictor starting up...")
    print("=" * 60)

    # 1. Load Lahman data
    lahman = LahmanData()
    lahman.load()
    app.state.lahman = lahman

    # 2. Fit OLS regression model on historical team data
    print("Fitting OLS team regression model...")
    team_model = fit_team_model(lahman.teams)
    app.state.team_model = team_model
    if team_model.is_fitted():
        ols = team_model.ols
        print(f"  R² = {ols.r_squared:.3f}  |  Walk-forward RMSE = {team_model.avg_rmse:.1f} wins")
        for name, coef, pval in zip(ols.feature_names, ols.coef, ols.pvalues):
            sig = "✓" if pval < 0.05 else "✗ (dropped)"
            print(f"    {name:<25} coef={coef:+.4f}  p={pval:.4f}  {sig}")
    else:
        print("  WARNING: Could not fit model — using manual weights")

    # 3. Build ID mapper (uses Lahman People.csv mlbID column; Chadwick is optional supplement)
    chadwick_path = CHADWICK_DIR / "people.csv"
    id_mapper = IDMapper(chadwick_path, lahman.people)
    app.state.id_mapper = id_mapper

    # 4. Initialize API client
    api_client = MLBApiClient()
    app.state.api_client = api_client

    # 5. Initialize projection models
    league_avg = lahman.get_league_averages(PROJECTION_YEAR - 1)
    app.state.league_avg = league_avg

    batting_model = MarcelBatting(lahman)
    pitching_model = MarcelPitching(lahman)
    app.state.batting_model = batting_model
    app.state.pitching_model = pitching_model

    # 6. Initialize cache
    cache = ProjectionCache()
    app.state.projection_cache = cache
    app.state.standings_cache = []
    app.state.teams_list = []

    # 7. Compute team projections
    print("Computing team projections...")
    try:
        await _compute_team_projections(app)
    except Exception as e:
        print(f"WARNING: Team projection failed: {e}")
        import traceback
        traceback.print_exc()

    # 8. Sanity check all projections
    _run_sanity_checks(app)

    # 9. Fetch Statcast data and apply adjustments to cached projections
    print("Fetching Statcast data...")
    statcast_client = StatcastClient()
    app.state.statcast_client = statcast_client
    try:
        batter_sc = await statcast_client.fetch_batter_statcast(PROJECTION_YEAR - 1)
        pitcher_sc = await statcast_client.fetch_pitcher_statcast(PROJECTION_YEAR - 1)
        app.state.batter_statcast = batter_sc
        app.state.pitcher_statcast = pitcher_sc
        print(f"  Loaded {len(batter_sc)} batter + {len(pitcher_sc)} pitcher Statcast records")

        # Apply Statcast adjustments to all cached projections
        adjusted_b, adjusted_p = 0, 0
        id_mapper_ref = app.state.id_mapper
        for lahman_id, proj in list(cache.batting.items()):
            mlbam_id = id_mapper_ref.lahman_to_mlbam(lahman_id)
            sc_data = batter_sc.get(mlbam_id) if mlbam_id else None
            team_id = proj.get("team_id")
            adjusted = adjust_batting_projection(proj, sc_data, team_id=team_id)
            cache.set_batting(lahman_id, adjusted)
            if adjusted.get("statcast_adjusted"):
                adjusted_b += 1

        for lahman_id, proj in list(cache.pitching.items()):
            mlbam_id = id_mapper_ref.lahman_to_mlbam(lahman_id)
            sc_data = pitcher_sc.get(mlbam_id) if mlbam_id else None
            team_id = proj.get("team_id")
            adjusted = adjust_pitching_projection(proj, sc_data, team_id=team_id)
            cache.set_pitching(lahman_id, adjusted)
            if adjusted.get("statcast_adjusted"):
                adjusted_p += 1

        print(f"  Applied Statcast adjustments: {adjusted_b} batters, {adjusted_p} pitchers")
    except Exception as e:
        print(f"  Statcast loading failed (graceful degradation): {e}")
        app.state.batter_statcast = {}
        app.state.pitcher_statcast = {}

    # 10. League-total calibration — scale HR and AVG so league totals match reality
    print("Applying league calibration scalars...")
    try:
        # Actual 2025 MLB totals (30 teams): ~5,694 HR, league AVG ~.248
        ACTUAL_LEAGUE_HR = 5694
        ACTUAL_LEAGUE_AVG = 0.248

        total_proj_hr = 0
        total_proj_hits = 0
        total_proj_ab = 0
        batter_count = 0

        for lahman_id, proj in cache.batting.items():
            total_proj_hr += proj.get("hr", 0)
            pa = proj.get("projected_pa", 0)
            avg = proj.get("avg", 0)
            ab = int(pa * 0.89)
            total_proj_hits += int(avg * ab)
            total_proj_ab += ab
            batter_count += 1

        proj_league_avg = total_proj_hits / total_proj_ab if total_proj_ab > 0 else 0.248

        hr_scalar = ACTUAL_LEAGUE_HR / total_proj_hr if total_proj_hr > 0 else 1.0
        avg_scalar = ACTUAL_LEAGUE_AVG / proj_league_avg if proj_league_avg > 0 else 1.0

        # Cap scalars to prevent wild corrections
        hr_scalar = max(0.85, min(hr_scalar, 1.25))
        avg_scalar = max(0.95, min(avg_scalar, 1.08))

        print(f"  Projected league HR: {total_proj_hr}, Actual: {ACTUAL_LEAGUE_HR}, Scalar: {hr_scalar:.3f}")
        print(f"  Projected league AVG: {proj_league_avg:.3f}, Actual: {ACTUAL_LEAGUE_AVG:.3f}, Scalar: {avg_scalar:.3f}")

        if abs(hr_scalar - 1.0) > 0.02 or abs(avg_scalar - 1.0) > 0.005:
            for lahman_id, proj in list(cache.batting.items()):
                proj["hr"] = max(0, int(round(proj["hr"] * hr_scalar)))
                proj["hr_rate"] = round(proj["hr"] / max(proj["projected_pa"], 1), 4)
                proj["avg"] = round(min(proj["avg"] * avg_scalar, 0.400), 3)
                proj["ops"] = round(proj["obp"] + proj["slg"], 3)
                cache.set_batting(lahman_id, proj)
            print(f"  Applied calibration to {batter_count} batters")

            # Update team roster caches with calibrated HR/AVG
            for team_id_key, team_proj in list(cache.teams.items()):
                for batter in team_proj.get("batters", []):
                    mlbam_id = batter.get("id")
                    lahman_id = id_mapper.mlbam_to_lahman(mlbam_id) if mlbam_id else None
                    if lahman_id:
                        updated = cache.get_batting(lahman_id)
                        if updated:
                            batter["hr"] = updated.get("hr")
                            batter["avg"] = updated.get("avg")
                            batter["ops"] = updated.get("ops")
                cache.set_team(team_id_key, team_proj)
        else:
            print("  Scalars close to 1.0 — no calibration needed")
    except Exception as e:
        print(f"  Calibration failed (non-fatal): {e}")
        import traceback
        traceback.print_exc()

    # 11. Recompute team wins using post-adjustment WAR, refresh standings + matchup win_pct
    print("Recomputing team projections with adjusted WAR...")
    try:
        # Get standings data needed for recomputation
        standings_data = await api_client.get_standings(PROJECTION_YEAR - 1)
        last_season_map = {t["team_id"]: t for t in standings_data}
        current_standings_data = await api_client.get_standings(PROJECTION_YEAR)
        current_season_map = {t["team_id"]: t for t in current_standings_data}

        new_standings = []
        for team_id_key, team_proj in list(cache.teams.items()):
            # Refresh individual player stats from adjusted caches
            refreshed_war = 0.0
            for batter in team_proj.get("batters", []):
                mlbam_id = batter.get("id")
                l_id = id_mapper.mlbam_to_lahman(mlbam_id) if mlbam_id else None
                if l_id:
                    updated = cache.get_batting(l_id)
                    if updated:
                        batter["hr"] = updated.get("hr")
                        batter["avg"] = updated.get("avg")
                        batter["ops"] = updated.get("ops")
                        batter["war"] = updated.get("war", 0)
                refreshed_war += batter.get("war", 0)
            for pitcher in team_proj.get("pitchers", []):
                mlbam_id = pitcher.get("id")
                l_id = id_mapper.mlbam_to_lahman(mlbam_id) if mlbam_id else None
                if l_id:
                    updated = cache.get_pitching(l_id)
                    if updated:
                        pitcher["era"] = updated.get("era")
                        pitcher["whip"] = updated.get("whip")
                        pitcher["k_per_9"] = updated.get("k_per_9")
                        pitcher["war"] = updated.get("war", 0)
                refreshed_war += pitcher.get("war", 0)

            # Recompute team wins with updated WAR
            ls = last_season_map.get(team_id_key)
            rs = team_proj.get("_rs", 0)
            ra = team_proj.get("_ra", 0)

            # Fall back to stored RS/RA or last season
            if rs == 0 and ls:
                rs = ls.get("runs_scored", 700)
                ra = ls.get("runs_allowed", 700)
            if rs == 0:
                rs, ra = 700, 700

            last_wins = ls.get("wins", 81) if ls else 81
            last_games = (ls.get("wins", 81) + ls.get("losses", 81)) if ls else 162

            new_team_proj = predict_wins(
                model=team_model,
                runs_scored=rs,
                runs_allowed=ra,
                last_season_wins=last_wins,
                games_last_season=last_games,
                roster_war=refreshed_war,
            )

            # Re-blend with Vegas
            vegas_line = get_vegas_line(team_id_key)
            model_wins = new_team_proj["projected_wins"]
            if vegas_line:
                blended_wins = int(round(model_wins * 0.6 + vegas_line * 0.4))
                new_team_proj["projected_wins"] = blended_wins
                new_team_proj["projected_losses"] = 162 - blended_wins
                new_team_proj["win_pct"] = round(blended_wins / 162, 3)
                new_team_proj["vegas_line"] = vegas_line
                new_team_proj["model_wins"] = model_wins
            else:
                new_team_proj["vegas_line"] = None

            # Re-apply Bayesian in-season update
            cs_data = current_season_map.get(team_id_key)
            if cs_data:
                cs_w = cs_data.get("wins", 0)
                cs_l = cs_data.get("losses", 0)
                cs_rs = cs_data.get("runs_scored", 0)
                cs_ra = cs_data.get("runs_allowed", 0)
                if cs_w + cs_l >= 10:
                    bayesian = blend_projection(
                        preseason_wins=new_team_proj["projected_wins"],
                        current_wins=cs_w,
                        current_losses=cs_l,
                        current_rs=cs_rs,
                        current_ra=cs_ra,
                    )
                    new_team_proj["projected_wins"] = bayesian["projected_wins"]
                    new_team_proj["projected_losses"] = bayesian["projected_losses"]
                    new_team_proj["win_pct"] = bayesian["win_pct"]

            # Update team cache with new win totals AND refreshed roster
            team_proj["projected_wins"] = new_team_proj["projected_wins"]
            team_proj["projected_losses"] = new_team_proj["projected_losses"]
            team_proj["win_pct"] = new_team_proj["win_pct"]
            team_proj["model_wins"] = new_team_proj.get("model_wins", new_team_proj["projected_wins"])
            cache.set_team(team_id_key, team_proj)

            new_standings.append({
                "team_id": team_id_key,
                "name": team_proj.get("name", ""),
                "abbreviation": team_proj.get("abbreviation", ""),
                "league": team_proj.get("league", ""),
                "division": team_proj.get("division", ""),
                "projected_wins": new_team_proj["projected_wins"],
                "projected_losses": new_team_proj["projected_losses"],
                "win_pct": new_team_proj["win_pct"],
                "vegas_line": vegas_line,
            })

        # Replace standings cache with recomputed values
        app.state.standings_cache = new_standings
        print(f"  Recomputed wins for {len(new_standings)} teams using adjusted WAR")
    except Exception as e:
        print(f"  Win recomputation failed (non-fatal, keeping original): {e}")
        import traceback
        traceback.print_exc()

    elapsed = (datetime.now(timezone.utc) - start).seconds
    app.state.startup_time = datetime.now(timezone.utc).isoformat()
    print("=" * 60)
    print(f"MLB Predictor ready!  (startup: {elapsed}s)")
    print("=" * 60)

    yield

    await api_client.close()
    await statcast_client.close()


app = FastAPI(title="MLB Predictor", lifespan=lifespan)

# Rate limiting
app.state.limiter = limiter


def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(search.router)
app.include_router(teams.router)
app.include_router(players.router)
app.include_router(matchups.router)
app.include_router(season.router)
app.include_router(edge.router)  # unlisted — not linked from frontend


@app.get("/api/health")
@limiter.limit("30/minute")
async def health(request: Request):
    return {
        "status": "ok",
        "startup_time": getattr(request.app.state, "startup_time", None),
        "teams_loaded": len(getattr(request.app.state, "standings_cache", [])),
        "model_fitted": getattr(request.app.state, "team_model", None) is not None
        and request.app.state.team_model.is_fitted(),
    }
