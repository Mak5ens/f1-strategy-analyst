"""The classification of a session: who won, from where, how far behind; the pole and the qualifying times; the
fastest lap. The other tools compute; this one reads what the official results say."""

from typing import Literal

from pydantic import BaseModel, Field

from core.tools import ToolError
from f1.tools.data import RaceData, integer, number


class ResultInput(BaseModel):
    season: int = Field(ge=2018, le=2100, description="Championship year, e.g. 2025")
    round: int = Field(ge=1, le=30, description="Round number in the season's calendar (find_race gives it)")
    session: Literal["R", "S", "Q", "SQ"] = Field(
        "R", description="R race, S sprint, Q qualifying, SQ sprint qualifying"
    )


class Classified(BaseModel):
    position: str = Field(description="A number, or R retired, D disqualified, W withdrawn, N not classified")
    driver: str = Field(description="Three-letter code")
    name: str
    team: str | None
    grid: int | None = Field(description="Starting position in a race or sprint; 0 for a pit lane start")
    status: str | None
    gap_to_winner_s: float | None = Field(description="Finishers on the lead lap only")
    race_time_s: float | None = Field(description="The winner only")
    laps: int | None
    q1_s: float | None = None
    q2_s: float | None = None
    q3_s: float | None = None


class FastestLap(BaseModel):
    driver: str
    name: str
    lap: int
    lap_time_s: float


class ResultOutput(BaseModel):
    season: int
    round: int
    session: str
    classification: list[Classified]
    fastest_lap: FastestLap | None = Field(description="Fastest lap not deleted by the stewards")


def session_result(data: RaceData, request: ResultInput) -> ResultOutput:
    rows = data.results(request.season, request.round, request.session)
    if not rows:
        raise ToolError(
            f"No results for {request.season} round {request.round} session {request.session}: "
            "not ingested, or no such session (find_race lists the sessions)."
        )
    names = {str(row["driver"]): str(row["full_name"] or row["driver"]) for row in rows}
    race = request.session in ("R", "S")
    classification = [
        Classified(
            position=str(row["classified_position"] or integer(row["position"]) or ""),
            driver=str(row["driver"]),
            name=names[str(row["driver"])],
            team=row["team"],
            grid=integer(row["grid_position"]) if race else None,
            status=row["status"] or None,
            gap_to_winner_s=number(row["gap_to_winner_s"]),
            race_time_s=number(row["race_time_s"]),
            laps=integer(row["laps"]),
            q1_s=None if race else number(row["q1_s"]),
            q2_s=None if race else number(row["q2_s"]),
            q3_s=None if race else number(row["q3_s"]),
        )
        for row in rows
    ]
    fastest = data.fastest_lap(request.season, request.round, request.session)
    return ResultOutput(
        season=request.season,
        round=request.round,
        session=request.session,
        classification=classification,
        fastest_lap=FastestLap(
            driver=str(fastest["driver"]),
            name=names.get(str(fastest["driver"]), str(fastest["driver"])),
            lap=int(fastest["lap_number"]),
            lap_time_s=round(float(fastest["lap_time_s"]), 3),
        )
        if fastest
        else None,
    )
