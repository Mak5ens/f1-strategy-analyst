"""Tyre degradation of a driver's stints: the slope of lap time against tyre age, fuel effect removed."""

import statistics
from collections import Counter
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from core.tools import ToolError
from f1.tools.data import DriverCode, RaceData, SessionRef, integer, is_clean, number

# Assumption: a car is about 0.06 s per lap faster for each lap of fuel burnt (about 1.8 kg per lap at about
# 0.035 s per kg, the order of magnitude teams and broadcasters give). Without this correction, the fuel burnt
# hides part of the tyre wear and the slopes come out too low.
DEFAULT_FUEL_EFFECT_S_PER_LAP = 0.06
# A clean lap more than 3% slower than the stint median was disturbed (traffic, a mistake, a yellow flag
# the track status missed): it says nothing about the tyres.
OUTLIER_RATIO = 1.03
MIN_LAPS = 5


class DegradationInput(SessionRef):
    driver: DriverCode
    stint: int | None = Field(None, ge=1, description="Stint number; every stint of the driver if omitted")
    fuel_effect_s_per_lap: float = Field(
        DEFAULT_FUEL_EFFECT_S_PER_LAP, ge=0, le=0.2, description="Lap time gained per lap of fuel burnt"
    )


class StintDegradation(BaseModel):
    stint: int
    compound: str | None
    start_lap: int
    end_lap: int
    laps_used: int = Field(description="Clean laps the slope is computed on")
    excluded: dict[str, int] = Field(description="Laps left out, by reason")
    degradation_s_per_lap: float | None = Field(
        description="Lap time lost per lap of tyre age, fuel effect removed. None below 5 clean laps"
    )
    raw_slope_s_per_lap: float | None = Field(description="Same slope on raw lap times, fuel effect included")
    r_squared: float | None = Field(description="Share of the lap time variation the tyre age explains")
    median_lap_s: float | None
    note: str | None = None


class DegradationOutput(BaseModel):
    season: int
    round: int
    session: str
    driver: str
    fuel_effect_s_per_lap: float
    stints: list[StintDegradation]


def stint_degradation(data: RaceData, request: DegradationInput) -> DegradationOutput:
    laps = data.driver_laps(request, request.driver)
    stints: dict[int, list[dict[str, Any]]] = {}
    for _, lap in sorted(laps.items()):
        if (stint := integer(lap["stint"])) is not None:
            stints.setdefault(stint, []).append(lap)
    if request.stint is not None:
        if request.stint not in stints:
            raise ToolError(f"{request.driver} has no stint {request.stint}; stints: {sorted(stints)}.")
        stints = {request.stint: stints[request.stint]}

    return DegradationOutput(
        season=request.season,
        round=request.round,
        session=request.session,
        driver=request.driver,
        fuel_effect_s_per_lap=request.fuel_effect_s_per_lap,
        stints=[_stint(stint, stint_laps, request.fuel_effect_s_per_lap) for stint, stint_laps in stints.items()],
    )


def _stint(stint: int, laps: list[dict[str, Any]], fuel_effect: float) -> StintDegradation:
    excluded: Counter[str] = Counter()
    clean = []
    for lap in laps:
        if is_clean(lap):
            clean.append(lap)
        else:
            excluded[_exclusion_reason(lap)] += 1
    if clean:
        median = statistics.median(float(lap["lap_time_s"]) for lap in clean)
        kept = [lap for lap in clean if float(lap["lap_time_s"]) <= median * OUTLIER_RATIO]
        if len(kept) < len(clean):
            excluded["slow outlier"] += len(clean) - len(kept)
        clean = kept

    summary = StintDegradation(
        stint=stint,
        compound=laps[0]["compound"] if isinstance(laps[0]["compound"], str) else None,
        start_lap=int(laps[0]["lap_number"]),
        end_lap=int(laps[-1]["lap_number"]),
        laps_used=len(clean),
        excluded=dict(excluded),
        degradation_s_per_lap=None,
        raw_slope_s_per_lap=None,
        r_squared=None,
        median_lap_s=round(statistics.median(float(lap["lap_time_s"]) for lap in clean), 3) if clean else None,
    )
    if len(clean) < MIN_LAPS:
        summary.note = f"Only {len(clean)} clean laps: at least {MIN_LAPS} are needed for a slope."
        return summary

    age = np.array([number(lap["tyre_life"]) or float(lap["lap_number"]) for lap in clean])
    lap_number = np.array([float(lap["lap_number"]) for lap in clean])
    raw = np.array([float(lap["lap_time_s"]) for lap in clean])
    # Each lap the car is lighter: add back what the fuel burnt since lap 1 gave, to compare at equal weight.
    corrected = raw + fuel_effect * (lap_number - 1)
    slope, intercept = np.polyfit(age, corrected, 1)
    raw_slope = np.polyfit(age, raw, 1)[0]
    residuals = corrected - (slope * age + intercept)
    total = float(np.sum((corrected - corrected.mean()) ** 2))
    summary.degradation_s_per_lap = round(float(slope), 4)
    summary.raw_slope_s_per_lap = round(float(raw_slope), 4)
    summary.r_squared = round(1 - float(np.sum(residuals**2)) / total, 3) if total > 0 else None
    return summary


def _exclusion_reason(lap: dict[str, Any]) -> str:
    if lap["lap_number"] == 1:
        return "standing start"
    if number(lap["pit_in_session_s"]) is not None or number(lap["pit_out_session_s"]) is not None:
        return "in or out lap"
    if lap["track_status"] != "1":
        return "not green flag"
    if lap["deleted"]:
        return "deleted"
    return "no lap time"
