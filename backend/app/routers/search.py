from fastapi import APIRouter, Request, Query

router = APIRouter()


@router.get("/api/search")
async def search(request: Request, q: str = Query(..., min_length=2)):
    """Search players and teams by name."""
    api_client = request.app.state.api_client
    teams_list = request.app.state.teams_list

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
