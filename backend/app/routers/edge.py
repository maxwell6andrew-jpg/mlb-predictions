"""
/api/edge/season — Model vs Vegas season win totals with value identification
/api/edge/today  — Today's games with Kalshi contract prices (prediction market)
/api/edge/props  — Player prop recommendations based on pitcher/batter matchups

PRIVATE ENDPOINTS — not linked from public frontend.
Kalshi API: contract price = implied probability. $0.55 YES = 55% chance.
Edge = our model probability - Kalshi implied probability.
"""

from fastapi import APIRouter, Request, Query
from datetime import datetime, timezone, timedelta
import math
import httpx

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.data.vegas_lines import get_vegas_line
from app.data.kalshi_client import fetch_mlb_markets, fetch_mlb_prop_markets, match_kalshi_team, get_kalshi_status
from app.data.park_factors import get_park_factor

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api/edge")

KELLY_FRACTION = 0.25  # 25% Kelly — conservative

# League average baselines (2024 season)
LG_AVG = 0.248
LG_HR_RATE = 0.033   # HR per PA
LG_K_RATE = 0.228    # K per PA
LG_H_RATE = 0.248    # hits per AB (approx AVG)
LG_ERA = 4.00
LG_K_PER_9 = 8.6


def _implied_prob(ml: int) -> float:
    """American moneyline → implied probability (includes vig)."""
    if ml < 0:
        return abs(ml) / (abs(ml) + 100)
    else:
        return 100 / (ml + 100)


def _no_vig_prob(home_ml: int, away_ml: int) -> tuple[float, float]:
    """Remove vig to get true implied probabilities."""
    raw_home = _implied_prob(home_ml)
    raw_away = _implied_prob(away_ml)
    total = raw_home + raw_away  # > 1.0 due to vig
    return raw_home / total, raw_away / total


def _decimal_odds(ml: int) -> float:
    """American moneyline → decimal odds."""
    if ml < 0:
        return 1 + 100 / abs(ml)
    else:
        return 1 + ml / 100


def _moneyline_from_prob(prob: float) -> int:
    """Probability → American moneyline."""
    if prob <= 0 or prob >= 1:
        return 0
    if prob >= 0.5:
        return int(-100 * prob / (1 - prob))
    else:
        return int(100 * (1 - prob) / prob)


def _ev(model_prob: float, decimal_odds: float, stake: float = 100.0) -> float:
    """Expected value per $100 bet."""
    profit = stake * (decimal_odds - 1)
    return model_prob * profit - (1 - model_prob) * stake


def _kelly(model_prob: float, decimal_odds: float) -> float:
    """Kelly criterion bet size as fraction of bankroll."""
    b = decimal_odds - 1
    if b <= 0:
        return 0.0
    f = (b * model_prob - (1 - model_prob)) / b
    return max(0.0, f * KELLY_FRACTION)


@router.get("/season")
@limiter.limit("20/minute")
async def edge_season(request: Request):
    """Model vs Vegas season win totals."""
    standings = getattr(request.app.state, "standings_cache", [])
    cache = request.app.state.projection_cache

    edges = []
    for team in standings:
        team_id = team["team_id"]
        model_wins = team["projected_wins"]
        vegas_wins = team.get("vegas_line")
        if not vegas_wins:
            continue

        diff = model_wins - vegas_wins
        if diff > 1.5:
            rec = "OVER"
            conf = "Strong" if diff > 4 else "Moderate" if diff > 2.5 else "Lean"
        elif diff < -1.5:
            rec = "UNDER"
            conf = "Strong" if diff < -4 else "Moderate" if diff < -2.5 else "Lean"
        else:
            rec = "PASS"
            conf = "No edge"

        edges.append({
            "team_id": team_id,
            "name": team["name"],
            "abbreviation": team["abbreviation"],
            "division": team["division"],
            "model_wins": model_wins,
            "vegas_wins": vegas_wins,
            "difference": round(diff, 1),
            "recommendation": rec,
            "confidence": conf,
        })

    edges.sort(key=lambda e: abs(e["difference"]), reverse=True)

    return {
        "season": edges,
        "value_bets": sum(1 for e in edges if e["recommendation"] != "PASS"),
        "methodology": "60% model / 40% Vegas blend. Large disagreements = strong model conviction.",
    }


@router.get("/today")
@limiter.limit("10/minute")
async def edge_today(request: Request):
    """
    Today's games with Kalshi contract prices.
    Compares model win probability to Kalshi market implied probability.
    Contract at $0.55 = market thinks 55% chance.
    Edge = model prob - contract price. Positive edge = buy YES.
    """
    cache = request.app.state.projection_cache
    standings = getattr(request.app.state, "standings_cache", [])

    # Build team name → team data lookup
    team_by_name = {}
    for team in standings:
        team_by_name[team["name"]] = team

    # Fetch Kalshi MLB game markets
    kalshi_games = await fetch_mlb_markets()

    if not kalshi_games:
        return {
            "date": datetime.now(timezone(timedelta(hours=-7))).strftime("%Y-%m-%d"),
            "games": [],
            "message": "No Kalshi MLB game markets found. Markets may not be posted yet for today.",
            "kalshi_status": get_kalshi_status(),
        }

    # Also fetch today's schedule for game times
    api_client = getattr(request.app.state, "api_client", None)
    pacific = timezone(timedelta(hours=-7))
    today = datetime.now(pacific).strftime("%Y-%m-%d")

    schedule_games = []
    if api_client:
        try:
            data = await api_client._get(
                "/schedule",
                params={"sportId": 1, "date": today, "hydrate": "team,linescore"},
                cache_ttl=300,
            )
            dates = data.get("dates", [])
            schedule_games = dates[0]["games"] if dates else []
        except Exception:
            pass

    # Build game time lookup
    game_times = {}
    for g in schedule_games:
        home = g["teams"]["home"]["team"]["name"]
        game_times[home] = g.get("gameDate", "")

    value_games = []

    for game in kalshi_games:
        home_name = game["home_team"]
        away_name = game["away_team"]
        kalshi_home = game["home_price"]
        kalshi_away = game["away_price"]

        if kalshi_home <= 0 and kalshi_away <= 0:
            continue

        # Find our model projections
        home_data = team_by_name.get(home_name)
        away_data = team_by_name.get(away_name)
        if not home_data or not away_data:
            continue

        home_proj = cache.get_team(home_data["team_id"])
        away_proj = cache.get_team(away_data["team_id"])
        if not home_proj or not away_proj:
            continue

        # Model win probability (log5 + home field)
        home_wpct = home_proj.get("win_pct", 0.5)
        away_wpct = away_proj.get("win_pct", 0.5)
        denom = home_wpct * (1 - away_wpct) + away_wpct * (1 - home_wpct)
        model_home = (home_wpct * (1 - away_wpct)) / denom if denom > 0 else 0.5
        model_home = min(0.95, max(0.05, model_home + 0.035))  # home field
        model_away = 1 - model_home

        # Edge = model prob - Kalshi implied prob
        home_edge = model_home - kalshi_home
        away_edge = model_away - kalshi_away

        # Decimal odds = 1 / contract_price (buy YES at 55¢, pays $1)
        home_dec_odds = 1 / kalshi_home if kalshi_home > 0 else 1
        away_dec_odds = 1 / kalshi_away if kalshi_away > 0 else 1

        # EV and Kelly
        home_ev = _ev(model_home, home_dec_odds)
        away_ev = _ev(model_away, away_dec_odds)
        home_kelly = _kelly(model_home, home_dec_odds)
        away_kelly = _kelly(model_away, away_dec_odds)

        # Get game time from schedule
        game_time = game_times.get(home_name, "")

        # Which side has value?
        if home_ev > away_ev and home_ev > 0:
            value_side = "HOME"
            value_team = home_name
            value_ev = home_ev
            value_kelly = home_kelly
            value_edge = home_edge
            value_price = kalshi_home  # Buy YES on home at this price
            model_prob = model_home
        elif away_ev > 0:
            value_side = "AWAY"
            value_team = away_name
            value_ev = away_ev
            value_kelly = away_kelly
            value_edge = away_edge
            value_price = kalshi_away  # Buy YES on away at this price
            model_prob = model_away
        else:
            value_side = "PASS"
            value_team = ""
            value_ev = max(home_ev, away_ev)
            value_kelly = 0
            value_edge = 0
            value_price = 0
            model_prob = 0

        # Edge strength
        if value_ev > 5:
            strength = "STRONG"
        elif value_ev > 2:
            strength = "MODERATE"
        elif value_ev > 0:
            strength = "SLIGHT"
        else:
            strength = "NO EDGE"

        value_games.append({
            "home_team": home_name,
            "away_team": away_name,
            "game_time": game_time,
            # Model
            "model_home_prob": round(model_home, 3),
            "model_away_prob": round(model_away, 3),
            # Kalshi market prices (= implied probabilities)
            "kalshi_home_price": round(kalshi_home, 3),
            "kalshi_away_price": round(kalshi_away, 3),
            "kalshi_ticker": game["event_ticker"],
            "kalshi_volume": game["volume"],
            # Edge analysis
            "value_side": value_side,
            "value_team": value_team,
            "value_price": round(value_price, 3),  # Buy YES at this price
            "edge_pct": round(value_edge * 100, 2),
            "ev_per_100": round(value_ev, 2),
            "kelly_pct": round(value_kelly * 100, 2),
            "strength": strength,
        })

    # Best bets first
    value_games.sort(key=lambda g: g["ev_per_100"], reverse=True)

    # --- BUILD $100 BET SLIP ---
    bankroll = 100.0
    bet_slip = []
    remaining_bankroll = bankroll
    for g in value_games:
        if g["value_side"] == "PASS":
            continue
        bet_amount = round(g["kelly_pct"] / 100 * bankroll, 2)
        if bet_amount < 1.0:
            continue
        if bet_amount > remaining_bankroll:
            bet_amount = round(remaining_bankroll, 2)
        if bet_amount <= 0:
            break
        remaining_bankroll -= bet_amount

        # Kalshi payout: buy YES contracts at value_price, each pays $1 if correct
        # Number of contracts = bet_amount / value_price
        # Profit per contract = (1 - value_price)
        contracts = bet_amount / g["value_price"] if g["value_price"] > 0 else 0
        potential_payout = round(contracts * 1.0, 2)  # Each contract pays $1
        potential_profit = round(potential_payout - bet_amount, 2)

        bet_slip.append({
            "team": g["value_team"],
            "opponent": g["away_team"] if g["value_side"] == "HOME" else g["home_team"],
            "side": g["value_side"],
            "buy_price": g["value_price"],  # Kalshi contract price
            "contracts": round(contracts, 1),
            "bet_amount": bet_amount,
            "potential_payout": potential_payout,
            "potential_profit": potential_profit,
            "ev_per_100": g["ev_per_100"],
            "model_prob": round(g["model_home_prob"] if g["value_side"] == "HOME" else g["model_away_prob"], 3),
            "edge_pct": g["edge_pct"],
            "matchup": f"{g['away_team']} @ {g['home_team']}",
            "game_time": g["game_time"],
        })

    total_wagered = round(sum(b["bet_amount"] for b in bet_slip), 2)
    total_potential_profit = round(sum(b["potential_profit"] for b in bet_slip), 2)

    return {
        "date": datetime.now(timezone(timedelta(hours=-7))).strftime("%Y-%m-%d"),
        "games": value_games,
        "total_games": len(value_games),
        "value_bets": sum(1 for g in value_games if g["value_side"] != "PASS"),
        "best_bet": value_games[0] if value_games and value_games[0]["value_side"] != "PASS" else None,
        "bet_slip": {
            "bankroll": bankroll,
            "bets": bet_slip,
            "total_wagered": total_wagered,
            "remaining_bankroll": round(bankroll - total_wagered, 2),
            "total_potential_profit": total_potential_profit,
            "num_bets": len(bet_slip),
        },
        "kalshi_status": get_kalshi_status(),
        "disclaimer": "For research/entertainment only. Not gambling advice.",
    }


@router.get("/props")
@limiter.limit("10/minute")
async def edge_props(request: Request):
    """
    Player prop recommendations based on pitcher/batter matchup projections.
    Uses our Marcel projections + Statcast adjustments to find edges in:
    - Strikeout props (pitcher K rate vs batter K rate)
    - Hit props (batter AVG vs pitcher WHIP)
    - HR props (batter HR rate vs pitcher HR/9, park factor)
    - Total bases props (batter SLG vs pitcher quality)
    """
    cache = request.app.state.projection_cache
    standings = getattr(request.app.state, "standings_cache", [])
    api_client = request.app.state.api_client
    id_mapper = request.app.state.id_mapper

    pacific = timezone(timedelta(hours=-7))
    today = datetime.now(pacific).strftime("%Y-%m-%d")

    # Fetch today's schedule with probable pitchers
    try:
        data = await api_client._get(
            "/schedule",
            params={"sportId": 1, "date": today, "hydrate": "probablePitcher,team,linescore"},
            cache_ttl=300,
        )
        dates = data.get("dates", [])
        games_raw = dates[0]["games"] if dates else []
    except Exception:
        games_raw = []

    if not games_raw:
        return {"date": today, "props": [], "message": "No games scheduled today."}

    all_props = []

    for g in games_raw:
        away_info = g["teams"]["away"]
        home_info = g["teams"]["home"]
        away_id = away_info["team"]["id"]
        home_id = home_info["team"]["id"]
        away_name = away_info["team"]["name"]
        home_name = home_info["team"]["name"]

        # Get probable pitchers
        away_sp_meta = away_info.get("probablePitcher", {})
        home_sp_meta = home_info.get("probablePitcher", {})
        away_sp_mlbam = away_sp_meta.get("id")
        home_sp_mlbam = home_sp_meta.get("id")
        away_sp_name = away_sp_meta.get("fullName", "TBD")
        home_sp_name = home_sp_meta.get("fullName", "TBD")

        # Pitcher projections
        away_sp_proj = _pitcher_from_cache(away_sp_mlbam, cache, id_mapper) if away_sp_mlbam else None
        home_sp_proj = _pitcher_from_cache(home_sp_mlbam, cache, id_mapper) if home_sp_mlbam else None

        # Team projections (contain batter lists)
        home_team_proj = cache.get_team(home_id)
        away_team_proj = cache.get_team(away_id)

        park = get_park_factor(home_id, "runs")
        park_hr = get_park_factor(home_id, "hr") if hasattr(get_park_factor, '__call__') else park

        game_time = g.get("gameDate", "")

        # Generate props for away batters vs home pitcher
        if home_sp_proj and away_team_proj:
            props = _generate_batter_props(
                batters=away_team_proj.get("batters", []),
                pitcher=home_sp_proj,
                pitcher_name=home_sp_name,
                pitcher_team=home_name,
                batter_team=away_name,
                cache=cache,
                id_mapper=id_mapper,
                park_factor=park,
                game_time=game_time,
            )
            all_props.extend(props)

        # Generate props for home batters vs away pitcher
        if away_sp_proj and home_team_proj:
            props = _generate_batter_props(
                batters=home_team_proj.get("batters", []),
                pitcher=away_sp_proj,
                pitcher_name=away_sp_name,
                pitcher_team=away_name,
                batter_team=home_name,
                cache=cache,
                id_mapper=id_mapper,
                park_factor=park,
                game_time=game_time,
            )
            all_props.extend(props)

        # Pitcher strikeout props
        if home_sp_proj and away_team_proj:
            k_prop = _generate_pitcher_k_prop(
                pitcher=home_sp_proj,
                pitcher_name=home_sp_name,
                pitcher_team=home_name,
                opp_team=away_name,
                opp_batters=away_team_proj.get("batters", []),
                cache=cache,
                id_mapper=id_mapper,
                game_time=game_time,
            )
            if k_prop:
                all_props.append(k_prop)

        if away_sp_proj and home_team_proj:
            k_prop = _generate_pitcher_k_prop(
                pitcher=away_sp_proj,
                pitcher_name=away_sp_name,
                pitcher_team=away_name,
                opp_team=home_name,
                opp_batters=home_team_proj.get("batters", []),
                cache=cache,
                id_mapper=id_mapper,
                game_time=game_time,
            )
            if k_prop:
                all_props.append(k_prop)

    # --- MATCH WITH KALSHI PROP MARKETS ---
    kalshi_props = await fetch_mlb_prop_markets()

    # Build lookup: normalize player name → list of Kalshi hit props
    kalshi_hit_props = {}
    for kp in kalshi_props:
        if kp.get("prop_type") == "KXMLBHIT" and kp.get("player_name"):
            name_key = kp["player_name"].lower().strip()
            if name_key not in kalshi_hit_props:
                kalshi_hit_props[name_key] = []
            kalshi_hit_props[name_key].append(kp)

    # Enrich model props with Kalshi market prices
    for prop in all_props:
        player_name = prop.get("player", "").lower().strip()

        if prop["type"] in ("hits", "strikeout") and player_name in kalshi_hit_props:
            # Find matching hit count line
            kalshi_matches = kalshi_hit_props[player_name]
            # For hits OVER 0.5 → match Kalshi 1+ hits
            # For strikeout → no direct Kalshi match yet
            if prop["type"] == "hits":
                # Our line is 0.5 hits → Kalshi "1+ hits" is equivalent
                for km in kalshi_matches:
                    if km.get("line") == 1:
                        prop["kalshi_price"] = km["price"]
                        prop["kalshi_ticker"] = km["ticker"]
                        prop["kalshi_label"] = km.get("prop_label", "")
                        # Edge = model implied prob of OVER - (1 - kalshi NO price)
                        # Kalshi YES price = implied prob of 1+ hits
                        # If our model says higher prob → buy YES
                        model_hit_prob = min(0.95, prop["projected_value"] / 1.0)  # rough
                        # More accurate: P(1+ hit) = 1 - (1-AVG)^AB
                        prop["kalshi_edge"] = round((model_hit_prob - km["price"]) * 100, 2)
                        break
                # Also attach 2+ hits market if available
                for km in kalshi_matches:
                    if km.get("line") == 2:
                        prop["kalshi_2plus_price"] = km["price"]
                        prop["kalshi_2plus_ticker"] = km["ticker"]
                        break

        elif prop["type"] == "home_run" and player_name:
            # No direct Kalshi HR prop yet, but check anyway
            pass

    # Sort by confidence (strongest props first)
    all_props.sort(key=lambda p: p["confidence_score"], reverse=True)

    # --- BUILD $100 PROPS BET SLIP (with real Kalshi prices) ---
    bankroll = 100.0
    props_bet_slip = []
    remaining = bankroll

    for prop in all_props:
        if prop["confidence_score"] < 55:
            continue

        kalshi_price = prop.get("kalshi_price", 0)
        has_kalshi = kalshi_price > 0

        # Size by confidence: strong=5%, moderate=3%, lean=2% of bankroll
        if prop["confidence_score"] >= 75:
            pct = 0.05
        elif prop["confidence_score"] >= 60:
            pct = 0.03
        else:
            pct = 0.02
        bet_amount = round(bankroll * pct, 2)
        if bet_amount > remaining:
            bet_amount = round(remaining, 2)
        if bet_amount < 1.0:
            break
        remaining -= bet_amount

        if has_kalshi:
            # Real Kalshi payout: buy YES at kalshi_price, pays $1 if correct
            contracts = bet_amount / kalshi_price
            potential_payout = round(contracts * 1.0, 2)
            potential_profit = round(potential_payout - bet_amount, 2)
            dec_odds = round(1 / kalshi_price, 2)
        else:
            # Fallback: estimated odds
            if prop["type"] == "home_run":
                est_odds = +320
            elif prop["type"] == "total_bases":
                est_odds = -115
            elif prop["type"] == "pitcher_strikeouts":
                est_odds = -120
            else:
                est_odds = -120
            dec_odds = round(_decimal_odds(est_odds), 2)
            potential_profit = round(bet_amount * (dec_odds - 1), 2)
            contracts = 0
            potential_payout = round(bet_amount + potential_profit, 2)

        props_bet_slip.append({
            "player": prop["player"],
            "player_team": prop["player_team"],
            "prop": prop["prop"],
            "type": prop["type"],
            "matchup": prop["matchup"],
            "projected_value": prop["projected_value"],
            "confidence": prop["confidence"],
            "confidence_score": prop["confidence_score"],
            "kalshi_price": kalshi_price if has_kalshi else None,
            "kalshi_ticker": prop.get("kalshi_ticker", ""),
            "kalshi_2plus_price": prop.get("kalshi_2plus_price"),
            "kalshi_2plus_ticker": prop.get("kalshi_2plus_ticker", ""),
            "kalshi_edge": prop.get("kalshi_edge"),
            "has_kalshi": has_kalshi,
            "decimal_odds": dec_odds,
            "contracts": round(contracts, 1) if has_kalshi else None,
            "bet_amount": bet_amount,
            "potential_payout": potential_payout,
            "potential_profit": potential_profit,
            "reasoning": prop["reasoning"],
            "game_time": prop["game_time"],
        })

    total_wagered = round(sum(b["bet_amount"] for b in props_bet_slip), 2)
    total_potential_profit = round(sum(b["potential_profit"] for b in props_bet_slip), 2)

    # --- KALSHI-ONLY PROP EDGES ---
    # Props where Kalshi price exists and our model disagrees significantly
    kalshi_edges = []
    for prop in all_props:
        if prop.get("kalshi_price") and prop.get("kalshi_edge", 0) > 3:
            kalshi_edges.append({
                "player": prop["player"],
                "player_team": prop.get("player_team", ""),
                "prop": prop.get("kalshi_label", prop["prop"]),
                "kalshi_price": prop["kalshi_price"],
                "kalshi_ticker": prop.get("kalshi_ticker", ""),
                "model_edge_pct": prop["kalshi_edge"],
                "confidence": prop["confidence"],
                "matchup": prop["matchup"],
                "game_time": prop.get("game_time", ""),
            })
    kalshi_edges.sort(key=lambda e: e["model_edge_pct"], reverse=True)

    return {
        "date": today,
        "props": all_props,
        "total_props": len(all_props),
        "strong_props": sum(1 for p in all_props if p["confidence_score"] >= 70),
        "kalshi_prop_count": sum(1 for p in all_props if p.get("kalshi_price")),
        "kalshi_edges": kalshi_edges,
        "bet_slip": {
            "bankroll": bankroll,
            "bets": props_bet_slip,
            "total_wagered": total_wagered,
            "remaining_bankroll": round(bankroll - total_wagered, 2),
            "total_potential_profit": total_potential_profit,
            "num_bets": len(props_bet_slip),
        },
        "kalshi_status": get_kalshi_status(),
    }


def _pitcher_from_cache(mlbam_id, cache, id_mapper):
    """Look up pitcher projection from cache."""
    if not mlbam_id:
        return None
    lahman_id = id_mapper.mlbam_to_lahman(mlbam_id)
    if not lahman_id:
        return None
    return cache.get_pitching(lahman_id)


def _batter_from_cache(mlbam_id, cache, id_mapper):
    """Look up batter projection from cache."""
    if not mlbam_id:
        return None
    lahman_id = id_mapper.mlbam_to_lahman(mlbam_id)
    if not lahman_id:
        return None
    return cache.get_batting(lahman_id)


def _generate_batter_props(batters, pitcher, pitcher_name, pitcher_team,
                           batter_team, cache, id_mapper, park_factor, game_time):
    """Generate hit, HR, and total bases props for batters facing a pitcher."""
    props = []
    p_era = pitcher.get("era", LG_ERA)
    p_k9 = pitcher.get("k_per_9", LG_K_PER_9)
    p_hr9 = pitcher.get("hr_per_9", 1.2)
    p_whip = pitcher.get("whip", 1.30)

    # Pitcher quality multipliers (relative to league average)
    pitcher_k_mult = p_k9 / LG_K_PER_9  # >1 = high-K pitcher
    pitcher_hr_mult = p_hr9 / 1.2  # >1 = gives up more HR
    pitcher_hit_mult = p_whip / 1.30  # >1 = gives up more hits

    for batter_info in batters[:9]:  # Top 9 lineup spots
        batter_mlbam = batter_info.get("id")
        batter_proj = _batter_from_cache(batter_mlbam, cache, id_mapper)
        if not batter_proj:
            continue

        batter_name = batter_proj.get("name", batter_info.get("name", "Unknown"))
        b_avg = batter_proj.get("avg", LG_AVG)
        b_hr = batter_proj.get("hr", 15)
        b_pa = batter_proj.get("projected_pa", 500)
        b_k_rate = batter_proj.get("k_rate", LG_K_RATE)
        b_hr_rate = batter_proj.get("hr_rate", LG_HR_RATE)
        b_slg = batter_proj.get("slg", 0.400)
        b_ops = batter_proj.get("ops", 0.700)
        position = batter_proj.get("position", batter_info.get("position", ""))

        # Skip pitchers
        if position in ("P", "SP", "RP"):
            continue

        # --- STRIKEOUT PROP ---
        # Matchup K rate = batter's K tendency × pitcher's K ability
        matchup_k_rate = b_k_rate * pitcher_k_mult
        # Assuming ~4 PA per game
        expected_ks = matchup_k_rate * 4.0
        k_line = 0.5
        # Only recommend OVER if projected value actually beats the line
        if expected_ks > k_line + 0.15 and pitcher_k_mult > 1.05:
            edge_over_line = expected_ks - k_line
            k_confidence = min(90, int(50 + edge_over_line * 25 + (pitcher_k_mult - 1) * 30))
            props.append({
                "type": "strikeout",
                "prop": f"OVER {k_line} Ks",
                "player": batter_name,
                "player_team": batter_team,
                "matchup": f"vs {pitcher_name} ({pitcher_team})",
                "line": k_line,
                "recommendation": "OVER",
                "projected_value": round(expected_ks, 2),
                "reasoning": f"{batter_name} K rate {b_k_rate:.1%} vs {pitcher_name} ({p_k9:.1f} K/9, {pitcher_k_mult:.0%} of avg)",
                "confidence_score": k_confidence,
                "confidence": "Strong" if k_confidence >= 75 else "Moderate" if k_confidence >= 60 else "Lean",
                "game_time": game_time,
            })

        # --- HIT PROP ---
        # Matchup hit rate = batter AVG adjusted by pitcher quality
        matchup_hit_rate = b_avg * pitcher_hit_mult
        expected_hits = matchup_hit_rate * 4.0  # ~4 AB
        hit_line = 0.5
        # Only recommend when projected output actually exceeds the line
        if expected_hits > hit_line + 0.15:
            edge_over_line = expected_hits - hit_line
            hit_confidence = min(90, int(50 + edge_over_line * 30 + (b_avg - LG_AVG) * 200))
            props.append({
                "type": "hits",
                "prop": f"OVER {hit_line} hits",
                "player": batter_name,
                "player_team": batter_team,
                "matchup": f"vs {pitcher_name} ({pitcher_team})",
                "line": hit_line,
                "recommendation": "OVER",
                "projected_value": round(expected_hits, 2),
                "reasoning": f"{batter_name} .{int(b_avg*1000)} AVG vs {pitcher_name} ({p_whip:.2f} WHIP) → proj {expected_hits:.1f} hits",
                "confidence_score": hit_confidence,
                "confidence": "Strong" if hit_confidence >= 75 else "Moderate" if hit_confidence >= 60 else "Lean",
                "game_time": game_time,
            })

        # --- HR PROP ---
        # HR probability per PA × ~4 PA = game HR probability
        matchup_hr_prob = b_hr_rate * pitcher_hr_mult * park_factor
        game_hr_prob = matchup_hr_prob * 4.0  # chance of at least 1 HR in ~4 PA
        # Only recommend when there's a real HR threat
        if game_hr_prob > 0.12 and b_hr >= 20:
            hr_confidence = min(85, int(40 + (game_hr_prob - 0.10) * 200 + (b_hr - 20) * 0.5))
            props.append({
                "type": "home_run",
                "prop": "to hit HR",
                "player": batter_name,
                "player_team": batter_team,
                "matchup": f"vs {pitcher_name} ({pitcher_team})",
                "line": 0.5,
                "recommendation": "YES",
                "projected_value": round(game_hr_prob, 3),
                "reasoning": f"{batter_name} proj {b_hr} HR ({b_hr_rate:.1%}/PA) vs {pitcher_name} ({p_hr9:.1f} HR/9) | park {park_factor:.2f}x → {game_hr_prob:.0%} chance",
                "confidence_score": hr_confidence,
                "confidence": "Strong" if hr_confidence >= 75 else "Moderate" if hr_confidence >= 60 else "Lean",
                "game_time": game_time,
            })

        # --- TOTAL BASES PROP ---
        # Expected TB per game ≈ SLG * AB_per_game, adjusted for pitcher/park
        expected_tb = b_slg * 3.8 * pitcher_hit_mult * park_factor
        tb_line = 1.5
        # Only recommend when projected TB actually exceeds the line
        if expected_tb > tb_line + 0.2:
            edge_over_line = expected_tb - tb_line
            tb_confidence = min(85, int(45 + edge_over_line * 20 + (b_ops - 0.700) * 50))
            props.append({
                "type": "total_bases",
                "prop": f"OVER {tb_line} total bases",
                "player": batter_name,
                "player_team": batter_team,
                "matchup": f"vs {pitcher_name} ({pitcher_team})",
                "line": tb_line,
                "recommendation": "OVER",
                "projected_value": round(expected_tb, 2),
                "reasoning": f"{batter_name} .{int(b_slg*1000)} SLG, {b_ops:.3f} OPS vs {pitcher_name} ({p_era:.2f} ERA) → proj {expected_tb:.1f} TB",
                "confidence_score": tb_confidence,
                "confidence": "Strong" if tb_confidence >= 75 else "Moderate" if tb_confidence >= 60 else "Lean",
                "game_time": game_time,
            })

    return props


def _generate_pitcher_k_prop(pitcher, pitcher_name, pitcher_team, opp_team,
                              opp_batters, cache, id_mapper, game_time):
    """Generate pitcher strikeout total prop."""
    p_k9 = pitcher.get("k_per_9", LG_K_PER_9)
    p_ip = pitcher.get("projected_ip", 150)
    p_era = pitcher.get("era", LG_ERA)

    # Average K rate of opposing lineup
    opp_k_rates = []
    for b in opp_batters[:9]:
        bp = _batter_from_cache(b.get("id"), cache, id_mapper)
        if bp:
            opp_k_rates.append(bp.get("k_rate", LG_K_RATE))

    avg_opp_k_rate = sum(opp_k_rates) / len(opp_k_rates) if opp_k_rates else LG_K_RATE

    # Projected Ks this game: (pitcher K/9) × (expected IP ~5.5-6) × (opp K tendency)
    expected_ip = min(6.5, max(4.5, p_ip / 30))  # rough per-start IP
    opp_k_mult = avg_opp_k_rate / LG_K_RATE
    projected_ks = (p_k9 / 9) * expected_ip * opp_k_mult

    # Standard line is usually 4.5 or 5.5
    if projected_ks >= 5.5:
        line = 5.5
    elif projected_ks >= 4.5:
        line = 4.5
    else:
        line = 3.5

    rec = "OVER" if projected_ks > line + 0.3 else "UNDER" if projected_ks < line - 0.5 else None
    if not rec:
        return None

    edge = abs(projected_ks - line)
    confidence = min(90, int(50 + edge * 15 + (p_k9 - LG_K_PER_9) * 5))

    return {
        "type": "pitcher_strikeouts",
        "prop": f"{rec} {line} Ks",
        "player": pitcher_name,
        "player_team": pitcher_team,
        "matchup": f"vs {opp_team}",
        "line": line,
        "recommendation": rec,
        "projected_value": round(projected_ks, 1),
        "reasoning": f"{pitcher_name} {p_k9:.1f} K/9, ~{expected_ip:.1f} IP | {opp_team} lineup K rate {avg_opp_k_rate:.1%} ({opp_k_mult:.0%} of avg)",
        "confidence_score": confidence,
        "confidence": "Strong" if confidence >= 75 else "Moderate" if confidence >= 60 else "Lean",
        "game_time": game_time,
    }


@router.get("/status")
@limiter.limit("30/minute")
async def kalshi_status(request: Request):
    """Check Kalshi market cache status."""
    return {"kalshi_status": get_kalshi_status()}


@router.get("/kalshi-debug")
@limiter.limit("10/minute")
async def kalshi_debug_view(request: Request):
    """Debug: show raw Kalshi markets for troubleshooting."""
    markets = await fetch_mlb_markets()
    return {
        "kalshi_status": get_kalshi_status(),
        "num_markets": len(markets),
        "markets": markets[:20],
    }
