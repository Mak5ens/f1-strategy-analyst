"""The rules of a duel (LAB-212) where the data is incomplete: no gap is made up, no order says more than it means."""

from f1.duels import DuelRace, DuelRound, qualifying_gap, summarize


def test_qualifying_takes_the_last_part_both_reached_or_only_the_places_without_times() -> None:
    mine = {"q1_s": 80.0, "q2_s": 79.5, "q3_s": None, "position": 11, "classified_position": None}
    theirs = {"q1_s": 80.4, "q2_s": 79.2, "q3_s": 78.9, "position": 3, "classified_position": None}
    found = qualifying_gap(mine, theirs)
    assert found and (found.part, found.gap_s, found.first_position, found.second_position) == ("Q2", 0.3, 11, 3)

    untimed = qualifying_gap({**mine, "q1_s": None, "q2_s": None}, {**theirs, "q1_s": None, "q2_s": None, "q3_s": None})
    assert untimed and (untimed.part, untimed.gap_s, untimed.first_position) == (None, None, 11)
    assert qualifying_gap(None, theirs) is None


def race(first: int, second: int, first_text: str, second_text: str) -> DuelRound:
    return DuelRound(
        round=1,
        grand_prix="Grand Prix",
        race=DuelRace(first_position=first, second_position=second, first_text=first_text, second_text=second_text,
                      first_points=0, second_points=0),
    )  # fmt: skip


def test_a_race_neither_finished_classified_counts_for_nobody() -> None:
    summary = summarize([race(19, 20, "D", "D"), race(4, 18, "4", "R"), race(17, 3, "R", "3")])
    assert (summary.race_first, summary.race_second) == (1, 1)
