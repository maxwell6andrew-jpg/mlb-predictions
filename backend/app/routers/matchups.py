"""
/api/matchups/today  — today's games with win probability predictions
/api/model/coefficients — OLS coefficient table with standard errors
/api/model/validation — walk-forward validation RMSE by year
"""

from fastapi import APIRouter, Request, HTTPException, Query
from datetime import date, datetime, timezone, timedelta
import httpx

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models.matchup import predict_game
from app.data.park_factors import get_park_factor

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api")

MLB_API = "https://statsapi.mlb.com/api/v1"


async def _fetch_today_schedule(api_client, game_date: str) -> list[dict]:
    try:
        data = await api_client._get(
            "/schedule",
            params={"sportId": 1, "date": game_date, "hydrate": "probablePitcher,team,linescore"},
            cache_ttl=300,  # 5-min cache for schedule
        )
        dates = data.get("dates", [])
        return dates[0]["games"] if dates else []
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MLB schedule API failed: {e}")


def _pitcher_from_cache(mlbam_id: int, cache, id_mapper) -> dict | None:
    """Look up a pitcher's Marcel projection from cache."""
    lahman_id = id_mapper.mlbam_to_lahman(mlbam_id)
    if not lahman_id:
        return None
    proj = cache.get_pitching(lahman_id)
    return proj


@router.get("/matchups/today")
@limiter.limit("20/minute")
async def matchups_today(request: Request, date_str: str = Query(None, alias="date")):
    """Return today's game predictions with win probabilities."""
    if date_str:
        today = date_str
    else:
        # Default to US Pacific time
        pacific = timezone(timedelta(hours=-7))
        today = datetime.now(pacific).strftime("%Y-%m-%d")
    api_client = request.app.state.api_client
    cache = request.app.state.projection_cache
    id_mapper = request.app.state.id_mapper
    league_avg = request.app.state.league_avg

    lg_era = league_avg.get("era", 4.00)
    lg_fip = lg_era  # FIP calibrated to match league ERA

    # Fetch schedule
    games_raw = await _fetch_today_schedule(api_client, today)

    if not games_raw:
        return {
            "date": today,
            "games": [],
            "fetch_status": "success",
            "message": "No games scheduled today",
        }

    predictions = []

    for g in games_raw:
        away_info = g["teams"]["away"]
        home_info = g["teams"]["home"]
        away_id = away_info["team"]["id"]
        home_id = home_info["team"]["id"]
        away_name = away_info["team"]["name"]
        home_name = home_info["team"]["name"]
        status = g["status"]["detailedState"]

        # Get probable pitchers
        away_sp_meta = away_info.get("probablePitcher", {})
        home_sp_meta = home_info.get("probablePitcher", {})
        away_sp_id = away_sp_meta.get("id")
        home_sp_id = home_sp_meta.get("id")
        away_sp_name = away_sp_meta.get("fullName", "TBD")
        home_sp_name = home_sp_meta.get("fullName", "TBD")

        away_sp_proj = _pitcher_from_cache(away_sp_id, cache, id_mapper) if away_sp_id else None
        home_sp_proj = _pitcher_from_cache(home_sp_id, cache, id_mapper) if home_sp_id else None

        # Add FIP to pitcher projections if not already present
        if away_sp_proj and "fip" not in away_sp_proj:
            away_sp_proj = _add_fip(away_sp_proj, lg_fip)
        if home_sp_proj and "fip" not in home_sp_proj:
            home_sp_proj = _add_fip(home_sp_proj, lg_fip)

        # Get team projections
        away_proj = cache.get_team(away_id)
        home_proj = cache.get_team(home_id)

        # Park factor for home venue
        park_factor = get_park_factor(home_id, "runs")

        # Pitcher handedness (from MLB API metadata)
        home_sp_hand = ""
        away_sp_hand = ""
        if home_sp_proj:
            home_sp_hand = home_sp_proj.get("throws", home_sp_meta.get("pitchHand", {}).get("code", ""))
        elif home_sp_meta:
            home_sp_hand = home_sp_meta.get("pitchHand", {}).get("code", "")
        if away_sp_proj:
            away_sp_hand = away_sp_proj.get("throws", away_sp_meta.get("pitchHand", {}).get("code", ""))
        elif away_sp_meta:
            away_sp_hand = away_sp_meta.get("pitchHand", {}).get("code", "")

        pred = predict_game(
            away_team_id=away_id,
            home_team_id=home_id,
            away_team_name=away_name,
            home_team_name=home_name,
            away_proj=away_proj,
            home_proj=home_proj,
            away_sp=away_sp_proj,
            home_sp=home_sp_proj,
            away_sp_name=away_sp_name,
            home_sp_name=home_sp_name,
            lg_era=lg_era,
            lg_fip=lg_fip,
            park_factor=park_factor,
            home_sp_hand=home_sp_hand,
            away_sp_hand=away_sp_hand,
        )
        pred["game_status"] = status
        pred["game_time"] = g.get("gameDate", "")
        predictions.append(pred)

    # Sort by largest win probability differential (most decisive matchups first)
    predictions.sort(key=lambda p: abs(p["home_win_prob"] - 0.5), reverse=True)

    return {
        "date": today,
        "games": predictions,
        "fetch_status": "success",
        "total_games": len(predictions),
        "last_updated": _now_ts(),
    }


@router.get("/model/coefficients")
@limiter.limit("20/minute")
async def model_coefficients(request: Request):
    """Return OLS coefficient table with standard errors and p-values."""
    team_model = getattr(request.app.state, "team_model", None)
    if team_model is None or not team_model.is_fitted():
        raise HTTPException(status_code=503, detail="Team regression model not yet fitted")

    full = getattr(team_model, "_ols_full", None)
    final = team_model.ols

    return {
        "model": final.to_dict(),
        "diagnostic_model": full.to_dict() if full else None,
        "walk_forward": [
            {
                "year": wf.year,
                "rmse": round(wf.rmse, 2),
                "n_teams": len(wf.predictions),
            }
            for wf in team_model.walk_forward
        ],
        "avg_rmse": round(team_model.avg_rmse, 2),
        "roster_war_coefficient": round(team_model.roster_war_coef, 3),
        "literature_notes": {
            "pythagorean_exponent": 1.83,
            "year_over_year_persistence": 0.535,
            "runs_per_win": 10.0,
            "source": "Tango et al. 'The Book' (2006); Davenport & Woolner (1999); Miller (2007)",
            "why_pyth_over_actual": (
                "Pythagorean win% is preferred over actual W-L as a predictor because "
                "actual wins contain luck variance (one-run game clustering, bullpen sequencing). "
                "Tango et al. show pyth_pct has lower RMSE for second-half prediction than actual_pct. "
                "pyth_pct and actual_pct are collinear (r≈0.85) so OLS cannot distinguish them — "
                "we enforce pyth_pct per literature."
            ),
        },
        "interpretation": (
            "Prediction model uses pyth_pct_lag only (literature-preferred). "
            "Pythagorean win% from prior year × 86.8 + 37.4 intercept ≈ 0.535 year-over-year persistence, "
            "regressing 46.5% toward 81 wins. Consistent with Tango (The Book): r≈0.53 for team wins YoY."
        ),
    }


@router.get("/model/validation")
@limiter.limit("20/minute")
async def model_validation(request: Request):
    """Return walk-forward validation detail (actual vs predicted by team/year)."""
    team_model = getattr(request.app.state, "team_model", None)
    if team_model is None or not team_model.is_fitted():
        raise HTTPException(status_code=503, detail="Model not fitted")

    return {
        "walk_forward_years": [
            {
                "year": wf.year,
                "rmse": round(wf.rmse, 2),
                "predictions": wf.predictions,
            }
            for wf in team_model.walk_forward
        ],
        "avg_rmse": round(team_model.avg_rmse, 2),
    }


def _add_fip(proj: dict, lg_fip: float) -> dict:
    """Compute FIP from projected components and add to projection dict."""
    ip = proj.get("projected_ip", 1)
    k9 = proj.get("k_per_9", 8.0)
    bb9 = proj.get("bb_per_9", 3.0)
    hr9 = proj.get("hr_per_9", 1.2)
    k = k9 / 9 * ip
    bb = bb9 / 9 * ip
    hr = hr9 / 9 * ip
    fip_val = (13 * hr + 3 * bb - 2 * k) / max(ip, 1) + lg_fip
    result = dict(proj)
    result["fip"] = round(fip_val, 2)
    return result


def _now_ts() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
