"""The free question of the home page (LAB-206): routed by code (`f1.router`), answered on the path it takes.

    rules   -> the retrieval pipeline: claims, each citing its passages; an abstention when nothing answers
    data    -> the race resolved by code, then the questions of LAB-205 on it: every number checked, or withheld
    debrief -> the agent, started by the API: the analyst goes on to its request
    None    -> the analyst chooses the path; and the race, when the question names none the data knows

What the analyst chooses comes back with the question (`route`, `season`, `round`): nothing is guessed. Every
question and its answer are kept, the latest shown on the home page.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal, Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field

from core.agent.chat import Chat, Reply
from core.agent.state import AgentState, Clarification
from core.agent.store import PostgresSettings
from core.retrieval.pipeline import Answer
from f1.display import Response
from f1.grand_prix import GrandPrix, RaceSummary
from f1.router import Route, Router, Routing

Status = Literal["answered", "abstained", "withheld", "refused", "stopped", "asked", "debrief"]

ROUTES_FR: dict[Route, str] = {
    "rules": "Le règlement",
    "data": "Les données d'une course",
    "debrief": "Un débrief de course",
}


PICK_RACE = (
    "Sur quelle course ? Les chiffres se calculent course par course, et la question n'en nomme aucune que les "
    "données connaissent sans ambiguïté."
)


class RaceLink(Response):
    season: int
    round: int
    grand_prix: str = Field(description="In French")


class Choice(Response):
    """An answer the analyst may pick: it comes back with the question."""

    label: str
    route: Route
    season: int | None = None
    round: int | None = None


class Cited(Response):
    """What a point of the answer cites: a passage of the FIA documents, or an analysis of the race."""

    id: str
    label: str
    text: str | None = None
    url: str | None = None


class AnswerPoint(Response):
    text: str
    sources: list[str] = Field(default_factory=list, description="Ids of `FreeAnswer.sources` it cites")
    facts: list[str] = Field(default_factory=list, description="Ids of `FreeAnswer.facts` its numbers come from")


class FreeAnswer(Response):
    """A free question and what came of it: an answer, an abstention, a choice to make, or a debrief started."""

    id: int = 0
    question: str
    route: Route | None = Field(None, description="The path taken; None while the analyst chooses it")
    status: Status
    reason: str | None = Field(None, description="Why the path, the abstention, or what is asked")
    points: list[AnswerPoint] = Field(default_factory=list)
    sources: list[Cited] = Field(default_factory=list, description="The FIA passages the points cite")
    facts: list[Cited] = Field(default_factory=list, description="The analyses of the race the points cite")
    notes: list[str] = Field(default_factory=list, description="What was assumed, e.g. the season of the rules")
    choices: list[Choice] = Field(default_factory=list, description="What the analyst may choose, when asked")
    race: RaceLink | None = Field(None, description="The race the question is about, for a link to its page")
    debrief: str | None = Field(None, description="The request started, for a debrief")
    asked_at: datetime | None = None


class Rules(Protocol):
    """What the rules path needs of the retrieval pipeline (`f1.rag.rag_pipeline`)."""

    def answer(self, question: str) -> Answer: ...


class FreeQuestions:
    def __init__(
        self,
        router: Router,
        grand_prix: GrandPrix,
        *,
        rules: Callable[[], Rules],
        chat: Callable[[], Chat],
    ) -> None:
        self.router = router
        self.grand_prix = grand_prix
        self._rules, self._chat = rules, chat  # built on first use: the rules alone need no lake, and so on

    def ask(
        self, question: str, *, route: Route | None = None, season: int | None = None, round_number: int | None = None
    ) -> FreeAnswer:
        """The answer, or what the analyst must choose. A debrief is only routed here: the API starts it."""
        routing = self.router.route(question)
        path = route or routing.route
        if path is None:
            choices = [Choice(label=ROUTES_FR[option], route=option) for option in ("rules", "data", "debrief")]
            return FreeAnswer(
                question=question, status="asked", reason=f"Comment y répondre ? {routing.reason.capitalize()}.",
                choices=choices,
            )  # fmt: skip
        if path == "debrief":
            return FreeAnswer(question=question, route="debrief", status="debrief", reason=routing.reason)
        if path == "rules":  # a link to the race whose stewards' decision it may be about, when it names one
            named = routing.grands_prix and len(routing.seasons) == 1
            link = self._resolve(routing) if named else None
            return self._rules_answer(question, link if isinstance(link, RaceLink) else None)
        race = self._race(season, round_number) if season and round_number else self._resolve(routing)
        if not isinstance(race, RaceLink):
            return FreeAnswer(question=question, route="data", status="asked", reason=PICK_RACE, choices=race)
        return self._data_answer(question, race, routing)

    def _rules_answer(self, question: str, race: RaceLink | None) -> FreeAnswer:
        from f1.rag.ask import ABSTENTIONS

        answer = self.rules(question)
        found = FreeAnswer(
            question=question, route="rules", status="answered", notes=list(answer.scope.notes), race=race
        )
        if answer.abstention:
            return found.model_copy(update={"status": "abstained", "reason": ABSTENTIONS[answer.abstention]})
        return found.model_copy(
            update={
                "points": [AnswerPoint(text=claim.text, sources=list(claim.sources)) for claim in answer.claims],
                "sources": _rule_sources(answer),
            }
        )

    def _data_answer(self, question: str, race: RaceLink, routing: Routing) -> FreeAnswer:
        reply = self.data(question, race, routing)
        if isinstance(reply, str):  # the race has no entry list in the lake
            return FreeAnswer(question=question, route="data", status="refused", reason=reply, race=race)
        return _data(question, race, reply)

    # The two paths' steps, also run by the evaluation (`f1.evals.agent`), which reads what they found.

    def rules(self, question: str) -> Answer:
        return self._rules().answer(question)

    def data(self, question: str, race: RaceLink, routing: Routing) -> Reply | str:
        """The reply of the questions of LAB-205 on the race; why not, when the race cannot be followed."""
        from f1.agent.theme import F1Theme

        chat = self._chat()
        theme = chat.theme
        assert isinstance(theme, F1Theme)
        subject = theme.free_subject(question, race.season, race.round, routing.named)
        if isinstance(subject, Clarification):
            return subject.question
        return chat.ask(question, state=AgentState(request=question, subject=subject))

    def resolve(self, routing: Routing) -> RaceLink | list[Choice]:
        return self._resolve(routing)

    def _race(self, season: int, round_number: int) -> RaceLink | list[Choice]:
        races = {race.round: race for race in self.grand_prix.calendar(season)}
        if (race := races.get(round_number)) is None:
            return self._resolve(Routing(None, [season]))
        return RaceLink(season=season, round=round_number, grand_prix=race.grand_prix)

    def _resolve(self, routing: Routing) -> RaceLink | list[Choice]:
        """The race the question names, when the data knows exactly one; else the races to choose from."""
        # No season named: the last editions of the Grand Prix it names, or the races of the latest season.
        seasons = routing.seasons or self.grand_prix.seasons()[: 4 if routing.grands_prix else 1]
        raced = [race for season in seasons for race in self.grand_prix.calendar(season) if race.winner]
        named = [race for race in raced if race.event in routing.grands_prix]
        if len(named) == 1 and len(routing.seasons) == 1:
            return RaceLink(season=named[0].season, round=named[0].round, grand_prix=named[0].grand_prix)
        among = named or [race for race in raced if race.season == max(seasons, default=0)] or raced
        return [_race_choice(race) for race in sorted(among, key=lambda r: (r.season, r.round), reverse=True)[:6]]


def _race_choice(race: RaceSummary) -> Choice:
    return Choice(label=f"{race.grand_prix} {race.season}", route="data", season=race.season, round=race.round)


def _rule_sources(answer: Answer) -> list[Cited]:
    return [
        Cited(id=source.id, label=source.label, text=source.text, url=source.passages[0].payload.get("url"))
        for source in answer.sources
    ]


def _data(question: str, race: RaceLink, reply: Reply) -> FreeAnswer:
    passages = {source.id: source for rule in reply.rules for source in rule.sources}
    results = {result.id: result for result in reply.results}
    cited = dict.fromkeys(id_ for point in reply.points for id_ in point.facts)
    quoted = dict.fromkeys(id_ for point in reply.points for id_ in point.sources)
    return FreeAnswer(
        question=question,
        route="data",
        status=reply.status,
        reason=reply.reason,
        points=[AnswerPoint(text=p.text, facts=list(p.facts), sources=list(p.sources)) for p in reply.points],
        facts=[Cited(id=id_, label=r.label) for id_ in cited if (r := results.get(id_))],
        sources=[Cited(id=id_, label=p.label, text=p.text) for id_ in quoted if (p := passages.get(id_))],
        race=race,
    )


_TABLE = """CREATE TABLE IF NOT EXISTS free_questions (
    id bigserial PRIMARY KEY,
    question text NOT NULL,
    route text,
    status text NOT NULL,
    answer jsonb NOT NULL,
    asked_at timestamptz NOT NULL DEFAULT now()
)"""


class FreeQuestionStore:
    """The free questions asked, and what came of each."""

    def __init__(self, settings: PostgresSettings | None = None) -> None:
        self._dsn = (settings or PostgresSettings()).dsn()
        with psycopg.connect(self._dsn, autocommit=True) as connection:
            connection.execute(_TABLE)

    def save(self, answer: FreeAnswer) -> FreeAnswer:
        with psycopg.connect(self._dsn, autocommit=True, row_factory=dict_row) as connection:
            row = connection.execute(
                "INSERT INTO free_questions (question, route, status, answer) VALUES (%s, %s, %s, %s) RETURNING *",
                (answer.question, answer.route, answer.status, Jsonb(answer.model_dump(mode="json"))),
            ).fetchone()
        assert row is not None
        return _answer(row)

    def get(self, question_id: int) -> FreeAnswer | None:
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            row = connection.execute("SELECT * FROM free_questions WHERE id = %s", (question_id,)).fetchone()
        return _answer(row) if row else None

    def latest(self, limit: int = 10) -> list[FreeAnswer]:
        """The latest questions first. One that waited for the analyst's choice is left out: the question asked
        again with that choice is kept."""
        with psycopg.connect(self._dsn, row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT * FROM free_questions WHERE status <> 'asked' ORDER BY asked_at DESC, id DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [_answer(row) for row in rows]


def _answer(row: dict[str, Any]) -> FreeAnswer:
    return FreeAnswer.model_validate({**row["answer"], "id": row["id"], "asked_at": row["asked_at"]})
