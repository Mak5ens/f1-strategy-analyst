"""Safety car, virtual safety car and red flag periods, read from the race control messages.

The messages follow fixed forms (2024 to 2026 checked):
- safety car: "SAFETY CAR DEPLOYED", then "SAFETY CAR IN THIS LAP": racing resumes on the next lap;
- virtual safety car: "VIRTUAL SAFETY CAR DEPLOYED" or "VSC DEPLOYED", then "... ENDING";
- red flag: flag RED, then "STANDING START" or "ROLLING START" when the race resumes, or a safety car deployed
  to lead the restart.
A red flag closes a safety car period still open; the chequered flag closes anything still open.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.tools import ToolError
from f1.tools.data import RaceData, SessionRef, integer

Kind = Literal["safety_car", "virtual_safety_car", "red_flag"]


class NeutralizationsInput(SessionRef):
    pass


class Neutralization(BaseModel):
    kind: Kind
    start_lap: int
    end_lap: int = Field(description="Lap of the message that ended it: racing resumes on the next lap")
    start_utc: datetime
    end_utc: datetime
    duration_s: float
    ended_by_finish: bool = Field(description="Still in force at the chequered flag")


class NeutralizationsOutput(BaseModel):
    season: int
    round: int
    session: str
    periods: list[Neutralization]
    safety_cars: int
    virtual_safety_cars: int
    red_flags: int


def neutralizations(data: RaceData, request: NeutralizationsInput) -> NeutralizationsOutput:
    messages = data.race_control_messages(request)
    if not messages:
        raise ToolError(f"No race control messages for the {request.label()}: not ingested, or no such session.")
    periods = find_periods(messages)
    return NeutralizationsOutput(
        season=request.season,
        round=request.round,
        session=request.session,
        periods=periods,
        safety_cars=sum(period.kind == "safety_car" for period in periods),
        virtual_safety_cars=sum(period.kind == "virtual_safety_car" for period in periods),
        red_flags=sum(period.kind == "red_flag" for period in periods),
    )


def find_periods(messages: list[dict[str, Any]]) -> list[Neutralization]:
    """Periods in the order they started, from messages sorted by time."""
    periods: list[Neutralization] = []
    open_: dict[Kind, dict[str, Any]] = {}

    def close(kind: Kind, message: dict[str, Any], *, finish: bool = False) -> None:
        start = open_.pop(kind)
        periods.append(
            Neutralization(
                kind=kind,
                start_lap=integer(start["lap"]) or 1,
                end_lap=integer(message["lap"]) or 1,
                start_utc=start["time_utc"],
                end_utc=message["time_utc"],
                duration_s=round((message["time_utc"] - start["time_utc"]).total_seconds(), 1),
                ended_by_finish=finish,
            )
        )

    for message in messages:
        text = str(message["message"] or "").upper()
        if message["flag"] == "CHEQUERED":
            for kind in list(open_):
                close(kind, message, finish=True)
            break
        if message["flag"] == "RED" and "red_flag" not in open_:
            for kind in list(open_):
                close(kind, message)
            open_["red_flag"] = message
        elif "red_flag" in open_ and (text in {"STANDING START", "ROLLING START"} or text == "SAFETY CAR DEPLOYED"):
            close("red_flag", message)
        if message["category"] != "SafetyCar":
            continue
        virtual = text.startswith(("VIRTUAL SAFETY CAR", "VSC"))
        car: Kind = "virtual_safety_car" if virtual else "safety_car"
        if message["status"] == "DEPLOYED" and car not in open_:
            open_[car] = message
        elif message["status"] in {"ENDING", "IN THIS LAP"} and car in open_:
            close(car, message)
    else:  # no chequered flag in the data: close what is open at the last message
        for kind in list(open_):
            close(kind, messages[-1], finish=True)

    return sorted(periods, key=lambda period: period.start_utc)
