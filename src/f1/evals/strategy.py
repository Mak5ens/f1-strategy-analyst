"""Strategy cases: who came out ahead when two drivers running next to each other made a stop, and why.

A rule reads the lake and the tools to find the main cause, then writes a reference with the facts behind it:
compounds and tyre age, stationary time and time lost of both stops, the gaps before and after, the pace between
the stops, traffic at the pit exit, a team's double stop, rain, a safety car or a VSC by name, a penalty served at
the stop. A cause the rule cannot settle gives no case.

Rules (LAB-201, after a person reviewed the first references):
- the stops compared are of the same rank (both drivers' 2nd stop), each the other's closest: a 1st stop is never
  compared with a rival's 2nd;
- a swap counts only when it holds a few laps after the later out-lap (or to the flag), not a position read in
  passing on an out-lap;
- a time penalty served at a stop is not a slow stop; a drive-through or a stop and go is not a strategic stop;
- an undercut is the winner stopping first, an overcut the winner stopping later;
- a question can rest on a false premise: the reference then says so first.
"""

import re
import statistics
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from core.tools import ToolError
from f1.evals import COMPOUNDS_FR
from f1.tools import RaceData
from f1.tools.data import SessionRef, integer, number
from f1.tools.penalties import Penalty, penalties
from f1.tools.pit_cycle import PitCycleInput, PitCycleOutput, pit_cycle
from f1.tools.pit_loss import PitLossInput, StopLoss, pit_stop_loss

HOLD_LAPS = 3  # laps after the later out-lap during which the new order must hold
MAX_LAPS_APART = 15  # stops further apart are not one pit cycle
MAX_SWING_S = 30.0  # a gap that moved more than this in a cycle: an incident (a spin, damage), not strategy
SLOW_STOP_S = 1.5  # stationary time over the rival's: a slow stop
DOUBLE_STACK_S = 2.0  # pit lane time over the race's median: the second car of a double stop waited
TRAFFIC_S = 1.5  # gap to the car ahead after the out-lap: stuck behind it
WET = {"INTERMEDIATE", "WET"}

NEUTRALIZATIONS_FR = {
    "4": "voiture de sécurité",
    "6": "voiture de sécurité virtuelle (VSC)",
    "7": "voiture de sécurité virtuelle (VSC)",
    "5": "drapeau rouge",
}


def served_at(
    stops: Sequence[dict[str, Any]], given: Sequence[Penalty], served: Sequence[tuple[str, int]]
) -> dict[tuple[str, int], list[Penalty]]:
    """Which stop served which penalty, by (driver, stop number).

    A time penalty is served at the driver's next stop. Race control says "PENALTY SERVED" since 2025: the stop is
    then the last one before that message; before, the first stop on or after the lap the penalty was given."""
    by_stop: dict[tuple[str, int], list[Penalty]] = {}
    used: set[tuple[str, int]] = set()
    for penalty in given:
        mine = [stop for stop in stops if stop["driver"] == penalty.driver and not stop["red_flag"]]
        laps = [lap for driver, lap in served if driver == penalty.driver and lap >= penalty.lap]
        candidates = (
            [stop for stop in mine if penalty.lap <= int(stop["lap"]) <= laps[0]][-1:]
            if laps
            else [stop for stop in mine if int(stop["lap"]) >= penalty.lap][:1]
        )
        for stop in candidates:
            key = (penalty.driver, int(stop["stop_number"]))
            if penalty.kind != "time" and key in used:
                continue
            by_stop.setdefault(key, []).append(penalty)
            used.add(key)
            if laps:
                served = [entry for entry in served if entry != (penalty.driver, laps[0])]
    return by_stop


def neutralization(statuses: Sequence[object]) -> str | None:
    """The neutralization seen during some laps, in French, the most constraining first."""
    seen = "".join(str(status) for status in statuses if status is not None)
    for code in "5467":
        if code in seen:
            return NEUTRALIZATIONS_FR[code]
    return None


@dataclass
class StopFacts:
    driver: str
    number: int  # rank among the strategic stops
    lap: int
    loss: StopLoss
    tyre_age: int | None  # laps on the set taken off
    fresh_after: bool | None
    pit_in_s: float | None
    neutralized_by: str | None  # under a safety car, a VSC or a red flag
    penalties: list[Penalty] = field(default_factory=list)
    teammate_ahead: str | None = None  # a teammate stopped just before, on the same lap
    pit_lane_excess_s: float | None = None  # over the race's median pit lane time
    traffic: tuple[str, float] | None = None  # (car ahead, gap) after the out-lap

    @property
    def penalty_s(self) -> float:
        return float(sum(penalty.seconds or 0 for penalty in self.penalties if penalty.kind == "time"))

    @property
    def stationary_s(self) -> float | None:
        """Stationary time less a time penalty served in the box."""
        value = self.loss.stationary_time_s
        return None if value is None else round(value - self.penalty_s, 1)


class RaceFacts:
    """What the strategy rule reads of one race, loaded once."""

    def __init__(
        self,
        data: RaceData,
        ref: SessionRef,
        names: dict[str, str],
        teams: dict[str, str],
        *,
        results: Sequence[dict[str, Any]] = (),
        decisions: Sequence[dict[str, Any]] = (),
    ) -> None:
        self.data, self.ref, self.names, self.teams = data, ref, names, teams
        self.results = {str(row["driver"]): row for row in results}
        self.decisions = decisions  # the stewards' decisions of the weekend, as the FIA corpus holds them
        laps = data.laps(ref)
        self.laps: dict[str, dict[int, dict[str, Any]]] = {}
        for lap in laps:
            self.laps.setdefault(str(lap["driver"]), {})[int(lap["lap_number"])] = lap
        self.raw_stops = [stop for driver in self.laps for stop in data.pit_stops(ref, driver)]
        given, served = penalties(data.race_control_messages(ref))
        self.given = given
        self.penalties = served_at(self.raw_stops, given, served)
        lanes = [
            value
            for stop in self.raw_stops
            if not stop["red_flag"] and (value := number(stop["pit_lane_time_s"])) is not None
        ]
        self.median_pit_lane = statistics.median(lanes) if lanes else None
        self.rain = self._rain(data, ref)
        self._stops: dict[str, list[StopFacts]] = {}

    def name(self, code: str) -> str:
        return self.names.get(code, code)

    def _rain(self, data: RaceData, ref: SessionRef) -> dict[int, bool] | None:
        """Lap -> rain fell during it, None without weather data."""
        weather = data.weather(ref)
        if not weather:
            return None
        rainy = [float(row["session_time_s"]) for row in weather if row["rainfall"]]
        by_lap: dict[int, bool] = {}
        for driver_laps in self.laps.values():
            for lap_number, lap in driver_laps.items():
                start, end = number(lap["lap_start_session_s"]), number(lap["lap_end_session_s"])
                if start is not None and end is not None:
                    wet = any(start - 60 <= t <= end for t in rainy)
                    by_lap[lap_number] = by_lap.get(lap_number, False) or wet
        return by_lap

    def stops(self, driver: str) -> list[StopFacts]:
        """The driver's strategic stops: not a red flag tyre change, not a drive-through or a stop and go."""
        if driver in self._stops:
            return self._stops[driver]
        try:
            losses = {
                stop.stop_number: stop
                for stop in pit_stop_loss(
                    self.data,
                    PitLossInput(season=self.ref.season, round=self.ref.round, session=self.ref.session, driver=driver),
                ).stops
            }
        except ToolError:
            losses = {}  # fmt: skip
        laps = self.laps.get(driver, {})
        facts: list[StopFacts] = []
        for stop in (s for s in self.raw_stops if s["driver"] == driver):
            number_ = int(stop["stop_number"])
            served = self.penalties.get((driver, number_), [])
            if stop["red_flag"] or number_ not in losses or any(p.kind != "time" for p in served):
                continue
            lap = int(stop["lap"])
            in_lap, out_lap = laps.get(lap), laps.get(lap + 1)
            facts.append(
                StopFacts(
                    driver=driver,
                    number=len(facts) + 1,
                    lap=lap,
                    loss=losses[number_],
                    tyre_age=integer(in_lap["tyre_life"]) if in_lap else None,
                    fresh_after=bool(out_lap["fresh_tyre"]) if out_lap and out_lap["fresh_tyre"] is not None else None,
                    pit_in_s=number(in_lap["pit_in_session_s"]) if in_lap else None,
                    neutralized_by=neutralization([laps[n]["track_status"] for n in (lap, lap + 1) if n in laps]),
                    penalties=served,
                    pit_lane_excess_s=(
                        round(lane - self.median_pit_lane, 1)
                        if (lane := losses[number_].pit_lane_time_s) is not None and self.median_pit_lane
                        else None
                    ),
                    traffic=self._traffic(driver, lap + 1),
                )
            )
        for made in facts:
            made.teammate_ahead = self._teammate_ahead(made)
        self._stops[driver] = facts
        return facts

    def _teammate_ahead(self, stop: StopFacts) -> str | None:
        team = self.teams.get(stop.driver)
        if not team or stop.pit_in_s is None:
            return None
        for other, laps in self.laps.items():
            if other == stop.driver or self.teams.get(other) != team or stop.lap not in laps:
                continue
            entered = number(laps[stop.lap]["pit_in_session_s"])
            if entered is not None and entered < stop.pit_in_s and stop.pit_in_s - entered < 30:
                return other
        return None

    def _traffic(self, driver: str, out_lap: int) -> tuple[str, float] | None:
        """The car right ahead after the out-lap and the next lap, within TRAFFIC_S both times."""
        mine = self.laps.get(driver, {})
        gaps = []
        for lap in (out_lap, out_lap + 1):
            row = mine.get(lap)
            position, end = (integer(row["position"]), number(row["lap_end_session_s"])) if row else (None, None)
            if position is None or position < 2 or end is None:
                return None
            ahead = next(
                (
                    (code, number(laps[lap]["lap_end_session_s"]))
                    for code, laps in self.laps.items()
                    if lap in laps and integer(laps[lap]["position"]) == position - 1
                ),
                None,
            )
            if ahead is None or ahead[1] is None or end - ahead[1] > TRAFFIC_S:
                return None
            gaps.append((ahead[0], round(end - ahead[1], 1)))
        return gaps[0] if gaps[0][0] == gaps[1][0] else None


@dataclass(frozen=True)
class Duel:
    """Two drivers next to each other before their stops of the same rank, and how it came out."""

    driver: str
    rival: str
    rank: int
    cycle: PitCycleOutput
    stops: dict[str, StopFacts]

    @property
    def swapped(self) -> bool:
        return self.cycle.driver_passed_rival or self.cycle.rival_passed_driver

    @property
    def ahead_after(self) -> str:
        return self.driver if self.cycle.gap_after_s < 0 else self.rival

    @property
    def ahead_before(self) -> str:
        return self.driver if self.cycle.gap_before_s < 0 else self.rival

    def gap_s(self, when: Literal["before", "after"]) -> float:
        return abs(self.cycle.gap_before_s if when == "before" else self.cycle.gap_after_s)


def duels(race: RaceFacts, top: Sequence[str]) -> Iterator[Duel]:
    """Each pair of the top drivers running next to each other before a pit cycle of the same rank."""
    for driver in top:
        for rival in top:
            if driver >= rival:
                continue
            mine, theirs = race.stops(driver), race.stops(rival)
            for a, b in zip(mine, theirs, strict=False):
                if not _paired(a, b, mine, theirs):
                    continue
                try:
                    cycle = pit_cycle(
                        race.data,
                        PitCycleInput(
                            season=race.ref.season,
                            round=race.ref.round,
                            session=race.ref.session,
                            driver=driver,
                            rival=rival,
                            driver_stop=a.loss.stop_number,
                            rival_stop=b.loss.stop_number,
                        ),
                    )
                except ToolError:
                    continue  # fmt: skip
                before, rival_before = cycle.position_before, cycle.rival_position_before
                if before is None or rival_before is None or abs(before - rival_before) != 1:
                    continue
                if abs(cycle.gained_s) > MAX_SWING_S:
                    continue
                duel = Duel(driver, rival, a.number, cycle, {driver: a, rival: b})
                if _holds(race, duel) and not _red_flag_inside(race, duel):
                    yield duel


def _paired(a: StopFacts, b: StopFacts, mine: Sequence[StopFacts], theirs: Sequence[StopFacts]) -> bool:
    """Same rank, each the other's closest stop, close enough in laps to be one cycle."""
    if abs(a.lap - b.lap) > MAX_LAPS_APART:
        return False
    closest_to_a = min(theirs, key=lambda stop: abs(stop.lap - a.lap))
    closest_to_b = min(mine, key=lambda stop: abs(stop.lap - b.lap))
    return closest_to_a is b and closest_to_b is a


def _holds(race: RaceFacts, duel: Duel) -> bool:
    """The order after the cycle holds HOLD_LAPS laps (or to the flag), and an undercut is not an overtake on
    track before the rival's stop."""
    mine, theirs = race.laps[duel.driver], race.laps[duel.rival]
    after = duel.cycle.gap_after_s
    for lap in range(duel.cycle.lap_after, duel.cycle.lap_after + HOLD_LAPS + 1):
        if lap not in mine or lap not in theirs:
            break
        gap = _gap(mine[lap], theirs[lap])
        if gap is None or (gap > 0) != (after > 0):
            return False
    if duel.swapped:
        first = min(duel.stops.values(), key=lambda stop: stop.lap)
        second = max(duel.stops.values(), key=lambda stop: stop.lap)
        if first.driver == duel.ahead_after:  # undercut: the first to stop stays behind until the rival stops
            for lap in range(duel.cycle.lap_before, second.lap):
                gap = _gap(mine.get(lap), theirs.get(lap))
                if gap is not None and (gap > 0) != (duel.cycle.gap_before_s > 0):
                    return False
    return True


def _gap(mine: dict[str, Any] | None, theirs: dict[str, Any] | None) -> float | None:
    if not mine or not theirs:
        return None
    end, reference = number(mine["lap_end_session_s"]), number(theirs["lap_end_session_s"])
    return None if end is None or reference is None else end - reference


def _red_flag_inside(race: RaceFacts, duel: Duel) -> bool:
    laps = race.laps[duel.driver]
    return any("5" in str(laps[lap]["track_status"]) for lap in range(duel.cycle.lap_before, duel.cycle.lap_after + 1)
               if lap in laps)  # fmt: skip


# ---- the cause and the facts, in French -------------------------------------------------------------------------


def elide(word: str, name: str) -> str:
    """`de Max`, `d'Oscar`; `que Max`, `qu'Oscar`."""
    return f"{word[:-1]}'{name}" if name[:1] in tuple("AEIOUÉ") else f"{word} {name}"


def laps_fr(count: int) -> str:
    return f"{count} tour" if count == 1 else f"{count} tours"


def list_fr(numbers: Sequence[int]) -> str:
    return str(numbers[0]) if len(numbers) == 1 else f"{', '.join(map(str, numbers[:-1]))} et {numbers[-1]}"


def _tyres(stop: StopFacts, *, before: bool) -> str:
    compound = stop.loss.compound_before if before else stop.loss.compound_after
    name = COMPOUNDS_FR.get(compound or "", (compound or "?").lower())
    if before:
        return f"{name} de {laps_fr(stop.tyre_age)}" if stop.tyre_age else name
    return f"{name} {'neufs' if stop.fresh_after else 'usagés'}" if stop.fresh_after is not None else name


def _pace(race: RaceFacts, faster: str, slower: str, laps: range) -> tuple[float, int] | None:
    """Mean lap time of `slower` minus `faster` on the green laps both ran without a stop."""
    a, b = race.laps[faster], race.laps[slower]
    deltas = []
    for lap in laps:
        if lap not in a or lap not in b:
            continue
        x, y = a[lap], b[lap]
        clean = all(
            number(row["lap_time_s"]) is not None
            and number(row["pit_in_session_s"]) is None
            and number(row["pit_out_session_s"]) is None
            and str(row["track_status"]) == "1"
            for row in (x, y)
        )
        if clean:
            deltas.append(float(y["lap_time_s"]) - float(x["lap_time_s"]))
    return (round(statistics.mean(deltas), 2), len(deltas)) if deltas else None


def _pit_difference(winner: StopFacts, loser: StopFacts) -> str:
    """What the stops themselves gave the winner, when it counts (half a second or more)."""
    if winner.loss.time_lost_s is None or loser.loss.time_lost_s is None:
        return ""
    difference = loser.loss.time_lost_s - winner.loss.time_lost_s
    if abs(difference) < 0.5:
        return ""
    return (
        f" ; son arrêt lui a aussi coûté {difference:.1f} s de moins ({winner.loss.time_lost_s:.1f} s contre "
        f"{loser.loss.time_lost_s:.1f} s)"
        if difference > 0
        else f" ; et ce malgré un arrêt qui lui a coûté {-difference:.1f} s de plus ({winner.loss.time_lost_s:.1f} s "
        f"contre {loser.loss.time_lost_s:.1f} s)"
    )


def cause(race: RaceFacts, duel: Duel) -> tuple[str, str] | None:
    """(tag, sentence) of the main cause of a swap, None when the rule cannot settle it."""
    winner, loser = duel.ahead_after, duel.ahead_before
    w, lose = duel.stops[winner], duel.stops[loser]
    W, L = race.name(winner), race.name(loser)
    margin = duel.gap_s("after")  # what the winner came out ahead by
    lead = duel.gap_s("before")  # what the loser was ahead by

    if lose.penalty_s and lose.penalty_s > margin:
        penalty = next(p for p in lose.penalties if p.kind == "time")
        return "penalty", (
            f"la pénalité {elide('de', L)} : {penalty.french()}, purgée à son arrêt du tour {lose.lap}, où ses "
            f"mécaniciens ont dû attendre {penalty.seconds} s avant de toucher la voiture ; {W} est ressorti devant "
            f"avec {margin:.1f} s d'avance seulement, moins que la pénalité"
        )
    if w.neutralized_by and not lose.neutralized_by:
        when = (
            f"alors {elide('que', L)} s'était déjà arrêté sous drapeau vert, au tour {lose.lap}"
            if lose.lap < w.lap
            else f"alors {elide('que', L)} est resté en piste et ne s'est arrêté qu'au tour {lose.lap}, sous "
            "drapeau vert"
        )
        return "neutralization", (
            f"un arrêt sous {w.neutralized_by} : {W} s'est arrêté au tour {w.lap} pendant la neutralisation, quand "
            f"le peloton roule au ralenti et qu'un arrêt coûte bien moins de temps sur les autres, {when}"
        )
    if lose.neutralized_by and not w.neutralized_by:
        return None  # the loser had the cheaper stop: something else decided, which the rule cannot tell
    if w.neutralized_by and lose.neutralized_by and w.lap < lose.lap:
        timing = f"le moment de l'arrêt sous {w.neutralized_by} : {W} s'est arrêté dès le tour {w.lap}, {L} "
        if "virtuelle" in w.neutralized_by:
            return "neutralization", (
                f"{timing}seulement au tour {lose.lap}, quand la neutralisation touchait à sa fin et que l'arrêt "
                f"coûtait plus cher"
            )
        return "neutralization", (
            f"{timing}{laps_fr(lose.lap - w.lap)} plus tard, au tour {lose.lap} ; resté en piste derrière la voiture "
            f"de sécurité pendant que le peloton se regroupait, {L} a perdu les {lead:.1f} s d'avance qu'il avait et "
            f"est ressorti derrière"
        )
    excess = lose.pit_lane_excess_s
    if lose.teammate_ahead and excess is not None and excess >= DOUBLE_STACK_S and excess > margin:
        return "double_stack", (
            f"le double arrêt de l'écurie {elide('de', L)} : son coéquipier {race.name(lose.teammate_ahead)} est "
            f"passé au stand juste avant lui au tour {lose.lap}, et {L} a dû attendre son tour : {excess:.1f} s de "
            f"plus que la médiane de la course dans la voie des stands"
        )
    slow, fast = lose.stationary_s, w.stationary_s
    if slow is not None and fast is not None and slow - fast >= SLOW_STOP_S and slow - fast > margin:
        return "slow_stop", (
            f"un arrêt lent {elide('de', L)} au tour {lose.lap} : {slow:.1f} s immobile, contre {fast:.1f} s pour {W}, "
            f"soit {slow - fast:.1f} s de plus, davantage que les {margin:.1f} s qui les séparaient ensuite"
        )
    if w.neutralized_by and lose.neutralized_by:
        return None  # both stopped on the same lap of a neutralization: the order in the pit lane decided
    if (w.loss.compound_after in WET) != (lose.loss.compound_after in WET) or (
        (w.loss.compound_before in WET) != (w.loss.compound_after in WET)
    ):
        if w.lap >= lose.lap:
            return None
        to = COMPOUNDS_FR.get(w.loss.compound_after or "", "?")
        return "weather", (
            f"le bon moment pour changer de pneus sur une piste qui évoluait : {W} est passé aux pneus {to} dès le "
            f"tour {w.lap}, {L} seulement au tour {lose.lap}"
        )
    gained = abs(duel.cycle.gained_s)
    pits = _pit_difference(w, lose)
    if w.lap < lose.lap:
        pace = _pace(race, winner, loser, range(w.lap + 2, lose.lap))
        how = (
            f" : sur ses pneus {_tyres(w, before=False)}, il a tourné {pace[0]:.2f} s plus vite par tour "
            f"{elide('que', L)}, resté en piste sur des {_tyres(lose, before=True)}, sur {laps_fr(pace[1])} "
            f"comparables"
            if pace and pace[0] > 0
            else f" : ses pneus {_tyres(w, before=False)} lui ont donné l'avantage dès son tour de sortie, face à "
            f"{L}, encore sur des {_tyres(lose, before=True)}"
        )
        traffic = (
            f" ; {L} est en plus ressorti des stands derrière {race.name(lose.traffic[0])}, à {lose.traffic[1]:.1f} s"
            if lose.traffic and lose.traffic[0] != winner
            else ""
        )
        return "undercut", (
            f"l'undercut : {W} s'est arrêté le premier, au tour {w.lap}, {laps_fr(lose.lap - w.lap)} avant {L}, et a "
            f"gagné {gained:.1f} s sur le cycle d'arrêts{how}{pits}{traffic}"
        )
    if w.lap > lose.lap:
        pace = _pace(race, winner, loser, range(lose.lap + 2, w.lap))
        if pace and pace[0] > 0:
            how = (
                f" : sur ses {_tyres(w, before=True)}, il a tourné {pace[0]:.2f} s plus vite par tour "
                f"{elide('que', L)}, pourtant sur des pneus {_tyres(lose, before=False)}, sur {laps_fr(pace[1])} "
                f"comparables"
            )
        elif pace:
            how = (
                f" : sur des pneus {_tyres(lose, before=False)}, {L} n'a repris que {-pace[0]:.2f} s par tour, "
                f"pas assez pour compenser"
            )
        else:
            how = ""
        if lose.traffic and lose.traffic[0] != winner:
            how += (
                f" ; {L} est ressorti des stands derrière {race.name(lose.traffic[0])}, à {lose.traffic[1]:.1f} s, "
                f"et y a perdu du temps"
            )
        return "overcut", (
            f"l'overcut : {W} est resté en piste {laps_fr(w.lap - lose.lap)} de plus {elide('que', L)} (arrêts aux "
            f"tours {lose.lap} et {w.lap}), et a gagné {gained:.1f} s sur le cycle d'arrêts{how}{pits}"
        )
    return None


def facts(race: RaceFacts, duel: Duel) -> list[str]:
    """The facts of the cycle, for both drivers, whatever the cause."""
    lines = [
        f"Écarts : {race.name(duel.ahead_before)} avait {duel.gap_s('before'):.1f} s d'avance à la fin du tour "
        f"{duel.cycle.lap_before} ; à la fin du tour {duel.cycle.lap_after}, {race.name(duel.ahead_after)} était "
        f"devant de {duel.gap_s('after'):.1f} s"
        + (f", et l'est resté au moins {laps_fr(HOLD_LAPS)}." if duel.swapped else ".")
    ]
    for code in (duel.ahead_before, next(c for c in duel.stops if c != duel.ahead_before)):
        stop = duel.stops[code]
        parts = [
            f"{race.name(code)} : arrêt au tour {stop.lap}, {_tyres(stop, before=True)} remplacés par des "
            f"{_tyres(stop, before=False)}"
        ]
        if stop.stationary_s is not None:
            parts.append(f"{stop.stationary_s:.1f} s immobile" + (" hors pénalité" if stop.penalty_s else ""))
        if stop.loss.time_lost_s is not None and not stop.neutralized_by:
            parts.append(f"{stop.loss.time_lost_s:.1f} s perdues au total sur les tours d'entrée et de sortie")
        for penalty in stop.penalties:
            parts.append(f"{penalty.french()} purgée à cet arrêt")
        if stop.neutralized_by:
            parts.append(f"sous {stop.neutralized_by}")
        if stop.teammate_ahead:
            parts.append(f"double arrêt de l'écurie, derrière son coéquipier {race.name(stop.teammate_ahead)}")
        if stop.traffic and stop.traffic[0] not in duel.stops:
            parts.append(f"ressorti derrière {race.name(stop.traffic[0])} ({stop.traffic[1]:.1f} s)")
        lines.append(", ".join(parts) + ".")
    window = range(duel.cycle.lap_before + 1, duel.cycle.lap_after + 1)
    laps = race.laps[duel.driver]
    neutral = neutralization([laps[lap]["track_status"] for lap in window if lap in laps])
    if neutral and not any(stop.neutralized_by for stop in duel.stops.values()):
        lines.append(f"Pendant le cycle : {neutral}, sans arrêt de l'un ou l'autre dessous.")
    yellow = [lap for lap in window if lap in laps and "2" in str(laps[lap]["track_status"])]
    if yellow:
        lines.append(f"Drapeau jaune {'au tour' if len(yellow) == 1 else 'aux tours'} {list_fr(yellow)}.")
    wet_tyres = sorted(
        {
            COMPOUNDS_FR[c]
            for stop in duel.stops.values()
            for c in (stop.loss.compound_before, stop.loss.compound_after)
            if c in WET
        }
    )
    rain = [lap for lap in window if race.rain and race.rain.get(lap)]
    if rain:
        lines.append(f"Pluie {'au tour' if len(rain) == 1 else 'aux tours'} {list_fr(rain)}.")
    elif wet_tyres:
        lines.append(f"Piste humide, pneus {' et '.join(wet_tyres)}, sans pluie pendant le cycle.")
    elif race.rain is not None:
        lines.append("Piste sèche, sans pluie pendant le cycle.")
    return lines + context(race, duel)


# ---- the race around the duel -----------------------------------------------------------------------------------
# What a person looks at before saying why: the start, the finish, each driver's strategy, the car each was stuck
# behind, the other penalties of the race, and the stewards' decisions of the weekend (from the FIA corpus).

SESSIONS_FR = {
    "Race": "en course",
    "Qualifying": "en qualifications",
    "Sprint Qualifying": "en qualifications sprint",
    "Sprint Shootout": "en qualifications sprint",
    "Sprint": "au sprint",
    "Practice 1": "aux essais libres 1",
    "Free Practice 1": "aux essais libres 1",
    "Practice 2": "aux essais libres 2",
    "Free Practice 2": "aux essais libres 2",
    "Practice 3": "aux essais libres 3",
    "Free Practice 3": "aux essais libres 3",
    "Reconnaissance Laps": "aux tours de reconnaissance",
}

# The facts of the stewards' decisions, by the start of the title's last part.
FACTS_FR = [
    ("unsafe release", "remise en piste dangereuse"),
    ("released in an unsafe", "remise en piste dangereuse"),
    ("pit lane speeding", "excès de vitesse dans la voie des stands"),
    ("speeding in the pit lane", "excès de vitesse dans la voie des stands"),
    ("changes made during parc ferme", "modifications en parc fermé"),
    ("parc ferme", "infraction au parc fermé"),
    ("pu elements", "éléments du moteur changés au-delà du quota"),
    ("changes to pu elements", "éléments du moteur changés au-delà du quota"),
    ("causing a collision", "collision provoquée"),
    ("leaving the track and gaining", "avantage pris en sortant de la piste"),
    ("leaving the track multiple", "dépassements répétés des limites de la piste"),
    ("leaving the track without", "sortie de piste sans raison valable"),
    ("failing to follow race director", "instructions du directeur de course non suivies"),
    ("failure to follow race director", "instructions du directeur de course non suivies"),
    ("failing to set a lap time with", "aucun temps dans les 107 %"),
    ("impeding", "a gêné un autre pilote"),
    ("forcing another driver", "a poussé un autre pilote hors de la piste"),
    ("yellow flag", "drapeau jaune non respecté"),
    ("failing to slow", "drapeau jaune non respecté"),
    ("failure to slow", "drapeau jaune non respecté"),
    ("qualifying sc2-sc1", "temps entre les lignes de voiture de sécurité dépassé"),
    ("sprint qualifying sc2-sc1", "temps entre les lignes de voiture de sécurité dépassé"),
    ("sc1", "temps entre les lignes de voiture de sécurité dépassé"),
    ("scl1", "temps entre les lignes de voiture de sécurité dépassé"),
    ("ignoring blue flags", "drapeaux bleus ignorés"),
    ("aborted start", "incident au départ avorté"),
    ("media commitment", "obligation médiatique manquée"),
    ("permission to start", "autorisation de prendre le départ"),
    ("driving unnecessarily slowly", "conduite inutilement lente"),
    ("driving erratically", "conduite erratique"),
    ("dangerous driving", "conduite dangereuse"),
    ("unsafe condition", "voiture laissée dans un état dangereux"),
    ("collision with car", "collision"),
    ("incident with car", "incident avec un autre pilote"),
    ("right of review", "demande de révision"),
    ("protest", "réclamation d'une écurie"),
    ("technical non-conformity", "non-conformité technique"),
    ("change to pu elements", "éléments du moteur changés au-delà du quota"),
    ("changes made under parc ferme", "modifications en parc fermé"),
    ("start procedure", "procédure de départ non respectée"),
    ("tyre operating", "procédure d'utilisation des pneus non respectée"),
    ("track limits", "dépassements répétés des limites de la piste"),
    ("forcing car", "a poussé un autre pilote hors de la piste"),
    ("red flag", "drapeau rouge non respecté"),
    ("failure to comply with red flag", "drapeau rouge non respecté"),
    ("technical non-compliance", "non-conformité technique"),
    ("technical regulations", "non-conformité technique"),
    ("overtaking under safety car", "dépassement sous voiture de sécurité"),
    ("change to pu element", "éléments du moteur changés au-delà du quota"),
    ("crossing the line at pit", "ligne blanche des stands franchie"),
    ("erratic driving", "conduite erratique"),
    ("driving in an unsafe condition", "voiture conduite dans un état dangereux"),
    ("incorrect starting position", "mauvaise position sur la grille de départ"),
    ("overtaking under yellow", "dépassement sous drapeau jaune"),
    ("virtual safety car", "infraction sous VSC"),
    ("safety car", "infraction sous voiture de sécurité"),
    ("false start", "faux départ"),
    ("moving before", "faux départ"),
    ("starting procedure", "procédure de départ non respectée"),
    ("practice start", "essai de départ hors de la zone prévue"),
    ("red light at pit exit", "feu rouge en sortie des stands"),
    ("pit lane incident", "incident dans la voie des stands"),
    ("pit lane infringement", "infraction dans la voie des stands"),
    ("pit entry", "infraction à l'entrée des stands"),
    ("pit exit", "infraction à la sortie des stands"),
    ("abnormal change of direction", "changement de direction anormal"),
    ("failing to maintain distance", "distance non respectée derrière la voiture de sécurité"),
]

PENALTIES_FR: list[tuple[str, str]] = [
    (r"(\d+)\s*second (?:time )?penalty", "pénalité de {0} s"),
    (r"(\d+)\s*(?:grid )?(?:place|position)s? (?:grid )?penalty", "recul de {0} place(s) sur la grille"),
    (r"drop of (\d+) grid (?:places?|positions?)", "recul de {0} place(s) sur la grille"),
    (r"back of the (?:starting )?grid", "départ en fond de grille"),
    (r"start the sprint from the pit ?lane", "départ du sprint depuis la voie des stands"),
    (r"pit ?lane start|start (?:the race )?from the pit ?lane", "départ depuis la voie des stands"),
    (r"start the race behind any other", "départ en fond de grille"),
    (r"(\d+) penalty laps?", "{0} tour(s) de pénalité"),
    (r"drive[- ]through", "drive-through"),
    (r"stop[- ](?:and[- ])?go", "stop and go"),
    (r"disqualif", "disqualification"),
    (r"fined?\D{0,12}€\s*([\d,.]+)", "amende de {0} €"),
    (r"€\s*([\d,.]+)\s*fine", "amende de {0} €"),
    (r"(\d+)\s*penalty points?", "{0} point(s) de pénalité"),
    (r"reprimand", "réprimande"),
    (r"warning", "avertissement"),
    (r"lap time[s]? .*deleted|deletion of (?:the )?lap time", "temps au tour supprimé"),
    (r"no further action|no penalty (?:is )?applied", "aucune sanction"),
]
HARMLESS = ("amende", "réprimande", "avertissement", "aucune sanction", "point(s) de pénalité")


def fact_fr(title: str) -> str:
    last = re.sub(r"^alleged\s+", "", title.split(" - ")[-1].strip(), flags=re.IGNORECASE)
    if turn := re.match(r"turn (\d+) incident", last, flags=re.IGNORECASE):
        return f"incident au virage {turn[1]}"
    for start, french in FACTS_FR:
        if last.lower().startswith(start):
            return french
    return f"« {last.lower()} »"


def penalty_fr(text: str) -> list[str]:
    found = []
    for pattern, french in PENALTIES_FR:
        if match := re.search(pattern, text, flags=re.IGNORECASE):
            value = french.format(*(group.replace(",", " ").rstrip(".") for group in match.groups()))
            if value not in found:
                found.append(value)
    return found


def decision_lines(race: RaceFacts, code: str) -> list[str]:
    """The weekend's decisions on a driver, the race's time penalties left out (race control already gives them)."""
    number = integer(race.results.get(code, {}).get("driver_number"))
    lines, seen = [], set()
    for decision in race.decisions:
        if number is None or decision.get("car_number") != number:
            continue
        session = str(decision.get("session") or "")
        penalty = str(decision.get("penalty") or "")
        found = penalty_fr(penalty)
        if session == "Race" and any(p.startswith(("pénalité de", "drive-through", "stop and go")) for p in found):
            continue
        what = fact_fr(str(decision.get("document_title") or ""))
        key = (session, what, penalty)
        if key in seen:
            continue
        seen.add(key)
        sanction = ", ".join(found) if found else f"« {penalty.strip()} »" if penalty else "décision sans sanction lue"
        effect = " (sans effet sur la course)" if found and session != "Race" and all(
            p.startswith(HARMLESS) for p in found) else ""  # fmt: skip
        lines.append(f"{what} {SESSIONS_FR.get(session, f'({session})' if session else '')}".strip()
                     + f" : {sanction}{effect}")  # fmt: skip
    return lines


def _start(race: RaceFacts, code: str) -> str | None:
    row = race.results.get(code)
    grid = integer(row.get("grid_position")) if row else None
    first = integer(race.laps.get(code, {}).get(1, {}).get("position"))
    if grid is None or first is None:
        return None
    start = "depuis la voie des stands" if grid == 0 else f"{grid}e sur la grille"
    if grid == 0:
        return f"{race.name(code)}, parti {start}, {first}e au premier tour"
    moved = grid - first
    change = (
        f"{moved} place{'s' if moved > 1 else ''} gagnée{'s' if moved > 1 else ''}"
        if moved > 0
        else f"{-moved} place{'s' if moved < -1 else ''} perdue{'s' if moved < -1 else ''}"
        if moved < 0
        else "aucune place perdue ni gagnée"
    )
    return f"{race.name(code)}, {start}, {first}e au premier tour ({change})"


def _strategy(race: RaceFacts, code: str) -> str | None:
    laps = race.laps.get(code, {})
    first = laps.get(min(laps)) if laps else None
    if not first or not isinstance(first["compound"], str):
        return None
    tyres = [COMPOUNDS_FR.get(first["compound"], first["compound"].lower())]
    for stop in (s for s in race.raw_stops if s["driver"] == code and not s["red_flag"]):
        if isinstance(stop["compound_after"], str):
            tyres.append(COMPOUNDS_FR.get(stop["compound_after"], stop["compound_after"].lower()))
    stops = len(race.stops(code))
    return f"{race.name(code)}, {stops} arrêt{'s' if stops > 1 else ''} ({' → '.join(tyres)})"


def _finish(race: RaceFacts, code: str) -> str | None:
    row = race.results.get(code)
    if not row:
        return None
    place = str(row.get("classified_position") or "")
    return f"{race.name(code)} {place}e" if place.isdigit() else f"{race.name(code)} non classé ({row.get('status')})"


def _behind_before(race: RaceFacts, code: str, lap: int, rival: str) -> str | None:
    """The car right in front of a driver at the end of a lap, within TRAFFIC_S, other than the rival."""
    row = race.laps.get(code, {}).get(lap)
    if not row or integer(row["position"]) in (None, 1):
        return None
    position, end = integer(row["position"]), number(row["lap_end_session_s"])
    for other, laps in race.laps.items():
        ahead = laps.get(lap)
        if other in (code, rival) or not ahead or integer(ahead["position"]) != (position or 0) - 1:
            continue
        reference = number(ahead["lap_end_session_s"])
        if end is not None and reference is not None and end - reference <= TRAFFIC_S:
            return f"{race.name(code)} était à {end - reference:.1f} s de {race.name(other)}"
    return None


def history(race: RaceFacts, a: str, b: str) -> list[tuple[int, str, str]]:
    """Each change of order between two drivers over the race: (lap, now ahead, how), the start first.

    The order is read at the line at the end of each lap both completed. "how" says where the pass came from: a stop
    (an in- or out-lap of either), a neutralization, or the track."""
    mine, theirs = race.laps.get(a, {}), race.laps.get(b, {})
    changes: list[tuple[int, str, str]] = []
    ahead = None
    for lap in sorted(mine.keys() & theirs.keys()):
        gap = _gap(mine[lap], theirs[lap])
        if gap is None:
            continue
        now = a if gap < 0 else b
        if now == ahead:
            continue
        if ahead is None:
            changes.append((lap, now, "au départ" if lap == 1 else f"au tour {lap}"))
        else:
            pitted = [
                code
                for code, laps in ((a, mine), (b, theirs))
                if any(
                    number(laps[n]["pit_in_session_s"]) is not None or number(laps[n]["pit_out_session_s"]) is not None
                    for n in (lap - 1, lap)
                    if n in laps
                )
            ]
            neutral = neutralization([mine[lap]["track_status"], theirs[lap]["track_status"]])
            if pitted:
                how = f"aux stands ({' et '.join(race.name(code) for code in pitted)} au stand)"
            elif neutral:
                how = f"sous {neutral}"
            else:
                how = "en piste"
            changes.append((lap, now, how))
        ahead = now
    return changes


def order_holds(race: RaceFacts, duel: Duel) -> bool:
    """No change of order from the cycle to the next stop of either driver, or to the flag."""
    later = [
        int(stop["lap"])
        for stop in race.raw_stops
        if stop["driver"] in duel.stops and int(stop["lap"]) > duel.cycle.lap_after
    ]
    until = min(later) if later else 10_000
    return not any(duel.cycle.lap_before < lap < until for lap, _, _ in history(race, duel.driver, duel.rival)[1:])


def context(race: RaceFacts, duel: Duel) -> list[str]:
    codes = [duel.ahead_before, next(c for c in duel.stops if c != duel.ahead_before)]
    lines = []
    changes = history(race, *codes)
    if changes:
        steps = [
            f"{race.name(ahead)} devant {how}"
            if index == 0
            else f"{race.name(ahead)} passe devant au tour {lap}, {how}"
            for index, (lap, ahead, how) in enumerate(changes)
        ]
        end = ", et jusqu'à l'arrivée" if len(changes) == 1 else ""
        lines.append(f"Le duel sur toute la course : {' ; '.join(steps)}{end}.")
    starts = [line for code in codes if (line := _start(race, code))]
    if starts:
        lines.append(f"Départ : {' ; '.join(starts)}.")
    behind = [line for code in codes if (line := _behind_before(race, code, duel.cycle.lap_before, next(
        c for c in codes if c != code)))]  # fmt: skip
    if behind:
        lines.append(f"Avant les arrêts (tour {duel.cycle.lap_before}) : {' ; '.join(behind)}.")
    strategies = [line for code in codes if (line := _strategy(race, code))]
    if strategies:
        lines.append(f"Stratégies : {' ; '.join(strategies)}.")
    finishes = [line for code in codes if (line := _finish(race, code))]
    if finishes:
        lines.append(f"Arrivée : {', '.join(finishes)}.")
    cycle_stops = {(stop.driver, stop.loss.stop_number) for stop in duel.stops.values()}
    served_in_cycle = {id(p) for key in cycle_stops for p in race.penalties.get(key, [])}
    others = [
        f"{race.name(p.driver)}, {p.french()} au tour {p.lap}"
        for p in race.given
        if p.driver in codes and id(p) not in served_in_cycle
    ]
    if others:
        lines.append(f"Autres pénalités de la course : {' ; '.join(others)}.")
    decided = [f"{race.name(code)}, {line}" for code in codes for line in decision_lines(race, code)]
    if decided:
        lines.append(f"Décisions des commissaires du week-end : {' ; '.join(decided)}.")
    return lines


def load_decisions() -> dict[tuple[int, int], list[dict[str, Any]]]:
    """Every stewards' decision of the FIA corpus, by (season, round). The corpus must be indexed (`just corpus`)."""
    from qdrant_client import models

    from core.retrieval.qdrant import qdrant_client

    client = qdrant_client()
    if not client.collection_exists("fia_parents"):
        raise RuntimeError("no FIA corpus in Qdrant: run `just corpus 2024 2025 2026` first")
    found: dict[tuple[int, int], list[dict[str, Any]]] = {}
    offset = None
    only = models.Filter(
        must=[models.FieldCondition(key="doc_type", match=models.MatchValue(value="stewards_decision"))]
    )
    fields = ["season", "round", "session", "car_number", "document_title", "penalty", "published", "document_number"]
    while True:
        points, offset = client.scroll("fia_parents", scroll_filter=only, limit=500, offset=offset, with_payload=fields)
        for point in points:
            payload = dict(point.payload or {})
            if payload.get("round") is not None:
                found.setdefault((int(payload["season"]), int(payload["round"])), []).append(payload)
        if offset is None:
            break
    for decisions in found.values():  # a fixed order, whatever Qdrant's
        decisions.sort(key=lambda d: (str(d.get("published")), int(d.get("document_number") or 0),
                                      str(d.get("document_title"))))  # fmt: skip
    return found
