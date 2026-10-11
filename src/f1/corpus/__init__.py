"""The FIA corpus: sporting regulations and stewards' decisions, indexed in Qdrant for the retrieval pipeline."""

from qdrant_client import models

from core.retrieval.embeddings import Embedder, GatewayEmbedder
from core.retrieval.index import HybridIndex
from core.retrieval.qdrant import qdrant_client

INDEX_NAME = "fia"
PAYLOAD_INDEXES = {
    "season": models.PayloadSchemaType.INTEGER,
    "doc_type": models.PayloadSchemaType.KEYWORD,
    "grand_prix": models.PayloadSchemaType.KEYWORD,
    "round": models.PayloadSchemaType.INTEGER,
    "article": models.PayloadSchemaType.KEYWORD,
}


def fia_index(embedder: Embedder | None = None) -> HybridIndex:
    """The index of the FIA corpus: collections `fia_chunks` and `fia_parents` in Qdrant."""
    return HybridIndex(qdrant_client(), INDEX_NAME, embedder or GatewayEmbedder(), payload_indexes=PAYLOAD_INDEXES)
