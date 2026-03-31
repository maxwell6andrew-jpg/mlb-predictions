"""Bayesian in-season updating for team win projections.

Blends preseason projection (prior) with observed in-season performance
(likelihood), weighted by sample size. Early in the season, the prior
dominates; by mid-season, observed performance carries more weight.

Based on the approach described in:
- Tango et al. "The Book" (2006): regression to mean ≈ 1/(1 + n/k)
- Bill James' log5 method for adjusting team strength estimates
- Bayesian beta-binomial model for win probability

Key insight: a team's "true talent" win rate is uncertain. The preseason
projection gives us a prior estimate. Each game played reduces that
uncertainty. The optimal blend weight depends on the ratio of games
played to the "reliability constant" k ≈ 69 games (where in-season
and preseason carry equal weight).
"""

# Reliability constant: number of games at which in-season record
# carries equal weight to the preseason projection.
# Derived from historical team win% variance analysis:
#   - True talent SD ≈ 0.060 (Tango)
#   - Single game SD ≈ 0.500
#   - k = (0.500)^2 / (0.060)^2 ≈ 69
RELIABILITY_K = 69


def blend_projection(
    preseason_wins: float,
    current_wins: int,
    current_losses: int,
    current_rs: int = 0,
    current_ra: int = 0,
) -> dict:
    """
    Blend preseason win projection with in-season observed performance.

    Returns updated projection with confidence interval and blend weights.
    """
    games_played = current_wins + current_losses

    if games_played < 5:
        # Not enough data to update — return preseason projection
        return {
            "projected_wins": round(preseason_wins),
            "projected_losses": 162 - round(preseason_wins),
            "win_pct": round(preseason_wins / 162, 3),
            "blend_weight_preseason": 1.0,
            "blend_weight_inseason": 0.0,
            "games_used": 0,
            "method": "preseason_only",
        }

    # In-season observed win rate
    observed_pct = current_wins / games_played

    # Pythagorean from in-season RS/RA (better signal than raw W-L)
    if current_rs > 0 and current_ra > 0:
        rs_pg = current_rs / games_played
        ra_pg = current_ra / games_played
        rs162 = rs_pg * 162
        ra162 = ra_pg * 162
        pyth_pct = rs162 ** 1.83 / (rs162 ** 1.83 + ra162 ** 1.83)
        # Blend observed W% and Pythagorean (Pythagorean is less noisy)
        inseason_pct = 0.6 * pyth_pct + 0.4 * observed_pct
    else:
        inseason_pct = observed_pct

    # Bayesian blend: weight = games / (games + k)
    inseason_weight = games_played / (games_played + RELIABILITY_K)
    preseason_weight = 1.0 - inseason_weight

    preseason_pct = preseason_wins / 162

    # Blended win rate
    blended_pct = preseason_pct * preseason_weight + inseason_pct * inseason_weight

    # Project remaining games at blended rate
    remaining = 162 - games_played
    projected_remaining_wins = blended_pct * remaining
    total_projected_wins = current_wins + projected_remaining_wins

    # Confidence interval narrows as more games are played
    # SD of remaining wins ≈ sqrt(remaining * p * (1-p))
    sd_remaining = (remaining * blended_pct * (1 - blended_pct)) ** 0.5
    ci_half = 1.645 * sd_remaining  # 90% CI

    projected_wins = round(total_projected_wins)
    projected_wins = max(40, min(projected_wins, 120))

    return {
        "projected_wins": projected_wins,
        "projected_losses": 162 - projected_wins,
        "win_pct": round(projected_wins / 162, 3),
        "blend_weight_preseason": round(preseason_weight, 3),
        "blend_weight_inseason": round(inseason_weight, 3),
        "blended_pct": round(blended_pct, 4),
        "preseason_pct": round(preseason_pct, 4),
        "inseason_pct": round(inseason_pct, 4),
        "games_used": games_played,
        "remaining_games": remaining,
        "ci_low": max(40, round(total_projected_wins - ci_half)),
        "ci_high": min(120, round(total_projected_wins + ci_half)),
        "method": "bayesian_blend",
    }
