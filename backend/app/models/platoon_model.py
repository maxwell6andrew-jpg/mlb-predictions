"""Platoon split adjustments for game-level predictions.

Applies batter-vs-pitcher handedness adjustments to team offensive
projections when the opposing starter's handedness is known.

Baseline platoon splits from historical MLB data (2015-2025):
  - LHB vs LHP: ~8% OPS penalty (same-side disadvantage)
  - RHB vs LHP: ~5% OPS bonus (opposite-side advantage)
  - LHB vs RHP: baseline (slight advantage)
  - RHB vs RHP: baseline

When player-specific split data is available with sufficient sample
(≥100 PA), we blend toward the player's actual splits.
"""

# OPS multipliers relative to a neutral at-bat
PLATOON_SPLITS = {
    ("L", "L"): 0.92,   # LHB vs LHP: 8% OPS penalty
    ("L", "R"): 1.02,   # LHB vs RHP: slight advantage
    ("R", "L"): 1.05,   # RHB vs LHP: 5% OPS bonus
    ("R", "R"): 0.99,   # RHB vs RHP: slight disadvantage
    ("S", "L"): 1.04,   # Switch vs LHP: bats right = advantage
    ("S", "R"): 1.01,   # Switch vs RHP: bats left = slight advantage
}

# Minimum PA before trusting player-specific splits over generic
MIN_PA_FOR_SPLITS = 100


def get_platoon_multiplier(
    batter_hand: str,
    pitcher_hand: str,
    player_splits: dict | None = None,
) -> float:
    """
    Get the OPS multiplier for a batter-pitcher handedness matchup.

    Args:
        batter_hand: "L", "R", or "S" (switch)
        pitcher_hand: "L" or "R"
        player_splits: Optional dict with player-specific split data
                      {"vs_L": {"ops": 0.750, "pa": 150}, "vs_R": {"ops": 0.850, "pa": 300}}

    Returns:
        OPS multiplier (1.0 = neutral)
    """
    # Normalize inputs
    bh = batter_hand.upper()[:1] if batter_hand else "R"
    ph = pitcher_hand.upper()[:1] if pitcher_hand else "R"

    generic = PLATOON_SPLITS.get((bh, ph), 1.0)

    # If we have player-specific split data with enough PA, blend
    if player_splits:
        split_key = f"vs_{ph}"
        split_data = player_splits.get(split_key)
        if split_data and split_data.get("pa", 0) >= MIN_PA_FOR_SPLITS:
            player_ops = split_data.get("ops", 0)
            overall_ops = player_splits.get("overall_ops", 0)
            if player_ops > 0 and overall_ops > 0:
                player_ratio = player_ops / overall_ops
                # Blend: 60% player-specific, 40% generic (regress toward generic)
                pa = split_data["pa"]
                blend = min(pa / 500, 0.6)  # max 60% weight on player splits
                return generic * (1 - blend) + player_ratio * blend

    return generic


def estimate_team_platoon_adjustment(
    team_batters: list[dict],
    pitcher_hand: str,
) -> float:
    """
    Estimate the aggregate platoon adjustment for a team's lineup
    against a pitcher of a given handedness.

    Args:
        team_batters: List of batter dicts with "bats" key (L/R/S)
        pitcher_hand: "L" or "R"

    Returns:
        Aggregate OPS multiplier for the team
    """
    if not team_batters or not pitcher_hand:
        return 1.0

    total_weight = 0
    weighted_mult = 0

    for batter in team_batters:
        bats = batter.get("bats", "R")
        war = max(batter.get("war", 0), 0.1)  # weight by projected value

        mult = get_platoon_multiplier(bats, pitcher_hand)
        weighted_mult += mult * war
        total_weight += war

    if total_weight == 0:
        return 1.0

    return weighted_mult / total_weight


def describe_platoon_advantage(
    team_batters: list[dict],
    pitcher_hand: str,
) -> str:
    """Generate a human-readable description of the platoon matchup."""
    if not team_batters or not pitcher_hand:
        return ""

    hand_counts = {"L": 0, "R": 0, "S": 0}
    for b in team_batters:
        h = b.get("bats", "R").upper()[:1]
        hand_counts[h] = hand_counts.get(h, 0) + 1

    total = sum(hand_counts.values())
    if total == 0:
        return ""

    ph = "LHP" if pitcher_hand.upper().startswith("L") else "RHP"

    if pitcher_hand.upper().startswith("L"):
        # vs LHP: RHB and switch hitters have advantage
        adv = hand_counts.get("R", 0) + hand_counts.get("S", 0)
        disadv = hand_counts.get("L", 0)
    else:
        # vs RHP: LHB and switch hitters have slight advantage
        adv = hand_counts.get("L", 0) + hand_counts.get("S", 0)
        disadv = hand_counts.get("R", 0)

    if adv > disadv * 1.5:
        return f"Strong platoon advantage vs {ph} ({adv}/{total} favorable matchups)"
    elif disadv > adv * 1.5:
        return f"Platoon disadvantage vs {ph} ({disadv}/{total} same-side matchups)"
    else:
        return f"Neutral platoon vs {ph}"
