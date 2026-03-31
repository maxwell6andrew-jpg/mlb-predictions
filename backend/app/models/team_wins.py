"""Team win total projections.

Blends three components:
- 40% Pythagorean expectation (from run differential)
- 35% Roster WAR aggregation
- 25% Historical regression toward 81 wins
"""

from app.config import REPLACEMENT_WINS


def pythagorean_wins(runs_scored: int, runs_allowed: int, games: int = 162) -> int:
    """Pythagenpat formula with exponent 1.83."""
    if runs_scored == 0 and runs_allowed == 0:
        return 81
    exp = 1.83
    rs = max(runs_scored, 1)
    ra = max(runs_allowed, 1)
    win_pct = rs ** exp / (rs ** exp + ra ** exp)
    return round(win_pct * games)


def roster_war_wins(total_war: float) -> int:
    """Convert total roster WAR to projected wins."""
    return round(total_war + REPLACEMENT_WINS)


def regressed_wins(actual_wins: int) -> int:
    """Regress actual wins 40% toward 81."""
    return round(actual_wins * 0.6 + 81 * 0.4)


def project_team_wins(
    runs_scored: int,
    runs_allowed: int,
    total_roster_war: float,
    last_season_wins: int,
) -> dict:
    """Compute blended team win projection."""
    pyth = pythagorean_wins(runs_scored, runs_allowed)
    roster = roster_war_wins(total_roster_war)
    reg = regressed_wins(last_season_wins)

    projected = round(0.40 * pyth + 0.35 * roster + 0.25 * reg)
    projected = max(40, min(projected, 120))
    losses = 162 - projected

    return {
        "projected_wins": projected,
        "projected_losses": losses,
        "win_pct": round(projected / 162, 3),
        "pythagorean_wins": pyth,
        "roster_war_wins": roster,
        "regressed_wins": reg,
        "projected_rs": runs_scored,
        "projected_ra": runs_allowed,
        "total_war": round(total_roster_war, 1),
    }
