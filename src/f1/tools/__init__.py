"""Deterministic race analysis tools: the numbers of a debrief come from here, never from a model.

`catalog(data)` returns every tool bound to the race data, ready for tool calling.
"""

from typing import Any

from core.tools import Tool
from f1.tools.data import RaceData
from f1.tools.degradation import DegradationInput, DegradationOutput, stint_degradation
from f1.tools.gaps import GapInput, GapOutput, gap_between_drivers
from f1.tools.neutralizations import NeutralizationsInput, NeutralizationsOutput, neutralizations
from f1.tools.pit_cycle import PitCycleInput, PitCycleOutput, pit_cycle
from f1.tools.pit_loss import PitLossInput, PitLossOutput, pit_stop_loss

__all__ = ["RaceData", "catalog"]


def catalog(data: RaceData) -> list[Tool[Any, Any]]:
    return [
        Tool(
            "gap_between_drivers",
            "Gap between two drivers at the end of each lap, and how it changed lap by lap.",
            GapInput,
            GapOutput,
            lambda request: gap_between_drivers(data, request),
        ),
        Tool(
            "stint_degradation",
            "Tyre degradation of a driver's stints: lap time lost per lap of tyre age, fuel effect removed, "
            "computed on green flag laps only.",
            DegradationInput,
            DegradationOutput,
            lambda request: stint_degradation(data, request),
        ),
        Tool(
            "pit_stop_loss",
            "Time a driver's pit stops cost: in-lap and out-lap against two normal laps, with pit lane and "
            "stationary times.",
            PitLossInput,
            PitLossOutput,
            lambda request: pit_stop_loss(data, request),
        ),
        Tool(
            "pit_cycle",
            "Undercut or overcut between two drivers who stopped at different laps: gap and positions before and "
            "after the stops, time gained.",
            PitCycleInput,
            PitCycleOutput,
            lambda request: pit_cycle(data, request),
        ),
        Tool(
            "neutralizations",
            "Safety car, virtual safety car and red flag periods of a race or sprint, with laps and times.",
            NeutralizationsInput,
            NeutralizationsOutput,
            lambda request: neutralizations(data, request),
        ),
    ]
