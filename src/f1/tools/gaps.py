"""Gap between two drivers, lap by lap."""

from typing import Any

from pydantic import BaseModel, Field

from core.tools import ToolError
from f1.tools.data import DriverCode, RaceData, SessionRef, integer, number


class GapInput(SessionRef):
    driver: DriverCode
    reference_driver: DriverCode
    from_lap: int | None = Field(None, ge=1, description="First lap to return; the first lap both completed if omitted")
    to_lap: int | None = Field(None, ge=1, description="Last lap to return; the last lap both completed if omitted")


class LapGap(BaseModel):
    lap: int
    gap_s: float = Field(
        description="Time between the two drivers crossing the line at the end of this lap. "
        "Positive: driver behind reference_driver"
    )
    lap_delta_s: float | None = Field(description="Change of the gap on this lap: positive, driver lost time")
    position: int | None
    reference_position: int | None


class GapOutput(BaseModel):
    season: int
    round: int
    session: str
    driver: str
    reference_driver: str
    laps: list[LapGap]
    first_gap_s: float
    final_gap_s: float
    gained_s: float = Field(description="Time the driver gained on reference_driver over the laps: positive, gained")


def gaps_at_line(driver_laps: dict[int, dict[str, Any]], reference_laps: dict[int, dict[str, Any]]) -> dict[int, float]:
    """Gap at the end of each lap both drivers completed with a timing: driver minus reference, in seconds."""
    gaps = {}
    for lap in sorted(driver_laps.keys() & reference_laps.keys()):
        end = number(driver_laps[lap]["lap_end_session_s"])
        reference_end = number(reference_laps[lap]["lap_end_session_s"])
        if end is not None and reference_end is not None:
            gaps[lap] = round(end - reference_end, 3)
    return gaps


def gap_between_drivers(data: RaceData, request: GapInput) -> GapOutput:
    if request.driver == request.reference_driver:
        raise ToolError("driver and reference_driver must differ.")
    mine = data.driver_laps(request, request.driver)
    theirs = data.driver_laps(request, request.reference_driver)
    gaps = gaps_at_line(mine, theirs)
    first, last = request.from_lap or 1, request.to_lap or max(gaps, default=0)
    selected = [lap for lap in gaps if first <= lap <= last]
    if not selected:
        raise ToolError(
            f"{request.driver} and {request.reference_driver} have no lap in common between laps {first} and {last}."
        )

    laps = [
        LapGap(
            lap=lap,
            gap_s=gaps[lap],
            lap_delta_s=round(gaps[lap] - gaps[lap - 1], 3) if lap - 1 in gaps else None,
            position=integer(mine[lap]["position"]),
            reference_position=integer(theirs[lap]["position"]),
        )
        for lap in selected
    ]
    return GapOutput(
        season=request.season,
        round=request.round,
        session=request.session,
        driver=request.driver,
        reference_driver=request.reference_driver,
        laps=laps,
        first_gap_s=laps[0].gap_s,
        final_gap_s=laps[-1].gap_s,
        gained_s=round(laps[0].gap_s - laps[-1].gap_s, 3),
    )
