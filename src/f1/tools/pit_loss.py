"""Time a pit stop cost: in-lap and out-lap against two normal laps of the same driver."""

import statistics
from typing import Any

from pydantic import BaseModel, Field

from core.tools import ToolError
from f1.tools.data import DriverCode, RaceData, SessionRef, is_clean, is_neutralized, number

# Normal laps are taken among the clean laps up to 5 laps before the in-lap and after the out-lap: close enough
# for the same fuel and tyre state, far enough to find a few laps.
REFERENCE_WINDOW = 5


class PitLossInput(SessionRef):
    driver: DriverCode
    stop_number: int | None = Field(None, ge=1, description="Stop number; every stop of the driver if omitted")


class StopLoss(BaseModel):
    stop_number: int
    lap: int = Field(description="In-lap")
    pit_lane_time_s: float | None = Field(description="Pit entry line to pit exit line")
    stationary_time_s: float | None = Field(description="Car stopped in the box")
    in_and_out_laps_s: float | None = Field(
        description="Time from the line before the in-lap to the end of the out-lap"
    )
    reference_lap_s: float | None = Field(description="Median of the normal laps around the stop")
    reference_laps: int
    time_lost_s: float | None = Field(
        description="in_and_out_laps_s minus two reference laps: what the stop cost; none under a red flag"
    )
    compound_before: str | None
    compound_after: str | None
    neutralized: bool = Field(description="Safety car, VSC or red flag during the in- or out-lap: the stop cost less")
    red_flag: bool


class PitLossOutput(BaseModel):
    season: int
    round: int
    session: str
    driver: str
    stops: list[StopLoss]


def pit_stop_loss(data: RaceData, request: PitLossInput) -> PitLossOutput:
    laps = data.driver_laps(request, request.driver)
    stops = data.pit_stops(request, request.driver)
    if request.stop_number is not None:
        stops = [stop for stop in stops if stop["stop_number"] == request.stop_number]
    if not stops:
        which = f"stop {request.stop_number}" if request.stop_number else "pit stop"
        raise ToolError(f"{request.driver} made no {which} in the {request.label()}.")
    return PitLossOutput(
        season=request.season,
        round=request.round,
        session=request.session,
        driver=request.driver,
        stops=[stop_loss(laps, stop) for stop in stops],
    )


def stop_loss(laps: dict[int, dict[str, Any]], stop: dict[str, Any]) -> StopLoss:
    in_lap = int(stop["lap"])
    out_lap = in_lap + 1
    before, after = laps.get(in_lap - 1), laps.get(out_lap)
    start = number(before["lap_end_session_s"]) if before else None
    end = number(after["lap_end_session_s"]) if after else None
    in_and_out = round(end - start, 3) if start is not None and end is not None else None

    window = [*range(in_lap - REFERENCE_WINDOW, in_lap), *range(out_lap + 1, out_lap + 1 + REFERENCE_WINDOW)]
    reference_times = [float(laps[lap]["lap_time_s"]) for lap in window if lap in laps and is_clean(laps[lap])]
    reference = round(statistics.median(reference_times), 3) if reference_times else None

    return StopLoss(
        stop_number=int(stop["stop_number"]),
        lap=in_lap,
        pit_lane_time_s=number(stop["pit_lane_time_s"]),
        stationary_time_s=number(stop["stationary_time_s"]),
        in_and_out_laps_s=in_and_out,
        reference_lap_s=reference,
        reference_laps=len(reference_times),
        # Under a red flag, the two laps hold the stoppage: no cost to compare (a debrief quoted "1539 s" lost).
        time_lost_s=round(in_and_out - 2 * reference, 3)
        if in_and_out is not None and reference is not None and not stop["red_flag"]
        else None,
        compound_before=stop["compound_before"] if isinstance(stop["compound_before"], str) else None,
        compound_after=stop["compound_after"] if isinstance(stop["compound_after"], str) else None,
        neutralized=any(is_neutralized(laps[lap]["track_status"]) for lap in (in_lap, out_lap) if lap in laps),
        red_flag=bool(stop["red_flag"]),
    )
