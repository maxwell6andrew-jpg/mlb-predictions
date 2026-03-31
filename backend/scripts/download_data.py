"""Download Lahman Baseball Database and Chadwick register CSVs."""

import os
import io
import ssl
import zipfile
import urllib.request
from pathlib import Path

# Handle macOS Python SSL cert issue
ssl_ctx = ssl.create_default_context()
try:
    import certifi
    ssl_ctx.load_verify_locations(certifi.where())
except ImportError:
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

BASE_DIR = Path(__file__).resolve().parent.parent / "data"
LAHMAN_DIR = BASE_DIR / "lahman"
CHADWICK_DIR = BASE_DIR / "chadwick"

# SABR hosts the Lahman database (the old GitHub repo is gone)
LAHMAN_ZIP_URL = "https://sabr.box.com/shared/static/y1prhc795jk8zvmelfd3jq7tl389y6cd.zip"
# Fallback: seanlahman.com
LAHMAN_FALLBACK_URL = "https://github.com/WebucatorTraining/lahman-baseball-mysql/raw/refs/heads/master/lahmansbaseballdb-2017-01-18.zip"

CHADWICK_PEOPLE_URL = "https://raw.githubusercontent.com/chadwickbureau/register/master/data/people.csv"

NEEDED_FILES = ["Batting.csv", "Pitching.csv", "Teams.csv", "People.csv", "Fielding.csv"]


def _download(url: str) -> bytes:
    """Download a URL, following redirects."""
    req = urllib.request.Request(url, headers={"User-Agent": "MLB-Predictor/1.0"})
    response = urllib.request.urlopen(req, context=ssl_ctx, timeout=120)
    return response.read()


def download_lahman():
    LAHMAN_DIR.mkdir(parents=True, exist_ok=True)

    if all((LAHMAN_DIR / f).exists() for f in NEEDED_FILES):
        print("Lahman data already present, skipping download.")
        return

    print("Downloading Lahman database...")
    for url in [LAHMAN_ZIP_URL, LAHMAN_FALLBACK_URL]:
        try:
            print(f"  Trying {url[:60]}...")
            data = _download(url)
            zip_data = io.BytesIO(data)
            with zipfile.ZipFile(zip_data) as zf:
                extracted = 0
                for name in zf.namelist():
                    basename = os.path.basename(name)
                    if basename in NEEDED_FILES:
                        print(f"  Extracting {basename}")
                        with zf.open(name) as src, open(LAHMAN_DIR / basename, "wb") as dst:
                            dst.write(src.read())
                        extracted += 1
                if extracted > 0:
                    print(f"  Extracted {extracted} files.")
                    return
                else:
                    print("  No matching files found in zip, trying next source...")
        except Exception as e:
            print(f"  Failed: {e}")
            continue

    print("WARNING: Could not download Lahman data from any source.")
    print("Please manually download CSVs from https://sabr.org/lahman-database/")
    print(f"and place them in: {LAHMAN_DIR}")


def download_chadwick():
    CHADWICK_DIR.mkdir(parents=True, exist_ok=True)
    dest = CHADWICK_DIR / "people.csv"

    if dest.exists():
        print("Chadwick register already present, skipping download.")
        return

    print("Downloading Chadwick register...")
    try:
        data = _download(CHADWICK_PEOPLE_URL)
        with open(dest, "wb") as f:
            f.write(data)
        print("Chadwick download complete.")
    except Exception as e:
        print(f"WARNING: Could not download Chadwick register: {e}")
        print("The app can still run but ID mapping will be limited.")


if __name__ == "__main__":
    download_lahman()
    download_chadwick()
    print("\nDone!")
    print(f"  Lahman:   {LAHMAN_DIR}")
    print(f"  Chadwick: {CHADWICK_DIR}")
