"""The weather of a race: temperatures at the start and their range, humidity, rain."""

from pydantic import BaseModel, Field

from core.tools import ToolError
from f1.tools.data import RaceData, SessionRef, number


class WeatherInput(SessionRef):
    pass


class WeatherOutput(BaseModel):
    season: int
    round: int
    session: str
    air_temp_start_c: float
    track_temp_start_c: float
    air_temp_min_c: float
    air_temp_max_c: float
    track_temp_min_c: float
    track_temp_max_c: float
    humidity_start_pct: float | None
    rainfall: bool = Field(description="Rain at some point of the session")
    rain_minutes: int = Field(description="Minutes with rain, one reading a minute")


def race_weather(data: RaceData, request: WeatherInput) -> WeatherOutput:
    rows = [row for row in data.weather(request) if number(row["air_temp_c"]) is not None]
    if not rows:
        raise ToolError(f"No weather for the {request.label()}.")
    air = [float(row["air_temp_c"]) for row in rows]
    track = [float(row["track_temp_c"]) for row in rows if number(row["track_temp_c"]) is not None] or [0.0]
    rain = [bool(row["rainfall"]) for row in rows]
    return WeatherOutput(
        season=request.season,
        round=request.round,
        session=request.session,
        air_temp_start_c=air[0],
        track_temp_start_c=track[0],
        air_temp_min_c=min(air),
        air_temp_max_c=max(air),
        track_temp_min_c=min(track),
        track_temp_max_c=max(track),
        humidity_start_pct=number(rows[0]["humidity_pct"]),
        rainfall=any(rain),
        rain_minutes=sum(rain),
    )
