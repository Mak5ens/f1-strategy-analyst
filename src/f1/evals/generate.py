"""Cases computed from the lake and the tools: the expected answer is read or computed, never written.

Three families:
- data: a fact of a race weekend (winner, pole, tyres used, stops, grid, result, fastest lap);
- computation: a number from a deterministic tool (time lost in a stop, pit lane time, tyre wear, gap at a lap,
  time gained in a pit cycle, safety cars);
- strategy: why a driver lost a place to another in the pit stops. The cause is a rule's guess (undercut, slow
  stop, neutralization), so these cases are marked unreviewed until a person checks them.

Races and drivers are drawn with a fixed seed, in a fixed order: the same lake gives the same cases.
"""

import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import duckdb

from core.evals.dataset import Case, Origin
from core.tools import ToolError
from f1.evals import COMPOUNDS_FR, grand_prix
from f1.jobs.facts import lap_time
from f1.tools import RaceData
from f1.tools.degradation import DegradationInput, stint_degradation
from f1.tools.gaps import GapInput, gap_between_drivers
from f1.tools.neutralizations import NeutralizationsInput, neutralizations
from f1.tools.pit_cycle import PitCycleInput, pit_cycle
from f1.tools.pit_loss import PitLossInput, pit_stop_loss

SEED = 146
STRATEGY_PER_RACE = 2
GENERATOR = "f1.evals.generate"


@dataclass(frozen=True)
class Race:
    season: int
    round: int
    event: str
    names: dict[str, str]  # driver code -> full name
    results: list[dict[str, Any]]  # race classification, in order

    @property
    def label(self) -> str:
        return grand_prix(self.event, self.season)

    @property
    def key(self) -> str:
        return f"{self.season}-r{self.round:02d}"

    def name(self, code: str) -> str:
        return self.names.get(code, code)


# The tables the generator reads, copied once into memory: the tools query the lake again for every case, and a
# query over S3 lists every file first.
TABLES = ("sessions", "results", "laps", "stints", "pit_stops", "race_control_messages")


def in_memory(db: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    memory = duckdb.connect()
    for table in TABLES:
        frame = db.sql(f"SELECT * FROM {table}").arrow()  # noqa: F841 (read by DuckDB by name)
        memory.execute(f"CREATE TABLE {table} AS SELECT * FROM frame")
    return memory


def races(db: duckdb.DuckDBPyConnection) -> list[Race]:
    found = []
    for season, round_number, event in db.execute(
        "SELECT season, round, event_name FROM sessions WHERE session = 'R' ORDER BY season, round"
    ).fetchall():
        rows: list[dict[str, Any]] = (
            db.execute(
                "SELECT * FROM results WHERE season = ? AND round = ? AND session = 'R' ORDER BY position NULLS LAST",
                [season, round_number],
            )
            .df()
            .to_dict("records")  # type: ignore[assignment]
        )
        names = {str(row["driver"]): str(row["full_name"]) for row in rows if row["full_name"]}
        found.append(Race(int(season), int(round_number), str(event), names, rows))
    return found


def _origin(race: Race, source: str, **inputs: Any) -> Origin:
    return Origin(
        method="computed",
        by=f"{GENERATOR}:{source}",
        inputs={"season": race.season, "round": race.round, "session": "R", **inputs},
        reviewed=False,
    )


def _last_name(full_name: str) -> str:
    return full_name.split()[-1]


def _ordinal(number: int) -> str:
    return "1er" if number == 1 else f"{number}e"


# ---- data -------------------------------------------------------------------------------------------------------


def _winner(db: duckdb.DuckDBPyConnection, race: Race, rng: random.Random) -> Case | None:
    winner = race.results[0] if race.results else None
    if not winner or winner["classified_position"] != "1":
        return None
    name = race.name(winner["driver"])
    return Case(
        id=f"data-winner-{race.key}",
        family="data",
        question=f"Qui a remporté le {race.label} ?",
        answer=f"{name} a remporté le {race.label}.",
        value=_last_name(name),
        origin=_origin(race, "results", table="results", position=1),
    )


def _pole(db: duckdb.DuckDBPyConnection, race: Race, rng: random.Random) -> Case | None:
    row = db.execute(
        "SELECT driver, full_name, q3_s FROM results WHERE season = ? AND round = ? AND session = 'Q' "
        "ORDER BY position NULLS LAST LIMIT 1",
        [race.season, race.round],
    ).fetchone()
    if row is None or row[2] is None:
        return None
    time = lap_time(float(row[2]))
    return Case(
        id=f"data-pole-{race.key}",
        family="data",
        question=f"Qui a signé la pole position du {race.label}, et en quel temps ?",
        answer=f"{row[1]} a signé la pole position en {time}.",
        value=[_last_name(str(row[1])), str(time)],
        origin=_origin(race, "results", table="results", session="Q", position=1),
    )


def _classified(race: Race) -> list[dict[str, Any]]:
    return [row for row in race.results if str(row["classified_position"]).isdigit()]


def _tyres(db: duckdb.DuckDBPyConnection, race: Race, rng: random.Random) -> Case | None:
    driver = rng.choice(_classified(race))["driver"]
    compounds = [
        str(row[0])
        for row in db.execute(
            "SELECT compound FROM stints WHERE season = ? AND round = ? AND session = 'R' AND driver = ? "
            "GROUP BY compound ORDER BY min(stint)",
            [race.season, race.round, driver],
        ).fetchall()
        if row[0]
    ]
    if not compounds:
        return None
    name = race.name(driver)
    french = ", ".join(COMPOUNDS_FR.get(compound, compound.lower()) for compound in compounds)
    return Case(
        id=f"data-tyres-{race.key}-{driver}",
        family="data",
        question=f"Quels types de pneus {name} a-t-il utilisés pendant la course du {race.label} ?",
        answer=f"{name} a utilisé des pneus {french}, dans cet ordre.",
        value=compounds,
        tags=["compounds_in_english"],
        origin=_origin(race, "stints", table="stints", driver=driver),
    )


def _stops(db: duckdb.DuckDBPyConnection, race: Race, rng: random.Random) -> Case | None:
    driver = rng.choice(_classified(race))["driver"]
    row = db.execute(
        "SELECT count(*) FROM pit_stops WHERE season = ? AND round = ? AND session = 'R' AND driver = ? "
        "AND NOT red_flag",
        [race.season, race.round, driver],
    ).fetchone()
    stops = int(row[0]) if row else 0
    name = race.name(driver)
    return Case(
        id=f"data-stops-{race.key}-{driver}",
        family="data",
        question=f"Combien d'arrêts aux stands {name} a-t-il effectués pendant la course du {race.label} ?",
        answer=f"{name} a effectué {stops} arrêt{'s' if stops > 1 else ''} (hors changements sous drapeau rouge).",
        value=stops,
        tolerance=0,
        origin=_origin(race, "pit_stops", table="pit_stops", driver=driver),
    )


def _grid_and_finish(db: duckdb.DuckDBPyConnection, race: Race, rng: random.Random) -> Case | None:
    row = rng.choice(_classified(race))
    grid, finish = int(row["grid_position"]), int(row["classified_position"])
    if grid == 0:
        return None
    name = race.name(row["driver"])
    return Case(
        id=f"data-finish-{race.key}-{row['driver']}",
        family="data",
        question=f"Parti de quelle position, {name} a-t-il terminé à quelle place au {race.label} ?",
        answer=f"{name} est parti {_ordinal(grid)} et a terminé {_ordinal(finish)}.",
        value=[str(grid), str(finish)],
        origin=_origin(race, "results", table="results", driver=row["driver"]),
    )


def _fastest_lap(db: duckdb.DuckDBPyConnection, race: Race, rng: random.Random) -> Case | None:
    row = db.execute(
        "SELECT driver, lap_number, lap_time_s FROM laps WHERE season = ? AND round = ? AND session = 'R' "
        "AND lap_time_s IS NOT NULL AND NOT coalesce(deleted, false) ORDER BY lap_time_s LIMIT 1",
        [race.season, race.round],
    ).fetchone()
    if row is None:
        return None
    name, time = race.name(str(row[0])), lap_time(float(row[2]))
    return Case(
        id=f"data-fastest-{race.key}",
        family="data",
        question=f"Qui a réalisé le meilleur tour en course au {race.label}, et en quel temps ?",
        answer=f"{name}, en {time} au tour {int(row[1])}.",
        value=[_last_name(name), str(time)],
        origin=_origin(race, "laps", table="laps", fastest=True),
    )


DATA: list[Callable[[duckdb.DuckDBPyConnection, Race, random.Random], Case | None]] = [
    _winner,
    _pole,
    _tyres,
    _stops,
    _grid_and_finish,
    _fastest_lap,
]


# ---- computation ------------------------------------------------------------------------------------------------


def _stop_cases(data: RaceData, race: Race, rng: random.Random) -> Iterator[Case]:
    """Time lost, pit lane time or stationary time of one stop of a driver."""
    driver = rng.choice(_classified(race))["driver"]
    try:
        stops = pit_stop_loss(data, PitLossInput(season=race.season, round=race.round, driver=driver)).stops
    except ToolError:
        return
    usable = [stop for stop in stops if not stop.neutralized and not stop.red_flag]
    if not usable:
        return
    stop = rng.choice(usable)
    name, nth = race.name(driver), _ordinal(stop.stop_number)
    inputs = {"tool": "pit_stop_loss", "driver": driver, "stop_number": stop.stop_number}
    which = rng.choice(["time_lost", "pit_lane", "stationary"])
    if which == "time_lost" and stop.time_lost_s is not None:
        yield Case(
            id=f"comp-time-lost-{race.key}-{driver}-{stop.stop_number}",
            family="computation",
            question=f"Combien de temps {name} a-t-il perdu lors de son {nth} arrêt au {race.label} ?",
            answer=(
                f"Environ {stop.time_lost_s:.1f} s : ses tours d'entrée et de sortie des stands, comparés à deux "
                f"tours normaux de {stop.reference_lap_s} s."
            ),
            value=stop.time_lost_s,
            tolerance=0.5,
            unit="s",
            origin=_origin(race, "pit_stop_loss", **inputs, field="time_lost_s"),
        )
    elif which == "pit_lane" and stop.pit_lane_time_s is not None:
        yield Case(
            id=f"comp-pit-lane-{race.key}-{driver}-{stop.stop_number}",
            family="computation",
            question=f"Combien de temps {name} a-t-il passé dans la voie des stands lors de son {nth} arrêt au "
            f"{race.label} ?",
            answer=f"{stop.pit_lane_time_s} s, de la ligne d'entrée à la ligne de sortie des stands.",
            value=stop.pit_lane_time_s,
            tolerance=0.1,
            unit="s",
            origin=_origin(race, "pit_stop_loss", **inputs, field="pit_lane_time_s"),
        )
    elif which == "stationary" and stop.stationary_time_s is not None:
        yield Case(
            id=f"comp-stationary-{race.key}-{driver}-{stop.stop_number}",
            family="computation",
            question=f"Combien de temps la voiture de {name} est-elle restée immobile lors de son {nth} arrêt au "
            f"{race.label} ?",
            answer=f"{stop.stationary_time_s} s à l'arrêt dans son emplacement.",
            value=stop.stationary_time_s,
            tolerance=0.1,
            unit="s",
            origin=_origin(race, "pit_stop_loss", **inputs, field="stationary_time_s"),
        )


def _degradation(data: RaceData, race: Race, rng: random.Random) -> Iterator[Case]:
    driver = rng.choice(_classified(race)[:10])["driver"]
    try:
        stints = stint_degradation(data, DegradationInput(season=race.season, round=race.round, driver=driver)).stints
    except ToolError:
        return
    # A slope worth asking about: enough clean laps, and laps that line up.
    good = [
        stint
        for stint in stints
        if stint.degradation_s_per_lap is not None and stint.laps_used >= 10 and (stint.r_squared or 0) >= 0.5
    ]
    if not good:
        return
    stint = rng.choice(good)
    name = race.name(driver)
    compound = COMPOUNDS_FR.get(stint.compound or "", (stint.compound or "").lower())
    yield Case(
        id=f"comp-degradation-{race.key}-{driver}-{stint.stint}",
        family="computation",
        question=f"Quelle a été la dégradation des pneus {compound} de {name} pendant son relais des tours "
        f"{stint.start_lap} à {stint.end_lap} au {race.label} ?",
        answer=(
            f"Environ {stint.degradation_s_per_lap:.3f} s perdues par tour d'usure, effet du carburant retiré, sur "
            f"{stint.laps_used} tours propres."
        ),
        value=stint.degradation_s_per_lap,
        tolerance=0.02,
        unit="s/tour",
        origin=_origin(race, "stint_degradation", tool="stint_degradation", driver=driver, stint=stint.stint),
    )


def _gap(data: RaceData, race: Race, rng: random.Random) -> Iterator[Case]:
    top = _classified(race)[:6]
    if len(top) < 2:
        return
    first, second = rng.sample(top, 2)
    driver, reference = sorted([first, second], key=lambda row: int(row["classified_position"]))[::-1]
    try:
        gaps = gap_between_drivers(
            data,
            GapInput(
                season=race.season, round=race.round, driver=driver["driver"], reference_driver=reference["driver"]
            ),
        )
    except ToolError:
        return
    lap = rng.choice(gaps.laps[len(gaps.laps) // 4 :])
    a, b = race.name(driver["driver"]), race.name(reference["driver"])
    where = "derrière" if lap.gap_s > 0 else "devant"
    yield Case(
        id=f"comp-gap-{race.key}-{driver['driver']}-{reference['driver']}-{lap.lap}",
        family="computation",
        question=f"Quel écart séparait {a} de {b} à la fin du tour {lap.lap} du {race.label} ?",
        answer=f"{abs(lap.gap_s)} s : {a} était {where} {b}.",
        value=abs(lap.gap_s),
        tolerance=0.1,
        unit="s",
        origin=_origin(
            race, "gap_between_drivers", tool="gap_between_drivers", driver=driver["driver"],
            reference_driver=reference["driver"], lap=lap.lap,
        ),
    )  # fmt: skip


def _safety_cars(data: RaceData, race: Race, rng: random.Random) -> Iterator[Case]:
    try:
        result = neutralizations(data, NeutralizationsInput(season=race.season, round=race.round))
    except ToolError:
        return
    yield Case(
        id=f"comp-safety-cars-{race.key}",
        family="computation",
        question=f"Combien de fois la voiture de sécurité est-elle intervenue pendant la course du {race.label} ?",
        answer=(
            f"{result.safety_cars} fois la voiture de sécurité, {result.virtual_safety_cars} fois la voiture de "
            f"sécurité virtuelle, {result.red_flags} drapeau(x) rouge(s)."
        ),
        value=result.safety_cars,
        tolerance=0,
        origin=_origin(race, "neutralizations", tool="neutralizations"),
    )


COMPUTATION: list[Callable[[RaceData, Race, random.Random], Iterator[Case]]] = [
    _stop_cases,
    _stop_cases,
    _degradation,
    _gap,
    _safety_cars,
]


# ---- strategy ---------------------------------------------------------------------------------------------------


def pit_cycles(data: RaceData, race: Race) -> Iterator[tuple[str, str, Any]]:
    """Each pair of drivers running next to each other in the top 10 whose first stops swapped them."""
    top = [row["driver"] for row in _classified(race)[:10]]
    for driver in top:
        for rival in top:
            if driver >= rival:
                continue
            try:
                cycle = pit_cycle(data, PitCycleInput(season=race.season, round=race.round, driver=driver, rival=rival))
            except ToolError:
                continue
            before, rival_before = cycle.position_before, cycle.rival_position_before
            next_to = before is not None and rival_before is not None and abs(before - rival_before) == 1
            if next_to and (cycle.driver_passed_rival or cycle.rival_passed_driver):
                yield driver, rival, cycle


def _cause(data: RaceData, race: Race, winner: str, loser: str, cycle: Any) -> tuple[str, str] | None:
    """The main cause of the swap, as a rule sees it: (tag, sentence). None when no rule applies."""
    if cycle.neutralized:
        return "neutralization", "les arrêts ont eu lieu pendant une neutralisation, qui a changé leur coût"
    stationary: dict[str, float | None] = {}
    for code in (winner, loser):
        try:
            stops = pit_stop_loss(data, PitLossInput(season=race.season, round=race.round, driver=code)).stops
        except ToolError:
            return None
        lap = cycle.driver_stop_lap if code == cycle.driver else cycle.rival_stop_lap
        stationary[code] = next((stop.stationary_time_s for stop in stops if stop.lap == lap), None)
    slow, fast = stationary[loser], stationary[winner]
    if slow is not None and fast is not None and slow - fast >= 1.5:
        return "slow_stop", f"un arrêt lent : {slow} s immobile, contre {fast} s"
    winner_lap = cycle.driver_stop_lap if winner == cycle.driver else cycle.rival_stop_lap
    loser_lap = cycle.rival_stop_lap if winner == cycle.driver else cycle.driver_stop_lap
    gained = abs(cycle.gained_s)
    if winner_lap < loser_lap:
        return "undercut", f"l'undercut : {race.name(winner)} s'est arrêté {loser_lap - winner_lap} tour(s) plus tôt " \
            f"et a gagné {gained} s sur le cycle d'arrêts"  # fmt: skip
    if winner_lap > loser_lap:
        return "overcut", f"l'overcut : {race.name(winner)} est resté {winner_lap - loser_lap} tour(s) de plus en " \
            f"piste et a gagné {gained} s sur le cycle d'arrêts"  # fmt: skip
    return None


def strategy_cases(data: RaceData, race: Race) -> Iterator[Case]:
    for driver, rival, cycle in pit_cycles(data, race):
        winner, loser = (driver, rival) if cycle.driver_passed_rival else (rival, driver)
        cause = _cause(data, race, winner, loser, cycle)
        if cause is None:
            continue
        tag, sentence = cause
        yield Case(
            id=f"strategy-{race.key}-{loser}-{winner}",
            family="strategy",
            question=f"Pourquoi {race.name(loser)} a-t-il perdu sa place face à {race.name(winner)} lors des arrêts "
            f"aux stands du {race.label} ?",
            answer=f"Cause principale : {sentence}.",
            tags=[f"cause:{tag}"],
            origin=Origin(
                method="rule",
                by=f"{GENERATOR}:pit_cycle",
                inputs={
                    "season": race.season,
                    "round": race.round,
                    "session": "R",
                    "driver": driver,
                    "rival": rival,
                    "tool": "pit_cycle",
                },
                reviewed=False,
            ),
        )


# ---- the whole set ----------------------------------------------------------------------------------------------


def generate(
    db: duckdb.DuckDBPyConnection, *, data_cases: int = 100, computation_cases: int = 100, strategy: int = 50
) -> list[Case]:
    """The computed cases, the same for the same lake."""
    db = in_memory(db)
    rng = random.Random(SEED)
    tools = RaceData(db)
    all_races = [race for race in races(db) if _classified(race)]
    cases: dict[str, Case] = {}

    def add(case: Case | None, family_limit: int) -> None:
        if case and case.id not in cases and sum(c.family == case.family for c in cases.values()) < family_limit:
            cases[case.id] = case

    order = all_races[:]
    rng.shuffle(order)
    # Templates in turn over the races, so that every kind of question and every race have their share.
    for index, race in enumerate(order * 3):
        add(DATA[index % len(DATA)](db, race, rng), data_cases)
    for index, race in enumerate(order * 3):
        for case in COMPUTATION[index % len(COMPUTATION)](tools, race, rng):
            add(case, computation_cases)
    for race in order:
        for case in list(strategy_cases(tools, race))[:STRATEGY_PER_RACE]:
            add(case, strategy)
    return list(cases.values())
