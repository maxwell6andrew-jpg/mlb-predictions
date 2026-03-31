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
from app.models.marcel_batting import MarcelBatting
from app.models.marcel_pitching import MarcelPitching
from app.models.team_regression import fit_team_model, predict_wins
from app.config import LAHMAN_DIR, CHADWICK_DIR, PROJECTION_YEAR

from app.routers import search, teams, players
from app.routers import matchups, season

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
                            cache.set_pitching(lahman_id, proj)
                if proj:
                    total_war += proj.get("war", 0)
                    team_pitchers.append({
                        "id": mlbam_id,
                        "name": proj.get("name", player["name"]),
                        "position": proj.get("position", pos),
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
                            cache.set_batting(lahman_id, proj)
                if proj:
                    total_war += proj.get("war", 0)
                    team_batters.append({
                        "id": mlbam_id,
                        "name": proj.get("name", player["name"]),
                        "position": proj.get("position", pos),
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

        # Use OLS model for projection (data-driven weights)
        team_proj = predict_wins(
            model=team_model,
            runs_scored=rs,
            runs_allowed=ra,
            last_season_wins=last_wins,
            games_last_season=last_games,
            roster_war=total_war,
        )
        team_proj.update({
            "team_id": team_id,
            "name": team_name,
            "abbreviation": team.get("abbreviation", ""),
            "league": team.get("league", ""),
            "division": team.get("division", ""),
            "batters": team_batters,
            "pitchers": team_pitchers,
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

    elapsed = (datetime.now(timezone.utc) - start).seconds
    app.state.startup_time = datetime.now(timezone.utc).isoformat()
    print("=" * 60)
    print(f"MLB Predictor ready!  (startup: {elapsed}s)")
    print("=" * 60)

    yield

    await api_client.close()


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
