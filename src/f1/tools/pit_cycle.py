"""Undercut and overcut: who gained what when two drivers stopped at different laps."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from core.tools import ToolError
from f1.tools.data import DriverCode, RaceData, SessionRef, integer, is_neutralized
from f1.tools.gaps import gaps_at_line


class PitCycleInput(SessionRef):
    driver: DriverCode
    rival: DriverCode
    driver_stop: int = Field(1, ge=1, description="Stop number of driver")
    rival_stop: int | None = Field(
        None, ge=1, description="Stop number of rival; the rival's stop closest in laps to driver's if omitted"
    )


class PitCycleOutput(BaseModel):
    season: int
    round: int
    session: str
    driver: str
    rival: str
    driver_stop_lap: int
    rival_stop_lap: int
    kind: Literal["undercut", "overcut", "same_lap"] = Field(
        description="undercut: driver stopped first; overcut: driver stopped later"
    )
    lap_before: int = Field(description="Last lap before either stopped")
    lap_after: int = Field(description="Out-lap of the later stopper: both stops are behind")
    gap_before_s: float = Field(description="Gap at the end of lap_before. Positive: driver behind rival")
    gap_after_s: float = Field(description="Gap at the end of lap_after. Positive: driver behind rival")
    gained_s: float = Field(description="gap_before_s minus gap_after_s: positive, driver gained on rival")
    position_before: int | None
    rival_position_before: int | None
    position_after: int | None
    rival_position_after: int | None
    driver_passed_rival: bool = Field(description="Driver was behind before the stops and ahead after")
    rival_passed_driver: bool
    neutralized: bool = Field(
        description="Safety car, VSC or red flag between lap_before and lap_after: "
        "the stops were cheaper than usual, the gain says little about strategy"
    )


def pit_cycle(data: RaceData, request: PitCycleInput) -> PitCycleOutput:
    if request.driver == request.rival:
        raise ToolError("driver and rival must differ.")
    mine = data.driver_laps(request, request.driver)
    theirs = data.driver_laps(request, request.rival)
    my_stop = _stop(data.pit_stops(request, request.driver), request.driver, request.driver_stop)
    their_stops = data.pit_stops(request, request.rival)
    if request.rival_stop is not None:
        their_stop = _stop(their_stops, request.rival, request.rival_stop)
    elif their_stops:
        their_stop = min(their_stops, key=lambda stop: abs(int(stop["lap"]) - int(my_stop["lap"])))
    else:
        raise ToolError(f"{request.rival} made no pit stop in the {request.label()}.")

    my_lap, their_lap = int(my_stop["lap"]), int(their_stop["lap"])
    # From the line before the first in-lap to the line after the last out-lap: both stops fully inside.
    lap_before, lap_after = min(my_lap, their_lap) - 1, max(my_lap, their_lap) + 1
    gaps = gaps_at_line(mine, theirs)
    if lap_before not in gaps or lap_after not in gaps:
        missing = lap_before if lap_before not in gaps else lap_after
        raise ToolError(f"No gap at the end of lap {missing}: one of the drivers did not complete it.")

    position_before, rival_before = _position(mine, lap_before), _position(theirs, lap_before)
    position_after, rival_after = _position(mine, lap_after), _position(theirs, lap_after)
    gap_before, gap_after = gaps[lap_before], gaps[lap_after]
    return PitCycleOutput(
        season=request.season,
        round=request.round,
        session=request.session,
        driver=request.driver,
        rival=request.rival,
        driver_stop_lap=my_lap,
        rival_stop_lap=their_lap,
        kind="undercut" if my_lap < their_lap else "overcut" if my_lap > their_lap else "same_lap",
        lap_before=lap_before,
        lap_after=lap_after,
        gap_before_s=gap_before,
        gap_after_s=gap_after,
        gained_s=round(gap_before - gap_after, 3),
        position_before=position_before,
        rival_position_before=rival_before,
        position_after=position_after,
        rival_position_after=rival_after,
        driver_passed_rival=gap_before > 0 > gap_after,
        rival_passed_driver=gap_before < 0 < gap_after,
        neutralized=any(
            is_neutralized(laps[lap]["track_status"])
            for laps in (mine, theirs)
            for lap in range(lap_before + 1, lap_after + 1)
            if lap in laps
        ),
    )


def _stop(stops: list[dict[str, Any]], driver: str, stop_number: int) -> dict[str, Any]:
    for stop in stops:
        if stop["stop_number"] == stop_number:
            return stop
    raise ToolError(f"{driver} has no stop {stop_number}; stops made: {len(stops)}.")


def _position(laps: dict[int, dict[str, Any]], lap: int) -> int | None:
    return integer(laps[lap]["position"]) if lap in laps else None
