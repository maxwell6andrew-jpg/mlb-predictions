from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LAHMAN_DIR = DATA_DIR / "lahman"
CHADWICK_DIR = DATA_DIR / "chadwick"
CACHE_DIR = DATA_DIR / "cache"

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"

PROJECTION_YEAR = 2026
HISTORY_YEARS = 3  # Look back 3 years for Marcel

# Replacement-level wins for a team of replacement players
REPLACEMENT_WINS = 48

# Runs per win (approximately 10)
RUNS_PER_WIN = 10
