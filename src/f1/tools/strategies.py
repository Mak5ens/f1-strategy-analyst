"""Every driver's tyre strategy in a race: the compound they started on, their stints, the laps they stopped.

A question on a choice ("why did Hamilton start on softs?") is answered against the others': how many started on
each compound, what the cars around them on the grid chose, how long the stints lasted. The counts are computed here:
a debrief may quote them, never compute them.
"""

from collections import Counter

import pandas as pd
from pydantic import BaseModel, Field

from core.tools import ToolError
from f1.tools.data import RaceData, SessionRef, integer


class StrategiesInput(SessionRef):
    pass


class DriverStint(BaseModel):
    compound: str | None
    start_lap: int
    end_lap: int
    laps: int
    new: bool | None = Field(description="A new set; false for a set used in an earlier session")


class DriverStrategy(BaseModel):
    driver: str
    grid: int | None = Field(description="Starting position; 0 for a pit lane start")
    position: str = Field(description="Finishing position, or R retired, D disqualified...")
    start_compound: str | None
    stops: int
    stop_laps: list[int] = Field(description="The in-lap of each stop")
    stints: list[DriverStint]


class StrategiesOutput(BaseModel):
    season: int
    round: int
    session: str
    drivers: list[DriverStrategy] = Field(description="In grid order")
    start_compounds: dict[str, int] = Field(description="How many drivers started on each compound")
    start_compounds_top_10: dict[str, int] = Field(description="The same among the first 10 on the grid")
    stops: dict[str, int] = Field(description="How many drivers made 0, 1, 2... stops")


def race_strategies(data: RaceData, request: StrategiesInput) -> StrategiesOutput:
    stints = data.stints(request)
    if not stints:
        raise ToolError(f"No stints for the {request.label()}: not ingested, or no such session.")
    results = {str(row["driver"]): row for row in data.results(request.season, request.round, request.session)}
    by_driver: dict[str, list[DriverStint]] = {}
    for row in stints:
        start, end = integer(row["start_lap"]), integer(row["end_lap"])
        if start is None or end is None:
            continue
        compound = row["compound"] if isinstance(row["compound"], str) else None
        fresh = row["fresh_tyre"]
        by_driver.setdefault(str(row["driver"]), []).append(
            DriverStint(
                compound=compound,
                start_lap=start,
                end_lap=end,
                laps=integer(row["laps"]) or end - start + 1,
                new=None if pd.isna(fresh) else bool(fresh),
            )
        )
    drivers = []
    for code, mine in by_driver.items():
        result = results.get(code, {})
        grid = integer(result.get("grid_position"))
        drivers.append(
            DriverStrategy(
                driver=code,
                grid=grid,
                position=str(result.get("classified_position") or integer(result.get("position")) or ""),
                start_compound=mine[0].compound,
                stops=len(mine) - 1,
                stop_laps=[stint.end_lap for stint in mine[:-1]],
                stints=mine,
            )
        )
    drivers.sort(key=lambda driver: (driver.grid or 99, driver.driver))
    top_10 = [driver for driver in drivers if driver.grid and driver.grid <= 10]
    return StrategiesOutput(
        season=request.season,
        round=request.round,
        session=request.session,
        drivers=drivers,
        start_compounds=dict(Counter(driver.start_compound or "UNKNOWN" for driver in drivers)),
        start_compounds_top_10=dict(Counter(driver.start_compound or "UNKNOWN" for driver in top_10)),
        stops={str(count): number for count, number in sorted(Counter(d.stops for d in drivers).items())},
    )
