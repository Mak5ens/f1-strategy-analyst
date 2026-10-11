"""Connection to Qdrant, from QDRANT_URL (and QDRANT_API_KEY on a secured instance)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from qdrant_client import QdrantClient


class QdrantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QDRANT_", env_file=".env", extra="ignore")

    url: str = "http://localhost:6333"
    api_key: SecretStr | None = None
    timeout_seconds: int = 60


def qdrant_client(settings: QdrantSettings | None = None) -> QdrantClient:
    settings = settings or QdrantSettings()
    api_key = settings.api_key.get_secret_value() if settings.api_key else None
    return QdrantClient(url=settings.url, api_key=api_key, timeout=settings.timeout_seconds)
