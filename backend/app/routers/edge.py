"""
/api/edge/season — Model vs Vegas season win totals with value identification
/api/edge/today  — Today's games with EV calculations and Kelly sizing
"""

from fastapi import APIRouter, Request, Query
from datetime import datetime, timezone, timedelta
import math

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.data.vegas_lines import get_vegas_line, get_all_vegas_lines

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api/edge")

# Assumed vig on a standard -110/-110 line
STANDARD_VIG = 0.0455

# Kelly fraction (25% Kelly = conservative, reduces ruin risk)
KELLY_FRACTION = 0.25

# Minimum edge threshold to flag as a value bet
MIN_EDGE_PCT = 2.0  # percent


def _implied_prob_from_moneyline(ml: int) -> float:
    """Convert American moneyline to implied probability (no-vig)."""
    if ml < 0:
        return abs(ml) / (abs(ml) + 100)
    else:
        return 100 / (ml + 100)


def _moneyline_from_prob(prob: float) -> int:
    """Convert probability to American moneyline."""
    if prob <= 0 or prob >= 1:
        return 0
    if prob >= 0.5:
        return int(-100 * prob / (1 - prob))
    else:
        return int(100 * (1 - prob) / prob)


def _kelly_bet(model_prob: float, decimal_odds: float, fraction: float = KELLY_FRACTION) -> float:
    """
    Kelly criterion: f* = (bp - q) / b
    Returns fraction of bankroll to bet. Negative = no bet.
    """
    b = decimal_odds - 1  # net odds
    p = model_prob
    q = 1 - p
    if b <= 0:
        return 0.0
    kelly = (b * p - q) / b
    return max(0.0, kelly * fraction)


def _expected_value(model_prob: float, decimal_odds: float, stake: float = 100.0) -> float:
    """EV = (prob_win × profit) - (prob_lose × stake)"""
    profit = stake * (decimal_odds - 1)
    return model_prob * profit - (1 - model_prob) * stake


def _decimal_from_moneyline(ml: int) -> float:
    """Convert American moneyline to decimal odds."""
    if ml < 0:
        return 1 + 100 / abs(ml)
    else:
        return 1 + ml / 100


@router.get("/season")
@limiter.limit("20/minute")
async def edge_season(request: Request):
    """Compare model projections vs Vegas season win totals. Flag disagreements."""
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
        edge_pct = (diff / vegas_wins) * 100 if vegas_wins else 0

        # Over/under recommendation
        if diff > 1.5:
            recommendation = "OVER"
            confidence = "Strong" if diff > 4 else "Moderate" if diff > 2.5 else "Lean"
        elif diff < -1.5:
            recommendation = "UNDER"
            confidence = "Strong" if diff < -4 else "Moderate" if diff < -2.5 else "Lean"
        else:
            recommendation = "PASS"
            confidence = "No edge"

        # Get team-level detail
        team_proj = cache.get_team(team_id)
        initial_war = team_proj.get("_initial_war", 0) if team_proj else 0

        edges.append({
            "team_id": team_id,
            "name": team["name"],
            "abbreviation": team["abbreviation"],
            "division": team["division"],
            "model_wins": model_wins,
            "vegas_wins": vegas_wins,
            "difference": round(diff, 1),
            "edge_pct": round(edge_pct, 1),
            "recommendation": recommendation,
            "confidence": confidence,
            "roster_war": round(initial_war, 1),
        })

    # Sort by absolute difference (biggest disagreements first)
    edges.sort(key=lambda e: abs(e["difference"]), reverse=True)

    return {
        "season": edges,
        "summary": {
            "total_teams": len(edges),
            "value_bets": sum(1 for e in edges if e["recommendation"] != "PASS"),
            "overs": sum(1 for e in edges if e["recommendation"] == "OVER"),
            "unders": sum(1 for e in edges if e["recommendation"] == "UNDER"),
            "avg_abs_diff": round(sum(abs(e["difference"]) for e in edges) / max(len(edges), 1), 1),
        },
        "methodology": {
            "model_blend": "60% Marcel+Statcast+OLS model, 40% Vegas consensus",
            "note": "Since our model already blends 40% Vegas, large disagreements indicate strong model conviction",
            "threshold": "±1.5 wins to flag as value bet",
        },
    }


@router.get("/today")
@limiter.limit("20/minute")
async def edge_today(request: Request):
    """Today's games with expected value, Kelly sizing, and edge identification."""
    from app.routers.matchups import _fetch_today_schedule, _pitcher_from_cache, _add_fip

    # Get date
    pacific = timezone(timedelta(hours=-7))
    today = datetime.now(pacific).strftime("%Y-%m-%d")

    api_client = request.app.state.api_client
    cache = request.app.state.projection_cache
    id_mapper = request.app.state.id_mapper
    league_avg = request.app.state.league_avg
    lg_era = league_avg.get("era", 4.00)

    games_raw = await _fetch_today_schedule(api_client, today)
    if not games_raw:
        return {"date": today, "games": [], "message": "No games today"}

    value_games = []

    for g in games_raw:
        away_info = g["teams"]["away"]
        home_info = g["teams"]["home"]
        away_id = away_info["team"]["id"]
        home_id = home_info["team"]["id"]
        away_name = away_info["team"]["name"]
        home_name = home_info["team"]["name"]

        # Get model win probability from matchups logic
        away_proj = cache.get_team(away_id)
        home_proj = cache.get_team(home_id)

        if not away_proj or not home_proj:
            continue

        away_wpct = away_proj.get("win_pct", 0.5)
        home_wpct = home_proj.get("win_pct", 0.5)

        # Log5 base probability
        home_prob = (home_wpct * (1 - away_wpct)) / (home_wpct * (1 - away_wpct) + away_wpct * (1 - home_wpct)) if (home_wpct + away_wpct) > 0 else 0.5

        # Add home field advantage
        home_prob = min(0.95, max(0.05, home_prob + 0.035))
        away_prob = 1 - home_prob

        # Get probable pitchers for context
        away_sp_name = away_info.get("probablePitcher", {}).get("fullName", "TBD")
        home_sp_name = home_info.get("probablePitcher", {}).get("fullName", "TBD")

        # Simulate typical Vegas lines from our model probability
        # In reality you'd pull these from an odds API, but for now derive fair lines
        home_fair_ml = _moneyline_from_prob(home_prob)
        away_fair_ml = _moneyline_from_prob(away_prob)

        # Assume Vegas line is ~2% toward each side (vig)
        # Home EV if you could bet at fair odds = 0 (break even)
        # The edge comes when MODEL disagrees with VEGAS
        # For now, use season-level edge as proxy for daily edge
        home_season_diff = home_proj.get("projected_wins", 81) - (get_vegas_line(home_id) or 81)
        away_season_diff = away_proj.get("projected_wins", 81) - (get_vegas_line(away_id) or 81)

        # Daily edge: if model thinks team is better than Vegas, there's value
        home_edge = home_season_diff - away_season_diff
        edge_per_game = home_edge / 162  # normalize to per-game

        # Adjust probabilities by the per-game edge
        adjusted_home_prob = min(0.95, max(0.05, home_prob + edge_per_game * 0.5))
        adjusted_away_prob = 1 - adjusted_home_prob

        # EV calculation (assuming -110 standard line for both sides)
        home_ev = _expected_value(adjusted_home_prob, _decimal_from_moneyline(-110))
        away_ev = _expected_value(adjusted_away_prob, _decimal_from_moneyline(-110))

        # Kelly sizing
        home_kelly = _kelly_bet(adjusted_home_prob, _decimal_from_moneyline(-110))
        away_kelly = _kelly_bet(adjusted_away_prob, _decimal_from_moneyline(-110))

        # Determine the value side
        if home_ev > away_ev and home_ev > 0:
            value_side = "HOME"
            value_team = home_name
            value_ev = home_ev
            value_kelly = home_kelly
            value_prob = adjusted_home_prob
            value_ml = home_fair_ml
        elif away_ev > 0:
            value_side = "AWAY"
            value_team = away_name
            value_ev = away_ev
            value_kelly = away_kelly
            value_prob = adjusted_away_prob
            value_ml = away_fair_ml
        else:
            value_side = "PASS"
            value_team = ""
            value_ev = 0
            value_kelly = 0
            value_prob = 0
            value_ml = 0

        # Edge strength
        if value_ev > 5:
            edge_strength = "Strong"
        elif value_ev > 2:
            edge_strength = "Moderate"
        elif value_ev > 0:
            edge_strength = "Slight"
        else:
            edge_strength = "No edge"

        value_games.append({
            "away_team": away_name,
            "away_id": away_id,
            "home_team": home_name,
            "home_id": home_id,
            "away_sp": away_sp_name,
            "home_sp": home_sp_name,
            "model_home_prob": round(adjusted_home_prob, 3),
            "model_away_prob": round(adjusted_away_prob, 3),
            "model_home_ml": home_fair_ml,
            "model_away_ml": away_fair_ml,
            "value_side": value_side,
            "value_team": value_team,
            "ev_per_100": round(value_ev, 2),
            "kelly_pct": round(value_kelly * 100, 2),
            "edge_strength": edge_strength,
            "game_time": g.get("gameDate", ""),
            "status": g["status"]["detailedState"],
        })

    # Sort: best value first
    value_games.sort(key=lambda g: g["ev_per_100"], reverse=True)

    return {
        "date": today,
        "games": value_games,
        "total_games": len(value_games),
        "value_bets": sum(1 for g in value_games if g["value_side"] != "PASS"),
        "methodology": {
            "kelly_fraction": f"{KELLY_FRACTION * 100:.0f}% Kelly (conservative)",
            "assumed_odds": "-110 standard line",
            "ev_formula": "EV = (model_prob × profit) - (1 - model_prob) × stake",
            "disclaimer": "For entertainment/research only. Not gambling advice.",
        },
    }
