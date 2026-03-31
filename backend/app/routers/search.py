import re
from fastapi import APIRouter, Request, Query

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.get("/api/search")
@limiter.limit("30/minute")
async def search(request: Request, q: str = Query(..., min_length=2, max_length=100)):
    """Search players and teams by name."""
    api_client = request.app.state.api_client
    teams_list = request.app.state.teams_list

    # Sanitize: only allow letters, numbers, spaces, hyphens, periods, apostrophes
    q = re.sub(r"[^\w\s\-.'']", "", q).strip()
    if len(q) < 2:
        return {"teams": [], "players": []}
    query_lower = q.lower()

    # Search teams
    matching_teams = [
        {"id": t["id"], "name": t["name"], "abbreviation": t["abbreviation"]}
        for t in teams_list
        if query_lower in t["name"].lower() or query_lower in t["abbreviation"].lower()
    ]

    # Search players via MLB API
    matching_players = await api_client.search_people(q)

    return {
        "teams": matching_teams[:10],
        "players": matching_players[:15],
    }
