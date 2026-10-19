"""What an analysis means, written by code in French (LAB-207): the debrief's model rephrases and links these readings
instead of deducing them from the numbers.

A first try at a debrief in prose read a pit cycle backwards ("Leclerc perd du terrain sur Piastri par l'undercut",
when the undercut gained 3 s, not enough to pass) and compared a degradation with a driver nobody measured. The
numbers were right; the meaning was the model's. Here the meaning is code: who was ahead before and after a cycle, what
the attempt gained, whether a degradation is measured well enough to say anything.

A reading's numbers come from the output it reads, rounded, or are counted by code from it (the laps between two
stops, the places gained from the grid). The reading is kept in the output (`lecture`): a draft citing the analysis
may copy them, and the number check finds them there.
"""

import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from f1.router import plain

COMPOUNDS_FR = {
    "SOFT": "tendres",
    "MEDIUM": "mediums",
    "HARD": "durs",
    "INTERMEDIATE": "intermédiaires",
    "WET": "pluie",
}
NEUTRALIZATIONS_FR = {
    "safety_car": "voiture de sécurité",
    "virtual_safety_car": "voiture de sécurité virtuelle",
    "red_flag": "drapeau rouge",
}
# Under this fit of a stint's lap times, its slope says nothing: traffic, fuel and track evolution weigh more.
RELIABLE_FIT = 0.3

Names = Mapping[str, str]


def reading(tool: str, output: Mapping[str, Any], names: Names) -> list[str]:
    """The sentences that say what the output of a tool means; none for a tool without a reading."""
    read = _READERS.get(tool)
    return read(output, names) if read else []


def _pit_cycle(output: Mapping[str, Any], names: Names) -> list[str]:
    driver, rival = output["driver"], output["rival"]
    name = {driver: names.get(driver, driver), rival: names.get(rival, rival)}
    lap = {driver: output["driver_stop_lap"], rival: output["rival_stop_lap"]}
    ahead_before, ahead_after = output["ahead_before"], output["ahead_after"]
    behind_before = rival if ahead_before == driver else driver
    # The gaps are the driver's to the rival: positive when the rival is ahead. Told from the car behind.
    gap_before, gap_after = abs(output["gap_before_s"]), abs(output["gap_after_s"])
    gained = output["gained_s"] if behind_before == driver else -output["gained_s"]  # by the car behind before
    first_in = driver if lap[driver] <= lap[rival] else rival
    second_in = rival if first_in == driver else driver
    apart = lap[second_in] - lap[first_in]
    stops = (
        f"{name[first_in]} rentre au tour {lap[first_in]}, {apart} tour{'s' if apart > 1 else ''} avant "
        f"{name[second_in]}, arrêté au tour {lap[second_in]}"
    )
    neutralized = " Les arrêts ont eu lieu sous neutralisation : ils ont coûté moins." if output["neutralized"] else ""
    if lap[driver] == lap[rival]:
        if ahead_before == ahead_after:
            return [f"Arrêts au même tour ({lap[driver]}) : {name[ahead_after]} reste devant.{neutralized}"]
        return [
            f"Arrêts au même tour ({lap[driver]}) : {name[ahead_after]} ressort devant {name[ahead_before]}, "
            f"l'arrêt lui-même a fait la différence.{neutralized}"
        ]
    first = driver if lap[driver] < lap[rival] else rival
    move = "undercut" if first == behind_before else "overcut"
    before, after = _fr(gap_before, 1), _fr(gap_after, 1)
    if ahead_before != ahead_after:
        return [
            f"{name[ahead_after]} passe devant {name[ahead_before]} grâce au cycle d'arrêts ({stops}) : son {move} "
            f"a réussi. Il était à {before} s derrière avant les arrêts, il est {after} s devant après.{neutralized}"
        ]
    chaser = name[behind_before]
    if gained > 0:
        what = (
            f"l'{move} {_of(chaser)} lui a rapporté {_fr(gained, 1)} s, pas assez pour passer : l'écart passe de "
            f"{before} s à {after} s"
        )
    else:
        what = f"l'{move} {_of(chaser)} lui a coûté {_fr(-gained, 1)} s : l'écart passe de {before} s à {after} s"
    return [
        f"{name[ahead_before]} reste devant {name[behind_before]} au cycle d'arrêts ({stops}) : {what}.{neutralized}"
    ]


def _pit_stop_loss(output: Mapping[str, Any], names: Names) -> list[str]:
    driver = names.get(output["driver"], output["driver"])
    if not output["stops"]:
        return [f"{driver} ne s'est pas arrêté."]
    sentences = []
    for stop in output["stops"]:
        before = COMPOUNDS_FR.get(stop.get("compound_before") or "", "?")
        after = COMPOUNDS_FR.get(stop.get("compound_after") or "", "?")
        when = (
            " pendant le drapeau rouge, sans perte de temps"
            if stop["red_flag"]
            else " sous neutralisation, ce qui coûte moins qu'un arrêt en course"
            if stop["neutralized"]
            else ""
        )
        lost = "" if stop["red_flag"] or stop["time_lost_s"] is None else f", {_fr(stop['time_lost_s'], 1)} s perdues"
        sentences.append(f"{driver} s'arrête au tour {stop['lap']}{when}{lost}, des {before} aux {after}.")
    return sentences


def _stint_degradation(output: Mapping[str, Any], names: Names) -> list[str]:
    driver = names.get(output["driver"], output["driver"])
    sentences = []
    for stint in output["stints"]:
        compound = COMPOUNDS_FR.get(stint.get("compound") or "", "?")
        laps = f"relais {stint['stint']} en {compound}, tours {stint['start_lap']} à {stint['end_lap']}"
        slope, fit = stint.get("degradation_s_per_lap"), stint.get("r_squared")
        if slope is None or fit is None or fit < RELIABLE_FIT:
            sentences.append(f"{driver}, {laps} : usure non mesurable, les temps au tour varient trop pour la lire.")
        elif slope <= 0:
            sentences.append(f"{driver}, {laps} : aucune perte mesurée due à l'usure des pneus.")
        else:
            sentences.append(f"{driver}, {laps} : {_fr(slope, 2)} s perdues par tour d'usure des pneus.")
    return sentences


def _neutralizations(output: Mapping[str, Any], names: Names) -> list[str]:
    if not output["periods"]:
        return ["Aucune voiture de sécurité, voiture de sécurité virtuelle ni drapeau rouge pendant la course."]
    return [
        f"{NEUTRALIZATIONS_FR.get(period['kind'], period['kind']).capitalize()} du tour {period['start_lap']} "
        f"au tour {period['end_lap']}."
        if period["start_lap"] != period["end_lap"]
        else f"{NEUTRALIZATIONS_FR.get(period['kind'], period['kind']).capitalize()} au tour {period['start_lap']}."
        for period in output["periods"]
    ]


def _gap(output: Mapping[str, Any], names: Names) -> list[str]:
    driver = names.get(output["driver"], output["driver"])
    reference = names.get(output["reference_driver"], output["reference_driver"])
    sentences = []
    for lap in output["laps"][:5]:  # a span cited by a question; a whole race is read in its numbers
        gap = lap["gap_s"]
        side = f"{_fr(abs(gap), 1)} s derrière" if gap > 0 else f"{_fr(abs(gap), 1)} s devant"
        sentences.append(f"À la fin du tour {lap['lap']}, {driver} est {side} {reference}.")
    return sentences


def _of(name: str) -> str:
    """ "de Charles Leclerc", "d'Alexander Albon"."""
    return f"d'{name}" if name[:1].upper() in "AEIOUYÉÈ" else f"de {name}"


def _places(gained: int) -> str:
    if gained == 0:
        return ", même place"
    count, plural = abs(gained), "s" if abs(gained) > 1 else ""
    return f", {count} place{plural} {'gagnée' if gained > 0 else 'perdue'}{plural}"


def _ordinal(rank: int) -> str:
    return "1er" if rank == 1 else f"{rank}e"


def _fr(value: float, decimals: int) -> str:
    """A number as French writes it: 7,2."""
    return f"{value:.{decimals}f}".replace(".", ",")


def lap_time(seconds: float) -> str:
    """A lap time as timing writes it: 95.069 -> "1:35.069". A model asked to convert wrote 1:32.000 (LAB-154)."""
    minutes, rest = divmod(round(seconds, 3), 60)
    return f"{int(minutes)}:{rest:06.3f}"


def _classification(output: Mapping[str, Any], names: Names) -> list[str]:
    """Each driver from the grid to the finish: the only places gained or lost a debrief may tell; the fastest lap.
    A qualifying session: each driver's place and best time."""
    if output.get("session") in {"Q", "SQ"}:
        return _qualifying(output, names)
    sentences = []
    for row in output.get("classification") or []:
        name = row.get("name") or names.get(row["driver"], row["driver"])
        grid, finish = row.get("grid"), _rank(row)
        start = "des stands" if grid == 0 else _ordinal(grid) if grid else "?"
        if finish is None:
            sentences.append(f"{name} : parti {start}, non classé ({row.get('status')}).")
            continue
        moved = "" if not grid else _places(grid - finish)
        sentences.append(f"{name} : parti {start}, arrivé {_ordinal(finish)}{moved}.")
    if fastest := output.get("fastest_lap"):
        name = fastest.get("name") or names.get(fastest["driver"], fastest["driver"])
        sentences.append(f"Meilleur tour en course : {name}, en {lap_time(fastest['lap_time_s'])} au tour "
                         f"{fastest['lap']}.")  # fmt: skip
    return sentences


def _qualifying(output: Mapping[str, Any], names: Names) -> list[str]:
    """The order of a qualifying, the pole first, each driver's best time in the last part reached."""
    sentences = []
    for row in output.get("classification") or []:
        name = row.get("name") or names.get(row["driver"], row["driver"])
        parts = [(part, row.get(f"q{number}_s")) for number, part in ((3, "Q3"), (2, "Q2"), (1, "Q1"))]
        best = next(((part, time) for part, time in parts if time), None)
        rank = _rank(row)
        place = "pole position" if rank == 1 else f"{_ordinal(rank)} des qualifications" if rank else "non classé"
        time = f", {lap_time(best[1])} en {best[0]}" if best else ", sans temps"
        sentences.append(f"{name} : {place}{time}.")
    return sentences


def _strategies(output: Mapping[str, Any], names: Names) -> list[str]:
    """Who started on which tyres, and who stopped how many times: what a question on a choice is answered against."""
    drivers = list(output.get("drivers") or [])
    sentences = []
    for compound in dict.fromkeys(str(d.get("start_compound")) for d in drivers if d.get("start_compound")):
        starters = [names.get(d["driver"], d["driver"]) for d in drivers if d.get("start_compound") == compound]
        count = f"{len(starters)} pilote{'s' if len(starters) > 1 else ''}"
        sentences.append(f"Départ en {COMPOUNDS_FR.get(compound, compound)} : {count} ({', '.join(starters)}).")
    for stops in sorted({len(d.get("stop_laps") or []) for d in drivers}):
        who = [names.get(d["driver"], d["driver"]) for d in drivers if len(d.get("stop_laps") or []) == stops]
        sentences.append(f"{stops} arrêt{'s' if stops > 1 else ''} : {', '.join(who)}.")
    return sentences


def _moments(output: Mapping[str, Any], names: Names) -> list[str]:
    """The moments that made the race, by rank (LAB-204): what each one was, with the numbers that measure it."""
    sentences = []
    for moment in output.get("moments") or []:
        name = names.get(moment["driver"], moment["driver"])
        laps = list(moment.get("laps") or [])
        text = _MOMENT_TEXT[moment["kind"]](moment, name, laps, names)
        sentences.append(f"Moment {moment['rank']} : {text}")
    if not sentences:
        return ["Aucun moment de la course n'a fait bouger le classement de façon mesurable."]
    sentences.append("Les moments sont classés par les points au championnat qu'ils ont fait bouger.")
    return sentences


def _start(moment: Mapping[str, Any], name: str, laps: list[int], names: Names) -> str:
    verb = "gagne" if moment["places"] > 0 else "perd"
    count = abs(moment["places"])
    return (
        f"{name} {verb} {count} place{'s' if count > 1 else ''} au départ, de {_ordinal(moment['from_position'])} à "
        f"{_ordinal(moment['to_position'])} à la fin du tour 1."
    )


def _overtakes(moment: Mapping[str, Any], name: str, laps: list[int], names: Names) -> str:
    made = [f"{names.get(code, code)} (tour {lap})" for code, lap in zip(moment["passed"], laps, strict=True)]
    count = moment["places"]
    what = f"{count} dépassements en piste" if count > 1 else "un dépassement en piste"
    return f"{name} réussit {what} : {', '.join(made)}."


def _cycle(moment: Mapping[str, Any], name: str, laps: list[int], names: Names) -> str:
    rival = names.get(moment["rival"], moment["rival"])
    move = "undercut" if moment["outcome"] == "undercut_worked" else "overcut"
    when = f"aux tours {laps[0]} et {laps[-1]}" if len(laps) > 1 else f"au tour {laps[0]}"
    return (
        f"{name} passe {rival} au cycle d'arrêts par un {move} (arrêts {when}) : il gagne "
        f"{_fr(moment['seconds'], 1)} s sur {rival}."
    )


def _neutralized_stop(moment: Mapping[str, Any], name: str, laps: list[int], names: Names) -> str:
    under = NEUTRALIZATIONS_FR.get(moment.get("neutralization") or "", "neutralisation")
    places = ""
    if moment.get("from_position") and moment.get("to_position"):
        places = f" ; {_ordinal(moment['from_position'])} avant l'arrêt, {_ordinal(moment['to_position'])} après"
    return (
        f"{name} s'arrête au tour {laps[0]} sous {under} : l'arrêt lui coûte {_fr(moment['seconds'], 1)} s de moins "
        f"qu'un arrêt habituel de la course{places}."
    )


def _slow_stop(moment: Mapping[str, Any], name: str, laps: list[int], names: Names) -> str:
    places = ""
    if moment.get("from_position") and moment.get("to_position"):
        places = f" ; {_ordinal(moment['from_position'])} avant l'arrêt, {_ordinal(moment['to_position'])} après"
    return (
        f"L'arrêt {_of(name)} au tour {laps[0]} lui coûte {_fr(moment['seconds'], 1)} s de plus que ceux des autres "
        f"pilotes arrêtés dans les mêmes tours{places}. Les données ne disent pas pourquoi (arrêt lent, sortie de "
        "piste...)."
    )


def _strategy(moment: Mapping[str, Any], name: str, laps: list[int], names: Names) -> str:
    stops, usual, changes = moment["stops"], moment["usual_stops"], list(moment.get("red_flag_changes") or [])
    made = "ne fait aucun arrêt" if stops == 0 else f"fait {stops} arrêt{'s' if stops > 1 else ''}"
    free = f", et change de pneus sous drapeau rouge au tour {changes[0]}" if changes else ""
    return (
        f"{name} {made} quand la plupart des pilotes en font {usual}{free} : parti "
        f"{_ordinal(moment['from_position'])}, arrivé {_ordinal(moment['to_position'])}{_places(moment['places'])}."
    )


def _setback(moment: Mapping[str, Any], name: str, laps: list[int], names: Names) -> str:
    count = abs(moment["places"])
    return (
        f"{name} perd {count} places au tour {laps[0]}, sans s'arrêter ni voiture de sécurité : de "
        f"{_ordinal(moment['from_position'])} à {_ordinal(moment['to_position'])}. Les données ne disent pas pourquoi "
        "(sortie de piste, problème...)."
    )


def _retirement(moment: Mapping[str, Any], name: str, laps: list[int], names: Names) -> str:
    where = f", alors {_ordinal(moment['from_position'])}" if moment.get("from_position") else ""
    why = f" ({moment['status']})" if moment.get("status") else ""
    return f"{name} abandonne au tour {laps[0]}{where}{why}."


_MOMENT_TEXT: dict[str, Callable[[Mapping[str, Any], str, list[int], Names], str]] = {
    "start": _start,
    "overtakes": _overtakes,
    "pit_cycle": _cycle,
    "neutralized_stop": _neutralized_stop,
    "slow_stop": _slow_stop,
    "strategy": _strategy,
    "setback": _setback,
    "retirement": _retirement,
}


_READERS: dict[str, Callable[[Mapping[str, Any], Names], list[str]]] = {
    "pit_cycle": _pit_cycle,
    "pit_stop_loss": _pit_stop_loss,
    "stint_degradation": _stint_degradation,
    "neutralizations": _neutralizations,
    "gap_between_drivers": _gap,
    "session_result": _classification,
    "race_strategies": _strategies,
    "key_moments": _moments,
}


# "Leclerc reste devant Piastri et Hamilton", "Russell ressort derrière Leclerc", "Hamilton passe Albon".
_AHEAD = re.compile(r"\b(?:devant|passe|depasse|double)\b")
_BEHIND = re.compile(r"\bderriere\b")
_NEGATION = re.compile(r"\b(?:ne|n')\b|\bsans\b|\bpas\b|\bjamais\b")


def order_problems(text: str, outputs: Iterable[Mapping[str, Any]], names: Names) -> list[str]:
    """The claims of a text on which of two drivers was ahead that the data contradicts, checked by code: a model
    asked to check them read "Leclerc reste devant Piastri" as right, quoting the reading that Piastri stayed ahead.

    A clause says its first driver is ahead of (or behind) the drivers named after "devant" (or "derrière"), or
    after "passe". It is contradicted when every analysis that orders the two, a pit cycle (who came out ahead) or
    the classification (who finished ahead), puts them the other way; a negated clause is not read."""
    orders = _orders(outputs)
    found = []
    for clause in re.split(r"[.;:!?,]| mais | alors que | tandis que ", plain(text)):
        if _NEGATION.search(clause) or not (ahead := _AHEAD.search(clause) or _BEHIND.search(clause)):
            continue
        before = _named(clause[: ahead.start()], names)
        after = _named(clause[ahead.end() :], names)
        if not before:
            continue
        first, behind = before[-1], ahead.re is _BEHIND
        for other in after:
            claimed = (other, first) if behind else (first, other)
            known = orders.get(frozenset(claimed))
            if known and claimed not in known:
                found.append(
                    f"sens, contredit (code) : « {names.get(claimed[0], claimed[0])} devant "
                    f"{names.get(claimed[1], claimed[1])} » ; les analyses mettent "
                    f"{names.get(claimed[1], claimed[1])} devant"
                )
    return found


def _orders(outputs: Iterable[Mapping[str, Any]]) -> dict[frozenset[str], set[tuple[str, str]]]:
    """For each pair of drivers, the orders (ahead, behind) the analyses give: after a pit cycle, at the finish."""
    orders: dict[frozenset[str], set[tuple[str, str]]] = {}
    for output in outputs:
        if "ahead_after" in output and "rival" in output:
            ahead = output["ahead_after"]
            other = output["rival"] if ahead == output["driver"] else output["driver"]
            orders.setdefault(frozenset((ahead, other)), set()).add((ahead, other))
        for moment in output.get("moments") or []:  # a pass on a pit cycle: the driver came out ahead
            if moment.get("kind") == "pit_cycle":
                orders.setdefault(frozenset((moment["driver"], moment["rival"])), set()).add(
                    (moment["driver"], moment["rival"])
                )
        for row in output.get("classification") or []:
            for other in output["classification"]:
                mine, theirs = _rank(row), _rank(other)
                if mine is not None and theirs is not None and mine < theirs:
                    pair = (str(row["driver"]), str(other["driver"]))
                    orders.setdefault(frozenset(pair), set()).add(pair)
    return orders


def _rank(row: Mapping[str, Any]) -> int | None:
    position = str(row.get("position") or "")
    return int(position) if position.isdigit() else None


def _named(clause: str, names: Names) -> list[str]:
    """The drivers a clause names, in order, by full or last name."""
    hits = []
    for code, name in names.items():
        full = plain(name)
        last = full.split()[-1]
        for alias in dict.fromkeys([full, last]):
            if match := re.search(rf"\b{re.escape(alias)}\b", clause):
                hits.append((match.start(), code))
                break
    return [code for _, code in sorted(hits)]
