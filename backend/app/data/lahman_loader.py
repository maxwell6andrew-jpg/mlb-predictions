"""Load and parse Lahman Baseball Database CSVs."""

import pandas as pd
from pathlib import Path
from app.config import LAHMAN_DIR


class LahmanData:
    def __init__(self):
        self.batting: pd.DataFrame = pd.DataFrame()
        self.pitching: pd.DataFrame = pd.DataFrame()
        self.teams: pd.DataFrame = pd.DataFrame()
        self.people: pd.DataFrame = pd.DataFrame()
        self.fielding: pd.DataFrame = pd.DataFrame()

    def load(self):
        print("Loading Lahman data...")
        self._download_lahman_if_missing()
        self.batting = self._load_csv("Batting.csv")
        self.pitching = self._load_csv("Pitching.csv")
        self.teams = self._load_csv("Teams.csv")
        self.people = self._load_csv("People.csv")
        self.fielding = self._load_csv("Fielding.csv")

        # Consolidate multi-stint seasons
        self.batting = self._consolidate_batting(self.batting)
        self.pitching = self._consolidate_pitching(self.pitching)

        print(f"  Batting: {len(self.batting)} player-seasons")
        print(f"  Pitching: {len(self.pitching)} player-seasons")
        print(f"  People: {len(self.people)} entries")

    def _download_lahman_if_missing(self):
        """Download Lahman CSVs from GitHub if not present."""
        needed = ["Batting.csv", "Pitching.csv", "Teams.csv", "People.csv", "Fielding.csv"]
        missing = [f for f in needed if not (LAHMAN_DIR / f).exists()]
        if not missing:
            return
        import urllib.request, zipfile, io
        print("  Downloading Lahman data from GitHub...")
        LAHMAN_DIR.mkdir(parents=True, exist_ok=True)
        url = "https://github.com/chadwickbureau/baseballdatabank/archive/refs/heads/master.zip"
        try:
            with urllib.request.urlopen(url) as resp:
                zf = zipfile.ZipFile(io.BytesIO(resp.read()))
            for name in zf.namelist():
                base = name.split("/")[-1]
                if base in needed:
                    with zf.open(name) as src, open(LAHMAN_DIR / base, "wb") as dst:
                        dst.write(src.read())
            print("  Lahman download complete.")
        except Exception as e:
            print(f"  WARNING: Could not download Lahman data: {e}")

    def _load_csv(self, filename: str) -> pd.DataFrame:
        path = LAHMAN_DIR / filename
        if not path.exists():
            print(f"  WARNING: {filename} not found at {path}")
            return pd.DataFrame()
        df = pd.read_csv(path, low_memory=False)
        # R package prefixes numeric column names with X (X2B -> 2B)
        rename = {c: c[1:] for c in df.columns if c.startswith("X") and c[1:2].isdigit()}
        if rename:
            df = df.rename(columns=rename)
        return df

    def _consolidate_batting(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sum counting stats across stints for players traded mid-season."""
        if df.empty:
            return df

        count_cols = ["G", "AB", "R", "H", "2B", "3B", "HR", "RBI", "SB", "CS",
                      "BB", "SO", "IBB", "HBP", "SH", "SF", "GIDP"]
        existing = [c for c in count_cols if c in df.columns]

        grouped = df.groupby(["playerID", "yearID"]).agg(
            {c: "sum" for c in existing}
        ).reset_index()

        # Get the last team for each player-year
        last_team = df.sort_values("stint").groupby(["playerID", "yearID"])["teamID"].last().reset_index()
        grouped = grouped.merge(last_team, on=["playerID", "yearID"])

        return grouped

    def _consolidate_pitching(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sum counting stats across stints for pitchers traded mid-season."""
        if df.empty:
            return df

        count_cols = ["W", "L", "G", "GS", "CG", "SHO", "SV", "IPouts",
                      "H", "ER", "HR", "BB", "SO", "IBB", "WP", "HBP",
                      "BK", "BFP", "GF", "R"]
        existing = [c for c in count_cols if c in df.columns]

        grouped = df.groupby(["playerID", "yearID"]).agg(
            {c: "sum" for c in existing}
        ).reset_index()

        last_team = df.sort_values("stint").groupby(["playerID", "yearID"])["teamID"].last().reset_index()
        grouped = grouped.merge(last_team, on=["playerID", "yearID"])

        return grouped

    def get_batting_history(self, player_id: str, end_year: int, n_years: int = 3) -> pd.DataFrame:
        """Get n_years of batting data ending at end_year (exclusive)."""
        start_year = end_year - n_years
        mask = (
            (self.batting["playerID"] == player_id) &
            (self.batting["yearID"] >= start_year) &
            (self.batting["yearID"] < end_year)
        )
        return self.batting[mask].sort_values("yearID", ascending=False)

    def get_pitching_history(self, player_id: str, end_year: int, n_years: int = 3) -> pd.DataFrame:
        """Get n_years of pitching data ending at end_year (exclusive)."""
        start_year = end_year - n_years
        mask = (
            (self.pitching["playerID"] == player_id) &
            (self.pitching["yearID"] >= start_year) &
            (self.pitching["yearID"] < end_year)
        )
        return self.pitching[mask].sort_values("yearID", ascending=False)

    def get_player_info(self, player_id: str) -> dict | None:
        """Get player bio from People table."""
        row = self.people[self.people["playerID"] == player_id]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "player_id": player_id,
            "name_first": r.get("nameFirst", ""),
            "name_last": r.get("nameLast", ""),
            "birth_year": int(r["birthYear"]) if pd.notna(r.get("birthYear")) else None,
            "bbref_id": r.get("bbrefID", player_id),
        }

    def get_league_averages(self, year: int) -> dict:
        """Compute league-wide batting averages for a given year."""
        bat = self.batting[self.batting["yearID"] == year]
        if bat.empty:
            # Fallback to most recent year
            max_year = self.batting["yearID"].max()
            bat = self.batting[self.batting["yearID"] == max_year]

        total_ab = bat["AB"].sum()
        total_h = bat["H"].sum()
        total_bb = bat["BB"].sum()
        total_hbp = bat.get("HBP", pd.Series([0])).sum()
        total_sf = bat.get("SF", pd.Series([0])).sum()
        total_hr = bat["HR"].sum()
        total_2b = bat["2B"].sum()
        total_3b = bat["3B"].sum()
        total_pa = total_ab + total_bb + total_hbp + total_sf

        avg = total_h / total_ab if total_ab else 0.250
        obp = (total_h + total_bb + total_hbp) / (total_ab + total_bb + total_hbp + total_sf) if total_pa else 0.320
        slg = (total_h - total_2b - total_3b - total_hr + 2 * total_2b + 3 * total_3b + 4 * total_hr) / total_ab if total_ab else 0.400

        # Pitching averages
        pit = self.pitching[self.pitching["yearID"] == year]
        if pit.empty:
            max_year = self.pitching["yearID"].max()
            pit = self.pitching[self.pitching["yearID"] == max_year]

        total_er = pit["ER"].sum()
        total_ipouts = pit["IPouts"].sum()
        total_ip = total_ipouts / 3 if total_ipouts else 1
        total_ph = pit["H"].sum()
        total_pbb = pit["BB"].sum()
        total_pso = pit["SO"].sum()
        total_phr = pit["HR"].sum()
        total_bfp = pit["BFP"].sum() if "BFP" in pit.columns else total_ip * 4.3

        lg_era = total_er / total_ip * 9 if total_ip else 4.00
        lg_whip = (total_ph + total_pbb) / total_ip if total_ip else 1.30
        lg_k9 = total_pso / total_ip * 9 if total_ip else 8.5
        lg_bb9 = total_pbb / total_ip * 9 if total_ip else 3.2
        lg_hr9 = total_phr / total_ip * 9 if total_ip else 1.2

        return {
            "avg": avg,
            "obp": obp,
            "slg": slg,
            "ops": obp + slg,
            "hr_rate": total_hr / total_pa if total_pa else 0.030,
            "bb_rate": total_bb / total_pa if total_pa else 0.080,
            "k_rate": bat["SO"].sum() / total_pa if total_pa else 0.220,
            "sb_rate": bat["SB"].sum() / total_pa if total_pa else 0.020,
            "era": lg_era,
            "whip": lg_whip,
            "k_per_9": lg_k9,
            "bb_per_9": lg_bb9,
            "hr_per_9": lg_hr9,
        }

    def get_primary_position(self, player_id: str) -> str:
        """Determine primary position from fielding data."""
        fld = self.fielding[self.fielding["playerID"] == player_id]
        if fld.empty:
            return "DH"
        # Most recent year, most games at position
        recent = fld[fld["yearID"] == fld["yearID"].max()]
        if recent.empty:
            return "DH"
        pos = recent.sort_values("G", ascending=False).iloc[0].get("POS", "DH")
        return pos if pos != "P" else "SP"

    def get_team_stats(self, year: int) -> pd.DataFrame:
        """Get team-level stats for a given year."""
        return self.teams[self.teams["yearID"] == year].copy()
