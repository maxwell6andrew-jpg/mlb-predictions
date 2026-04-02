"""
Kalshi API client — fetch MLB contract prices for edge analysis.

Kalshi is a prediction market where prices = implied probabilities.
Contract at $0.55 = market thinks 55% chance.
If our model says 62%, that's a 7% edge → buy YES.

Auth: RSA-PSS signed requests (API key + private key PEM).
Docs: https://docs.kalshi.com
"""

import os
import time
import base64
import httpx
from datetime import datetime, timezone
from pathlib import Path

# Config from environment
KALSHI_API_KEY = os.environ.get("KALSHI_API_KEY", "")
KALSHI_PRIVATE_KEY_PATH = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
KALSHI_PRIVATE_KEY_PEM = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")  # Raw PEM content (for Render)

# Use production API
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_URL = "https://demo-api.kalshi.co/trade-api/v2"

# Cache
_markets_cache: dict = {}
_cache_time: datetime | None = None
CACHE_TTL_SECONDS = 300  # 5 minutes

# Team name mapping: Kalshi market titles → our team names
KALSHI_TEAM_NAMES = {
    "diamondbacks": "Arizona Diamondbacks",
    "braves": "Atlanta Braves",
    "orioles": "Baltimore Orioles",
    "red sox": "Boston Red Sox",
    "cubs": "Chicago Cubs",
    "white sox": "Chicago White Sox",
    "reds": "Cincinnati Reds",
    "guardians": "Cleveland Guardians",
    "rockies": "Colorado Rockies",
    "tigers": "Detroit Tigers",
    "astros": "Houston Astros",
    "royals": "Kansas City Royals",
    "angels": "Los Angeles Angels",
    "dodgers": "Los Angeles Dodgers",
    "marlins": "Miami Marlins",
    "brewers": "Milwaukee Brewers",
    "twins": "Minnesota Twins",
    "mets": "New York Mets",
    "yankees": "New York Yankees",
    "athletics": "Athletics",
    "a's": "Athletics",
    "phillies": "Philadelphia Phillies",
    "pirates": "Pittsburgh Pirates",
    "padres": "San Diego Padres",
    "giants": "San Francisco Giants",
    "mariners": "Seattle Mariners",
    "cardinals": "St. Louis Cardinals",
    "rays": "Tampa Bay Rays",
    "rangers": "Texas Rangers",
    "blue jays": "Toronto Blue Jays",
    "nationals": "Washington Nationals",
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


def match_kalshi_team(title: str) -> str | None:
    """Extract team name from a Kalshi market title."""
    title_lower = title.lower()
    for keyword, team_name in KALSHI_TEAM_NAMES.items():
        if keyword in title_lower:
            return team_name
    return None


async def fetch_mlb_markets() -> list[dict]:
    """
    Fetch MLB game markets from Kalshi.
    Returns parsed list of games with contract prices (= implied probabilities).
    """
    global _markets_cache, _cache_time

    # Return cached if fresh
    now = datetime.now(timezone.utc)
    if _cache_time and (now - _cache_time).total_seconds() < CACHE_TTL_SECONDS and _markets_cache:
        return _markets_cache.get("games", [])

    private_key = _load_private_key()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # First, try to find MLB series tickers
            markets = []

            # Method 1: Search by series with MLB/baseball category
            for search_term in ["MLB", "baseball"]:
                path = "/markets"
                params = {
                    "limit": 200,
                    "status": "open",
                    "series_ticker": search_term,
                }
                headers = _get_headers("GET", path, private_key) if private_key else {}
                try:
                    resp = await client.get(f"{BASE_URL}{path}", params=params, headers=headers)
                    if resp.status_code == 200:
                        batch = resp.json().get("markets", [])
                        markets.extend(batch)
                        print(f"  Kalshi: series_ticker={search_term} → {len(batch)} markets")
                except Exception:
                    pass

            # Method 2: If no series results, try the events endpoint
            if not markets:
                path = "/events"
                params = {"limit": 100, "status": "open"}
                headers = _get_headers("GET", path, private_key) if private_key else {}
                try:
                    resp = await client.get(f"{BASE_URL}{path}", params=params, headers=headers)
                    if resp.status_code == 200:
                        events = resp.json().get("events", [])
                        mlb_events = [e for e in events if any(
                            kw in (e.get("title", "") + e.get("category", "")).lower()
                            for kw in ["mlb", "baseball", "yankees", "dodgers", "mets"]
                        )]
                        print(f"  Kalshi: Found {len(mlb_events)} MLB events out of {len(events)} total")
                        for event in mlb_events:
                            event_ticker = event.get("event_ticker", "")
                            if event_ticker:
                                mpath = "/markets"
                                mparams = {"limit": 50, "event_ticker": event_ticker}
                                mheaders = _get_headers("GET", mpath, private_key) if private_key else {}
                                mresp = await client.get(f"{BASE_URL}{mpath}", params=mparams, headers=mheaders)
                                if mresp.status_code == 200:
                                    batch = mresp.json().get("markets", [])
                                    markets.extend(batch)
                except Exception as e:
                    print(f"  Kalshi: Events search failed: {e}")

            # Method 3: Fallback — fetch all open markets and filter
            if not markets:
                path = "/markets"
                params = {"limit": 200, "status": "open"}
                headers = _get_headers("GET", path, private_key) if private_key else {}
                resp = await client.get(f"{BASE_URL}{path}", params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                markets = data.get("markets", [])

            print(f"  Kalshi: Total markets to scan: {len(markets)}")
            # Log first few market titles for debugging
            for m in markets[:5]:
                print(f"    → {m.get('ticker', '?')}: {m.get('title', '?')}")

            # Filter for MLB game markets
            mlb_games = []
            for market in markets:
                ticker = market.get("ticker", "")
                title = market.get("title", "")
                subtitle = market.get("subtitle", "")
                category = market.get("category", "")

                # Filter for MLB — look for baseball/MLB indicators
                is_mlb = (
                    "mlb" in ticker.lower()
                    or "mlb" in title.lower()
                    or "baseball" in category.lower()
                    or any(team in title.lower() for team in KALSHI_TEAM_NAMES.keys())
                )

                if not is_mlb:
                    continue

                yes_price = market.get("yes_ask", 0) or market.get("last_price", 0)
                no_price = market.get("no_ask", 0)
                yes_bid = market.get("yes_bid", 0)
                no_bid = market.get("no_bid", 0)

                # Normalize prices (Kalshi uses cents, 0-100 or dollars 0-1)
                if yes_price and yes_price > 1:
                    yes_price = yes_price / 100
                if no_price and no_price > 1:
                    no_price = no_price / 100
                if yes_bid and yes_bid > 1:
                    yes_bid = yes_bid / 100
                if no_bid and no_bid > 1:
                    no_bid = no_bid / 100

                mlb_games.append({
                    "ticker": ticker,
                    "title": title,
                    "subtitle": subtitle,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "yes_bid": yes_bid,
                    "no_bid": no_bid,
                    "volume": market.get("volume", 0),
                    "open_interest": market.get("open_interest", 0),
                    "close_time": market.get("close_time", ""),
                    "event_ticker": market.get("event_ticker", ""),
                    "result": market.get("result", ""),
                    "status": market.get("status", ""),
                })

            _markets_cache = {"games": mlb_games}
            _cache_time = now
            print(f"  Kalshi: Found {len(mlb_games)} MLB markets")
            return mlb_games

    except Exception as e:
        print(f"  Kalshi API error: {e}")
        return _markets_cache.get("games", [])


async def fetch_market_orderbook(ticker: str) -> dict:
    """Fetch order book for a specific market — shows best bid/ask."""
    private_key = _load_private_key()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            path = f"/markets/{ticker}/orderbook"
            headers = _get_headers("GET", path, private_key) if private_key else {}
            resp = await client.get(f"{BASE_URL}{path}", headers=headers)
            resp.raise_for_status()
            return resp.json().get("orderbook", {})
    except Exception as e:
        print(f"  Kalshi orderbook error for {ticker}: {e}")
        return {}


def get_kalshi_status() -> str:
    """Return cache status."""
    if _cache_time:
        age = (datetime.now(timezone.utc) - _cache_time).seconds
        count = len(_markets_cache.get("games", []))
        return f"{count} MLB markets cached ({age}s ago)"
    return "No Kalshi data fetched yet"
