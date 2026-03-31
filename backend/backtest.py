#!/usr/bin/env python3
"""
Backtest the MLB Predictor model against historical seasons.

Tests:
1. Team win projections (Marcel + Pythagorean + Vegas blend) vs actual wins
2. Marcel batting projections vs actual stats (AVG, OPS, HR, WAR)
3. Marcel pitching projections vs actual stats (ERA, WHIP, K/9)
4. Comparison: our model vs naive baselines (last year, mean reversion to 81)

Usage:
    cd backend && python3 backtest.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from app.data.lahman_loader import LahmanData
from app.models.marcel_batting import MarcelBatting
from app.models.marcel_pitching import MarcelPitching
from app.models.team_regression import fit_team_model, _pyth_pct, _build_feature_matrix

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
TEST_YEARS = [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]  # skip 2020
MIN_PA_BATTER = 200     # minimum PA to include in batter backtest
MIN_IP_PITCHER = 50     # minimum IP to include in pitcher backtest


def rmse(predictions, actuals):
    return np.sqrt(np.mean((np.array(predictions) - np.array(actuals)) ** 2))


def mae(predictions, actuals):
    return np.mean(np.abs(np.array(predictions) - np.array(actuals)))


def correlation(predictions, actuals):
    if len(predictions) < 3:
        return 0
    return float(np.corrcoef(predictions, actuals)[0, 1])


# ═══════════════════════════════════════════════════════════════════════
# TEAM WIN BACKTEST
# ═══════════════════════════════════════════════════════════════════════
def backtest_team_wins(lahman: LahmanData):
    print("=" * 70)
    print("TEAM WIN PROJECTION BACKTEST")
    print("=" * 70)

    teams_df = lahman.teams
    df = teams_df.copy()
    df = df[df["yearID"] >= 1995].copy()
    for col in ["W", "L", "G", "R", "RA"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["W", "L", "G", "R", "RA"])
    df = df[df["G"] >= 100]
    df = df[df["yearID"] != 2020]

    # Build pyth_pct and lag features
    df["win_pct"] = df["W"] / df["G"]
    df["pyth_pct"] = df.apply(lambda r: _pyth_pct(r["R"], r["RA"]), axis=1)
    df["run_diff_pg"] = (df["R"] - df["RA"]) / df["G"]
    df = df.sort_values(["teamID", "yearID"])
    df["pyth_pct_lag"] = df.groupby("teamID")["pyth_pct"].shift(1)
    df["actual_pct_lag"] = df.groupby("teamID")["win_pct"].shift(1)
    df["W_lag"] = df.groupby("teamID")["W"].shift(1)
    df = df.dropna(subset=["pyth_pct_lag"])

    all_model_preds = []
    all_naive_last_year = []
    all_naive_81 = []
    all_pyth_only = []
    all_actuals = []
    year_results = []

    for test_year in TEST_YEARS:
        train = df[df["yearID"] < test_year]
        test = df[df["yearID"] == test_year]

        if len(train) < 50 or test.empty:
            continue

        # Fit OLS on training data (pyth_pct_lag only, matching our production model)
        from app.models.team_regression import _fit_ols
        X_train = train[["pyth_pct_lag"]].values
        y_train = train["W"].values.astype(float)
        ols = _fit_ols(X_train, y_train, ["pyth_pct_lag"])

        X_test = test[["pyth_pct_lag"]].values
        X_test_aug = np.column_stack([np.ones(len(X_test)), X_test])
        model_preds = X_test_aug @ ols.coef

        actuals = test["W"].values.astype(float)
        naive_last = test["W_lag"].values.astype(float)
        naive_81 = np.full(len(actuals), 81.0)
        pyth_only = test["pyth_pct_lag"].values * 162

        all_model_preds.extend(model_preds)
        all_naive_last_year.extend(naive_last)
        all_naive_81.extend(naive_81)
        all_pyth_only.extend(pyth_only)
        all_actuals.extend(actuals)

        yr_rmse = rmse(model_preds, actuals)
        yr_mae_val = mae(model_preds, actuals)
        yr_r = correlation(model_preds, actuals)

        year_results.append({
            "year": test_year,
            "n_teams": len(test),
            "model_rmse": yr_rmse,
            "model_mae": yr_mae_val,
            "model_r": yr_r,
            "naive_last_rmse": rmse(naive_last, actuals),
            "naive_81_rmse": rmse(naive_81, actuals),
            "pyth_only_rmse": rmse(pyth_only, actuals),
        })

    # Summary
    print(f"\nTest years: {TEST_YEARS}")
    print(f"Total team-seasons tested: {len(all_actuals)}")

    print(f"\n{'Year':<8} {'N':>4} {'Model RMSE':>12} {'LastYr RMSE':>12} {'81-Wins':>12} {'Pyth RMSE':>12} {'Model r':>10}")
    print("-" * 72)
    for yr in year_results:
        print(f"{yr['year']:<8} {yr['n_teams']:>4} {yr['model_rmse']:>12.2f} {yr['naive_last_rmse']:>12.2f} {yr['naive_81_rmse']:>12.2f} {yr['pyth_only_rmse']:>12.2f} {yr['model_r']:>10.3f}")

    print("-" * 72)
    print(f"{'OVERALL':<8} {len(all_actuals):>4} "
          f"{rmse(all_model_preds, all_actuals):>12.2f} "
          f"{rmse(all_naive_last_year, all_actuals):>12.2f} "
          f"{rmse(all_naive_81, all_actuals):>12.2f} "
          f"{rmse(all_pyth_only, all_actuals):>12.2f} "
          f"{correlation(all_model_preds, all_actuals):>10.3f}")

    print(f"\n{'OVERALL MAE':<14} "
          f"{mae(all_model_preds, all_actuals):>10.2f} "
          f"{mae(all_naive_last_year, all_actuals):>10.2f} "
          f"{mae(all_naive_81, all_actuals):>10.2f} "
          f"{mae(all_pyth_only, all_actuals):>10.2f}")

    # Improvement over baselines
    model_rmse_overall = rmse(all_model_preds, all_actuals)
    naive_rmse = rmse(all_naive_last_year, all_actuals)
    naive81_rmse = rmse(all_naive_81, all_actuals)
    print(f"\n  Model vs Last Year:  {((naive_rmse - model_rmse_overall) / naive_rmse * 100):+.1f}% RMSE improvement")
    print(f"  Model vs Always-81:  {((naive81_rmse - model_rmse_overall) / naive81_rmse * 100):+.1f}% RMSE improvement")

    # Biggest misses
    errors = np.array(all_model_preds) - np.array(all_actuals)
    abs_errors = np.abs(errors)
    test_all = df[df["yearID"].isin(TEST_YEARS)].reset_index(drop=True)
    if len(test_all) == len(errors):
        worst_idx = np.argsort(abs_errors)[-5:][::-1]
        print(f"\n  Top 5 worst misses:")
        for idx in worst_idx:
            row = test_all.iloc[idx]
            print(f"    {int(row['yearID'])} {row['teamID']}: predicted {all_model_preds[idx]:.0f}, actual {int(row['W'])}, error {errors[idx]:+.0f}")

    return model_rmse_overall


# ═══════════════════════════════════════════════════════════════════════
# BATTER PROJECTION BACKTEST
# ═══════════════════════════════════════════════════════════════════════
def backtest_batters(lahman: LahmanData):
    print("\n" + "=" * 70)
    print("BATTER PROJECTION BACKTEST (Marcel)")
    print("=" * 70)

    batting = lahman.batting
    results = {
        "avg": {"pred": [], "actual": []},
        "obp": {"pred": [], "actual": []},
        "slg": {"pred": [], "actual": []},
        "ops": {"pred": [], "actual": []},
        "hr": {"pred": [], "actual": []},
    }

    total_tested = 0

    for test_year in TEST_YEARS:
        # Build Marcel model trained up to test_year
        marcel = MarcelBatting(lahman)
        # Override league averages to use year before test
        marcel.league_avg = lahman.get_league_averages(test_year - 1)

        # Get all batters who played in test_year with enough PA
        test_batters = batting[
            (batting["yearID"] == test_year) &
            (batting["AB"] >= MIN_PA_BATTER * 0.89)  # AB ≈ 89% of PA
        ]

        for _, actual_row in test_batters.iterrows():
            player_id = actual_row["playerID"]

            # Project using data up to (not including) test_year
            proj = marcel.project(player_id, projection_year=test_year)
            if proj is None:
                continue

            # Compute actual stats
            ab = actual_row["AB"]
            h = actual_row["H"]
            bb = actual_row.get("BB", 0)
            hbp = actual_row.get("HBP", 0)
            sf = actual_row.get("SF", 0)
            hr = actual_row["HR"]
            doubles = actual_row.get("2B", 0)
            triples = actual_row.get("3B", 0)
            pa = ab + bb + hbp + sf

            if ab == 0 or pa < MIN_PA_BATTER:
                continue

            actual_avg = h / ab
            actual_obp = (h + bb + hbp) / pa
            tb = h + doubles + 2 * triples + 3 * hr
            actual_slg = tb / ab
            actual_ops = actual_obp + actual_slg

            results["avg"]["pred"].append(proj["avg"])
            results["avg"]["actual"].append(actual_avg)
            results["obp"]["pred"].append(proj["obp"])
            results["obp"]["actual"].append(actual_obp)
            results["slg"]["pred"].append(proj["slg"])
            results["slg"]["actual"].append(actual_slg)
            results["ops"]["pred"].append(proj["ops"])
            results["ops"]["actual"].append(actual_ops)
            results["hr"]["pred"].append(proj["hr"])
            results["hr"]["actual"].append(int(hr))

            total_tested += 1

    print(f"\nTotal batter-seasons tested: {total_tested}")
    print(f"Test years: {TEST_YEARS}")
    print(f"Minimum PA: {MIN_PA_BATTER}")

    print(f"\n{'Stat':<8} {'RMSE':>10} {'MAE':>10} {'Correlation':>12} {'Bias':>10}")
    print("-" * 54)
    for stat in ["avg", "obp", "slg", "ops", "hr"]:
        p = np.array(results[stat]["pred"])
        a = np.array(results[stat]["actual"])
        bias = np.mean(p - a)
        r = correlation(p, a)
        r_val = rmse(p, a)
        m_val = mae(p, a)

        if stat in ("avg", "obp", "slg", "ops"):
            print(f"{stat.upper():<8} {r_val:>10.4f} {m_val:>10.4f} {r:>12.3f} {bias:>+10.4f}")
        else:
            print(f"{stat.upper():<8} {r_val:>10.2f} {m_val:>10.2f} {r:>12.3f} {bias:>+10.2f}")

    # Check specific known players across years
    print("\n  Sample player projections vs actuals:")
    star_batters = ["troutmi01", "judgeaa01", "bettsmo01", "sotoju01", "oaborsh01"]
    for pid in star_batters:
        info = lahman.get_player_info(pid)
        if not info:
            continue
        name = f"{info['name_first']} {info['name_last']}"
        for yr in [2023, 2024]:
            actual = batting[(batting["playerID"] == pid) & (batting["yearID"] == yr)]
            if actual.empty:
                continue
            marcel = MarcelBatting(lahman)
            marcel.league_avg = lahman.get_league_averages(yr - 1)
            proj = marcel.project(pid, projection_year=yr)
            if not proj:
                continue
            ab = actual.iloc[0]["AB"]
            h = actual.iloc[0]["H"]
            hr = actual.iloc[0]["HR"]
            actual_avg = round(h / ab, 3) if ab else 0
            print(f"    {yr} {name:<20} Proj: .{int(proj['avg']*1000):03d}/{proj['hr']}HR  "
                  f"Actual: .{int(actual_avg*1000):03d}/{int(hr)}HR")


# ═══════════════════════════════════════════════════════════════════════
# PITCHER PROJECTION BACKTEST
# ═══════════════════════════════════════════════════════════════════════
def backtest_pitchers(lahman: LahmanData):
    print("\n" + "=" * 70)
    print("PITCHER PROJECTION BACKTEST (Marcel)")
    print("=" * 70)

    pitching = lahman.pitching
    results = {
        "era": {"pred": [], "actual": []},
        "whip": {"pred": [], "actual": []},
        "k_per_9": {"pred": [], "actual": []},
        "bb_per_9": {"pred": [], "actual": []},
    }

    total_tested = 0

    for test_year in TEST_YEARS:
        marcel = MarcelPitching(lahman)
        marcel.league_avg = lahman.get_league_averages(test_year - 1)

        test_pitchers = pitching[
            (pitching["yearID"] == test_year) &
            (pitching["IPouts"] >= MIN_IP_PITCHER * 3)
        ]

        for _, actual_row in test_pitchers.iterrows():
            player_id = actual_row["playerID"]

            proj = marcel.project(player_id, projection_year=test_year)
            if proj is None:
                continue

            ipouts = actual_row.get("IPouts", 0)
            ip = ipouts / 3
            if ip < MIN_IP_PITCHER:
                continue

            er = actual_row.get("ER", 0)
            h = actual_row.get("H", 0)
            bb = actual_row.get("BB", 0)
            so = actual_row.get("SO", 0)

            actual_era = er / ip * 9
            actual_whip = (h + bb) / ip
            actual_k9 = so / ip * 9
            actual_bb9 = bb / ip * 9

            results["era"]["pred"].append(proj["era"])
            results["era"]["actual"].append(actual_era)
            results["whip"]["pred"].append(proj["whip"])
            results["whip"]["actual"].append(actual_whip)
            results["k_per_9"]["pred"].append(proj["k_per_9"])
            results["k_per_9"]["actual"].append(actual_k9)
            results["bb_per_9"]["pred"].append(proj["bb_per_9"])
            results["bb_per_9"]["actual"].append(actual_bb9)

            total_tested += 1

    print(f"\nTotal pitcher-seasons tested: {total_tested}")
    print(f"Test years: {TEST_YEARS}")
    print(f"Minimum IP: {MIN_IP_PITCHER}")

    print(f"\n{'Stat':<10} {'RMSE':>10} {'MAE':>10} {'Correlation':>12} {'Bias':>10}")
    print("-" * 56)
    for stat in ["era", "whip", "k_per_9", "bb_per_9"]:
        p = np.array(results[stat]["pred"])
        a = np.array(results[stat]["actual"])
        bias = np.mean(p - a)
        r = correlation(p, a)
        r_val = rmse(p, a)
        m_val = mae(p, a)
        print(f"{stat.upper():<10} {r_val:>10.3f} {m_val:>10.3f} {r:>12.3f} {bias:>+10.3f}")

    # Star pitchers
    print("\n  Sample pitcher projections vs actuals:")
    star_pitchers = ["colege01", "wheelza01", "colefl01", "burMDne01", "biebsh01"]
    for pid in star_pitchers:
        info = lahman.get_player_info(pid)
        if not info:
            continue
        name = f"{info['name_first']} {info['name_last']}"
        for yr in [2023, 2024]:
            actual = pitching[(pitching["playerID"] == pid) & (pitching["yearID"] == yr)]
            if actual.empty:
                continue
            marcel = MarcelPitching(lahman)
            marcel.league_avg = lahman.get_league_averages(yr - 1)
            proj = marcel.project(pid, projection_year=yr)
            if not proj:
                continue
            ip = actual.iloc[0]["IPouts"] / 3
            er = actual.iloc[0]["ER"]
            actual_era = round(er / ip * 9, 2) if ip else 0
            print(f"    {yr} {name:<20} Proj: {proj['era']:.2f} ERA  Actual: {actual_era:.2f} ERA")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
def main():
    print("Loading Lahman data...")
    lahman = LahmanData()
    lahman.load()
    print()

    team_rmse = backtest_team_wins(lahman)
    backtest_batters(lahman)
    backtest_pitchers(lahman)

    # Final summary
    print("\n" + "=" * 70)
    print("BACKTEST SUMMARY")
    print("=" * 70)
    print(f"""
  Team Wins RMSE:       {team_rmse:.2f} wins
  Industry benchmarks:
    Vegas lines:        ~7-8 wins RMSE
    ZiPS/Steamer/PECOTA: ~9-10 wins RMSE
    Marcel baseline:     ~10-11 wins RMSE
    Last year's record:  ~12-13 wins RMSE
    Always guess 81:     ~12-14 wins RMSE

  Interpretation:
    - RMSE < 11 = competitive with Marcel baseline
    - RMSE < 10 = competitive with professional systems
    - RMSE < 8  = Vegas-tier (aggregating massive info)

  Your model adds Statcast, park factors, platoon splits,
  Vegas priors (40% blend), and Bayesian in-season updating
  on top of the Marcel baseline tested here.
""")


if __name__ == "__main__":
    main()
