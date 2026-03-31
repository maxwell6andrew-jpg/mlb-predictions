"""Statcast-based adjustment layer for Marcel projections.

Applied AFTER Marcel projections are computed. Blends Statcast expected
stats (xwOBA, xSLG, barrel rate, exit velo) with Marcel rate projections
to correct for luck and quality-of-contact signals Marcel cannot see.

If no Statcast data is available for a player, the Marcel projection
passes through unchanged (graceful degradation).
"""

from app.data.park_factors import get_park_factor

# How much weight to give Statcast vs Marcel (0 = pure Marcel, 1 = pure Statcast)
# Research (Carleton 2019, Sullivan 2021) shows 30-40% optimal for full-season Statcast
BLEND_WEIGHT = 0.35

# League average Statcast benchmarks (2023-2025)
LG_BARREL_RATE = 7.5   # percent
LG_EXIT_VELO = 88.5    # mph
LG_XWOBA = 0.310
LG_XSLG = 0.390
LG_XBA = 0.248
LG_HARD_HIT = 35.0     # percent


def adjust_batting_projection(
    marcel: dict,
    statcast: dict | None,
    team_id: int | None = None,
) -> dict:
    """
    Adjust a Marcel batting projection using Statcast data and park factors.

    Returns a new dict with adjusted stats plus metadata about what changed.
    Original Marcel projection is never mutated.
    """
    proj = dict(marcel)
    adjustments = {}

    # --- Park factor adjustment ---
    if team_id:
        hr_pf = get_park_factor(team_id, "hr")
        runs_pf = get_park_factor(team_id, "runs")

        if hr_pf != 1.0:
            # Adjust HR rate: half-season home, half away (neutral)
            effective_pf = (hr_pf + 1.0) / 2  # ~50% home games
            old_hr = proj["hr"]
            proj["hr"] = int(proj["hr"] * effective_pf)
            proj["hr_rate"] = round(proj["hr"] / max(proj["projected_pa"], 1), 4)
            if proj["hr"] != old_hr:
                adjustments["park_hr"] = f"{old_hr} → {proj['hr']} (park factor {hr_pf:.2f})"

        # Adjust run-dependent stats
        if runs_pf != 1.0:
            effective_runs_pf = (runs_pf + 1.0) / 2
            old_rbi = proj.get("rbi", 0)
            proj["rbi"] = int(proj.get("rbi", 0) * effective_runs_pf)
            proj["r"] = int(proj.get("r", 0) * effective_runs_pf)

        proj["park_factor"] = hr_pf
        proj["park_adjusted"] = True
    else:
        proj["park_adjusted"] = False

    # --- Statcast adjustment ---
    if not statcast or statcast.get("pa", 0) < 100:
        proj["statcast_adjusted"] = False
        proj["statcast_data"] = None
        proj["adjustments"] = adjustments
        return proj

    # 1. xwOBA luck correction
    xwoba = statcast.get("xwoba", 0)
    actual_woba = statcast.get("actual_woba", 0)
    if xwoba > 0 and actual_woba > 0:
        luck_gap = xwoba - actual_woba  # positive = unlucky (xwOBA > actual)

        # Adjust OBP and SLG toward expected values
        if abs(luck_gap) > 0.010:  # only adjust if gap is meaningful
            obp_adj = luck_gap * BLEND_WEIGHT * 0.8  # OBP is ~80% of wOBA signal
            slg_adj = luck_gap * BLEND_WEIGHT * 1.2  # SLG captures more of the power component

            old_obp = proj["obp"]
            old_slg = proj["slg"]
            proj["obp"] = round(proj["obp"] + obp_adj, 3)
            proj["slg"] = round(proj["slg"] + slg_adj, 3)
            proj["ops"] = round(proj["obp"] + proj["slg"], 3)
            proj["avg"] = round(proj["avg"] + luck_gap * BLEND_WEIGHT * 0.5, 3)

            adjustments["xwoba_luck"] = f"gap={luck_gap:+.3f}, OBP {old_obp}→{proj['obp']}, SLG {old_slg}→{proj['slg']}"

    # 2. Barrel rate → HR adjustment
    barrel_rate = statcast.get("barrel_rate", 0)
    if barrel_rate > 0:
        barrel_diff = barrel_rate - LG_BARREL_RATE  # positive = above average barrels
        # Each 1% above average barrel rate ≈ 2% more HR
        hr_multiplier = 1.0 + (barrel_diff / LG_BARREL_RATE) * 0.15 * BLEND_WEIGHT
        hr_multiplier = max(0.80, min(hr_multiplier, 1.20))  # cap at ±20%

        old_hr = proj["hr"]
        proj["hr"] = max(0, int(proj["hr"] * hr_multiplier))
        proj["hr_rate"] = round(proj["hr"] / max(proj["projected_pa"], 1), 4)
        if proj["hr"] != old_hr:
            adjustments["barrel_hr"] = f"barrel={barrel_rate:.1f}% (lg avg {LG_BARREL_RATE}%), HR {old_hr}→{proj['hr']}"

    # 3. Exit velocity → power quality signal
    exit_velo = statcast.get("exit_velo", 0)
    if exit_velo > 0:
        ev_diff = exit_velo - LG_EXIT_VELO
        # High exit velo with low SLG = unlucky/due for correction
        if ev_diff > 2.0 and proj["slg"] < 0.430:
            slg_boost = ev_diff * 0.002 * BLEND_WEIGHT
            proj["slg"] = round(proj["slg"] + slg_boost, 3)
            proj["ops"] = round(proj["obp"] + proj["slg"], 3)
            adjustments["exit_velo"] = f"{exit_velo:.1f} mph (+{ev_diff:.1f} vs lg), SLG boosted"

    # Recalculate WAR after adjustments
    lg_obp = 0.315
    lg_slg = 0.400
    woba = proj["obp"] * 0.7 + proj["slg"] * 0.3
    lg_woba = lg_obp * 0.7 + lg_slg * 0.3
    batting_runs = (woba - lg_woba) / 1.15 * proj["projected_pa"]
    replacement = 20 * (proj["projected_pa"] / 600)
    proj["war"] = round((batting_runs + replacement) / 10, 1)

    # Attach Statcast data for display
    proj["statcast_adjusted"] = True
    proj["statcast_data"] = {
        "barrel_rate": barrel_rate,
        "exit_velo": exit_velo,
        "xwoba": xwoba,
        "xslg": statcast.get("xslg", 0),
        "xba": statcast.get("xba", 0),
        "hard_hit_rate": statcast.get("hard_hit_rate", 0),
        "xwoba_minus_woba": round(xwoba - actual_woba, 3) if xwoba and actual_woba else 0,
    }
    proj["adjustments"] = adjustments

    return proj


def adjust_pitching_projection(
    marcel: dict,
    statcast: dict | None,
    team_id: int | None = None,
) -> dict:
    """
    Adjust a Marcel pitching projection using Statcast data and park factors.
    """
    proj = dict(marcel)
    adjustments = {}

    # --- Park factor adjustment ---
    if team_id:
        runs_pf = get_park_factor(team_id, "runs")
        hr_pf = get_park_factor(team_id, "hr")

        if runs_pf != 1.0:
            effective_pf = (runs_pf + 1.0) / 2  # half home games
            old_era = proj["era"]
            proj["era"] = round(proj["era"] * effective_pf, 2)
            proj["whip"] = round(proj["whip"] * ((effective_pf + 1.0) / 2), 2)  # WHIP less affected
            if abs(proj["era"] - old_era) > 0.05:
                adjustments["park_era"] = f"{old_era} → {proj['era']} (park factor {runs_pf:.2f})"

        if hr_pf != 1.0:
            effective_hr_pf = (hr_pf + 1.0) / 2
            old_hr9 = proj["hr_per_9"]
            proj["hr_per_9"] = round(proj["hr_per_9"] * effective_hr_pf, 1)
            if proj["hr_per_9"] != old_hr9:
                adjustments["park_hr9"] = f"{old_hr9} → {proj['hr_per_9']}"

        proj["park_factor"] = runs_pf
        proj["park_adjusted"] = True
    else:
        proj["park_adjusted"] = False

    # --- Statcast adjustment ---
    if not statcast:
        proj["statcast_adjusted"] = False
        proj["statcast_data"] = None
        proj["adjustments"] = adjustments
        return proj

    # 1. xERA correction
    xera = statcast.get("xera", 0)
    actual_era = statcast.get("actual_era", 0)
    if xera > 0 and actual_era > 0:
        # Blend Marcel ERA toward xERA
        era_gap = proj["era"] - xera  # positive = Marcel thinks worse than xERA suggests
        if abs(era_gap) > 0.15:  # meaningful gap
            old_era = proj["era"]
            proj["era"] = round(proj["era"] - era_gap * BLEND_WEIGHT, 2)
            adjustments["xera"] = f"xERA={xera:.2f}, Marcel ERA {old_era}→{proj['era']}"

    # 2. Barrel rate against → HR/9 correction
    barrel_against = statcast.get("barrel_rate_against", 0)
    if barrel_against > 0:
        barrel_diff = barrel_against - LG_BARREL_RATE
        # High barrel rate against = HR/9 should be higher
        hr9_adj = barrel_diff * 0.02 * BLEND_WEIGHT
        old_hr9 = proj["hr_per_9"]
        proj["hr_per_9"] = round(max(0.5, proj["hr_per_9"] + hr9_adj), 1)
        if proj["hr_per_9"] != old_hr9:
            adjustments["barrel_hr9"] = f"barrel against={barrel_against:.1f}%, HR/9 {old_hr9}→{proj['hr_per_9']}"

    # 3. xwOBA against → overall quality signal
    xwoba_against = statcast.get("xwoba", 0)
    actual_woba_against = statcast.get("actual_woba", 0)
    if xwoba_against > 0 and actual_woba_against > 0:
        luck_gap = xwoba_against - actual_woba_against
        # Positive = opponents were unlucky against this pitcher (pitcher overperformed)
        # → pitcher's ERA should regress upward
        if abs(luck_gap) > 0.010:
            era_luck_adj = luck_gap * 2.0 * BLEND_WEIGHT  # wOBA gap translates to ~2x ERA impact
            old_era = proj["era"]
            proj["era"] = round(proj["era"] + era_luck_adj, 2)
            adjustments["woba_luck"] = f"xwOBA vs actual gap={luck_gap:+.3f}, ERA {old_era}→{proj['era']}"

    # Recalculate WAR
    ip = proj["projected_ip"]
    so = int(proj["k_per_9"] / 9 * ip)
    bb = int(proj["bb_per_9"] / 9 * ip)
    hr_allowed = int(proj["hr_per_9"] / 9 * ip)
    lg_era = 4.16
    lg_hr9 = 1.18
    lg_bb9 = 3.21
    lg_k9 = 8.49
    cfip = lg_era - (13 * lg_hr9 / 9 + 3 * lg_bb9 / 9 - 2 * lg_k9 / 9)
    fip = (13 * hr_allowed + 3 * bb - 2 * so) / max(ip, 1) + cfip
    is_starter = proj.get("position", "SP") == "SP"
    replacement = 0.3 * (ip / (180 if is_starter else 60))
    proj["war"] = round((lg_era - fip) / 10 * (ip / 9) + replacement, 1)

    proj["statcast_adjusted"] = True
    proj["statcast_data"] = {
        "xera": xera,
        "xwoba_against": xwoba_against,
        "barrel_rate_against": barrel_against,
        "exit_velo_against": statcast.get("exit_velo_against", 0),
        "hard_hit_rate_against": statcast.get("hard_hit_rate_against", 0),
    }
    proj["adjustments"] = adjustments

    return proj
