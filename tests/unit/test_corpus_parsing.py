"""Parsing of the FIA documents, on page texts shaped like pypdf's output of the real PDFs."""

import pytest

from f1.corpus import regulations
from f1.corpus.decisions import cited_articles, parse_decision
from f1.corpus.regulations import parse_regulations


def page_2025(number: int, body: str) -> str:
    return (
        f"2025 Formula 1 Sporting Regulations {number}/9 30 April 2025\n"
        "©2025 Fédération Internationale de l’Automobile  Issue 5\n" + body
    )


PAGES_2025 = [
    page_2025(1, "ART CONTENTS PAGE\n1 REGULATIONS 2\n55 SAFETY CAR 3\n57 SUSPENDING A RACE 4"),
    page_2025(2, "1) REGULATIONS\n1.1 The FIA will organise the Championship.\n1.2 The final text is in English."),
    page_2025(
        3,
        "55) SAFETY CAR\n55.1 The FIA safety car will be driven by an FIA appointed driver.\n"
        "55.2 The safety car will be brought into operation to neutralise a race.\n"
        "This is the second line of 55.2, which mentions Article\n55.1 which is not a new paragraph.",
    ),
    page_2025(
        4, "57) SUSPENDING A RACE\n57.1 Should it become necessary to suspend the race, red flags will be shown."
    ),
    page_2025(
        5,
        "57.2 Whilst the race is suspended, tyres may be changed.\n"
        "60) POST RACE PARC FERMÉ\n60.1 Cars go to parc fermé.",
    ),
    page_2025(6, "APPENDIX 1\nINFORMATION REQUIRED BY THE FIA\nEntry form fields."),
]


def page_2026(number: int, body: str) -> str:
    return (
        f"SECTION B: SPORTING REGULATIONS\n0\nB\nB{number}\n2026 Formula 1 Regulations - Section B [Sporting]\n"
        "©2026 Fédération Internationale de l’Automobile\n01 October 2026\nIssue 09\n" + body
    )


PAGES_2026 = [
    page_2026(1, "CONTENTS:\nARTICLE B5: TOTAL TIME CLASSIFIED SESSIONS (TTCS) 35\nB5.12 Virtual Safety Car (VSC) 44"),
    page_2026(2, "ARTICLE B5: TOTAL TIME CLASSIFIED SESSIONS (TTCS)\nB5.12 Virtual Safety Car (VSC)\n"),
    page_2026(3, "B5.12.1 Deployment of VSC\nThe VSC procedure may be initiated by the Race Director.\n"),
    page_2026(4, "B5.12.2 Ending of VSC\nWhen the Race Director decides to end the VSC, a message is sent.\n"),
    page_2026(
        5, "B5.13 Safety Car (SC)\nB5.13.1 Deployment of Safety Car\nThe Safety Car may be brought into operation."
    ),
]


def test_2025_layout() -> None:
    document = parse_regulations(PAGES_2025, season=2025, issue=5, published="2025-04-30", url="https://x/reg.pdf")
    assert document.doc_id == "sporting-regulations-2025"
    assert [parent.key for parent in document.parents] == ["1", "55", "57", "60"]  # no contents, no appendix
    assert [chunk.key for chunk in document.chunks] == ["1.1", "1.2", "55.1", "55.2", "57.1", "57.2", "60.1"]
    chunk = next(chunk for chunk in document.chunks if chunk.key == "55.2")
    assert chunk.text.startswith("2025 Formula 1 Sporting Regulations, Article 55.2, Safety car:\n55.2 The safety car")
    assert "55.1 which is not a new paragraph" in chunk.text
    assert chunk.parent_key == "55"
    assert chunk.metadata == {"article": "55.2", "parent_article": "55", "title": "Safety car", "page": 3}
    assert "Fédération" not in "".join(chunk.text for chunk in document.chunks)  # running headers dropped
    suspension = next(parent for parent in document.parents if parent.key == "57")
    assert "57.2 Whilst the race is suspended" in suspension.text  # a parent spans pages
    assert document.metadata["issue"] == 5


def test_2026_layout() -> None:
    document = parse_regulations(PAGES_2026, season=2026, issue=9, published="2026-10-01", url="https://x/b.pdf")
    assert [parent.key for parent in document.parents] == ["B5.12", "B5.13"]
    assert [chunk.key for chunk in document.chunks] == ["B5.12.1", "B5.12.2", "B5.13.1"]
    vsc = document.parents[0]
    assert vsc.metadata["title"] == "Virtual Safety Car (VSC)"
    assert vsc.metadata["article_title"] == "Total time classified sessions (ttcs)"
    assert document.chunks[0].text.startswith("2026 Formula 1 Sporting Regulations, Article B5.12.1, Virtual Safety")


def test_long_paragraphs_are_split_at_items_and_parents_stay_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(regulations, "MAX_CHUNK_CHARS", 120)
    monkeypatch.setattr(regulations, "MAX_PARENT_CHARS", 300)
    items = "\n".join(f"{letter}) A rule about tyres that takes some room on the page." for letter in "abcdef")
    pages = [page_2025(i, "") for i in range(1, 4)]
    pages[1] = page_2025(2, f"30) TYRES\n30.1 Tyres must be used as follows:\n{items}\n30.2 Short rule.")
    document = parse_regulations(pages, season=2025, issue=1, published="2025-01-01", url="u")
    keys = [chunk.key for chunk in document.chunks]
    assert keys[0] == "30.1#1" and keys[-1] == "30.2"
    assert all(len(chunk.text.split(":\n", 1)[1]) <= 120 for chunk in document.chunks)
    assert len(document.parents) > 1 and all(len(parent.text) <= 400 for parent in document.parents)
    assert {chunk.parent_key for chunk in document.chunks} == {parent.key for parent in document.parents}


def test_an_unknown_layout_fails_loudly() -> None:
    with pytest.raises(ValueError, match="No article found"):
        parse_regulations(["Some other document\nwith no article"], season=2025, issue=1, published="", url="")


DECISION = """2025 ITALIAN GRAND PRIX
05 - 07 September 2025
The Stewards
Document 44
Date 07 September 2025
Time 17:27
The Stewards, having received a report, have considered the following
matter and determine the following:
No / Driver 14 - Fernando Alonso
Competitor Aston Martin Aramco F1 Team
Time 14:25
Session Race
Fact Car 14 crossed back into the Pit Exit Road
during the reconnaissance laps
Infringement Breach of Article 12.2.1 i) of the FIA International Sporting Code
Decision Driver: Warning.
Reason The Stewards reviewed video evidence.
As no dangerous situation was caused, a Warning is sufficient.
Competitors are reminded that they have the right to appeal certain decisions.
Felix Holter Mathieu Remmerie"""


def test_decision() -> None:
    document = parse_decision(
        [DECISION],
        season=2025,
        grand_prix="Italian Grand Prix",
        round_number=16,
        url="https://x/d.pdf",
        file_name="2025_italian_grand_prix_-_infringement_-_car_14_-_failing_to_follow_instructions.pdf",
    )
    assert [chunk.key for chunk in document.chunks] == ["summary", "reason#1"]
    summary = document.chunks[0].text
    assert summary.startswith("Stewards' decision, 2025 Italian Grand Prix, Race: Car 14 (Fernando Alonso, Aston")
    assert "Fact: Car 14 crossed back into the Pit Exit Road during the reconnaissance laps" in summary
    assert "Decision: Driver: Warning." in summary
    assert "right to appeal" not in document.parents[0].text and "Holter" not in document.parents[0].text
    assert {key: document.metadata[key] for key in ("round", "document_number", "published", "car_number")} == {
        "round": 16,
        "document_number": "44",
        "published": "2025-09-07",
        "car_number": 14,
    }
    assert document.metadata["penalty"] == "Driver: Warning."
    assert document.metadata["cited_articles"] == ["12.2.1 i) (International Sporting Code)"]
    assert document.metadata["document_title"] == "Infringement - Car 14 - Failing to follow instructions"


def test_a_decision_in_another_form_is_kept_as_text() -> None:
    text = "2025 ABU DHABI GRAND PRIX\nThe Stewards determine the following:\nQualifying SC2-SC1 times are confirmed."
    document = parse_decision(
        [text],
        season=2025,
        grand_prix="Abu Dhabi Grand Prix",
        round_number=24,
        url="u",
        file_name="a_-_decision_-_b.pdf",
    )
    assert [chunk.key for chunk in document.chunks] == ["reason#1"]
    assert "SC2-SC1 times are confirmed" in document.chunks[0].text


def test_cited_articles() -> None:
    text = "Breach of Article 33.4 of the FIA Formula 1 Sporting Regulations and Article B1.8.4"
    assert cited_articles(text) == ["33.4 (Sporting Regulations)", "B1.8.4"]
