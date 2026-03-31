"""
Daily matchup prediction engine.

For each scheduled game:
  - Pull starting pitcher projections (FIP-based)
  - Pull team offensive metrics (projected wOBA/OPS)
  - Pull bullpen ERA
  - Use log5 + linear adjustments to compute win probability
  - Return key factors driving the prediction
"""

from __future__ import annotations
import math
from typing import Optional


# Home field advantage: +0.035 in win probability (≈54% baseline for home team)
HOME_FIELD_ADV = 0.035

# Park-neutral baseline win probability for each team (can be overridden by team W%)
LEAGUE_WIN_PCT = 0.500


def _log5(p_a: float, p_b: float) -> float:
    """
    Log5 formula (Bill James): probability team A beats team B given
    each team's true talent win probability against a .500 opponent.
    """
    p_a = max(0.001, min(0.999, p_a))
    p_b = max(0.001, min(0.999, p_b))
    num = p_a * (1 - p_b)
    denom = p_a * (1 - p_b) + p_b * (1 - p_a)
    return num / denom if denom > 0 else 0.5


def _fip(hr: float, bb: float, k: float, ip: float, fip_constant: float = 3.10) -> float:
    """
    Fielding Independent Pitching.
    fip_constant calibrated so league-average FIP ≈ league-average ERA.
    """
    if ip <= 0:
        return fip_constant
    return (13 * hr + 3 * bb - 2 * k) / ip + fip_constant


def _fip_to_runs_saved(fip: float, lg_fip: float, innings: float = 5.5) -> float:
    """Convert FIP vs league average into run differential for this start."""
    era_diff = lg_fip - fip  # positive = pitcher is better than average
    runs_per_inning = era_diff / 9
    return runs_per_inning * innings


def _win_prob_from_run_diff(run_diff: float) -> float:
    """
    Convert expected run differential to win probability using a logistic curve.
    Empirically: +1 run advantage ≈ +11% win probability.
    """
    return 1 / (1 + math.exp(-0.37 * run_diff))


def predict_game(
    away_team_id: int,
    home_team_id: int,
    away_team_name: str,
    home_team_name: str,
    away_proj: Optional[dict],   # team projection dict from cache
    home_proj: Optional[dict],   # team projection dict from cache
    away_sp: Optional[dict],     # pitcher projection dict
    home_sp: Optional[dict],     # pitcher projection dict
    away_sp_name: str = "TBD",
    home_sp_name: str = "TBD",
    lg_era: float = 4.00,
    lg_fip: float = 4.00,
    park_factor: float = 1.0,
    home_sp_hand: str = "",
    away_sp_hand: str = "",
) -> dict:
    """
    Predict a single game. Returns win probability for home team + key factors.
    """
    factors = []

    # -----------------------------------------------------------------------
    # 1. Base win probability from team talent (projected W-L)
    # -----------------------------------------------------------------------
    away_win_pct = away_proj["win_pct"] if away_proj else LEAGUE_WIN_PCT
    home_win_pct = home_proj["win_pct"] if home_proj else LEAGUE_WIN_PCT

    base_prob = _log5(home_win_pct, away_win_pct)

    # -----------------------------------------------------------------------
    # 2. Home field advantage
    # -----------------------------------------------------------------------
    base_prob = min(0.99, base_prob + HOME_FIELD_ADV)

    # -----------------------------------------------------------------------
    # 3. Starting pitcher adjustment
    # -----------------------------------------------------------------------
    sp_run_diff = 0.0

    if away_sp and home_sp:
        away_fip = away_sp.get("fip", away_sp.get("era", lg_fip))
        home_fip = home_sp.get("fip", home_sp.get("era", lg_fip))
        away_ip = away_sp.get("projected_ip", 150)
        home_ip = home_sp.get("projected_ip", 150)
        per_start = 5.5  # expected innings per start

        # Runs saved in this start vs league average
        away_sp_runs = _fip_to_runs_saved(away_fip, lg_fip, per_start)
        home_sp_runs = _fip_to_runs_saved(home_fip, lg_fip, per_start)

        # From home team perspective: home SP saving runs helps home, away SP saving runs hurts home
        sp_run_diff = home_sp_runs - away_sp_runs

        fip_diff = round(away_fip - home_fip, 2)
        direction = "Home SP advantage" if fip_diff > 0.20 else ("Away SP advantage" if fip_diff < -0.20 else "Even SP matchup")
        factors.append({
            "factor": "SP FIP differential",
            "value": f"{'+' if fip_diff >= 0 else ''}{fip_diff} FIP",
            "direction": direction,
            "impact": "medium",
        })
    elif home_sp:
        home_fip = home_sp.get("fip", home_sp.get("era", lg_fip))
        home_sp_runs = _fip_to_runs_saved(home_fip, lg_fip)
        sp_run_diff = home_sp_runs
        factors.append({"factor": "SP FIP", "value": f"Home SP FIP {home_fip:.2f}", "direction": "Home SP advantage" if home_fip < lg_fip else "Home SP below avg", "impact": "medium"})
    elif away_sp:
        away_fip = away_sp.get("fip", away_sp.get("era", lg_fip))
        away_sp_runs = _fip_to_runs_saved(away_fip, lg_fip)
        sp_run_diff = -away_sp_runs
        factors.append({"factor": "SP FIP", "value": f"Away SP FIP {away_fip:.2f}", "direction": "Away SP advantage" if away_fip < lg_fip else "Away SP below avg", "impact": "medium"})
    else:
        factors.append({"factor": "SP matchup", "value": "Both TBD", "direction": "No SP data", "impact": "low"})

    # -----------------------------------------------------------------------
    # 4. Offensive matchup (projected OPS differential)
    # -----------------------------------------------------------------------
    ops_run_diff = 0.0
    if home_proj and away_proj:
        home_ops = _team_avg_ops(home_proj)
        away_ops = _team_avg_ops(away_proj)
        ops_diff = home_ops - away_ops
        # Rough conversion: .030 OPS difference ≈ 0.3 runs/game ≈ 0.5 run over a game
        ops_run_diff = ops_diff / 0.030 * 0.3
        if abs(ops_diff) > 0.015:
            direction = "Home offense advantage" if ops_diff > 0 else "Away offense advantage"
            factors.append({
                "factor": "Lineup wRC+ gap",
                "value": f"{'+'if ops_diff>=0 else ''}{ops_diff:.3f} OPS",
                "direction": direction,
                "impact": "high" if abs(ops_diff) > 0.040 else "medium",
            })

    # -----------------------------------------------------------------------
    # 5. Bullpen ERA differential
    # -----------------------------------------------------------------------
    bullpen_run_diff = 0.0
    if home_proj and away_proj:
        home_bp = _bullpen_era(home_proj)
        away_bp = _bullpen_era(away_proj)
        if home_bp and away_bp:
            # Bullpen pitches ~3.5 innings/game
            bp_innings = 3.5
            home_bp_runs = (lg_era - home_bp) / 9 * bp_innings
            away_bp_runs = (lg_era - away_bp) / 9 * bp_innings
            bullpen_run_diff = home_bp_runs - away_bp_runs
            bp_diff = round(away_bp - home_bp, 2)
            if abs(bp_diff) > 0.20:
                direction = "Home bullpen advantage" if bp_diff > 0 else "Away bullpen advantage"
                factors.append({
                    "factor": "Bullpen ERA",
                    "value": f"{'+'if bp_diff>=0 else ''}{bp_diff} ERA",
                    "direction": direction,
                    "impact": "medium",
                })

    # -----------------------------------------------------------------------
    # 6. Park factor adjustment
    # -----------------------------------------------------------------------
    park_run_adj = 0.0
    if park_factor != 1.0:
        # Park factor affects total run scoring — adjust run diff slightly
        # A hitter's park (1.10) adds ~0.3 runs to total; this slightly benefits the home team
        park_run_adj = (park_factor - 1.0) * 1.5  # ~0.15 runs per 0.10 park factor
        factors.append({
            "factor": "Park factor",
            "value": f"{park_factor:.2f}x run environment",
            "direction": "Hitter-friendly park" if park_factor > 1.05 else ("Pitcher-friendly park" if park_factor < 0.95 else "Neutral park"),
            "impact": "high" if abs(park_factor - 1.0) > 0.10 else ("medium" if abs(park_factor - 1.0) > 0.03 else "low"),
        })

    # -----------------------------------------------------------------------
    # 7. Platoon advantage
    # -----------------------------------------------------------------------
    platoon_run_adj = 0.0
    if (home_sp_hand or away_sp_hand) and home_proj and away_proj:
        from app.models.platoon_model import estimate_team_platoon_adjustment, describe_platoon_advantage

        # Home lineup vs away SP
        home_batters = home_proj.get("batters", [])
        away_batters = away_proj.get("batters", [])

        home_platoon = estimate_team_platoon_adjustment(home_batters, away_sp_hand) if away_sp_hand else 1.0
        away_platoon = estimate_team_platoon_adjustment(away_batters, home_sp_hand) if home_sp_hand else 1.0

        platoon_diff = home_platoon - away_platoon
        platoon_run_adj = platoon_diff * 1.5  # convert OPS multiplier diff to runs

        if abs(platoon_diff) > 0.01:
            desc = describe_platoon_advantage(home_batters, away_sp_hand) if away_sp_hand else ""
            factors.append({
                "factor": "Platoon splits",
                "value": f"Home lineup {home_platoon:.3f}x vs Away lineup {away_platoon:.3f}x",
                "direction": desc or ("Home platoon advantage" if platoon_diff > 0 else "Away platoon advantage"),
                "impact": "medium" if abs(platoon_diff) > 0.02 else "low",
            })

    # -----------------------------------------------------------------------
    # 8. Total run differential → win probability
    # -----------------------------------------------------------------------
    total_run_diff = sp_run_diff + ops_run_diff * 0.5 + bullpen_run_diff + park_run_adj + platoon_run_adj
    adjustment = _win_prob_from_run_diff(total_run_diff) - 0.5  # centered adjustment
    home_win_prob = max(0.05, min(0.95, base_prob + adjustment * 0.5))

    # Record factor contributions
    home_talent_factor = base_prob - 0.5
    if abs(home_talent_factor) > 0.02:
        factors.insert(0, {
            "factor": "Team talent",
            "value": f"{int(home_win_pct*162)}-{162 - int(home_win_pct*162)} vs {int(away_win_pct*162)}-{162 - int(away_win_pct*162)} projected",
            "direction": "Home talent advantage" if home_talent_factor > 0 else "Away talent advantage",
            "impact": "high" if abs(home_talent_factor) > 0.05 else "medium",
        })

    # Sort factors by impact
    impact_order = {"high": 0, "medium": 1, "low": 2}
    factors.sort(key=lambda f: impact_order.get(f.get("impact", "low"), 2))

    return {
        "game_id": f"{away_team_id}@{home_team_id}",
        "away_team_id": away_team_id,
        "away_team_name": away_team_name,
        "away_sp": away_sp_name,
        "away_fip": round(away_sp.get("fip", away_sp.get("era", lg_fip)), 2) if away_sp else None,
        "home_team_id": home_team_id,
        "home_team_name": home_team_name,
        "home_sp": home_sp_name,
        "home_fip": round(home_sp.get("fip", home_sp.get("era", lg_fip)), 2) if home_sp else None,
        "home_win_prob": round(home_win_prob, 3),
        "away_win_prob": round(1 - home_win_prob, 3),
        "predicted_winner": home_team_name if home_win_prob >= 0.5 else away_team_name,
        "confidence": _confidence_label(home_win_prob),
        "factors": factors[:4],  # top 4 factors
    }


def _team_avg_ops(team_proj: dict) -> float:
    """Compute average OPS of projected lineup (top 9 batters by PA)."""
    batters = [b for b in team_proj.get("batters", []) if b.get("ops") is not None]
    if not batters:
        return 0.720
    # Weight by projected PA proxy (war as proxy for playing time)
    top = sorted(batters, key=lambda b: b.get("war", 0), reverse=True)[:9]
    ops_vals = [b["ops"] for b in top if b.get("ops")]
    return sum(ops_vals) / len(ops_vals) if ops_vals else 0.720


def _bullpen_era(team_proj: dict) -> Optional[float]:
    """Compute average ERA for relievers."""
    relievers = [
        p for p in team_proj.get("pitchers", [])
        if p.get("position") == "RP" and p.get("era") is not None
    ]
    if not relievers:
        return None
    eras = [p["era"] for p in relievers if p.get("era")]
    return sum(eras) / len(eras) if eras else None


def _confidence_label(home_win_prob: float) -> str:
    diff = abs(home_win_prob - 0.5)
    if diff >= 0.15:
        return "Strong"
    elif diff >= 0.08:
        return "Moderate"
    else:
        return "Toss-up"
