"""
Live odds from The Odds API (free tier: 500 requests/month).
Fetches real moneylines from DraftKings, FanDuel, etc.

API key must be set as ODDS_API_KEY environment variable — never hardcoded.
"""

import os
import httpx
from datetime import datetime, timezone

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
BASE_URL = "https://api.the-odds-api.com/v4"
SPORT = "baseball_mlb"

# Cache to avoid burning requests
_odds_cache: dict = {}
_cache_time: datetime | None = None
CACHE_TTL_SECONDS = 900  # 15 minutes — saves API calls


async def fetch_live_odds() -> list[dict]:
    """
    Fetch current MLB moneylines from The Odds API.
    Returns list of games with odds from multiple bookmakers.
    Uses in-memory cache (15 min TTL) to conserve the 500/month quota.
    """
    global _odds_cache, _cache_time

    if not ODDS_API_KEY:
        return []

    # Return cached if fresh
    now = datetime.now(timezone.utc)
    if _cache_time and (now - _cache_time).total_seconds() < CACHE_TTL_SECONDS and _odds_cache:
        return _odds_cache.get("games", [])

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BASE_URL}/sports/{SPORT}/odds",
                params={
                    "apiKey": ODDS_API_KEY,
                    "regions": "us",
                    "markets": "h2h,totals",
                    "oddsFormat": "american",
                    "bookmakers": "draftkings,fanduel,betmgm,caesars",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            # Parse remaining quota from headers
            remaining = resp.headers.get("x-requests-remaining", "?")
            used = resp.headers.get("x-requests-used", "?")
            print(f"  Odds API: {remaining} requests remaining ({used} used this month)")

            games = []
            for game in data:
                parsed = _parse_game(game)
                if parsed:
                    games.append(parsed)

            _odds_cache = {"games": games}
            _cache_time = now
            return games

    except Exception as e:
        print(f"  Odds API error: {e}")
        # Return stale cache if available
        return _odds_cache.get("games", [])


def _parse_game(game: dict) -> dict | None:
    """Parse a single game from The Odds API response."""
    home_team = game.get("home_team", "")
    away_team = game.get("away_team", "")
    commence = game.get("commence_time", "")

    bookmakers = game.get("bookmakers", [])
    if not bookmakers:
        return None

    # Collect moneylines and totals from all books
    h2h_odds = []
    totals = []

    for book in bookmakers:
        book_name = book.get("key", "")
        for market in book.get("markets", []):
            if market["key"] == "h2h":
                outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
                home_ml = outcomes.get(home_team)
                away_ml = outcomes.get(away_team)
                if home_ml is not None and away_ml is not None:
                    h2h_odds.append({
                        "book": book_name,
                        "home_ml": home_ml,
                        "away_ml": away_ml,
                    })
            elif market["key"] == "totals":
                for o in market.get("outcomes", []):
                    if o["name"] == "Over":
                        totals.append({
                            "book": book_name,
                            "total": o.get("point", 0),
                            "over_odds": o.get("price", -110),
                        })

    if not h2h_odds:
        return None

    # Best available odds (best line for each side)
    best_home_ml = max(o["home_ml"] for o in h2h_odds)
    best_away_ml = max(o["away_ml"] for o in h2h_odds)
    best_home_book = next(o["book"] for o in h2h_odds if o["home_ml"] == best_home_ml)
    best_away_book = next(o["book"] for o in h2h_odds if o["away_ml"] == best_away_ml)

    # Consensus (average) odds
    avg_home_ml = round(sum(o["home_ml"] for o in h2h_odds) / len(h2h_odds))
    avg_away_ml = round(sum(o["away_ml"] for o in h2h_odds) / len(h2h_odds))

    # Game total
    avg_total = round(sum(t["total"] for t in totals) / len(totals), 1) if totals else None

    return {
        "home_team": home_team,
        "away_team": away_team,
        "commence_time": commence,
        "odds": h2h_odds,
        "best_home_ml": best_home_ml,
        "best_home_book": best_home_book,
        "best_away_ml": best_away_ml,
        "best_away_book": best_away_book,
        "consensus_home_ml": avg_home_ml,
        "consensus_away_ml": avg_away_ml,
        "game_total": avg_total,
        "num_books": len(h2h_odds),
    }


def get_remaining_requests() -> str:
    """Return cached quota info."""
    return f"Cache age: {(datetime.now(timezone.utc) - _cache_time).seconds}s" if _cache_time else "No requests made yet"


# Team name mapping: The Odds API uses full names, MLB API uses slightly different ones
ODDS_TO_MLB_NAME = {
    "Arizona Diamondbacks": "Arizona Diamondbacks",
    "Atlanta Braves": "Atlanta Braves",
    "Baltimore Orioles": "Baltimore Orioles",
    "Boston Red Sox": "Boston Red Sox",
    "Chicago Cubs": "Chicago Cubs",
    "Chicago White Sox": "Chicago White Sox",
    "Cincinnati Reds": "Cincinnati Reds",
    "Cleveland Guardians": "Cleveland Guardians",
    "Colorado Rockies": "Colorado Rockies",
    "Detroit Tigers": "Detroit Tigers",
    "Houston Astros": "Houston Astros",
    "Kansas City Royals": "Kansas City Royals",
    "Los Angeles Angels": "Los Angeles Angels",
    "Los Angeles Dodgers": "Los Angeles Dodgers",
    "Miami Marlins": "Miami Marlins",
    "Milwaukee Brewers": "Milwaukee Brewers",
    "Minnesota Twins": "Minnesota Twins",
    "New York Mets": "New York Mets",
    "New York Yankees": "New York Yankees",
    "Oakland Athletics": "Athletics",
    "Philadelphia Phillies": "Philadelphia Phillies",
    "Pittsburgh Pirates": "Pittsburgh Pirates",
    "San Diego Padres": "San Diego Padres",
    "San Francisco Giants": "San Francisco Giants",
    "Seattle Mariners": "Seattle Mariners",
    "St. Louis Cardinals": "St. Louis Cardinals",
    "Tampa Bay Rays": "Tampa Bay Rays",
    "Texas Rangers": "Texas Rangers",
    "Toronto Blue Jays": "Toronto Blue Jays",
    "Washington Nationals": "Washington Nationals",
}


def match_odds_to_team_name(odds_name: str) -> str:
    """Convert Odds API team name to MLB API team name."""
    return ODDS_TO_MLB_NAME.get(odds_name, odds_name)
