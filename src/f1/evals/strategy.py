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

PENALTY = re.compile(
    r"^FIA STEWARDS: (?P<served>PENALTY SERVED - )?"
    r"(?:(?P<seconds>\d+) SECOND (?P<kind>TIME|STOP/GO)|(?P<other>DRIVE THROUGH|STOP-AND-GO)) PENALTY "
    r"FOR CAR \d+ \((?P<driver>[A-Z]{3})\)(?: - (?P<reason>.+))?"
)


@dataclass(frozen=True)
class Penalty:
    driver: str
    kind: Literal["time", "drive_through", "stop_go"]
    seconds: int | None  # added to the stop for a time penalty; held in the box for a stop and go
    reason: str
    lap: int  # the lap race control announced it

    def french(self) -> str:
        what = (
            f"une pénalité de {self.seconds} s"
            if self.kind == "time"
            else "un drive-through"
            if self.kind == "drive_through"
            else f"un stop and go de {self.seconds or 10} s"
        )
        return f"{what} {reason_fr(self.reason)}".strip()


# The stewards' usual reasons, in French; another reason is quoted as it is.
REASONS_FR = [
    ("CAUSING A COLLISION", "pour avoir provoqué une collision"),
    ("LEAVING THE TRACK AND GAINING", "pour avoir gagné un avantage en sortant de la piste"),
    ("FALSE START", "pour un faux départ"),
    ("STARTING PROCEDURE", "pour une infraction à la procédure de départ"),
    ("SPEEDING IN THE PIT LANE", "pour excès de vitesse dans la voie des stands"),
    ("TRACK LIMITS", "pour dépassements répétés des limites de la piste"),
    ("RELEASING IN UNSAFE", "pour une remise en piste dangereuse"),
    ("UNSAFE RELEASE", "pour une remise en piste dangereuse"),
    ("FORCING ANOTHER", "pour avoir poussé un autre pilote hors de la piste"),
    ("YELLOW FLAG", "pour ne pas avoir respecté un drapeau jaune"),
    ("FAILING TO SLOW UNDER YELLOW", "pour ne pas avoir ralenti sous drapeau jaune"),
    ("IGNORING BLUE FLAGS", "pour avoir ignoré les drapeaux bleus"),
    ("VSC INFRINGEMENT", "pour une infraction sous VSC"),
    ("SAFETY CAR INFRINGEMENT", "pour une infraction sous voiture de sécurité"),
    ("FAILING TO FOLLOW RACE DIRECTOR", "pour ne pas avoir suivi les instructions du directeur de course"),
]


def reason_fr(reason: str) -> str:
    reason = re.sub(r"\s*\(\d{2}:\d{2}:\d{2}\)$", "", reason.strip())
    if not reason:
        return ""
    for start, french in REASONS_FR:
        if reason.upper().startswith(start):
            return french
    return f"(« {reason.lower()} »)"


def penalties(messages: Sequence[dict[str, Any]]) -> tuple[list[Penalty], list[tuple[str, int]]]:
    """The penalties given in a race, in order, and the (driver, lap) of each "PENALTY SERVED" message."""
    given, served = [], []
    for message in messages:
        found = PENALTY.match(str(message["message"]))
        if not found:
            continue
        lap = integer(message["lap"]) or 1
        if found["served"]:
            served.append((found["driver"], lap))
            continue
        other = found["other"]
        kind: Literal["time", "drive_through", "stop_go"] = (
            "drive_through"
            if other == "DRIVE THROUGH"
            else "stop_go"
            if other or found["kind"] == "STOP/GO"
            else "time"
        )
        seconds = int(found["seconds"]) if found["seconds"] else None
        given.append(Penalty(found["driver"], kind, seconds, (found["reason"] or "").strip(), lap))
    return given, served


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

    def __init__(self, data: RaceData, ref: SessionRef, names: dict[str, str], teams: dict[str, str]) -> None:
        self.data, self.ref, self.names, self.teams = data, ref, names, teams
        laps = data.laps(ref)
        self.laps: dict[str, dict[int, dict[str, Any]]] = {}
        for lap in laps:
            self.laps.setdefault(str(lap["driver"]), {})[int(lap["lap_number"])] = lap
        self.raw_stops = [stop for driver in self.laps for stop in data.pit_stops(ref, driver)]
        given, served = penalties(data.race_control_messages(ref))
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
    return lines
