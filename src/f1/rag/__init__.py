"""Questions on the FIA rules: the production retrieval pipeline of `core`, with the profile of the FIA corpus."""

from core.gateway import gateway_client
from core.retrieval.pipeline import PipelineConfig, RetrievalPipeline
from core.retrieval.rerank import GatewayReranker
from core.tracing import tracer
from f1.corpus import fia_index
from f1.rag.profile import FiaProfile


def rag_pipeline(config: PipelineConfig | None = None) -> RetrievalPipeline:
    """The pipeline over the FIA index, its models behind the gateway, traced to the f1 team's Langfuse project."""
    index = fia_index()
    seasons = [int(season) for season in index.values("season")]
    profile = FiaProfile(seasons, [str(name) for name in index.values("grand_prix")])
    return RetrievalPipeline(
        index, profile, llm=gateway_client(), reranker=GatewayReranker(), tracer=tracer(), config=config
    )
