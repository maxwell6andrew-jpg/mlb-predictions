"""Marcel projection system for pitchers.

Same algorithm as batting but uses BFP (batters faced) for weighting
and pitching-specific stats.
"""

import pandas as pd
from app.data.lahman_loader import LahmanData
from app.config import PROJECTION_YEAR

REGRESSION = {
    "era": 1000,
    "whip": 900,
    "k_per_9": 500,
    "bb_per_9": 700,
    "hr_per_9": 800,
}

WEIGHTS = [5, 4, 3]
PEAK_AGE = 27

AGING = {
    "SP": (0.003, -0.005, -0.010, -0.018),
    "RP": (0.002, -0.004, -0.008, -0.015),
}
DEFAULT_AGING = (0.003, -0.005, -0.010, -0.016)


def aging_multiplier(age: int, role: str) -> float:
    """For pitchers, higher = worse for ERA/WHIP, so we invert the effect."""
    curve = AGING.get(role, DEFAULT_AGING)
    gain_pre, loss_28_30, loss_31_33, loss_34plus = curve

    if age <= PEAK_AGE:
        return 1.0 - gain_pre * (PEAK_AGE - age)  # Younger = slightly worse (developing)

    mult = 1.0
    if age > PEAK_AGE:
        years_28_30 = min(age, 30) - PEAK_AGE
        mult += abs(loss_28_30) * years_28_30  # ERA goes up
    if age > 30:
        years_31_33 = min(age, 33) - 30
        mult += abs(loss_31_33) * years_31_33
    if age > 33:
        years_34plus = age - 33
        mult += abs(loss_34plus) * years_34plus

    return min(mult, 1.8)


def aging_multiplier_positive(age: int, role: str) -> float:
    """For stats where higher is better (K/9)."""
    curve = AGING.get(role, DEFAULT_AGING)
    gain_pre, loss_28_30, loss_31_33, loss_34plus = curve

    if age <= PEAK_AGE:
        return 1.0 + gain_pre * (PEAK_AGE - age)

    mult = 1.0
    if age > PEAK_AGE:
        mult += loss_28_30 * min(age, 30) - PEAK_AGE if age > PEAK_AGE else 0
    # Simplified: K/9 drops less than other stats
    years_past = age - PEAK_AGE
    mult = 1.0 - 0.003 * years_past
    return max(mult, 0.6)


def project_playing_time(ip_history: list[float], age: int, is_starter: bool) -> float:
    while len(ip_history) < 3:
        ip_history.append(0)

    weighted = sum(ip * w for ip, w in zip(ip_history, WEIGHTS)) / sum(WEIGHTS)
    baseline = 150.0 if is_starter else 55.0
    projected = weighted * 0.8 + baseline * 0.2

    if age > 33:
        projected *= max(0.5, 1.0 - 0.05 * (age - 33))

    max_ip = 220.0 if is_starter else 80.0
    return min(max(projected, 20), max_ip)


class MarcelPitching:
    def __init__(self, lahman: LahmanData):
        self.lahman = lahman
        self.league_avg = lahman.get_league_averages(PROJECTION_YEAR - 1)

    def project(self, lahman_id: str, projection_year: int = PROJECTION_YEAR) -> dict | None:
        history = self.lahman.get_pitching_history(lahman_id, projection_year, n_years=3)
        if history.empty:
            return None

        player_info = self.lahman.get_player_info(lahman_id)
        if not player_info:
            return None

        birth_year = player_info.get("birth_year")
        age = projection_year - birth_year if birth_year else 28
        name = f"{player_info['name_first']} {player_info['name_last']}"

        # Determine if starter or reliever
        total_gs = history["GS"].sum() if "GS" in history.columns else 0
        total_g = history["G"].sum() if "G" in history.columns else 1
        is_starter = total_gs / max(total_g, 1) > 0.5
        role = "SP" if is_starter else "RP"

        # Step 1: Weighted averages
        rates = self._weighted_rates(history)
        if rates is None:
            return None

        # Get IP history for playing time
        ip_list = []
        for _, row in history.iterrows():
            ipouts = row.get("IPouts", 0)
            ip_list.append(ipouts / 3)

        # Compute PA-weighted BFP for regression denominator
        bfp_list = []
        for _, row in history.iterrows():
            bfp = row.get("BFP", 0)
            if bfp == 0:
                ipouts = row.get("IPouts", 0)
                bfp = int(ipouts / 3 * 4.3)
            bfp_list.append(bfp)

        n = len(bfp_list)
        w = WEIGHTS[:n]
        weighted_bfp = sum(b * wt for b, wt in zip(bfp_list, w)) / sum(w) * n if n > 0 else 0

        # Step 2: Regress toward league mean
        regressed = {}
        for stat, reg_const in REGRESSION.items():
            reliability = weighted_bfp / (weighted_bfp + reg_const)
            player_rate = rates.get(stat, self.league_avg.get(stat, 0))
            lg_rate = self.league_avg.get(stat, 0)
            regressed[stat] = player_rate * reliability + lg_rate * (1 - reliability)

        # Step 3: Aging
        era_mult = aging_multiplier(age, role)
        regressed["era"] *= era_mult
        regressed["whip"] *= era_mult
        regressed["bb_per_9"] *= era_mult
        regressed["hr_per_9"] *= era_mult
        regressed["k_per_9"] *= aging_multiplier_positive(age, role)

        # Step 4: Playing time
        projected_ip = project_playing_time(ip_list, age, is_starter)

        # Convert to counting stats
        era = regressed["era"]
        whip = regressed["whip"]
        k_per_9 = regressed["k_per_9"]
        bb_per_9 = regressed["bb_per_9"]
        hr_per_9 = regressed["hr_per_9"]

        so = int(k_per_9 / 9 * projected_ip)
        bb = int(bb_per_9 / 9 * projected_ip)
        hr_allowed = int(hr_per_9 / 9 * projected_ip)

        # Wins estimate (rough)
        w = int(projected_ip / 9 * 0.55) if is_starter else int(projected_ip / 20)
        l = int(projected_ip / 9 * 0.45) if is_starter else int(projected_ip / 30)
        sv = 0 if is_starter else int(projected_ip / 3)

        # WAR via FIP
        # FIP = (13*HR + 3*BB - 2*K) / IP + cFIP
        # cFIP is computed from LEAGUE totals so it doesn't cancel out
        lg_era = self.league_avg.get("era", 4.0)
        lg_hr9 = self.league_avg.get("hr_per_9", 1.2)
        lg_bb9 = self.league_avg.get("bb_per_9", 3.2)
        lg_k9 = self.league_avg.get("k_per_9", 8.5)
        cfip = lg_era - (13 * lg_hr9 / 9 + 3 * lg_bb9 / 9 - 2 * lg_k9 / 9)

        player_fip_component = (13 * hr_allowed + 3 * bb - 2 * so) / max(projected_ip, 1)
        fip = player_fip_component + cfip

        # WAR = (lg_FIP - player_FIP) / runs_per_win * (IP/9) + replacement_level
        replacement_level = 0.3 * (projected_ip / (180 if is_starter else 60))
        war = round((lg_era - fip) / 10 * (projected_ip / 9) + replacement_level, 1)

        confidence = min(weighted_bfp / 1500, 1.0)

        return {
            "player_id": lahman_id,
            "name": name,
            "age": age,
            "position": role,
            "type": "pitching",
            "projected_ip": round(projected_ip, 1),
            "era": round(era, 2),
            "whip": round(whip, 2),
            "k_per_9": round(k_per_9, 1),
            "bb_per_9": round(bb_per_9, 1),
            "hr_per_9": round(hr_per_9, 1),
            "w": w,
            "l": l,
            "sv": sv,
            "so": so,
            "bb": bb,
            "war": war,
            "confidence": round(confidence, 2),
        }

    def _weighted_rates(self, history: pd.DataFrame) -> dict | None:
        total_weighted_bfp = 0
        weighted_sums = {k: 0.0 for k in REGRESSION}

        for i, (_, row) in enumerate(history.iterrows()):
            if i >= 3:
                break
            weight = WEIGHTS[i]
            ipouts = row.get("IPouts", 0)
            ip = ipouts / 3
            if ip == 0:
                continue

            bfp = row.get("BFP", int(ip * 4.3))
            if bfp == 0:
                bfp = int(ip * 4.3)

            er = row.get("ER", 0)
            h = row.get("H", 0)
            bb = row.get("BB", 0)
            so = row.get("SO", 0)
            hr = row.get("HR", 0)

            rates = {
                "era": er / ip * 9 if ip else 4.50,
                "whip": (h + bb) / ip if ip else 1.30,
                "k_per_9": so / ip * 9 if ip else 8.0,
                "bb_per_9": bb / ip * 9 if ip else 3.0,
                "hr_per_9": hr / ip * 9 if ip else 1.2,
            }

            for stat in REGRESSION:
                weighted_sums[stat] += rates[stat] * bfp * weight
            total_weighted_bfp += bfp * weight

        if total_weighted_bfp == 0:
            return None

        return {stat: weighted_sums[stat] / total_weighted_bfp for stat in REGRESSION}
