"""Client for the free MLB Stats API (statsapi.mlb.com)."""

import httpx
import json
import hashlib
import time
from pathlib import Path
from app.config import MLB_API_BASE, CACHE_DIR


class MLBApiClient:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    async def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)

    async def _get(self, endpoint: str, params: dict = None, cache_ttl: int = 3600) -> dict:
        """GET with disk caching."""
        await self._ensure_client()
        url = f"{MLB_API_BASE}{endpoint}"
        cache_key = hashlib.md5(f"{url}{params}".encode()).hexdigest()
        cache_file = CACHE_DIR / f"{cache_key}.json"

        # Check cache
        if cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < cache_ttl:
                return json.loads(cache_file.read_text())

        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        # Write cache
        cache_file.write_text(json.dumps(data))
        return data

    async def get_all_teams(self) -> list[dict]:
        """Get all 30 MLB teams."""
        data = await self._get("/teams", {"sportId": 1}, cache_ttl=86400)
        teams = []
        for t in data.get("teams", []):
            teams.append({
                "id": t["id"],
                "name": t["name"],
                "abbreviation": t.get("abbreviation", ""),
                "league": t.get("league", {}).get("name", ""),
                "division": t.get("division", {}).get("name", ""),
                "venue": t.get("venue", {}).get("name", ""),
            })
        return teams

    async def get_roster(self, team_id: int) -> list[dict]:
        """Get active roster for a team."""
        data = await self._get(f"/teams/{team_id}/roster", {"rosterType": "active"}, cache_ttl=21600)
        roster = []
        for entry in data.get("roster", []):
            person = entry.get("person", {})
            pos = entry.get("position", {})
            roster.append({
                "id": person.get("id"),
                "name": person.get("fullName", ""),
                "jersey": entry.get("jerseyNumber", ""),
                "position": pos.get("abbreviation", ""),
                "position_type": pos.get("type", ""),
            })
        return roster

    async def get_player(self, player_id: int) -> dict | None:
        """Get player bio and career stats."""
        try:
            data = await self._get(
                f"/people/{player_id}",
                {"hydrate": "stats(group=[hitting,pitching],type=[yearByYear])"},
                cache_ttl=3600,
            )
        except httpx.HTTPStatusError:
            return None

        people = data.get("people", [])
        if not people:
            return None

        p = people[0]
        result = {
            "id": p["id"],
            "name": p.get("fullName", ""),
            "first_name": p.get("firstName", ""),
            "last_name": p.get("lastName", ""),
            "birth_date": p.get("birthDate", ""),
            "age": p.get("currentAge"),
            "position": p.get("primaryPosition", {}).get("abbreviation", ""),
            "position_type": p.get("primaryPosition", {}).get("type", ""),
            "bats": p.get("batSide", {}).get("code", ""),
            "throws": p.get("pitchHand", {}).get("code", ""),
            "team": p.get("currentTeam", {}).get("name", ""),
            "team_id": p.get("currentTeam", {}).get("id"),
            "stats": [],
        }

        # Parse year-by-year stats
        for stat_group in p.get("stats", []):
            group_name = stat_group.get("group", {}).get("displayName", "")
            for split in stat_group.get("splits", []):
                season = split.get("season")
                stats = split.get("stat", {})
                if season:
                    result["stats"].append({
                        "year": int(season),
                        "group": group_name,
                        "team": split.get("team", {}).get("name", ""),
                        **stats,
                    })

        return result

    async def get_standings(self, season: int = 2026) -> list[dict]:
        """Get current standings."""
        data = await self._get("/standings", {"leagueId": "103,104", "season": season}, cache_ttl=3600)
        teams = []
        for record in data.get("records", []):
            div = record.get("division", {}).get("name", "")
            league = record.get("league", {}).get("name", "")
            for tr in record.get("teamRecords", []):
                teams.append({
                    "team_id": tr.get("team", {}).get("id"),
                    "name": tr.get("team", {}).get("name", ""),
                    "wins": tr.get("wins", 0),
                    "losses": tr.get("losses", 0),
                    "runs_scored": tr.get("runsScored", 0),
                    "runs_allowed": tr.get("runsAllowed", 0),
                    "division": div,
                    "league": league,
                })
        return teams

    async def search_people(self, query: str) -> list[dict]:
        """Search for players by name."""
        try:
            data = await self._get(
                "/people/search",
                {"names": query, "sportId": 1, "active": "true"},
                cache_ttl=3600,
            )
        except Exception:
            return []

        results = []
        for row in data.get("people", [])[:15]:
            results.append({
                "id": row.get("id"),
                "name": row.get("fullName", ""),
                "position": row.get("primaryPosition", {}).get("abbreviation", ""),
                "team": row.get("currentTeam", {}).get("name", ""),
            })
        return results

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
