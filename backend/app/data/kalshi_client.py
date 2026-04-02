"""
Kalshi API client — fetch MLB game contract prices for edge analysis.

Kalshi is a prediction market where prices = implied probabilities.
Contract at $0.54 = market thinks 54% chance.
If our model says 62%, that's an 8% edge → buy YES.

Market structure:
  - Events: KXMLBGAME-26APR041915ATLAZ (game-level, contains 2 markets)
  - Markets: KXMLBGAME-26APR041915ATLAZ-ATL (team to win, binary YES/NO)
  - Prices: last_price_dollars, no_ask_dollars, no_bid_dollars (string format "0.5400")

Auth: RSA-PSS signed requests (API key + private key PEM).
Docs: https://docs.kalshi.com
"""

import os
import re
import time
import base64
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# Config from environment
KALSHI_API_KEY = os.environ.get("KALSHI_API_KEY", "")
KALSHI_PRIVATE_KEY_PATH = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
KALSHI_PRIVATE_KEY_PEM = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")  # Raw PEM content (for Render)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

# Cache
_markets_cache: dict = {}
_cache_time: Optional[datetime] = None
CACHE_TTL_SECONDS = 300  # 5 minutes

# Kalshi abbreviation → our full team name
KALSHI_ABBREV_TO_TEAM = {
    "AZ": "Arizona Diamondbacks",
    "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox",
    "CHC": "Chicago Cubs",
    "CWS": "Chicago White Sox",
    "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians",
    "COL": "Colorado Rockies",
    "DET": "Detroit Tigers",
    "HOU": "Houston Astros",
    "KC": "Kansas City Royals",
    "LAA": "Los Angeles Angels",
    "LAD": "Los Angeles Dodgers",
    "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers",
    "MIN": "Minnesota Twins",
    "NYM": "New York Mets",
    "NYY": "New York Yankees",
    "OAK": "Athletics",
    "PHI": "Philadelphia Phillies",
    "PIT": "Pittsburgh Pirates",
    "SD": "San Diego Padres",
    "SF": "San Francisco Giants",
    "SEA": "Seattle Mariners",
    "STL": "St. Louis Cardinals",
    "TB": "Tampa Bay Rays",
    "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays",
    "WSH": "Washington Nationals",
}

# Kalshi title names → our team names
KALSHI_TITLE_TO_TEAM = {
    "Arizona": "Arizona Diamondbacks",
    "Atlanta": "Atlanta Braves",
    "Baltimore": "Baltimore Orioles",
    "Boston": "Boston Red Sox",
    "Chicago C": "Chicago Cubs",
    "Chicago WS": "Chicago White Sox",
    "Cincinnati": "Cincinnati Reds",
    "Cleveland": "Cleveland Guardians",
    "Colorado": "Colorado Rockies",
    "Detroit": "Detroit Tigers",
    "Houston": "Houston Astros",
    "Kansas City": "Kansas City Royals",
    "Los Angeles A": "Los Angeles Angels",
    "Los Angeles D": "Los Angeles Dodgers",
    "Miami": "Miami Marlins",
    "Milwaukee": "Milwaukee Brewers",
    "Minnesota": "Minnesota Twins",
    "New York M": "New York Mets",
    "New York Y": "New York Yankees",
    "Oakland": "Athletics",
    "Philadelphia": "Philadelphia Phillies",
    "Pittsburgh": "Pittsburgh Pirates",
    "San Diego": "San Diego Padres",
    "San Francisco": "San Francisco Giants",
    "Seattle": "Seattle Mariners",
    "St. Louis": "St. Louis Cardinals",
    "Tampa Bay": "Tampa Bay Rays",
    "Texas": "Texas Rangers",
    "Toronto": "Toronto Blue Jays",
    "Washington": "Washington Nationals",
}


def _load_private_key():
    """Load RSA private key from PEM file or env var."""
    try:
        from cryptography.hazmat.primitives import serialization

        # Option 1: Raw PEM content in env var (for Render / cloud deploys)
        if KALSHI_PRIVATE_KEY_PEM:
            pem_data = KALSHI_PRIVATE_KEY_PEM.encode()
            return serialization.load_pem_private_key(pem_data, password=None)

        # Option 2: File path
        key_path = KALSHI_PRIVATE_KEY_PATH
        if key_path and Path(key_path).exists():
            with open(key_path, "rb") as f:
                return serialization.load_pem_private_key(f.read(), password=None)

        return None
    except Exception as e:
        print(f"  Kalshi: Failed to load private key: {e}")
        return None


def _sign_request(private_key, timestamp_ms: str, method: str, path: str) -> str:
    """Sign a Kalshi API request with RSA-PSS."""
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        message = f"{timestamp_ms}{method}{path}".encode()
        signature = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode()
    except Exception as e:
        print(f"  Kalshi: Signing failed: {e}")
        return ""


def _get_headers(method: str, path: str, private_key=None):
    """Build auth headers for Kalshi API."""
    if not KALSHI_API_KEY or not private_key:
        return {}
    timestamp_ms = str(int(time.time() * 1000))
    signature = _sign_request(private_key, timestamp_ms, method, path)
    return {
        "KALSHI-ACCESS-KEY": KALSHI_API_KEY,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "Content-Type": "application/json",
    }


def _parse_dollars(val) -> float:
    """Parse a Kalshi dollar string like '0.5400' to float."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def match_kalshi_team(title: str) -> Optional[str]:
    """Extract team name from a Kalshi event/market title."""
    # Try title-based mapping first (e.g. "Atlanta vs Arizona")
    for kalshi_name, team_name in KALSHI_TITLE_TO_TEAM.items():
        if kalshi_name in title:
            return team_name
    return None


def _parse_event_ticker(event_ticker: str) -> dict:
    """
    Parse KXMLBGAME-26APR041915ATLAZ into components.
    Returns: {date: "2026-04-04", time: "19:15", away_abbrev: "ATL", home_abbrev: "AZ"}
    """
    # Pattern: KXMLBGAME-26MMMDDHHMMAWYHOME
    match = re.match(r'KXMLBGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})(.+)', event_ticker)
    if not match:
        return {}

    year = f"20{match.group(1)}"
    month_str = match.group(2)
    day = match.group(3)
    time_str = match.group(4)
    teams_str = match.group(5)

    months = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
              "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"}
    month = months.get(month_str, "01")

    hour = time_str[:2]
    minute = time_str[2:]

    return {
        "date": f"{year}-{month}-{day}",
        "time": f"{hour}:{minute}",
        "teams_str": teams_str,
    }


async def fetch_mlb_markets() -> list[dict]:
    """
    Fetch today's MLB game markets from Kalshi.

    Strategy:
    1. Paginate through /events to find KXMLBGAME events
    2. For each game event, fetch individual market tickers with prices
    3. Return structured game data with contract prices
    """
    global _markets_cache, _cache_time

    now = datetime.now(timezone.utc)
    if _cache_time and (now - _cache_time).total_seconds() < CACHE_TTL_SECONDS and _markets_cache:
        return _markets_cache.get("games", [])

    private_key = _load_private_key()
    if not private_key:
        print("  Kalshi: No private key available")
        return []

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # Get today and tomorrow's date strings for filtering
            pacific = timezone(timedelta(hours=-7))
            today = datetime.now(pacific)
            today_str = today.strftime("%y%b%d").upper()  # e.g. "26APR02"
            tomorrow = today + timedelta(days=1)
            tomorrow_str = tomorrow.strftime("%y%b%d").upper()

            # Find all KXMLBGAME events by paginating through events
            game_events = []
            cursor = None
            pages_searched = 0

            for page in range(50):  # Up to 10,000 events
                path = "/events"
                headers = _get_headers("GET", path, private_key)
                params = {"limit": 200, "with_nested_markets": "true"}
                if cursor:
                    params["cursor"] = cursor

                resp = await client.get(f"{BASE_URL}{path}", params=params, headers=headers)
                if resp.status_code != 200:
                    print(f"  Kalshi: Events page {page} returned {resp.status_code}")
                    break

                data = resp.json()
                events = data.get("events", [])
                cursor = data.get("cursor")
                pages_searched += 1

                for e in events:
                    ticker = e.get("event_ticker", "")
                    if ticker.startswith("KXMLBGAME-"):
                        # Check if it's for today or tomorrow
                        if today_str in ticker or tomorrow_str in ticker:
                            game_events.append(e)

                if not cursor or not events:
                    break

            print(f"  Kalshi: Searched {pages_searched} event pages, found {len(game_events)} MLB game events")

            # Now fetch full market details for each game
            games = []
            for event in game_events:
                event_ticker = event.get("event_ticker", "")
                title = event.get("title", "")  # e.g. "Atlanta vs Arizona"

                # Parse teams from title: "Atlanta vs Arizona"
                parts = title.split(" vs ")
                if len(parts) != 2:
                    continue

                away_kalshi = parts[0].strip()
                home_kalshi = parts[1].strip()
                away_team = KALSHI_TITLE_TO_TEAM.get(away_kalshi, away_kalshi)
                home_team = KALSHI_TITLE_TO_TEAM.get(home_kalshi, home_kalshi)

                # Parse date/time from ticker
                parsed = _parse_event_ticker(event_ticker)
                game_date = parsed.get("date", "")
                game_time = parsed.get("time", "")

                # Get individual market data for each team
                # Markets are: KXMLBGAME-26APR041915ATLAZ-ATL and -AZ
                nested_markets = event.get("markets", [])

                away_price = 0.0
                home_price = 0.0
                away_ticker = ""
                home_ticker = ""
                total_volume = 0

                if nested_markets:
                    # Use nested market data from event response
                    for m in nested_markets:
                        mticker = m.get("ticker", "")
                        last_price = _parse_dollars(m.get("last_price_dollars"))
                        no_ask = _parse_dollars(m.get("no_ask_dollars"))
                        vol = m.get("volume", 0) or 0
                        total_volume += vol

                        # Determine which team this market is for
                        suffix = mticker.split("-")[-1] if "-" in mticker else ""
                        team_name = KALSHI_ABBREV_TO_TEAM.get(suffix, "")

                        price = last_price if last_price > 0 else (1.0 - _parse_dollars(m.get("no_bid_dollars")))

                        if team_name == away_team:
                            away_price = price
                            away_ticker = mticker
                        elif team_name == home_team:
                            home_price = price
                            home_ticker = mticker
                else:
                    # Fetch market data individually
                    for suffix_team in [(away_kalshi, away_team), (home_kalshi, home_team)]:
                        # Try to find the right market ticker suffix
                        for abbrev, full_name in KALSHI_ABBREV_TO_TEAM.items():
                            if full_name == suffix_team[1]:
                                mticker = f"{event_ticker}-{abbrev}"
                                mpath = f"/markets/{mticker}"
                                mheaders = _get_headers("GET", mpath, private_key)
                                try:
                                    mresp = await client.get(f"{BASE_URL}{mpath}", headers=mheaders)
                                    if mresp.status_code == 200:
                                        m = mresp.json().get("market", {})
                                        price = _parse_dollars(m.get("last_price_dollars"))
                                        vol = m.get("volume", 0) or 0
                                        total_volume += vol

                                        if full_name == away_team:
                                            away_price = price
                                            away_ticker = mticker
                                        else:
                                            home_price = price
                                            home_ticker = mticker
                                except Exception:
                                    pass
                                break

                # Skip games with no price data
                if away_price <= 0 and home_price <= 0:
                    continue

                # If we only have one side, infer the other
                if away_price > 0 and home_price <= 0:
                    home_price = 1.0 - away_price
                elif home_price > 0 and away_price <= 0:
                    away_price = 1.0 - home_price

                games.append({
                    "event_ticker": event_ticker,
                    "title": title,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_price": round(home_price, 4),
                    "away_price": round(away_price, 4),
                    "home_ticker": home_ticker,
                    "away_ticker": away_ticker,
                    "volume": total_volume,
                    "game_date": game_date,
                    "game_time": game_time,
                })

            _markets_cache = {"games": games}
            _cache_time = now
            print(f"  Kalshi: {len(games)} MLB games with prices")
            return games

    except Exception as e:
        print(f"  Kalshi API error: {e}")
        import traceback
        traceback.print_exc()
        return _markets_cache.get("games", [])


def get_kalshi_status() -> str:
    """Return cache status."""
    if _cache_time:
        age = (datetime.now(timezone.utc) - _cache_time).seconds
        count = len(_markets_cache.get("games", []))
        return f"{count} MLB games cached ({age}s ago)"
    return "No Kalshi data fetched yet"
