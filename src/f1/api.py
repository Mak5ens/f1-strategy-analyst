"""HTTP API of the app. The health endpoint and the service's identity for now; debriefs and human review come with
LAB-152.

The front in `web/` calls it through a client generated from this app's OpenAPI document, committed as
`web/openapi.json` (`just web-gen-client`): `tests/unit/test_api.py` fails while the two differ.

    uv run python -m f1.api > web/openapi.json
"""

import json
from importlib.metadata import version

from fastapi import FastAPI
from pydantic import BaseModel

# The version of the API contract, not the app's: release-please bumps the app's on every release, and the OpenAPI
# document, and the front's generated client, would change with it.
app = FastAPI(title="F1 Strategy Analyst", version="0.1.0")


class Health(BaseModel):
    status: str


class Info(BaseModel):
    name: str
    version: str


@app.get("/healthz")
def healthz() -> Health:
    """Liveness probe: the process answers. It does not check the gateway or the databases."""
    return Health(status="ok")


@app.get("/info")
def info() -> Info:
    """The service and the version of the app it runs."""
    return Info(name="f1-strategy-analyst", version=version("f1-strategy-analyst"))


def openapi_document() -> str:
    """The OpenAPI document as committed in `web/openapi.json`: indented, keys in the app's order, a final newline."""
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    print(openapi_document(), end="")
