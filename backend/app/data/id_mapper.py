"""Map between Lahman playerIDs and MLB Stats API (MLBAM) IDs.

Uses Lahman People.csv directly (has mlbID column = MLBAM ID).
Falls back to Chadwick register if available for better name coverage.
"""

import pandas as pd
from pathlib import Path


class IDMapper:
    def __init__(self, chadwick_path: Path, lahman_people: pd.DataFrame):
        self._lahman_to_mlbam: dict[str, int] = {}
        self._mlbam_to_lahman: dict[int, str] = {}
        self._mlbam_names: dict[int, str] = {}

        self._build(chadwick_path, lahman_people)

    def _build(self, chadwick_path: Path, lahman_people: pd.DataFrame):
        print("Building ID mapper...")

        # Primary: use Lahman People.csv which has mlbID (= MLBAM ID)
        if not lahman_people.empty and "mlbID" in lahman_people.columns:
            lp = lahman_people[["playerID", "mlbID", "nameFirst", "nameLast"]].dropna(subset=["mlbID"])
            lp = lp[lp["mlbID"] > 0]
            lp["mlbID"] = lp["mlbID"].astype(int)
            for _, row in lp.iterrows():
                lahman_id = str(row["playerID"])
                mlbam_id = int(row["mlbID"])
                self._lahman_to_mlbam[lahman_id] = mlbam_id
                self._mlbam_to_lahman[mlbam_id] = lahman_id
                first = row.get("nameFirst", "") or ""
                last = row.get("nameLast", "") or ""
                if first or last:
                    self._mlbam_names[mlbam_id] = f"{first} {last}".strip()

        # Supplement with Chadwick register if available and non-empty
        if chadwick_path.exists() and chadwick_path.stat().st_size > 1000:
            try:
                cw = pd.read_csv(
                    chadwick_path,
                    usecols=["key_bbref", "key_mlbam", "name_first", "name_last"],
                    low_memory=False,
                )
                cw = cw.dropna(subset=["key_mlbam", "key_bbref"])
                cw["key_mlbam"] = cw["key_mlbam"].astype(int)

                if "bbrefID" in lahman_people.columns:
                    lahman_ids = lahman_people[["playerID", "bbrefID"]].dropna(subset=["bbrefID"])
                    merged = lahman_ids.merge(cw, left_on="bbrefID", right_on="key_bbref", how="inner")
                else:
                    merged = cw.rename(columns={"key_bbref": "playerID"})

                for _, row in merged.iterrows():
                    lahman_id = row.get("playerID", row.get("key_bbref", ""))
                    mlbam_id = int(row["key_mlbam"])
                    if lahman_id and mlbam_id:
                        self._lahman_to_mlbam[lahman_id] = mlbam_id
                        self._mlbam_to_lahman[mlbam_id] = lahman_id
            except Exception as e:
                print(f"  Chadwick supplement skipped: {e}")

        print(f"  Mapped {len(self._lahman_to_mlbam)} players (Lahman <-> MLBAM)")

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
