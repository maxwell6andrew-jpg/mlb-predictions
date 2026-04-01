"""
/api/edge/season — Model vs Vegas season win totals with value identification
/api/edge/today  — Today's games with REAL odds from DraftKings/FanDuel/etc

PRIVATE ENDPOINTS — not linked from public frontend.
Requires ODDS_API_KEY environment variable for live odds.
"""

from fastapi import APIRouter, Request, Query
from datetime import datetime, timezone, timedelta
import math

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.data.vegas_lines import get_vegas_line
from app.data.odds_client import fetch_live_odds, match_odds_to_team_name, get_remaining_requests

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api/edge")

KELLY_FRACTION = 0.25  # 25% Kelly — conservative


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
    Today's games with REAL live odds.
    Compares model win probability to actual sportsbook lines.
    Calculates true EV and Kelly sizing using real moneylines.
    """
    cache = request.app.state.projection_cache
    standings = getattr(request.app.state, "standings_cache", [])

    # Build team name → team data lookup
    team_by_name = {}
    for team in standings:
        team_by_name[team["name"]] = team

    # Fetch real live odds
    live_odds = await fetch_live_odds()

    if not live_odds:
        return {
            "date": datetime.now(timezone(timedelta(hours=-7))).strftime("%Y-%m-%d"),
            "games": [],
            "message": "No live odds available. Check ODDS_API_KEY env var.",
            "quota": get_remaining_requests(),
        }

    value_games = []

    for game in live_odds:
        home_name_odds = game["home_team"]
        away_name_odds = game["away_team"]

        # Map to our team names
        home_name = match_odds_to_team_name(home_name_odds)
        away_name = match_odds_to_team_name(away_name_odds)

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

        # Real odds from sportsbooks
        best_home_ml = game["best_home_ml"]
        best_away_ml = game["best_away_ml"]
        consensus_home_ml = game["consensus_home_ml"]
        consensus_away_ml = game["consensus_away_ml"]

        # Vegas implied probability (no-vig)
        vegas_home, vegas_away = _no_vig_prob(consensus_home_ml, consensus_away_ml)

        # Edge = model prob - vegas implied prob
        home_edge = model_home - vegas_home
        away_edge = model_away - vegas_away

        # EV using BEST available odds (line shop)
        home_ev = _ev(model_home, _decimal_odds(best_home_ml))
        away_ev = _ev(model_away, _decimal_odds(best_away_ml))

        # Kelly sizing using best odds
        home_kelly = _kelly(model_home, _decimal_odds(best_home_ml))
        away_kelly = _kelly(model_away, _decimal_odds(best_away_ml))

        # Which side has value?
        if home_ev > away_ev and home_ev > 0:
            value_side = "HOME"
            value_team = home_name
            value_ev = home_ev
            value_kelly = home_kelly
            value_edge = home_edge
            value_ml = best_home_ml
            value_book = game["best_home_book"]
            model_prob = model_home
            vegas_prob = vegas_home
        elif away_ev > 0:
            value_side = "AWAY"
            value_team = away_name
            value_ev = away_ev
            value_kelly = away_kelly
            value_edge = away_edge
            value_ml = best_away_ml
            value_book = game["best_away_book"]
            model_prob = model_away
            vegas_prob = vegas_away
        else:
            value_side = "PASS"
            value_team = ""
            value_ev = max(home_ev, away_ev)
            value_kelly = 0
            value_edge = 0
            value_ml = 0
            value_book = ""
            model_prob = 0
            vegas_prob = 0

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
            "game_time": game["commence_time"],
            "game_total": game["game_total"],
            # Model
            "model_home_prob": round(model_home, 3),
            "model_away_prob": round(model_away, 3),
            "model_home_ml": _moneyline_from_prob(model_home),
            "model_away_ml": _moneyline_from_prob(model_away),
            # Real Vegas odds
            "vegas_home_ml": consensus_home_ml,
            "vegas_away_ml": consensus_away_ml,
            "vegas_home_prob": round(vegas_home, 3),
            "vegas_away_prob": round(vegas_away, 3),
            # Best available line (line shopping)
            "best_home_ml": best_home_ml,
            "best_home_book": game["best_home_book"],
            "best_away_ml": best_away_ml,
            "best_away_book": game["best_away_book"],
            # Edge analysis
            "value_side": value_side,
            "value_team": value_team,
            "edge_pct": round(value_edge * 100, 2),
            "ev_per_100": round(value_ev, 2),
            "kelly_pct": round(value_kelly * 100, 2),
            "kelly_bet_on_100": round(value_kelly * 100, 2),  # $ to bet if bankroll = $100
            "best_book": value_book,
            "strength": strength,
            # All books for this game
            "all_odds": game["odds"],
            "num_books": game["num_books"],
        })

    # Best bets first
    value_games.sort(key=lambda g: g["ev_per_100"], reverse=True)

    return {
        "date": datetime.now(timezone(timedelta(hours=-7))).strftime("%Y-%m-%d"),
        "games": value_games,
        "total_games": len(value_games),
        "value_bets": sum(1 for g in value_games if g["value_side"] != "PASS"),
        "best_bet": value_games[0] if value_games and value_games[0]["value_side"] != "PASS" else None,
        "quota": get_remaining_requests(),
        "bankroll_note": "kelly_bet_on_100 = dollars to wager if your bankroll is $100. Scale linearly.",
        "disclaimer": "For research/entertainment only. Not gambling advice.",
    }


@router.get("/quota")
@limiter.limit("30/minute")
async def odds_quota(request: Request):
    """Check remaining Odds API requests."""
    return {"quota": get_remaining_requests()}
