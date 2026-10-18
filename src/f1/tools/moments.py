"""The moments that made a race, found and ranked by code: the "top 5" debrief tells the first five.

Each moment is measured: places gained or lost, seconds gained on a pit cycle or saved by a stop under a safety
car. The ranking is an editorial rule, written here and in docs/tools.md, never a model's choice: a moment is worth
the championship points it moved, as if the race had ended there (a pass for the lead, 7 points; from 15th to 10th,
1), places breaking ties; and no kind of moment, no driver, fills the whole top.
"""

import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.tools import ToolError
from f1.tools.data import RaceData, SessionRef, integer, is_neutralized, number
from f1.tools.neutralizations import find_periods
from f1.tools.pit_cycle import PitCycleInput, pit_cycle
from f1.tools.pit_loss import StopLoss, stop_loss

MomentKind = Literal[
    "start", "overtakes", "pit_cycle", "neutralized_stop", "slow_stop", "strategy", "setback", "retirement"
]
TOP = 5
# The points of each place, race and sprint: what a place is worth.
POINTS = {"R": [25, 18, 15, 12, 10, 8, 6, 4, 2, 1], "S": [8, 7, 6, 5, 4, 3, 2, 1]}
# Places count a tenth of a point: they order the moments outside the points, and break ties.
PLACE = 0.1
# A moment is kept when it is worth this much: 2 places at the start, from an unusual strategy or lost on a green
# lap without a stop (an off, a problem); 2 passes on track, or 1 that moved points; a pass on a pit cycle; 5 s
# saved by a stop under a safety car, or lost by a stop against the others'; and every retirement.
MIN_PLACES = 2
MIN_SAVED_S = 5.0
# Two stops more than this many laps apart are not one pit cycle: the drivers were not fighting with their stops.
CYCLE_LAPS = 15
# A stop is compared with the stops made within this many laps, under the same conditions, when there are enough:
# when the whole field changes to intermediates, the stop to compare with is theirs, not a dry one.
NEAR_LAPS = 3
ENOUGH_STOPS = 3
PER_KIND = 2  # in the top: at most two moments of a kind, and two of a driver
PER_DRIVER = 2


class MomentsInput(SessionRef):
    pass


class Moment(BaseModel):
    rank: int = Field(description="1 is the moment that weighed most")
    kind: MomentKind = Field(
        description="start: places gained or lost on lap 1; overtakes: passes on track (no stop, no neutralization "
        "on the lap); pit_cycle: a pass made by the stops, undercut or overcut; neutralized_stop: a stop under a "
        "safety car or VSC, cheaper than the race's usual stop; slow_stop: a stop that cost much more than the others' "
        "(a slow stop, an off on the in-lap); strategy: a number of stops unlike most drivers'; "
        "setback: places lost on a green flag lap without a stop; retirement: out of the race"
    )
    lap: int = Field(description="When it happened: the first lap of the moment")
    driver: str = Field(description="Who it is about: the driver who gained, or lost")
    rival: str | None = Field(None, description="pit_cycle: the driver passed by the stops")
    places: int = Field(description="Places gained (negative: lost); for overtakes, the passes on track")
    seconds: float | None = Field(
        None,
        description="pit_cycle: gained on the rival over the cycle; neutralized_stop: saved on the usual stop; "
        "slow_stop: lost on top of the usual stop",
    )
    laps: list[int] = Field(default_factory=list, description="overtakes: the lap of each pass; else the stop laps")
    passed: list[str] = Field(default_factory=list, description="overtakes: the drivers passed, in order")
    from_position: int | None = Field(
        None,
        description="start, strategy: grid; neutralized_stop, slow_stop: before the stop; setback: before the lap; "
        "retirement: on the driver's last lap",
    )
    to_position: int | None = Field(
        None,
        description="start: after lap 1; strategy: finish; neutralized_stop: after the neutralization; slow_stop: "
        "after the out-lap; setback: after the lap",
    )
    status: str | None = Field(None, description="retirement: the official reason")
    outcome: Literal["undercut_worked", "overcut_worked"] | None = None
    stops: int | None = Field(None, description="strategy: the driver's stops")
    usual_stops: int | None = Field(None, description="strategy: what most drivers made")
    red_flag_changes: list[int] = Field(
        default_factory=list, description="strategy: laps of tyre changes under a red flag, not counted as stops"
    )
    neutralization: Literal["safety_car", "virtual_safety_car", "red_flag"] | None = None
    score: float = Field(description="The points the moment moved, as if the race had ended there, plus a tenth "
                         "of a point a place")  # fmt: skip


class MomentsOutput(BaseModel):
    season: int
    round: int
    session: str
    moments: list[Moment] = Field(description=f"The first {TOP}, by rank")
    candidates: int = Field(description="Moments found before the ranking kept the first ones")


def key_moments(data: RaceData, request: MomentsInput) -> MomentsOutput:
    cached, worth = _Cached(data), Worth(request.session)
    laps = _by_driver(cached.laps(request))
    results = {str(row["driver"]): row for row in cached.results(request.season, request.round, request.session)}
    if not results:
        raise ToolError(f"No classification for the {request.label()}.")
    found = [
        *_start(laps, results, worth),
        *_overtakes(laps, worth),
        *_cycles(cached, request, laps, worth),
        *_neutralized_stops(cached, request, laps, worth),
        *_slow_stops(cached, request, laps, worth),
        *_strategies(cached, request, results, worth),
        *_setbacks(laps, worth),
        *_retirements(laps, results, worth),
    ]
    found.sort(key=lambda moment: (-moment.score, moment.lap))
    top: list[Moment] = []
    kinds: Counter[str] = Counter()
    drivers: Counter[str] = Counter()
    for moment in found:
        if kinds[moment.kind] >= PER_KIND or drivers[moment.driver] >= PER_DRIVER:
            continue
        top.append(moment.model_copy(update={"rank": len(top) + 1}))
        kinds[moment.kind] += 1
        drivers[moment.driver] += 1
        if len(top) == TOP:
            break
    return MomentsOutput(
        season=request.season, round=request.round, session=request.session, moments=top, candidates=len(found)
    )


class Worth:
    """What a change of place is worth: the points between the two places, and a tenth of a point a place."""

    def __init__(self, session: str) -> None:
        self._points = POINTS.get(session, POINTS["R"])

    def points(self, position: int | None) -> int:
        return self._points[position - 1] if position and position <= len(self._points) else 0

    def between(self, before: int | None, after: int | None) -> float:
        if before is None or after is None:
            return 0.0
        return round(abs(self.points(before) - self.points(after)) + abs(before - after) * PLACE, 2)


Laps = Mapping[str, Mapping[int, dict[str, Any]]]


def _by_driver(rows: Sequence[dict[str, Any]]) -> dict[str, dict[int, dict[str, Any]]]:
    laps: dict[str, dict[int, dict[str, Any]]] = {}
    for lap in rows:
        if not lap["fastf1_generated"]:
            laps.setdefault(str(lap["driver"]), {})[int(lap["lap_number"])] = lap
    return laps


def _position(laps: Laps, driver: str, lap: int) -> int | None:
    row = laps.get(driver, {}).get(lap)
    return integer(row["position"]) if row else None


def _start(laps: Laps, results: Mapping[str, dict[str, Any]], worth: Worth) -> list[Moment]:
    moments = []
    for driver, result in results.items():
        grid, after = integer(result.get("grid_position")), _position(laps, driver, 1)
        if not grid or after is None or abs(grid - after) < MIN_PLACES:  # grid 0: a pit lane start
            continue
        places = grid - after
        moments.append(
            Moment(
                rank=0,
                kind="start",
                lap=1,
                driver=driver,
                places=places,
                from_position=grid,
                to_position=after,
                score=worth.between(grid, after),
            )
        )
    return moments


def _stopped(lap: dict[str, Any] | None) -> bool:
    return lap is None or number(lap["pit_in_session_s"]) is not None or number(lap["pit_out_session_s"]) is not None


def passes(laps: Laps) -> list[tuple[int, str, str, int]]:
    """Every pass on track: at the end of lap n, `driver` is ahead of `passed`, who was ahead at the end of lap n-1;
    neither stopped on either lap, and the lap saw no safety car, VSC or red flag. (lap, driver, passed, position)."""
    found = []
    last = max((lap for mine in laps.values() for lap in mine), default=0)
    for n in range(2, last + 1):
        here = {driver: mine for driver, mine in laps.items() if n in mine and n - 1 in mine}
        for driver, passed in combinations(sorted(here), 2):
            for a, b in ((driver, passed), (passed, driver)):
                was = integer(here[a][n - 1]["position"]), integer(here[b][n - 1]["position"])
                now = integer(here[a][n]["position"]), integer(here[b][n]["position"])
                if None in was or None in now or not (was[0] > was[1] and now[0] < now[1]):  # type: ignore[operator]
                    continue
                rows = (here[a][n], here[b][n], here[a][n - 1], here[b][n - 1])
                if any(_stopped(row) for row in rows) or any(is_neutralized(row["track_status"]) for row in rows[:2]):
                    continue
                found.append((n, a, b, int(now[0])))  # type: ignore[arg-type]
    return sorted(found)


def _overtakes(laps: Laps, worth: Worth) -> list[Moment]:
    by_driver: dict[str, list[tuple[int, str, int]]] = {}
    for lap, driver, passed, position in passes(laps):
        by_driver.setdefault(driver, []).append((lap, passed, position))
    moments = []
    for driver, made in by_driver.items():
        score = round(sum(worth.between(position + 1, position) for _, _, position in made), 2)
        if len(made) < MIN_PLACES and score <= PLACE:  # a single pass outside the points
            continue
        moments.append(
            Moment(
                rank=0,
                kind="overtakes",
                lap=made[0][0],
                driver=driver,
                places=len(made),
                laps=[lap for lap, _, _ in made],
                passed=[passed for _, passed, _ in made],
                score=score,
            )
        )
    return moments


def _setbacks(laps: Laps, worth: Worth) -> list[Moment]:
    """Places lost in one green flag lap without a stop: an off, a spin, a problem. The data says how many, not
    why."""
    moments = []
    for driver, mine in laps.items():
        for n, lap in mine.items():
            before = mine.get(n - 1)
            if n < 2 or before is None or _stopped(lap) or _stopped(before) or is_neutralized(lap["track_status"]):
                continue
            was, now = integer(before["position"]), integer(lap["position"])
            if was is None or now is None or now - was < MIN_PLACES:
                continue
            moments.append(
                Moment(
                    rank=0,
                    kind="setback",
                    lap=n,
                    driver=driver,
                    places=was - now,
                    laps=[n],
                    from_position=was,
                    to_position=now,
                    score=worth.between(was, now),
                )
            )
    return moments


def _retirements(laps: Laps, results: Mapping[str, dict[str, Any]], worth: Worth) -> list[Moment]:
    """A driver out of the race: worth the points of the place they held, and a place for every car behind."""
    moments = []
    for driver, result in results.items():
        if str(result.get("classified_position")) != "R" or not laps.get(driver):
            continue
        last = max(laps[driver])
        position = _position(laps, driver, last)
        status = result.get("status")
        moments.append(
            Moment(
                rank=0,
                kind="retirement",
                lap=last,
                driver=driver,
                places=0,
                laps=[last],
                from_position=position,
                status=status if isinstance(status, str) else None,
                score=worth.between(position, len(results) + 1),
            )
        )
    return moments


def _cycles(data: RaceData, ref: SessionRef, laps: Laps, worth: Worth) -> list[Moment]:
    """Each pass made by the stops: two drivers who stopped within CYCLE_LAPS laps of each other, on different laps,
    without a neutralization, and swapped places (`pit_cycle`, told from the one who came out ahead)."""
    stops = {driver: data.pit_stops(ref, driver) for driver in laps}
    moments: dict[tuple[str, str, int, int], Moment] = {}
    for driver, rival in combinations(sorted(laps), 2):
        for mine in stops[driver]:
            for theirs in stops[rival]:
                apart = abs(int(mine["lap"]) - int(theirs["lap"]))
                if apart == 0 or apart > CYCLE_LAPS or mine["red_flag"] or theirs["red_flag"]:
                    continue
                try:
                    cycle = pit_cycle(data, PitCycleInput(
                        season=ref.season, round=ref.round, session=ref.session, driver=driver, rival=rival,
                        driver_stop=int(mine["stop_number"]), rival_stop=int(theirs["stop_number"]),
                    ))  # fmt: skip
                except ToolError:
                    continue
                if cycle.neutralized or cycle.outcome not in {"undercut_worked", "overcut_worked"}:
                    continue
                winner = cycle.ahead_after
                loser = rival if winner == driver else driver
                gained = cycle.gained_s if winner == driver else -cycle.gained_s
                position = cycle.position_after if winner == driver else cycle.rival_position_after
                key = (winner, loser, cycle.driver_stop_lap, cycle.rival_stop_lap)
                moments[key] = Moment(
                    rank=0,
                    kind="pit_cycle",
                    lap=min(cycle.driver_stop_lap, cycle.rival_stop_lap),
                    driver=winner,
                    rival=loser,
                    places=1,
                    seconds=round(gained, 3),
                    laps=sorted({cycle.driver_stop_lap, cycle.rival_stop_lap}),
                    outcome=cycle.outcome,
                    score=worth.between(position + 1 if position else None, position),
                )
    return list(moments.values())


def _neutralized_stops(data: RaceData, ref: SessionRef, laps: Laps, worth: Worth) -> list[Moment]:
    """A stop under a safety car or VSC, against the median cost of the race's green flag stops."""
    losses = _losses(data, ref, laps)
    usual = [loss.time_lost_s for _, loss in losses if not loss.neutralized and loss.time_lost_s is not None]
    if not usual:
        return []
    median = statistics.median(usual)
    messages = data.race_control_messages(ref)
    periods = find_periods(messages) if messages else []
    moments = []
    for driver, loss in losses:
        if not loss.neutralized or loss.time_lost_s is None or median - loss.time_lost_s < MIN_SAVED_S:
            continue
        period = next((p for p in periods if p.start_lap <= loss.lap + 1 and loss.lap <= p.end_lap), None)
        before = _position(laps, driver, loss.lap - 1)
        after = _position(laps, driver, (period.end_lap if period else loss.lap) + 1)
        saved = round(median - loss.time_lost_s, 3)
        places = before - after if before is not None and after is not None else 0
        moments.append(
            Moment(
                rank=0,
                kind="neutralized_stop",
                lap=loss.lap,
                driver=driver,
                places=places,
                seconds=saved,
                laps=[loss.lap],
                from_position=before,
                to_position=after,
                neutralization=period.kind if period else None,
                score=round(worth.between(before, after) + saved / MIN_SAVED_S * PLACE, 2),
            )
        )
    return moments


def _losses(data: RaceData, ref: SessionRef, laps: Laps) -> list[tuple[str, StopLoss]]:
    """What each stop cost (`pit_stop_loss`), those under a red flag left out: their laps hold the stoppage."""
    return [
        (driver, loss)
        for driver, mine in laps.items()
        for loss in (stop_loss(mine, stop) for stop in data.pit_stops(ref, driver))
        if loss.time_lost_s is not None and not loss.red_flag
    ]


def _slow_stops(data: RaceData, ref: SessionRef, laps: Laps, worth: Worth) -> list[Moment]:
    """A stop that cost MIN_SAVED_S more than the usual one: the stops made near it under the same conditions
    (neutralized or not), or the race's when there are too few. The data says how much, not why."""
    losses = _losses(data, ref, laps)
    moments = []
    for driver, loss in losses:
        alike = [other for _, other in losses if other is not loss and other.neutralized == loss.neutralized]
        near = [other for other in alike if abs(other.lap - loss.lap) <= NEAR_LAPS]
        usual = [other.time_lost_s for other in (near if len(near) >= ENOUGH_STOPS else alike)]
        if len(usual) < ENOUGH_STOPS or loss.time_lost_s is None:
            continue
        normal = statistics.median(u for u in usual if u is not None)
        extra = round(loss.time_lost_s - normal, 3)
        if extra < MIN_SAVED_S:
            continue
        before, after = _position(laps, driver, loss.lap - 1), _position(laps, driver, loss.lap + 1)
        places = before - after if before is not None and after is not None else 0
        # Any stop loses places: the extra time's share of the stop is its share of the points they were worth.
        share = min(1.0, extra / loss.time_lost_s)
        moments.append(
            Moment(
                rank=0,
                kind="slow_stop",
                lap=loss.lap,
                driver=driver,
                places=places,
                seconds=extra,
                laps=[loss.lap],
                from_position=before,
                to_position=after,
                score=round(worth.between(before, after) * share, 2),
            )
        )
    return moments


def _strategies(data: RaceData, ref: SessionRef, results: Mapping[str, dict[str, Any]], worth: Worth) -> list[Moment]:
    """A driver who made more or fewer stops than most, and gained places from the grid with it. A tyre change under
    a red flag costs nothing and is not a stop: at São Paulo 2024, Verstappen made none before the red flag."""
    stops = {driver: sum(not stop["red_flag"] for stop in data.pit_stops(ref, driver)) for driver in results}
    classified = [driver for driver, result in results.items() if str(result.get("classified_position")).isdigit()]
    if not classified:
        return []
    usual = Counter(stops[driver] for driver in classified).most_common(1)[0][0]
    moments = []
    for driver in classified:
        grid, finish = integer(results[driver].get("grid_position")), integer(results[driver].get("position"))
        if stops[driver] == usual or not grid or finish is None or grid - finish < MIN_PLACES:
            continue
        own = data.pit_stops(ref, driver)
        stop_laps = [int(stop["lap"]) for stop in own if not stop["red_flag"]]
        changes = [int(stop["lap"]) for stop in own if stop["red_flag"]]
        moments.append(
            Moment(
                rank=0,
                kind="strategy",
                lap=min([*stop_laps, *changes], default=1),
                driver=driver,
                places=grid - finish,
                laps=stop_laps,
                from_position=grid,
                to_position=finish,
                stops=stops[driver],
                usual_stops=usual,
                red_flag_changes=changes,
                score=worth.between(grid, finish),
            )
        )
    return moments


class _Cached(RaceData):
    """The race read once: the pit cycles of every pair of drivers would query the lake hundreds of times."""

    def __init__(self, data: RaceData) -> None:
        super().__init__(data._db)
        self._cache: dict[tuple[Any, ...], list[dict[str, Any]]] = {}

    def _rows(self, table: str, ref: SessionRef, *, order: str) -> list[dict[str, Any]]:
        key = (table, ref.season, ref.round, ref.session, order)
        if key not in self._cache:
            self._cache[key] = super()._rows(table, ref, order=order)
        return self._cache[key]
