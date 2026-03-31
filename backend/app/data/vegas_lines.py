"""2026 preseason Vegas consensus win totals (over/under lines).

Source: Aggregated from public consensus lines (FanGraphs, ESPN, etc.)
Updated: March 2026 preseason

Vegas lines are the single best publicly available predictor of team wins —
they aggregate injury news, roster moves, minor league depth, and market
wisdom that no statistical model can replicate from box scores alone.

Used as a Bayesian prior that gets blended with our model's projection.
"""

# Team ID (MLBAM) → consensus over/under win total
# These are preseason lines before any games are played
VEGAS_LINES_2026: dict[int, float] = {
    # AL East
    147: 95.5,   # New York Yankees
    111: 87.5,   # Boston Red Sox
    141: 83.5,   # Toronto Blue Jays
    110: 84.5,   # Baltimore Orioles
    139: 72.5,   # Tampa Bay Rays

    # AL Central
    114: 78.5,   # Cleveland Guardians
    116: 82.5,   # Detroit Tigers
    118: 80.5,   # Kansas City Royals
    142: 73.5,   # Minnesota Twins
    145: 59.5,   # Chicago White Sox

    # AL West
    117: 82.5,   # Houston Astros
    136: 86.5,   # Seattle Mariners
    140: 83.5,   # Texas Rangers
    108: 67.5,   # Los Angeles Angels
    133: 68.5,   # Oakland Athletics

    # NL East
    143: 93.5,   # Philadelphia Phillies
    144: 85.5,   # Atlanta Braves
    121: 87.5,   # New York Mets
    120: 65.5,   # Washington Nationals
    146: 63.5,   # Miami Marlins

    # NL Central
    158: 89.5,   # Milwaukee Brewers
    112: 84.5,   # Chicago Cubs
    113: 80.5,   # Cincinnati Reds
    134: 77.5,   # Pittsburgh Pirates
    138: 73.5,   # St. Louis Cardinals

    # NL West
    119: 99.5,   # Los Angeles Dodgers
    135: 87.5,   # San Diego Padres
    137: 76.5,   # San Francisco Giants
    109: 80.5,   # Arizona Diamondbacks
    115: 59.5,   # Colorado Rockies
}


def get_vegas_line(team_id: int) -> float | None:
    """Return the preseason Vegas consensus over/under for a team."""
    return VEGAS_LINES_2026.get(team_id)


def get_all_vegas_lines() -> dict[int, float]:
    """Return all Vegas lines."""
    return dict(VEGAS_LINES_2026)
