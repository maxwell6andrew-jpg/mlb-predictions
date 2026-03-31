"""Map between Lahman playerIDs and MLB Stats API (MLBAM) IDs.

Uses a bundled crosswalk file (data/id_crosswalk.csv) extracted from
the Chadwick register. This file maps key_bbref (= Lahman playerID)
to key_mlbam (= MLBAM ID) for ~23K players.

Falls back to Lahman People.csv bbrefID column if crosswalk is missing.
"""

import pandas as pd
from pathlib import Path

CROSSWALK_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "id_crosswalk.csv"


class IDMapper:
    def __init__(self, chadwick_path: Path, lahman_people: pd.DataFrame):
        self._lahman_to_mlbam: dict[str, int] = {}
        self._mlbam_to_lahman: dict[int, str] = {}
        self._mlbam_names: dict[int, str] = {}

        self._build(chadwick_path, lahman_people)

    def _build(self, chadwick_path: Path, lahman_people: pd.DataFrame):
        print("Building ID mapper...")
        mapped = 0

        # Primary: bundled crosswalk file (key_bbref → key_mlbam)
        if CROSSWALK_PATH.exists():
            try:
                cw = pd.read_csv(CROSSWALK_PATH, low_memory=False)
                cw = cw.dropna(subset=["key_mlbam", "key_bbref"])
                cw["key_mlbam"] = cw["key_mlbam"].astype(int)

                for _, row in cw.iterrows():
                    bbref_id = str(row["key_bbref"])
                    mlbam_id = int(row["key_mlbam"])
                    self._lahman_to_mlbam[bbref_id] = mlbam_id
                    self._mlbam_to_lahman[mlbam_id] = bbref_id
                    first = row.get("name_first", "") or ""
                    last = row.get("name_last", "") or ""
                    if first or last:
                        self._mlbam_names[mlbam_id] = f"{first} {last}".strip()

                mapped = len(self._lahman_to_mlbam)
                print(f"  Crosswalk: mapped {mapped} players")
            except Exception as e:
                print(f"  Crosswalk load failed: {e}")

        # Supplement with Chadwick register if available (larger, more complete)
        if chadwick_path.exists() and chadwick_path.stat().st_size > 1000:
            try:
                cw = pd.read_csv(
                    chadwick_path,
                    usecols=["key_bbref", "key_mlbam", "name_first", "name_last"],
                    low_memory=False,
                )
                cw = cw.dropna(subset=["key_mlbam", "key_bbref"])
                cw["key_mlbam"] = cw["key_mlbam"].astype(int)

                added = 0
                for _, row in cw.iterrows():
                    bbref_id = str(row["key_bbref"])
                    mlbam_id = int(row["key_mlbam"])
                    if mlbam_id not in self._mlbam_to_lahman:
                        self._lahman_to_mlbam[bbref_id] = mlbam_id
                        self._mlbam_to_lahman[mlbam_id] = bbref_id
                        added += 1
                if added:
                    print(f"  Chadwick supplement: added {added} more players")
            except Exception as e:
                print(f"  Chadwick supplement skipped: {e}")

        # Fallback: if People.csv has mlbID column (some Lahman versions)
        if len(self._lahman_to_mlbam) == 0 and not lahman_people.empty and "mlbID" in lahman_people.columns:
            lp = lahman_people[["playerID", "mlbID", "nameFirst", "nameLast"]].dropna(subset=["mlbID"])
            lp = lp[lp["mlbID"] > 0]
            lp["mlbID"] = lp["mlbID"].astype(int)
            for _, row in lp.iterrows():
                lahman_id = str(row["playerID"])
                mlbam_id = int(row["mlbID"])
                self._lahman_to_mlbam[lahman_id] = mlbam_id
                self._mlbam_to_lahman[mlbam_id] = lahman_id
            print(f"  Lahman People.csv mlbID fallback: {len(self._lahman_to_mlbam)} players")

        print(f"  Total mapped: {len(self._lahman_to_mlbam)} players (Lahman <-> MLBAM)")

    def lahman_to_mlbam(self, lahman_id: str) -> int | None:
        return self._lahman_to_mlbam.get(lahman_id)

    def mlbam_to_lahman(self, mlbam_id: int) -> str | None:
        return self._mlbam_to_lahman.get(mlbam_id)

    def get_name(self, mlbam_id: int) -> str | None:
        return self._mlbam_names.get(mlbam_id)

    @property
    def all_lahman_ids(self) -> list[str]:
        return list(self._lahman_to_mlbam.keys())

    @property
    def all_mlbam_ids(self) -> list[int]:
        return list(self._mlbam_to_lahman.keys())
