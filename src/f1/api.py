"""HTTP API of the app. Only the health endpoint for now; questions, debriefs and human review come later (LAB-152)."""

from fastapi import FastAPI

app = FastAPI(title="F1 Strategy Analyst", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe: the process answers. It does not check the gateway or the databases."""
    return {"status": "ok"}
