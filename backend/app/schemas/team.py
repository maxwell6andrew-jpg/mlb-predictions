from pydantic import BaseModel


class StandingsEntry(BaseModel):
    team_id: int
    name: str
    abbreviation: str = ""
    league: str = ""
    division: str = ""
    projected_wins: int = 81
    projected_losses: int = 81
    win_pct: float = 0.500


class TeamResponse(BaseModel):
    team_id: int
    name: str
    abbreviation: str = ""
    league: str = ""
    division: str = ""
    projected_wins: int = 81
    projected_losses: int = 81
    win_pct: float = 0.500
    pythagorean_wins: int = 81
    roster_war_wins: int = 81
    regressed_wins: int = 81
    projected_rs: int = 0
    projected_ra: int = 0
    total_war: float = 0.0
    batters: list[dict] = []
    pitchers: list[dict] = []


class StandingsResponse(BaseModel):
    standings: list[StandingsEntry]


class SearchResult(BaseModel):
    teams: list[dict] = []
    players: list[dict] = []
