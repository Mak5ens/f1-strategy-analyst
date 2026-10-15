"""Penalties of a race, read from race control's messages: who, what, why, and the lap it was announced.

The stewards' messages are the source ("FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 16 (LEC) - CAUSING A
COLLISION"); since 2025, race control also announces when a penalty is served. A penalty's seconds in a debrief
come from here, never from a model.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from f1.tools.data import RaceData, SessionRef, integer

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


class PenaltiesInput(SessionRef):
    pass


class GivenPenalty(BaseModel):
    driver: str
    kind: Literal["time", "drive_through", "stop_go"]
    seconds: int | None = Field(description="Seconds added (time penalty) or held in the box (stop and go)")
    reason: str
    reason_fr: str
    lap: int = Field(description="Lap race control announced it")
    served_lap: int | None = Field(description="Lap race control said it was served (since 2025), if it did")


class PenaltiesOutput(BaseModel):
    season: int
    round: int
    session: str
    penalties: list[GivenPenalty]


def race_penalties(data: RaceData, request: PenaltiesInput) -> PenaltiesOutput:
    given, served = penalties(data.race_control_messages(request))
    rows = []
    for penalty in given:
        later = [lap for driver, lap in served if driver == penalty.driver and lap >= penalty.lap]
        rows.append(
            GivenPenalty(
                driver=penalty.driver,
                kind=penalty.kind,
                seconds=penalty.seconds,
                reason=penalty.reason,
                reason_fr=reason_fr(penalty.reason),
                lap=penalty.lap,
                served_lap=min(later) if later else None,
            )
        )
    return PenaltiesOutput(season=request.season, round=request.round, session=request.session, penalties=rows)
