"""Park factors for all 30 MLB venues.

Park factors represent how much a ballpark inflates or suppresses
a given stat relative to league average (1.0 = neutral).

Source: FanGraphs/ESPN multi-year park factors (2021-2025 avg).
These change slowly year-to-year (r ≈ 0.85), so hardcoding is appropriate.
"""

# Keyed by MLB team ID
# runs: overall run-scoring factor
# hr: home run factor
# h: hit factor (BABIP-related)
PARK_FACTORS: dict[int, dict[str, float]] = {
    # American League East
    110: {"runs": 1.02, "hr": 1.05, "h": 1.00, "name": "Baltimore Orioles"},         # Camden Yards
    111: {"runs": 1.08, "hr": 1.15, "h": 1.03, "name": "Boston Red Sox"},             # Fenway Park
    147: {"runs": 1.05, "hr": 1.15, "h": 0.98, "name": "New York Yankees"},           # Yankee Stadium
    139: {"runs": 0.96, "hr": 0.92, "h": 0.98, "name": "Tampa Bay Rays"},             # Tropicana Field
    141: {"runs": 1.02, "hr": 1.08, "h": 0.99, "name": "Toronto Blue Jays"},          # Rogers Centre

    # American League Central
    145: {"runs": 0.98, "hr": 0.95, "h": 1.00, "name": "Chicago White Sox"},          # Guaranteed Rate
    114: {"runs": 0.97, "hr": 0.90, "h": 1.00, "name": "Cleveland Guardians"},        # Progressive Field
    116: {"runs": 1.03, "hr": 1.12, "h": 0.99, "name": "Detroit Tigers"},             # Comerica Park
    118: {"runs": 1.06, "hr": 1.10, "h": 1.02, "name": "Kansas City Royals"},         # Kauffman Stadium
    142: {"runs": 1.00, "hr": 1.02, "h": 0.99, "name": "Minnesota Twins"},            # Target Field

    # American League West
    117: {"runs": 0.99, "hr": 0.98, "h": 1.00, "name": "Houston Astros"},             # Minute Maid Park
    108: {"runs": 0.96, "hr": 0.90, "h": 0.99, "name": "Los Angeles Angels"},         # Angel Stadium
    133: {"runs": 0.96, "hr": 0.92, "h": 0.99, "name": "Athletics"},                  # Coliseum / new park
    136: {"runs": 0.95, "hr": 0.85, "h": 0.99, "name": "Seattle Mariners"},           # T-Mobile Park
    140: {"runs": 1.05, "hr": 1.12, "h": 1.01, "name": "Texas Rangers"},              # Globe Life Field

    # National League East
    144: {"runs": 1.01, "hr": 1.05, "h": 0.99, "name": "Atlanta Braves"},             # Truist Park
    146: {"runs": 0.95, "hr": 0.88, "h": 0.98, "name": "Miami Marlins"},              # loanDepot Park
    121: {"runs": 1.02, "hr": 1.08, "h": 0.99, "name": "New York Mets"},              # Citi Field
    143: {"runs": 1.03, "hr": 1.08, "h": 1.00, "name": "Philadelphia Phillies"},      # Citizens Bank Park
    120: {"runs": 0.97, "hr": 0.93, "h": 1.00, "name": "Washington Nationals"},       # Nationals Park

    # National League Central
    112: {"runs": 1.05, "hr": 1.15, "h": 1.01, "name": "Chicago Cubs"},               # Wrigley Field
    113: {"runs": 1.06, "hr": 1.18, "h": 1.01, "name": "Cincinnati Reds"},            # Great American Ballpark
    158: {"runs": 1.01, "hr": 1.05, "h": 0.99, "name": "Milwaukee Brewers"},          # American Family Field
    134: {"runs": 0.96, "hr": 0.92, "h": 0.98, "name": "Pittsburgh Pirates"},         # PNC Park
    138: {"runs": 0.97, "hr": 0.92, "h": 0.99, "name": "St. Louis Cardinals"},        # Busch Stadium

    # National League West
    109: {"runs": 1.01, "hr": 1.05, "h": 0.99, "name": "Arizona Diamondbacks"},       # Chase Field
    115: {"runs": 1.35, "hr": 1.25, "h": 1.12, "name": "Colorado Rockies"},           # Coors Field
    119: {"runs": 1.03, "hr": 1.10, "h": 0.99, "name": "Los Angeles Dodgers"},        # Dodger Stadium
    135: {"runs": 0.98, "hr": 1.00, "h": 0.97, "name": "San Diego Padres"},           # Petco Park
    137: {"runs": 0.88, "hr": 0.82, "h": 0.93, "name": "San Francisco Giants"},       # Oracle Park
}


def get_park_factor(team_id: int, stat: str = "runs") -> float:
    """Get park factor for a team's home venue. Returns 1.0 if unknown."""
    entry = PARK_FACTORS.get(team_id)
    if not entry:
        return 1.0
    return entry.get(stat, 1.0)


def get_park_name(team_id: int) -> str:
    entry = PARK_FACTORS.get(team_id)
    return entry.get("name", "Unknown") if entry else "Unknown"


def neutralize_stat(value: float, team_id: int, stat: str = "runs") -> float:
    """Remove park effect from a stat (convert to park-neutral)."""
    pf = get_park_factor(team_id, stat)
    return value / pf if pf != 0 else value


def apply_park_factor(value: float, team_id: int, stat: str = "runs") -> float:
    """Apply park effect to a neutral stat."""
    return value * get_park_factor(team_id, stat)
