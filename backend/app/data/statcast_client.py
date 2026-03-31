"""Fetch Statcast data from Baseball Savant leaderboards.

Downloads season-level CSV leaderboards (not per-player queries) for
efficiency. All data is keyed by MLBAM player ID.

Graceful degradation: if any fetch fails, returns empty dict.
"""

import io
import csv
import hashlib
from pathlib import Path
from datetime import datetime, timezone

import httpx

from app.config import CACHE_DIR

SAVANT_BASE = "https://baseballsavant.mlb.com"

# Cache Statcast CSVs for 12 hours
CACHE_TTL = 43200

STATCAST_CACHE = CACHE_DIR / "statcast"


class StatcastClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "MLBPredictor/1.0 (research)"},
            follow_redirects=True,
        )
        STATCAST_CACHE.mkdir(parents=True, exist_ok=True)

    async def close(self):
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Batter Statcast (xwOBA, xSLG, barrel%, exit velo, xBA)
    # ------------------------------------------------------------------
    async def fetch_batter_statcast(self, year: int) -> dict[int, dict]:
        """Fetch expected stats leaderboard for batters."""
        url = (
            f"{SAVANT_BASE}/leaderboard/expected_statistics"
            f"?type=batter&year={year}&position=&team=&min=50&csv=true"
        )
        rows = await self._fetch_csv(url, f"batter_xstats_{year}")
        result = {}
        for row in rows:
            try:
                mlbam_id = int(row.get("player_id", 0))
                if mlbam_id == 0:
                    continue
                result[mlbam_id] = {
                    "name": row.get("player_name", "").strip(' "'),
                    "pa": _int(row.get("pa", 0)),
                    "xba": _float(row.get("est_ba", row.get("xba", 0))),
                    "xslg": _float(row.get("est_slg", row.get("xslg", 0))),
                    "xwoba": _float(row.get("est_woba", row.get("xwoba", 0))),
                    "xobp": _float(row.get("est_obp", row.get("xobp", 0))),
                    "barrel_rate": _float(row.get("brl_percent", row.get("barrel_batted_rate", 0))),
                    "exit_velo": _float(row.get("avg_hit_speed", row.get("exit_velocity_avg", 0))),
                    "hard_hit_rate": _float(row.get("hard_hit_percent", row.get("ev95percent", 0))),
                    "actual_woba": _float(row.get("woba", 0)),
                    "actual_ba": _float(row.get("ba", 0)),
                    "actual_slg": _float(row.get("slg", 0)),
                }
            except (ValueError, KeyError):
                continue
        return result

    # ------------------------------------------------------------------
    # Pitcher Statcast (xERA, xFIP, xBA against, barrel% against)
    # ------------------------------------------------------------------
    async def fetch_pitcher_statcast(self, year: int) -> dict[int, dict]:
        """Fetch expected stats leaderboard for pitchers."""
        url = (
            f"{SAVANT_BASE}/leaderboard/expected_statistics"
            f"?type=pitcher&year={year}&position=&team=&min=50&csv=true"
        )
        rows = await self._fetch_csv(url, f"pitcher_xstats_{year}")
        result = {}
        for row in rows:
            try:
                mlbam_id = int(row.get("player_id", 0))
                if mlbam_id == 0:
                    continue
                result[mlbam_id] = {
                    "name": row.get("player_name", "").strip(' "'),
                    "xba": _float(row.get("est_ba", row.get("xba", 0))),
                    "xslg": _float(row.get("est_slg", row.get("xslg", 0))),
                    "xwoba": _float(row.get("est_woba", row.get("xwoba", 0))),
                    "xera": _float(row.get("xera", 0)),
                    "barrel_rate_against": _float(row.get("brl_percent", row.get("barrel_batted_rate", 0))),
                    "exit_velo_against": _float(row.get("avg_hit_speed", row.get("exit_velocity_avg", 0))),
                    "hard_hit_rate_against": _float(row.get("hard_hit_percent", 0)),
                    "actual_woba": _float(row.get("woba", 0)),
                    "actual_era": _float(row.get("era", 0)),
                }
            except (ValueError, KeyError):
                continue
        return result

    # ------------------------------------------------------------------
    # Internal: CSV fetch with disk caching
    # ------------------------------------------------------------------
    async def _fetch_csv(self, url: str, cache_key: str) -> list[dict]:
        """Fetch a CSV URL, cache to disk, return list of row dicts."""
        cache_file = STATCAST_CACHE / f"{cache_key}.csv"

        # Check disk cache
        if cache_file.exists():
            age = datetime.now(timezone.utc).timestamp() - cache_file.stat().st_mtime
            if age < CACHE_TTL:
                try:
                    text = cache_file.read_text(encoding="utf-8")
                    return list(csv.DictReader(io.StringIO(text)))
                except Exception:
                    pass

        # Fetch from Baseball Savant
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            text = resp.text

            # Validate we got CSV, not HTML error page
            if text.strip().startswith("<!") or text.strip().startswith("<html"):
                print(f"  Statcast: got HTML instead of CSV for {cache_key}")
                return []

            # Cache to disk
            cache_file.write_text(text, encoding="utf-8")

            return list(csv.DictReader(io.StringIO(text)))
        except Exception as e:
            print(f"  Statcast fetch failed ({cache_key}): {e}")
            return []


def _float(val) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _int(val) -> int:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0
