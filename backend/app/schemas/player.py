from pydantic import BaseModel


class PlayerBio(BaseModel):
    id: int
    name: str
    team: str = ""
    position: str = ""
    age: int | None = None
    bats: str = ""
    throws: str = ""


class BattingProjection(BaseModel):
    type: str = "batting"
    projected_pa: int = 0
    avg: float = 0.0
    obp: float = 0.0
    slg: float = 0.0
    ops: float = 0.0
    hr: int = 0
    rbi: int = 0
    r: int = 0
    sb: int = 0
    bb: int = 0
    so: int = 0
    war: float = 0.0
    hr_rate: float = 0.0
    bb_rate: float = 0.0
    k_rate: float = 0.0
    confidence: float = 0.0


class PitchingProjection(BaseModel):
    type: str = "pitching"
    projected_ip: float = 0.0
    era: float = 0.0
    whip: float = 0.0
    k_per_9: float = 0.0
    bb_per_9: float = 0.0
    hr_per_9: float = 0.0
    w: int = 0
    l: int = 0
    sv: int = 0
    so: int = 0
    bb: int = 0
    war: float = 0.0
    confidence: float = 0.0


class HistoricalSeason(BaseModel):
    year: int
    avg: float | None = None
    obp: float | None = None
    slg: float | None = None
    ops: float | None = None
    hr: int | None = None
    era: float | None = None
    whip: float | None = None
    k_per_9: float | None = None
    bb_per_9: float | None = None


class PlayerResponse(BaseModel):
    player: PlayerBio
    projection: dict
    historical: list[dict] = []
    league_averages: dict = {}
