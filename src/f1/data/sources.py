"""Clients of the three public sources. Network only: the shaping into tables is in `transform.py`.

- FastF1: schedule, laps, results, race control messages and weather, from the official live timing archive.
  It keeps an HTTP cache on disk and enforces its own rate limits (it raises RateLimitExceededError beyond them).
- OpenF1: pit stops, for the stationary time that FastF1 lacks.
- Jolpica-F1 (the successor of the Ergast API): championship standings after each round.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

import fastf1
import pandas as pd
from fastf1.exceptions import RateLimitExceededError

from core.http import RateLimitedClient

__all__ = [
    "RACE_SESSIONS",
    "SESSION_CODES",
    "EventInfo",
    "FastF1Source",
    "JolpicaClient",
    "OpenF1Client",
    "RateLimitExceededError",
    "SessionData",
]

# FastF1 session name -> code used in the lake: every session of a weekend. A conventional weekend has three
# practices, qualifying and the race; a sprint weekend one practice, sprint qualifying, the sprint, qualifying and
# the race.
SESSION_CODES = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Sprint Qualifying": "SQ",
    "Qualifying": "Q",
    "Sprint": "S",
    "Race": "R",
}
# Sessions that race: pit stops mean something there, and a session without laps is an error.
RACE_SESSIONS = frozenset({"S", "R"})


@dataclass(frozen=True)
class EventInfo:
    season: int
    round: int
    event_name: str
    # code -> start time (UTC) of the sessions of SESSION_CODES that this event has
    sessions: dict[str, datetime]


@dataclass(frozen=True)
class SessionData:
    info: dict[str, Any]  # one row of the sessions table
    laps: pd.DataFrame
    results: pd.DataFrame
    race_control_messages: pd.DataFrame
    weather: pd.DataFrame


class FastF1Source:
    def __init__(self, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(cache_dir))

    def schedule(self, season: int) -> list[EventInfo]:
        frame = fastf1.get_event_schedule(season, include_testing=False)
        events = []
        for _, row in frame.iterrows():
            sessions = {}
            for slot in range(1, 6):
                name, start = row.get(f"Session{slot}"), row.get(f"Session{slot}DateUtc")
                if name in SESSION_CODES and pd.notna(start):
                    sessions[SESSION_CODES[name]] = pd.Timestamp(start).tz_localize(UTC).to_pydatetime()
            events.append(EventInfo(season, int(row["RoundNumber"]), str(row["EventName"]), sessions))
        return events

    def session(self, season: int, round_number: int, code: str) -> SessionData:
        name = next(name for name, value in SESSION_CODES.items() if value == code)
        session = fastf1.get_session(season, round_number, name)
        session.load(laps=True, telemetry=False, weather=True, messages=True)
        event, session_info = session.event, session.session_info
        info = {
            "session_name": session.name,
            "event_name": event["EventName"],
            "official_event_name": event["OfficialEventName"],
            "country": event["Country"],
            "location": event["Location"],
            "event_format": event["EventFormat"],
            "start_utc": session.date,
            "total_laps": getattr(session, "total_laps", None),
            "session_key": session_info.get("Key"),
            "meeting_key": session_info.get("Meeting", {}).get("Key"),
        }
        return SessionData(
            info=info,
            laps=pd.DataFrame(session.laps),
            results=pd.DataFrame(session.results),
            race_control_messages=pd.DataFrame(session.race_control_messages),
            weather=pd.DataFrame(session.weather_data),
        )


class _ApiClient:
    def __init__(self, base_url: str, **options: Any) -> None:
        self._http = RateLimitedClient(base_url, min_interval=0.5, **options)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Raw JSON of an endpoint, for checks against the stored data."""
        return self._http.get_json(path, params)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class OpenF1Client(_ApiClient):
    """OpenF1's free tier allows a few calls per second; one call every half second stays well below."""

    def __init__(self, base_url: str = "https://api.openf1.org/v1", **options: Any) -> None:
        super().__init__(base_url, **options)

    def pit_stops(self, session_key: int) -> list[dict[str, Any]]:
        pits = self._http.get_json("/pit", {"session_key": session_key}, missing_ok=True)
        return list(pits or [])


class JolpicaClient(_ApiClient):
    """Jolpica-F1 allows 4 calls per second and 500 per hour; two calls per round stay far below both."""

    def __init__(self, base_url: str = "https://api.jolpi.ca/ergast/f1", **options: Any) -> None:
        super().__init__(base_url, **options)

    def driver_standings(self, season: int, round_number: int) -> list[dict[str, Any]]:
        data = self._http.get_json(f"/{season}/{round_number}/driverstandings/", {"limit": 100})
        return _standings(data, "DriverStandings")

    def constructor_standings(self, season: int, round_number: int) -> list[dict[str, Any]]:
        data = self._http.get_json(f"/{season}/{round_number}/constructorstandings/", {"limit": 100})
        return _standings(data, "ConstructorStandings")


def _standings(data: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    lists = data["MRData"]["StandingsTable"]["StandingsLists"]
    return list(lists[0][kind]) if lists else []
