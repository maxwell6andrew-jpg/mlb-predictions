"""Marcel projection system for batters.

The Marcel method (Tom Tango) uses:
1. Weighted 3-year average (5/4/3 weights)
2. Regression toward league mean
3. Aging curve adjustment
4. Playing time projection

Enhanced with adaptive shrinkage for players with < 3 years MLB experience:
- Rate stats computed only from actual seasons (no zero-padding dilution)
- Regression constants scaled by experience years (James-Stein principle)
- Playing time floor for proven starters
"""

import pandas as pd
from app.data.lahman_loader import LahmanData
from app.config import PROJECTION_YEAR

# Regression constants — how much PA is needed before we trust the player's rate
# These are the BASE constants for 3+ year veterans
REGRESSION = {
    "avg": 1000,
    "obp": 900,
    "slg": 1000,
    "hr_rate": 800,
    "bb_rate": 800,
    "k_rate": 400,
    "sb_rate": 1200,
}

# Experience-based regression scaling (James-Stein adaptive shrinkage)
# Fewer MLB years → less regression needed because we removed zero-padding
# (zero-padding was providing implicit regression that is no longer present)
EXPERIENCE_REGRESSION_SCALE = {
    1: 0.70,   # 1 MLB year: 70% of base constant
    2: 0.85,   # 2 MLB years: 85% of base constant
}
# 3+ years: 100% (standard Marcel)

# Year weights: most recent = 5, -1 = 4, -2 = 3
WEIGHTS = [5, 4, 3]

# Stat-specific peak ages (research: Lichtman 2014, JC Bradbury 2010, Hicks/Judge 2020)
# Power peaks later (~28-29), speed earliest (~25-26), contact/OBP at 27
PEAK_AGES = {
    "hr_rate": 29,
    "slg": 28,
    "sb_rate": 25,
    "avg": 27,
    "obp": 27,
    "bb_rate": 28,  # plate discipline improves with experience
    "k_rate": 26,   # K rate improves early then plateaus
}
DEFAULT_PEAK = 27

# Position-specific decline rates: (gain_per_year_before_peak, loss_28-30, loss_31-33, loss_34+)
AGING = {
    "C":  (0.003, -0.008, -0.015, -0.022),
    "SS": (0.004, -0.006, -0.012, -0.018),
    "CF": (0.004, -0.006, -0.012, -0.020),
    "2B": (0.004, -0.005, -0.010, -0.016),
    "3B": (0.004, -0.005, -0.010, -0.016),
    "RF": (0.003, -0.005, -0.010, -0.016),
    "LF": (0.003, -0.005, -0.010, -0.016),
    "1B": (0.003, -0.004, -0.008, -0.014),
    "DH": (0.002, -0.004, -0.008, -0.014),
    "OF": (0.003, -0.005, -0.010, -0.016),
}
DEFAULT_AGING = (0.003, -0.005, -0.010, -0.016)

# Speed declines faster than power
SPEED_AGING = (0.005, -0.010, -0.018, -0.028)
POWER_AGING = (0.002, -0.003, -0.007, -0.012)
DISCIPLINE_AGING = (0.004, -0.003, -0.006, -0.010)  # walk rate holds longer


def aging_multiplier(age: int, position: str, stat: str = "avg") -> float:
    """Stat-specific aging curve with position modifiers."""
    peak = PEAK_AGES.get(stat, DEFAULT_PEAK)

    # Choose curve based on stat type
    if stat in ("sb_rate",):
        curve = SPEED_AGING
    elif stat in ("hr_rate", "slg"):
        curve = POWER_AGING
    elif stat in ("bb_rate",):
        curve = DISCIPLINE_AGING
    else:
        curve = AGING.get(position, DEFAULT_AGING)

    gain_pre, loss_28_30, loss_31_33, loss_34plus = curve

    if age <= peak:
        return 1.0 + gain_pre * (peak - age)

    mult = 1.0
    years_past_peak = age - peak
    # First 3 years post-peak
    y1 = min(years_past_peak, 3)
    mult += loss_28_30 * y1
    # Years 4-6 post-peak
    if years_past_peak > 3:
        y2 = min(years_past_peak - 3, 3)
        mult += loss_31_33 * y2
    # 7+ years post-peak
    if years_past_peak > 6:
        y3 = years_past_peak - 6
        mult += loss_34plus * y3

    return max(mult, 0.5)


def project_playing_time(pa_history: list[int], age: int, n_real_years: int = 3) -> int:
    """Project PA using weighted average of REAL seasons only.

    Key changes from vanilla Marcel:
    - Only uses actual MLB seasons (no zero-padding)
    - Regulars (500+ PA last year) get a 500 PA floor
    - Regulars regress toward 550, part-timers toward 400
    """
    if not pa_history:
        return 400

    # Only use real (non-zero) seasons for the weighted average
    real_pa = [(pa, WEIGHTS[i]) for i, pa in enumerate(pa_history) if pa > 0]
    if not real_pa:
        return 400

    weighted = sum(pa * w for pa, w in real_pa) / sum(w for _, w in real_pa)

    # Regulars regress toward 550; part-timers toward 400
    baseline = 550 if weighted >= 500 else 400

    # Less regression for players with fewer years (they don't need the extra penalty)
    if n_real_years >= 3:
        regress_pct = 0.20
    elif n_real_years == 2:
        regress_pct = 0.15
    else:
        regress_pct = 0.10  # 1-year players: 90% their actual PT, 10% baseline

    projected = weighted * (1 - regress_pct) + baseline * regress_pct

    if age > 33:
        projected *= max(0.5, 1.0 - 0.05 * (age - 33))

    # Floor: if most recent season was 500+ PA, project at least 500
    most_recent_pa = pa_history[0] if pa_history else 0
    if most_recent_pa >= 500:
        projected = max(projected, 500)

    return int(min(max(projected, 100), 700))


class MarcelBatting:
    def __init__(self, lahman: LahmanData):
        self.lahman = lahman
        self.league_avg = lahman.get_league_averages(PROJECTION_YEAR - 1)

    def project(self, lahman_id: str, projection_year: int = PROJECTION_YEAR) -> dict | None:
        """Run Marcel projection for a batter."""
        history = self.lahman.get_batting_history(lahman_id, projection_year, n_years=3)
        if history.empty:
            return None

        player_info = self.lahman.get_player_info(lahman_id)
        if not player_info:
            return None

        birth_year = player_info.get("birth_year")
        age = projection_year - birth_year if birth_year else 28
        position = self.lahman.get_primary_position(lahman_id)
        name = f"{player_info['name_first']} {player_info['name_last']}"

        # Step 1: Weighted averages (only uses real seasons — no zero dilution)
        rates = self._weighted_rates(history)
        if rates is None:
            return None

        # Build PA list from actual history
        if "BB" in history.columns:
            pa_list = []
            for _, row in history.iterrows():
                pa = row.get("AB", 0) + row.get("BB", 0) + row.get("HBP", 0) + row.get("SF", 0)
                pa_list.append(int(pa))
        else:
            pa_list = [int(x) for x in history["AB"].tolist()]

        # Count real MLB years (non-zero PA)
        n_real_years = sum(1 for pa in pa_list if pa > 0)

        # Compute weighted PA using ONLY real seasons (no zero-padding)
        real_pa_weighted = [(pa, WEIGHTS[i]) for i, pa in enumerate(pa_list) if pa > 0]
        if not real_pa_weighted:
            return None
        weighted_pa = sum(pa * w for pa, w in real_pa_weighted) / sum(w for _, w in real_pa_weighted) * n_real_years

        # Step 2: Regress toward league mean with experience-scaled constants
        reg_scale = EXPERIENCE_REGRESSION_SCALE.get(n_real_years, 1.0)
        regressed = {}
        for stat, reg_const in REGRESSION.items():
            scaled_const = reg_const * reg_scale
            reliability = weighted_pa / (weighted_pa + scaled_const)
            player_rate = rates.get(stat, self.league_avg.get(stat, 0))
            lg_rate = self.league_avg.get(stat, 0)
            regressed[stat] = player_rate * reliability + lg_rate * (1 - reliability)

        # Step 3: Stat-specific aging adjustment
        for stat in regressed:
            age_mult = aging_multiplier(age, position, stat)
            regressed[stat] *= age_mult

        # Step 4: Project playing time (experience-aware)
        projected_pa = project_playing_time(pa_list, age, n_real_years)

        # Convert rates to counting stats
        avg = regressed["avg"]
        obp = regressed["obp"]
        slg = regressed["slg"]
        hr = int(regressed["hr_rate"] * projected_pa)
        bb = int(regressed["bb_rate"] * projected_pa)
        so = int(regressed["k_rate"] * projected_pa)
        sb = int(regressed["sb_rate"] * projected_pa)
        ab = int(projected_pa * 0.89)  # ~89% of PA are AB
        hits = int(avg * ab)
        rbi = int(hr * 3.2 + (hits - hr) * 0.28)  # Rough RBI estimate
        runs = int(projected_pa * (obp * 0.5 + slg * 0.2))

        # WAR estimate (simplified)
        woba = obp * 0.7 + slg * 0.3  # Rough wOBA approximation
        lg_woba = self.league_avg["obp"] * 0.7 + self.league_avg["slg"] * 0.3
        batting_runs = (woba - lg_woba) / 1.15 * projected_pa
        replacement = 20 * (projected_pa / 600)
        war = round((batting_runs + replacement) / 10, 1)

        # Confidence based on sample size
        total_real_pa = sum(pa_list)
        confidence = min(total_real_pa / 1500, 1.0)

        return {
            "player_id": lahman_id,
            "name": name,
            "age": age,
            "position": position,
            "type": "batting",
            "mlb_years": n_real_years,
            "projected_pa": projected_pa,
            "avg": round(avg, 3),
            "obp": round(obp, 3),
            "slg": round(slg, 3),
            "ops": round(obp + slg, 3),
            "hr": hr,
            "rbi": rbi,
            "r": runs,
            "sb": sb,
            "bb": bb,
            "so": so,
            "war": war,
            "hr_rate": round(regressed["hr_rate"], 4),
            "bb_rate": round(regressed["bb_rate"], 4),
            "k_rate": round(regressed["k_rate"], 4),
            "confidence": round(confidence, 2),
        }

    def _weighted_rates(self, history: pd.DataFrame) -> dict | None:
        """Compute weighted rate stats from batting history.

        Only includes seasons with actual PA — zero-PA seasons are skipped,
        not counted. This prevents dilution of rate stats for young players.
        """
        total_weighted_pa = 0
        weighted_sums = {k: 0.0 for k in REGRESSION}

        for i, (_, row) in enumerate(history.iterrows()):
            if i >= 3:
                break
            weight = WEIGHTS[i]
            ab = row.get("AB", 0)
            bb = row.get("BB", 0)
            hbp = row.get("HBP", 0)
            sf = row.get("SF", 0)
            pa = ab + bb + hbp + sf

            if pa == 0:
                continue

            h = row.get("H", 0)
            doubles = row.get("2B", 0)
            triples = row.get("3B", 0)
            hr = row.get("HR", 0)
            sb_val = row.get("SB", 0)
            so = row.get("SO", 0)

            avg = h / ab if ab else 0
            obp_val = (h + bb + hbp) / (ab + bb + hbp + sf) if (ab + bb + hbp + sf) else 0
            tb = h + doubles + 2 * triples + 3 * hr
            slg = tb / ab if ab else 0

            rates = {
                "avg": avg,
                "obp": obp_val,
                "slg": slg,
                "hr_rate": hr / pa,
                "bb_rate": bb / pa,
                "k_rate": so / pa,
                "sb_rate": sb_val / pa,
            }

            for stat in REGRESSION:
                weighted_sums[stat] += rates[stat] * pa * weight
            total_weighted_pa += pa * weight

        if total_weighted_pa == 0:
            return None

        return {stat: weighted_sums[stat] / total_weighted_pa for stat in REGRESSION}
