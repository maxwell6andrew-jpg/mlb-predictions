from fastapi import APIRouter, Request, HTTPException

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.get("/api/standings")
@limiter.limit("30/minute")
async def get_standings(request: Request):
    """Get projected standings for all 30 teams."""
    standings_cache = request.app.state.standings_cache
    if not standings_cache:
        raise HTTPException(503, "Projections not yet computed")
    return {"standings": standings_cache}


@router.get("/api/team/{team_id}")
@limiter.limit("30/minute")
async def get_team(request: Request, team_id: int):
    """Get detailed team projection."""
    if team_id < 100 or team_id > 200:
        raise HTTPException(400, "Invalid team ID")
    team_cache = request.app.state.projection_cache.teams

    if team_id not in team_cache:
        raise HTTPException(404, f"Team {team_id} not found")

    return team_cache[team_id]
