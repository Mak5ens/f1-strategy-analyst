"""The FIA website client against a fake site: which documents it picks, and that it asks for each one once."""

import json
from pathlib import Path

import httpx
import pytest

from core.http import RateLimitedClient
from f1.corpus.fia import FiaWebsite

REGULATIONS_HTML = """
<a href="https://www.fia.com/sites/default/files/fia_2024_formula_1_sporting_regulations_-_issue_6_-_2024-04-30_v1.pdf">
<a href="https://www.fia.com/sites/default/files/fia_2024_formula_1_sporting_regulations_-_issue_6_-_2024-04-30_v2.pdf">
<a href="https://www.fia.com/sites/default/files/fia_2024_formula_1_sporting_regulations_-_issue_7_-_2024-07-31.pdf">
<a href="https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_09_-_2026-10-01.pdf">
<a href="https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_10_-_2026-12-01_0.pdf">
<a href="https://www.fia.com/sites/default/files/fia_2026_formula_1_sporting_regulations_pu_-_issue_7_-_2024-10-17.pdf">
<a href="https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_c_technical_-_iss_20_-_2026-08-05.pdf">
"""
CHAMPIONSHIP_HTML = '<a href="/documents/championships/fia-formula-one-world-championship-14/season/season-2025-2071">'
SEASON_HTML = """
<a href="/decision-document-list/nojs/56445" class="event-title data-id-56445  use-ajax">Italian Grand Prix</a>
<a href="/decision-document-list/nojs/55323" class="event-title use-ajax">Bahrain Tests Season 2025</a>
"""
MONZA_DOCUMENTS = [
    "/system/files/decision-document/2025_italian_grand_prix_-_infringement_-_car_14_-_failing_to_follow.pdf",
    "/system/files/decision-document/2025_italian_grand_prix_-_decision_-_car_5_overtook_car_30.pdf",
    "/system/files/decision-document/2025_italian_grand_prix_-_infringement_-_race_deleted_lap_times.pdf",
    "/system/files/decision-document/2025_italian_grand_prix_-_final_race_classification.pdf",
    "/system/files/decision-document/2025_italian_grand_prix_-_summons_-_car_14.pdf",
    # 2024 documents: another folder, spaces and capitals
    "/sites/default/files/decision-document/2024 Monaco Grand Prix - Infringement - Car 31 - Causing a collision.pdf",
    "/sites/default/files/decision-document/2024 Monaco Grand Prix - Race Deleted Lap Times.pdf",
]


@pytest.fixture
def site(tmp_path: Path) -> tuple[FiaWebsite, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        path = request.url.path
        if path == "/regulation/category/110":
            return httpx.Response(200, text=REGULATIONS_HTML)
        if path.endswith("fia-formula-one-world-championship-14"):
            return httpx.Response(200, text=CHAMPIONSHIP_HTML)
        if path.endswith("season-2025-2071"):
            return httpx.Response(200, text=SEASON_HTML)
        if path == "/decision-document-list/ajax/56445":
            assert request.method == "POST" and request.headers["X-Requested-With"] == "XMLHttpRequest"
            html = "".join(f'<a href="{document}" download>' for document in MONZA_DOCUMENTS)
            return httpx.Response(200, json=[{"command": "settings"}, {"command": "insert", "data": html}])
        if path.endswith(".pdf"):
            return httpx.Response(200, content=b"%PDF-1.4 fake")
        return httpx.Response(404)

    client = RateLimitedClient("https://www.fia.com", min_interval=0, transport=httpx.MockTransport(handler))
    return FiaWebsite(tmp_path / "fia", client=client), calls


def test_latest_regulations_pick_the_last_issue_of_the_season(site: tuple[FiaWebsite, list[str]]) -> None:
    website, _ = site
    issue_2024 = website.latest_regulations(2024)
    assert (issue_2024.issue, issue_2024.published) == (7, "2024-07-31")
    issue_2026 = website.latest_regulations(2026)  # sporting section only, not the old power unit drafts
    assert (issue_2026.issue, issue_2026.url.endswith("iss_10_-_2026-12-01_0.pdf")) == (10, True)
    with pytest.raises(LookupError):
        website.latest_regulations(2019)


def test_decisions_are_only_stewards_decisions_of_grands_prix(site: tuple[FiaWebsite, list[str]]) -> None:
    website, calls = site
    decisions = website.decisions(2025)
    assert [decision.file_name for decision in decisions] == [
        "2024 Monaco Grand Prix - Infringement - Car 31 - Causing a collision.pdf",
        "2025_italian_grand_prix_-_decision_-_car_5_overtook_car_30.pdf",
        "2025_italian_grand_prix_-_infringement_-_car_14_-_failing_to_follow.pdf",
    ]
    assert {decision.event for decision in decisions} == {"Italian Grand Prix"}
    assert "POST /decision-document-list/ajax/55323" not in calls  # tests skipped


def test_lists_and_documents_are_fetched_once(site: tuple[FiaWebsite, list[str]], tmp_path: Path) -> None:
    website, calls = site
    first = website.decisions(2025)
    path = website.download(first[0].url)
    website.download(first[0].url)
    website.decisions(2025)
    assert path.read_bytes() == b"%PDF-1.4 fake"
    assert calls.count("POST /decision-document-list/ajax/56445") == 1
    assert sum(call.endswith(".pdf") for call in calls) == 1
    assert json.loads((tmp_path / "fia" / "events" / "2025-56445.json").read_text())
    website.decisions(2025, refresh=True)
    assert calls.count("POST /decision-document-list/ajax/56445") == 2
