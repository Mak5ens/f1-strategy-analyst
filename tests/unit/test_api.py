from importlib.metadata import version
from pathlib import Path

from fastapi.testclient import TestClient

from f1.api import app, openapi_document

OPENAPI = Path(__file__).parents[2] / "web" / "openapi.json"


def test_healthz() -> None:
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_info_names_the_app_and_its_version() -> None:
    response = TestClient(app).get("/info")

    assert response.json() == {"name": "f1-strategy-analyst", "version": version("f1-strategy-analyst")}


def test_the_front_client_is_generated_from_this_api() -> None:
    # The front's client is generated from web/openapi.json: a schema changed here without `just web-gen-client`
    # would leave the front calling an API that no longer exists.
    assert OPENAPI.read_text() == openapi_document(), "the API changed: run `just web-gen-client` and commit web/"
