"""Simple in-memory cache for projections."""


class ProjectionCache:
    def __init__(self):
        self.batting: dict[str, dict] = {}   # keyed by lahman_id
        self.pitching: dict[str, dict] = {}  # keyed by lahman_id
        self.teams: dict[int, dict] = {}     # keyed by mlbam team_id

    def get_batting(self, lahman_id: str) -> dict | None:
        return self.batting.get(lahman_id)

    def set_batting(self, lahman_id: str, projection: dict):
        self.batting[lahman_id] = projection

    def get_pitching(self, lahman_id: str) -> dict | None:
        return self.pitching.get(lahman_id)

    def set_pitching(self, lahman_id: str, projection: dict):
        self.pitching[lahman_id] = projection

    def get_team(self, team_id: int) -> dict | None:
        return self.teams.get(team_id)

    def set_team(self, team_id: int, projection: dict):
        self.teams[team_id] = projection
