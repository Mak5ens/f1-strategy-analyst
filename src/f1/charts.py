"""Which race chart shows an analysis (LAB-189): read by code from the tool and its arguments, so that a debrief's
point can open the chart of the numbers it cites, zoomed on the laps they are about.

    gap_between_drivers  -> the gaps, to the reference driver, over the laps asked
    pit_cycle            -> the gaps, to the rival, from a few laps before the first stop to a few after the second
    stint_degradation    -> the pace of the driver, over the stint asked (or the race)
    pit_stop_loss        -> the positions of the driver

Any other analysis has no chart: a chart is never guessed.
"""

from typing import Any, Literal

from pydantic import Field

from core.agent.state import Result
from f1.display import Response

# Laps shown on each side of a pit cycle: the cycle reads better with the laps that led to it and followed it.
CYCLE_MARGIN = 3


class FactChart(Response):
    kind: Literal["positions", "gaps", "pace"]
    drivers: list[str] = Field(description="Codes of the drivers the analysis is about, highlighted")
    reference: str | None = Field(None, description="The driver the gaps are measured to")
    from_lap: int | None = Field(None, description="First lap of the zoom; the whole race when None")
    to_lap: int | None = None


def chart_for(result: Result) -> FactChart | None:
    """The chart of an analysis that computed something; None for one that failed or that no chart shows."""
    if not result.ok or result.output is None:
        return None
    arguments, output = result.arguments, result.output
    if result.tool == "gap_between_drivers":
        laps = [lap["lap"] for lap in output.get("laps", [])]
        return FactChart(
            kind="gaps",
            drivers=[arguments["driver"], arguments["reference_driver"]],
            reference=arguments["reference_driver"],
            from_lap=arguments.get("from_lap") or min(laps, default=None),
            to_lap=arguments.get("to_lap") or max(laps, default=None),
        )
    if result.tool == "pit_cycle":
        return FactChart(
            kind="gaps",
            drivers=[output["driver"], output["rival"]],
            reference=output["rival"],
            from_lap=max(1, int(output["lap_before"]) - CYCLE_MARGIN),
            to_lap=int(output["lap_after"]) + CYCLE_MARGIN,
        )
    if result.tool == "stint_degradation":
        stints: list[dict[str, Any]] = output.get("stints", [])
        asked = arguments.get("stint") is not None and len(stints) == 1
        return FactChart(
            kind="pace",
            drivers=[arguments["driver"]],
            from_lap=stints[0]["start_lap"] if asked else None,
            to_lap=stints[0]["end_lap"] if asked else None,
        )
    if result.tool == "pit_stop_loss":
        return FactChart(kind="positions", drivers=[arguments["driver"]])
    return None
