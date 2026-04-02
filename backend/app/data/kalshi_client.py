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
            pem_str = KALSHI_PRIVATE_KEY_PEM.strip()

            # Render mangles newlines in env vars. Handle all formats:
            # Format A: literal \n characters (most common Render issue)
            if "\\n" in pem_str:
                pem_str = pem_str.replace("\\n", "\n")

            # Format B: Everything on one line, no newlines at all
            # e.g. "-----BEGIN RSA PRIVATE KEY-----MIIEpAI...-----END RSA PRIVATE KEY-----"
            if "\n" not in pem_str and "-----BEGIN" in pem_str:
                # Extract the base64 content between BEGIN and END markers
                import re
                m = re.match(r'(-----BEGIN [A-Z ]+-----)(.+)(-----END [A-Z ]+-----)', pem_str)
                if m:
                    header = m.group(1)
                    b64 = m.group(2)
                    footer = m.group(3)
                    # Wrap base64 at 64 chars per line (PEM standard)
                    wrapped = "\n".join(b64[i:i+64] for i in range(0, len(b64), 64))
                    pem_str = f"{header}\n{wrapped}\n{footer}"

            pem_data = pem_str.strip().encode()
            print(f"  Kalshi: Loading key from env var ({len(pem_data)} bytes)")
            return serialization.load_pem_private_key(pem_data, password=None)

        # Option 2: File path
        key_path = KALSHI_PRIVATE_KEY_PATH
        if key_path and Path(key_path).exists():
            with open(key_path, "rb") as f:
                return serialization.load_pem_private_key(f.read(), password=None)

        print("  Kalshi: No private key configured (set KALSHI_PRIVATE_KEY_PEM or KALSHI_PRIVATE_KEY_PATH)")
        return None
    except Exception as e:
        print(f"  Kalshi: Failed to load private key: {e}")
        import traceback
        traceback.print_exc()
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
    Fetch today's + tomorrow's MLB game markets from Kalshi.

    Strategy: Directly fetch each game's market by constructing tickers
    from today's MLB schedule. Ticker format: KXMLBGAME-26APR02HHMMAWYHOME
    We fetch the individual market endpoints for each team (fast, no pagination).
    """
    global _markets_cache, _cache_time

    now = datetime.now(timezone.utc)
    if _cache_time and (now - _cache_time).total_seconds() < CACHE_TTL_SECONDS and _markets_cache:
        return _markets_cache.get("games", [])

    private_key = _load_private_key()
    if not private_key:
        print("  Kalshi: No private key available")
        return []

    # Reverse mapping: full team name → Kalshi abbreviation
    team_to_abbrev = {v: k for k, v in KALSHI_ABBREV_TO_TEAM.items()}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Get today's MLB schedule from MLB Stats API (free, no auth)
            pacific = timezone(timedelta(hours=-7))
            today = datetime.now(pacific)
            games = []

            for day_offset in [0, 1]:  # Today and tomorrow
                target = today + timedelta(days=day_offset)
                date_str = target.strftime("%Y-%m-%d")
                kalshi_date = target.strftime("%y%b%d").upper()  # "26APR02"

                try:
                    sched_resp = await client.get(
                        "https://statsapi.mlb.com/api/v1/schedule",
                        params={"sportId": 1, "date": date_str, "hydrate": "team"},
                        timeout=10,
                    )
                    sched_data = sched_resp.json()
                    sched_dates = sched_data.get("dates", [])
                    day_games = sched_dates[0]["games"] if sched_dates else []
                except Exception as e:
                    print(f"  Kalshi: MLB schedule fetch failed for {date_str}: {e}")
                    continue

                print(f"  Kalshi: {len(day_games)} MLB games on {date_str}")

                for g in day_games:
                    away_name = g["teams"]["away"]["team"]["name"]
                    home_name = g["teams"]["home"]["team"]["name"]
                    game_time_str = g.get("gameDate", "")

                    away_abbrev = team_to_abbrev.get(away_name, "")
                    home_abbrev = team_to_abbrev.get(home_name, "")
                    if not away_abbrev or not home_abbrev:
                        continue

                    # Parse game time to build Kalshi ticker
                    # gameDate is ISO: "2026-04-02T23:10:00Z" → need ET
                    try:
                        game_dt = datetime.fromisoformat(game_time_str.replace("Z", "+00:00"))
                        et = game_dt.astimezone(timezone(timedelta(hours=-4)))
                        time_part = et.strftime("%H%M")  # "1910"
                    except Exception:
                        time_part = "1900"  # fallback

                    # Construct event ticker: KXMLBGAME-26APR021910ATLAZ
                    event_ticker = f"KXMLBGAME-{kalshi_date}{time_part}{away_abbrev}{home_abbrev}"

                    # Fetch both team markets directly
                    away_market_ticker = f"{event_ticker}-{away_abbrev}"
                    home_market_ticker = f"{event_ticker}-{home_abbrev}"

                    away_price = 0.0
                    home_price = 0.0
                    total_volume = 0

                    for mticker, is_away in [(away_market_ticker, True), (home_market_ticker, False)]:
                        mpath = f"/markets/{mticker}"
                        mheaders = _get_headers("GET", mpath, private_key)
                        try:
                            mresp = await client.get(f"{BASE_URL}{mpath}", headers=mheaders)
                            if mresp.status_code == 200:
                                m = mresp.json().get("market", {})
                                price = _parse_dollars(m.get("last_price_dollars"))
                                vol = m.get("volume", 0) or 0
                                total_volume += vol
                                if is_away:
                                    away_price = price
                                else:
                                    home_price = price
                            elif mresp.status_code == 404:
                                # Try with different time offsets (Kalshi time might differ by a few min)
                                pass
                        except Exception:
                            pass

                    # Skip if no prices found
                    if away_price <= 0 and home_price <= 0:
                        # Try nearby time offsets (±5 min, ±10 min)
                        found = False
                        for offset_min in [5, -5, 10, -10, 15, -15, 30, -30]:
                            try:
                                alt_dt = et + timedelta(minutes=offset_min)
                                alt_time = alt_dt.strftime("%H%M")
                                alt_event = f"KXMLBGAME-{kalshi_date}{alt_time}{away_abbrev}{home_abbrev}"
                                alt_ticker = f"{alt_event}-{away_abbrev}"
                                apath = f"/markets/{alt_ticker}"
                                aheaders = _get_headers("GET", apath, private_key)
                                aresp = await client.get(f"{BASE_URL}{apath}", headers=aheaders)
                                if aresp.status_code == 200:
                                    event_ticker = alt_event
                                    m = aresp.json().get("market", {})
                                    away_price = _parse_dollars(m.get("last_price_dollars"))
                                    # Also get home
                                    hpath = f"/markets/{alt_event}-{home_abbrev}"
                                    hheaders = _get_headers("GET", hpath, private_key)
                                    hresp = await client.get(f"{BASE_URL}{hpath}", headers=hheaders)
                                    if hresp.status_code == 200:
                                        hm = hresp.json().get("market", {})
                                        home_price = _parse_dollars(hm.get("last_price_dollars"))
                                    found = True
                                    break
                            except Exception:
                                continue
                        if not found:
                            continue

                    # Infer missing side
                    if away_price > 0 and home_price <= 0:
                        home_price = 1.0 - away_price
                    elif home_price > 0 and away_price <= 0:
                        away_price = 1.0 - home_price

                    games.append({
                        "event_ticker": event_ticker,
                        "title": f"{away_name} vs {home_name}",
                        "home_team": home_name,
                        "away_team": away_name,
                        "home_price": round(home_price, 4),
                        "away_price": round(away_price, 4),
                        "home_ticker": f"{event_ticker}-{home_abbrev}",
                        "away_ticker": f"{event_ticker}-{away_abbrev}",
                        "volume": total_volume,
                        "game_date": date_str,
                        "game_time_iso": game_time_str,
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


async def fetch_mlb_prop_markets() -> list[dict]:
    """
    Fetch today's + tomorrow's MLB player prop markets from Kalshi.

    Prop types:
      - KXMLBHIT: Player hits (1+, 2+, 3+, 4+ hits)
      - KXMLBTOTAL: Game total runs (over 3, 4, 5, 6... runs)
      - KXMLBSPREAD: Run line (team wins by X+ runs)
      - KXMLBRFI: Run in first inning (binary)

    Market ticker examples:
      KXMLBHIT-26APR021410MINKC-KCBWITT7-2  → Bobby Witt Jr. 2+ hits
      KXMLBTOTAL-26APR032215NYMSF-8         → NYM vs SF: Over 8 total runs
      KXMLBSPREAD-26APR032145ATLAZ-ATL2     → Atlanta wins by 2+ runs
    """
    global _markets_cache, _cache_time

    now = datetime.now(timezone.utc)

    # Return cached props if fresh
    if _cache_time and (now - _cache_time).total_seconds() < CACHE_TTL_SECONDS and _markets_cache.get("props"):
        return _markets_cache.get("props", [])

    private_key = _load_private_key()
    if not private_key:
        return []

    team_to_abbrev = {v: k for k, v in KALSHI_ABBREV_TO_TEAM.items()}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            pacific = timezone(timedelta(hours=-7))
            today = datetime.now(pacific)
            all_props = []

            for day_offset in [0, 1]:
                target = today + timedelta(days=day_offset)
                date_str = target.strftime("%Y-%m-%d")
                kalshi_date = target.strftime("%y%b%d").upper()

                try:
                    sched_resp = await client.get(
                        "https://statsapi.mlb.com/api/v1/schedule",
                        params={"sportId": 1, "date": date_str, "hydrate": "team,probablePitcher"},
                        timeout=10,
                    )
                    sched_data = sched_resp.json()
                    sched_dates = sched_data.get("dates", [])
                    day_games = sched_dates[0]["games"] if sched_dates else []
                except Exception as e:
                    print(f"  Kalshi props: MLB schedule fetch failed for {date_str}: {e}")
                    continue

                for g in day_games:
                    away_name = g["teams"]["away"]["team"]["name"]
                    home_name = g["teams"]["home"]["team"]["name"]
                    game_time_str = g.get("gameDate", "")

                    away_abbrev = team_to_abbrev.get(away_name, "")
                    home_abbrev = team_to_abbrev.get(home_name, "")
                    if not away_abbrev or not home_abbrev:
                        continue

                    try:
                        game_dt = datetime.fromisoformat(game_time_str.replace("Z", "+00:00"))
                        et = game_dt.astimezone(timezone(timedelta(hours=-4)))
                        time_part = et.strftime("%H%M")
                    except Exception:
                        time_part = "1900"

                    game_suffix = f"{kalshi_date}{time_part}{away_abbrev}{home_abbrev}"

                    # Fetch prop events for this game: hits, totals, spreads, RFI
                    for prop_type in ["KXMLBHIT", "KXMLBTOTAL", "KXMLBSPREAD", "KXMLBRFI"]:
                        event_ticker = f"{prop_type}-{game_suffix}"
                        mpath = "/markets"
                        mheaders = _get_headers("GET", mpath, private_key)

                        try:
                            mresp = await client.get(
                                f"{BASE_URL}{mpath}",
                                headers=mheaders,
                                params={"event_ticker": event_ticker, "limit": 100},
                            )
                            if mresp.status_code != 200:
                                # Try time offsets
                                found = False
                                for offset_min in [5, -5, 10, -10, 15, -15, 30, -30]:
                                    try:
                                        alt_dt = et + timedelta(minutes=offset_min)
                                        alt_time = alt_dt.strftime("%H%M")
                                        alt_suffix = f"{kalshi_date}{alt_time}{away_abbrev}{home_abbrev}"
                                        alt_event = f"{prop_type}-{alt_suffix}"
                                        aheaders = _get_headers("GET", mpath, private_key)
                                        aresp = await client.get(
                                            f"{BASE_URL}{mpath}",
                                            headers=aheaders,
                                            params={"event_ticker": alt_event, "limit": 100},
                                        )
                                        if aresp.status_code == 200:
                                            markets = aresp.json().get("markets", [])
                                            if markets:
                                                event_ticker = alt_event
                                                mresp = aresp
                                                found = True
                                                break
                                    except Exception:
                                        continue
                                if not found:
                                    continue

                            markets = mresp.json().get("markets", [])
                        except Exception:
                            continue

                        for m in markets:
                            price = _parse_dollars(m.get("last_price_dollars"))
                            if price <= 0:
                                continue  # No price = no liquidity

                            ticker = m.get("ticker", "")
                            subtitle = m.get("subtitle", m.get("title", ""))

                            prop_data = {
                                "ticker": ticker,
                                "event_ticker": event_ticker,
                                "prop_type": prop_type,
                                "subtitle": subtitle,
                                "price": round(price, 4),
                                "volume": m.get("volume", 0) or 0,
                                "home_team": home_name,
                                "away_team": away_name,
                                "game_date": date_str,
                                "game_time_iso": game_time_str,
                            }

                            # Parse prop details from subtitle and ticker
                            if prop_type == "KXMLBHIT":
                                # "Bobby Witt Jr.: 2+ hits?" or "Juan Soto: 1+ hits?"
                                hit_match = re.match(r'(.+?):\s*(\d+)\+\s*hits\?', subtitle)
                                if hit_match:
                                    prop_data["player_name"] = hit_match.group(1).strip()
                                    prop_data["line"] = int(hit_match.group(2))
                                    prop_data["prop_label"] = f"{prop_data['line']}+ hits"

                                # Extract team abbrev from ticker: ...-KCBWITT7-2
                                parts = ticker.replace(event_ticker + "-", "").split("-")
                                if parts:
                                    player_part = parts[0]
                                    # Match team abbrev at start
                                    for abbrev in sorted(KALSHI_ABBREV_TO_TEAM.keys(), key=len, reverse=True):
                                        if player_part.startswith(abbrev):
                                            prop_data["player_team"] = KALSHI_ABBREV_TO_TEAM[abbrev]
                                            break

                            elif prop_type == "KXMLBTOTAL":
                                # Ticker ends with run count: ...-8 means 8+ total runs
                                parts = ticker.replace(event_ticker + "-", "")
                                try:
                                    run_line = int(parts)
                                    prop_data["line"] = run_line
                                    prop_data["prop_label"] = f"Over {run_line} total runs"
                                    prop_data["player_name"] = f"{away_name} vs {home_name}"
                                except ValueError:
                                    pass

                            elif prop_type == "KXMLBSPREAD":
                                # "Atlanta wins by over 2.5 runs?"
                                spread_match = re.match(r'(.+?)\s+wins\s+by\s+over\s+([\d.]+)\s+runs\?', subtitle)
                                if spread_match:
                                    team_city = spread_match.group(1).strip()
                                    spread_val = float(spread_match.group(2))
                                    prop_data["spread_team"] = team_city
                                    prop_data["line"] = spread_val
                                    prop_data["prop_label"] = f"{team_city} -{spread_val}"
                                    prop_data["player_name"] = f"{team_city} -{spread_val}"

                            elif prop_type == "KXMLBRFI":
                                prop_data["line"] = 0.5
                                prop_data["prop_label"] = "Run in 1st inning"
                                prop_data["player_name"] = f"{away_name} vs {home_name}"

                            all_props.append(prop_data)

            # Cache props alongside games
            _markets_cache["props"] = all_props
            if not _cache_time:
                _cache_time = now
            print(f"  Kalshi: {len(all_props)} prop markets with prices")
            return all_props

    except Exception as e:
        print(f"  Kalshi props API error: {e}")
        import traceback
        traceback.print_exc()
        return _markets_cache.get("props", [])


def get_kalshi_status() -> str:
    """Return cache status."""
    if _cache_time:
        age = (datetime.now(timezone.utc) - _cache_time).seconds
        count = len(_markets_cache.get("games", []))
        props_count = len(_markets_cache.get("props", []))
        return f"{count} MLB games, {props_count} props cached ({age}s ago)"
    return "No Kalshi data fetched yet"
