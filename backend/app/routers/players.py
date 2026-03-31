from fastapi import APIRouter, Request, HTTPException
import pandas as pd

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


def _build_historical(lahman, lahman_id: str, is_pitcher: bool, n_years: int = 5) -> list[dict]:
    """Build historical stat line for charts."""
    if is_pitcher:
        hist = lahman.get_pitching_history(lahman_id, 2026, n_years=n_years)
        result = []
        for _, row in hist.iterrows():
            ipouts = row.get("IPouts", 0)
            ip = ipouts / 3
            if ip == 0:
                continue
            result.append({
                "year": int(row["yearID"]),
                "era": round(row.get("ER", 0) / ip * 9, 2) if ip else None,
                "whip": round((row.get("H", 0) + row.get("BB", 0)) / ip, 2) if ip else None,
                "k_per_9": round(row.get("SO", 0) / ip * 9, 1) if ip else None,
                "bb_per_9": round(row.get("BB", 0) / ip * 9, 1) if ip else None,
            })
        return sorted(result, key=lambda x: x["year"])
    else:
        hist = lahman.get_batting_history(lahman_id, 2026, n_years=n_years)
        result = []
        for _, row in hist.iterrows():
            ab = row.get("AB", 0)
            if ab == 0:
                continue
            h = row.get("H", 0)
            bb = row.get("BB", 0)
            hbp = row.get("HBP", 0)
            sf = row.get("SF", 0)
            doubles = row.get("2B", 0)
            triples = row.get("3B", 0)
            hr = row.get("HR", 0)
            pa = ab + bb + hbp + sf

            avg = h / ab if ab else 0
            obp = (h + bb + hbp) / pa if pa else 0
            tb = h + doubles + 2 * triples + 3 * hr
            slg = tb / ab if ab else 0

            result.append({
                "year": int(row["yearID"]),
                "avg": round(avg, 3),
                "obp": round(obp, 3),
                "slg": round(slg, 3),
                "ops": round(obp + slg, 3),
                "hr": int(hr),
            })
        return sorted(result, key=lambda x: x["year"])


@router.get("/api/player/{player_id}")
@limiter.limit("30/minute")
async def get_player(request: Request, player_id: int):
    """Get player projection and historical data."""
    id_mapper = request.app.state.id_mapper
    lahman = request.app.state.lahman
    api_client = request.app.state.api_client
    batting_model = request.app.state.batting_model
    pitching_model = request.app.state.pitching_model
    cache = request.app.state.projection_cache
    league_avg = request.app.state.league_avg

    # Map MLBAM ID to Lahman ID
    lahman_id = id_mapper.mlbam_to_lahman(player_id)

    # Get player info from API
    api_player = await api_client.get_player(player_id)
    if not api_player:
        raise HTTPException(404, f"Player {player_id} not found")

    is_pitcher = api_player.get("position_type") == "Pitcher"

    # Try cached projection first
    projection = None
    if lahman_id:
        if is_pitcher:
            projection = cache.get_pitching(lahman_id)
            if not projection:
                projection = pitching_model.project(lahman_id)
                if projection:
                    cache.set_pitching(lahman_id, projection)
        else:
            projection = cache.get_batting(lahman_id)
            if not projection:
                projection = batting_model.project(lahman_id)
                if projection:
                    cache.set_batting(lahman_id, projection)

    # Fallback: replacement-level projection
    if not projection:
        if is_pitcher:
            projection = {
                "type": "pitching",
                "projected_ip": 0,
                "era": league_avg.get("era", 4.50),
                "whip": league_avg.get("whip", 1.30),
                "k_per_9": league_avg.get("k_per_9", 8.5),
                "bb_per_9": league_avg.get("bb_per_9", 3.2),
                "hr_per_9": league_avg.get("hr_per_9", 1.2),
                "w": 0, "l": 0, "sv": 0, "so": 0, "bb": 0,
                "war": 0.0, "confidence": 0.1,
                "name": api_player["name"],
                "age": api_player.get("age", 0),
                "position": api_player.get("position", "P"),
            }
        else:
            projection = {
                "type": "batting",
                "projected_pa": 0,
                "avg": league_avg.get("avg", 0.250),
                "obp": league_avg.get("obp", 0.320),
                "slg": league_avg.get("slg", 0.400),
                "ops": league_avg.get("avg", 0.250) + league_avg.get("slg", 0.400),
                "hr": 0, "rbi": 0, "r": 0, "sb": 0, "bb": 0, "so": 0,
                "war": 0.0, "hr_rate": 0, "bb_rate": 0, "k_rate": 0,
                "confidence": 0.1,
                "name": api_player["name"],
                "age": api_player.get("age", 0),
                "position": api_player.get("position", ""),
            }

    # Build historical data
    historical = []
    if lahman_id:
        historical = _build_historical(lahman, lahman_id, is_pitcher, n_years=5)

    player_bio = {
        "id": player_id,
        "name": api_player["name"],
        "team": api_player.get("team", ""),
        "position": api_player.get("position", ""),
        "age": api_player.get("age"),
        "bats": api_player.get("bats", ""),
        "throws": api_player.get("throws", ""),
    }

    return {
        "player": player_bio,
        "projection": projection,
        "historical": historical,
        "league_averages": league_avg,
    }
