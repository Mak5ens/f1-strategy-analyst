"""What another strategy would have given a driver (LAB-213): the same stops on other laps, projected by code.

A model, not a measure. It projects the difference between the strategy asked and the one raced, lap by lap, and adds
it to the times the driver really set: what both strategies share (the driver's level, the fuel, the laps under a
safety car, the traffic the race had) cancels out. On each lap:

- under a neutralization in the race, no difference: the lap was set by the safety car, whatever the tyres;
- else the difference of the two stints' lines at that lap, each the `degradation` tool's fuel-corrected line
  (lap time = intercept + degradation * tyre age - fuel effect * (lap - 1)): moving a stop changes the tyre age, and
  on which stint the lap falls;
- on a stint run on another compound, its own line shifted by what that compound changes to a line in this race
  (`degradation.compound_shift`: the median, over the other drivers who ran both compounds, of the difference of their
  own lines), so that the driver's level stays theirs;
- and the stops' cost, moved with them: what the driver's green-flag stops cost (`pit_stop_loss`, median), or what
  the stops under a neutralization cost in this race, when the new in- or out-lap is neutralized.

What it does not know: traffic and overtaking the new strategy would have met, safety cars it would have met
differently, a set of tyres other than the one raced for a new compound (the age it was fitted at is kept), and
a stint run beyond the tyre ages it was fitted on (the line is extended, and the laps are counted).

Not a tool of the agent: the analyst reads its refusals on the simulator, so they are written in French.
"""

import statistics
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from pydantic import BaseModel, Field

from core.tools import ToolError
from f1.evals.simulation import compound_error, expected_error
from f1.tools.data import DriverCode, RaceData, SessionRef, integer, is_neutralized, number
from f1.tools.degradation import DEFAULT_FUEL_EFFECT_S_PER_LAP, StintFit, by_stint, compound_shift, fit, race_fits, wear
from f1.tools.pit_loss import stop_loss


class SimulationInput(SessionRef):
    driver: DriverCode
    stops: list[int] | None = Field(
        None, description="The in-laps of the strategy asked, one per stop raced, in order; the ones raced if omitted"
    )
    rival: DriverCode | None = Field(None, description="The driver the gaps are measured to; the leader if omitted")
    compounds: list[str | None] | None = Field(
        None, description="The compound of each stint asked, in order; None (or omitted) keeps the one raced"
    )


DRY = ("SOFT", "MEDIUM", "HARD")


class SimulatedLap(BaseModel):
    lap: int
    difference_s: float = Field(description="Time the strategy asked gains (negative) or loses on this lap")
    raced_gap_s: float | None = Field(description="Gap to the rival (or the leader) at the line, as raced")
    projected_gap_s: float | None
    raced_position: int | None
    projected_position: int | None


class SimulatedStint(BaseModel):
    compound: str | None = Field(description="The compound asked: the one raced unless another was chosen")
    raced_compound: str | None
    raced_from: int = Field(description="First lap raced on it")
    raced_to: int
    asked_from: int = Field(description="First lap on it in the strategy asked")
    asked_to: int
    degradation_s_per_lap: float | None
    extrapolated_laps: int = Field(description="Laps asked at tyre ages beyond those the line was fitted on")


class ExpectedError(BaseModel):
    """The error measured on real stints' lines extended by as many laps (`f1.evals.simulation`)."""

    laps_from: int = Field(description="The range of laps extended this error was measured on")
    laps_to: int
    samples: int
    median_s: float = Field(description="Median absolute error on the time of those laps")
    p90_s: float
    bias_s: float = Field(description="Median signed error: negative, the line projects them too fast")
    season: int


class SimulationOutput(BaseModel):
    season: int
    round: int
    session: str
    driver: str
    rival: str | None
    raced_stops: list[int]
    stops: list[int]
    stints: list[SimulatedStint]
    green_stop_loss_s: float = Field(description="What a green-flag stop costs the driver: the median measured")
    neutralized_stop_loss_s: float | None = Field(description="What a stop under a neutralization cost in this race")
    time_difference_s: float = Field(description="Race time of the strategy asked less the one raced: negative, gains")
    laps: list[SimulatedLap]
    model_error_s: float = Field(description="Root mean square error of the stints' lines on the clean laps fitted")
    extended_laps: int = Field(description="The most laps a stint runs beyond its length as raced")
    expected_error: ExpectedError | None = Field(
        None, description="The error measured on real stints extended as much; None with no extension or no report"
    )
    compound_error: ExpectedError | None = Field(
        None, description="The error measured on real stints projected from another compound; None if none changes"
    )
    notes: list[str] = Field(default_factory=list)


def simulate_strategy(data: RaceData, request: SimulationInput) -> SimulationOutput:
    every = data.laps(request)
    mine = {int(lap["lap_number"]): lap for lap in every if lap["driver"] == request.driver}
    if not mine:
        raise ToolError(f"aucun pilote {request.driver} dans cette course.")
    stops = [stop for stop in data.pit_stops(request, request.driver) if not stop.get("red_flag")]
    raced = [int(stop["lap"]) for stop in stops]
    last = max(mine)
    asked = raced if request.stops is None else request.stops
    _check(asked, raced, last)

    stints = list(by_stint(mine).items())
    if len(stints) != len(raced) + 1:
        raise ToolError(f"les relais de {request.driver} ne suivent pas ses {len(raced)} arrêts.")
    fits = [fit(number_, stint_laps) for number_, stint_laps in stints]
    for (number_, _), one in zip(stints, fits, strict=True):
        if one.intercept_s is None or one.summary.degradation_s_per_lap is None:
            raise ToolError(
                f"le relais {number_} de {request.driver} n'a que {one.summary.laps_used} tours propres, il en faut 5 "
                "pour projeter son rythme."
            )

    raced_compounds = [one.summary.compound for one in fits]
    asked_compounds = _compounds(request.compounds, raced_compounds)
    lines = _lines(every, request.driver, fits, raced_compounds, asked_compounds)

    green, neutralized = _losses(data, request, every, mine, stops)
    raced_bounds = _bounds(raced, last)
    asked_bounds = _bounds(asked, last)
    first_age = [integer(stint_laps[0]["tyre_life"]) or 1 for _, stint_laps in stints]

    raced_lines = [_own(one) for one in fits]

    def lap_time(lap: int, bounds: Sequence[tuple[int, int]], by: Sequence[Line]) -> float:
        k = next(index for index, (start, end) in enumerate(bounds) if start <= lap <= end)
        return wear(*by[k], first_age[k] + lap - bounds[k][0])  # the fuel is the same lap: it cancels

    def stop_cost(in_lap: int) -> float:
        quiet = not any(is_neutralized(mine.get(lap, {}).get("track_status")) for lap in (in_lap, in_lap + 1))
        if quiet:
            return green
        if neutralized is None:
            raise ToolError(
                f"aucun arrêt sous neutralisation n'a été mesuré dans cette course : le tour {in_lap} ne peut pas être "
                "chiffré."
            )
        return neutralized

    differences: dict[int, float] = {}
    for lap in range(1, last + 1):
        neutral = is_neutralized(mine.get(lap, {}).get("track_status"))
        if not (neutral or lap == 1):
            differences[lap] = lap_time(lap, asked_bounds, lines) - lap_time(lap, raced_bounds, raced_lines)
        else:
            differences[lap] = 0.0
    for in_lap in raced:
        differences[min(in_lap + 1, last)] -= stop_cost(in_lap)
    for in_lap in asked:
        differences[min(in_lap + 1, last)] += stop_cost(in_lap)

    laps = _laps(every, mine, differences, request.rival)
    changed = [
        end - start + 1 for k, (start, end) in enumerate(asked_bounds) if asked_compounds[k] != raced_compounds[k]
    ]
    return SimulationOutput(
        season=request.season,
        round=request.round,
        session=request.session,
        driver=request.driver,
        rival=request.rival,
        raced_stops=raced,
        stops=list(asked),
        stints=[
            SimulatedStint(
                compound=asked_compounds[k],
                raced_compound=one.summary.compound,
                raced_from=raced_bounds[k][0],
                raced_to=raced_bounds[k][1],
                asked_from=asked_bounds[k][0],
                asked_to=asked_bounds[k][1],
                degradation_s_per_lap=round(lines[k].slope, 4),
                extrapolated_laps=_extrapolated(one, first_age[k], raced_bounds[k], asked_bounds[k]),
            )
            for k, one in enumerate(fits)
        ],
        green_stop_loss_s=green,
        neutralized_stop_loss_s=neutralized,
        time_difference_s=round(sum(differences.values()), 3),
        laps=laps,
        model_error_s=_error(fits, mine),
        extended_laps=(extended := _extended(raced_bounds, asked_bounds)),
        expected_error=_expected(expected_error(extended, request.season)),
        compound_error=_expected(compound_error(max(changed), request.season) if changed else None),
        notes=_notes(fits, first_age, raced_bounds, asked_bounds),
    )


def _expected(found: dict[str, Any] | None) -> ExpectedError | None:
    if found is None:
        return None
    (low, high), rest = found["laps"], {key: value for key, value in found.items() if key != "laps"}
    return ExpectedError(laps_from=low, laps_to=high, **rest)


class Line(NamedTuple):
    """A stint's line as `degradation.wear` reads it: bent past the last tyre age it was fitted on."""

    intercept: float
    slope: float
    curvature: float
    last_age: float


def _own(line: StintFit) -> Line:
    assert line.intercept_s is not None and line.summary.degradation_s_per_lap is not None
    last = line.ages[1] if line.ages else 0
    return Line(line.intercept_s, line.summary.degradation_s_per_lap, line.curvature_s, last)


def _compounds(asked: Sequence[str | None] | None, raced: Sequence[str | None]) -> list[str | None]:
    """The compound of each stint asked, and the rule a dry race asks: two dry compounds at least."""
    if asked is None:
        return list(raced)
    if len(asked) != len(raced):
        raise ToolError(f"le pilote a couru {len(raced)} relais : il faut un composé par relais.")
    found = [one.upper() if one else raced[k] for k, one in enumerate(asked)]
    if any(one is not None and one not in DRY for one, before in zip(found, raced, strict=True) if one != before):
        raise ToolError("seul un composé sec (tendre, médium ou dur) peut remplacer celui d'un relais.")
    dry = all(one in DRY for one in raced if one) and len({one for one in raced if one}) >= 2
    if dry and len({one for one in found if one}) < 2:
        raise ToolError(
            "en course sèche, le règlement sportif impose d'utiliser au moins deux composés secs différents."
        )
    return found


def _lines(
    every: Sequence[dict[str, Any]],
    driver: str,
    fits: Sequence[StintFit],
    raced: Sequence[str | None],
    asked: Sequence[str | None],
) -> list[Line]:
    """Each stint's line asked: the one raced, or shifted to the compound asked as the other drivers measure it."""
    lines, field = [], None
    for k, one in enumerate(fits):
        line = _own(one)
        before, after = raced[k], asked[k]
        if after != before:
            if before is None or after is None:
                raise ToolError(f"le composé du relais {k + 1} n'est pas connu : il ne peut pas être changé.")
            field = field if field is not None else race_fits(list(every))
            shift = compound_shift(field, before, after, exclude=driver)
            if shift is None:
                raise ToolError(
                    f"trop peu de pilotes ont couru en {_french(before)} et en {_french(after)} dans cette course pour "
                    "mesurer ce que change le composé."
                )
            # Not bent: the curvature measured is the compound raced's, and bending it projects worse (docs/tools.md).
            line = line._replace(
                intercept=line.intercept + shift.intercept_s,
                slope=line.slope + shift.degradation_s_per_lap,
                curvature=0.0,
            )
        lines.append(line)
    return lines


def _french(compound: str) -> str:
    return {"SOFT": "tendres", "MEDIUM": "médiums", "HARD": "durs"}.get(compound, compound.lower())


def _extended(raced: Sequence[tuple[int, int]], asked: Sequence[tuple[int, int]]) -> int:
    """The most laps a stint runs beyond its length as raced."""
    return max(0, *((a[1] - a[0]) - (r[1] - r[0]) for r, a in zip(raced, asked, strict=True)))


def _check(asked: Sequence[int], raced: Sequence[int], last: int) -> None:
    if len(asked) != len(raced):
        raise ToolError(f"le pilote s'est arrêté {len(raced)} fois : il faut un tour d'arrêt par arrêt.")
    if list(asked) != sorted(set(asked)) or any(lap < 2 or lap >= last for lap in asked):
        raise ToolError(f"les tours d'arrêt doivent se suivre, du tour 2 au tour {last - 1}.")


def _bounds(stops: Sequence[int], last: int) -> list[tuple[int, int]]:
    """Each stint's first and last lap: a stint ends on its in-lap."""
    starts = [1, *(stop + 1 for stop in stops)]
    ends = [*stops, last]
    return list(zip(starts, ends, strict=True))


def _losses(
    data: RaceData,
    ref: SessionRef,
    every: Sequence[Mapping[str, Any]],
    mine: Mapping[int, dict[str, Any]],
    stops: Sequence[dict[str, Any]],
) -> tuple[float, float | None]:
    """The driver's green-flag stop cost, and the race's stop cost under a neutralization (medians measured)."""
    green = [loss.time_lost_s for stop in stops if (loss := stop_loss(mine, stop)).time_lost_s and not loss.neutralized]
    if not green:
        raise ToolError(
            "aucun arrêt du pilote sous drapeau vert n'a été mesuré : le coût d'un arrêt ne peut pas être projeté."
        )
    neutral: list[float] = []
    for code in sorted({str(lap["driver"]) for lap in every}):
        laps = {int(lap["lap_number"]): dict(lap) for lap in every if lap["driver"] == code}
        for stop in data.pit_stops(ref, code):
            loss = stop_loss(laps, stop)
            if loss.neutralized and not loss.red_flag and loss.time_lost_s is not None:
                neutral.append(loss.time_lost_s)
    return round(statistics.median(green), 3), round(statistics.median(neutral), 3) if neutral else None


def _laps(
    every: Sequence[Mapping[str, Any]],
    mine: Mapping[int, dict[str, Any]],
    differences: Mapping[int, float],
    rival: str | None,
) -> list[SimulatedLap]:
    ends: dict[int, dict[str, float]] = {}
    for row in every:
        if (end := number(row["lap_end_session_s"])) is not None:
            ends.setdefault(int(row["lap_number"]), {})[str(row["driver"])] = end
    driver = str(next(iter(mine.values()))["driver"])
    rows, total = [], 0.0
    for lap in sorted(differences):
        total += differences[lap]
        at = ends.get(lap, {})
        raced = at.get(driver)
        if raced is None:
            continue
        reference = at.get(rival) if rival else min(at.values())
        projected = raced + total
        others = [end for code, end in at.items() if code != driver]
        rows.append(
            SimulatedLap(
                lap=lap,
                difference_s=round(differences[lap], 3),
                raced_gap_s=None if reference is None else round(raced - reference, 3),
                projected_gap_s=None if reference is None else round(projected - reference, 3),
                raced_position=1 + sum(end < raced for end in others),
                projected_position=1 + sum(end < projected for end in others),
            )
        )
    return rows


def _extrapolated(line: StintFit, first_age: int, raced: tuple[int, int], asked: tuple[int, int]) -> int:
    """Laps asked at tyre ages beyond both the stint raced and the laps its line was fitted on."""
    known = max(line.ages[1] if line.ages else 0, first_age + raced[1] - raced[0])
    return sum(age > known for age in range(first_age, first_age + asked[1] - asked[0] + 1))


def _error(fits: Sequence[StintFit], mine: Mapping[int, dict[str, Any]]) -> float:
    """How far the lines are from the laps they were fitted on: the model's error on one lap."""
    residuals = []
    for line in fits:
        assert line.intercept_s is not None and line.summary.degradation_s_per_lap is not None
        for lap in line.laps:
            row = mine[lap]
            age = number(row["tyre_life"]) or float(lap)
            model = line.intercept_s + line.summary.degradation_s_per_lap * age
            model -= DEFAULT_FUEL_EFFECT_S_PER_LAP * (lap - 1)
            residuals.append(float(row["lap_time_s"]) - model)
    return round((sum(r * r for r in residuals) / len(residuals)) ** 0.5, 3) if residuals else 0.0


def _notes(
    fits: Sequence[StintFit],
    first_age: Sequence[int],
    raced: Sequence[tuple[int, int]],
    asked: Sequence[tuple[int, int]],
) -> list[str]:
    notes = []
    for k, line in enumerate(fits):
        if extra := _extrapolated(line, first_age[k], raced[k], asked[k]):
            notes.append(f"stint {k + 1}: {extra} laps beyond the tyre ages it was fitted on, its line extended")
    return notes
